#!/usr/bin/env python3
"""
Upload video folder to S3 with parallel file uploads.

Reads S3 credentials from a credential directory (never from CLI args).
Uploads files with correct content types. Prints progress per file.

Usage:
    python3 upload_s3.py <folder_path> --key <registry_key> --credential-dir <dir>
"""

import sys
import os
import json
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".vtt": "text/vtt; charset=utf-8",
    ".srt": "text/plain; charset=utf-8",
    ".json": "application/json",
}

# Files to upload (by extension). Skip raw Deepgram JSON and temp files.
UPLOAD_EXTENSIONS = {".html", ".mp4", ".webm", ".vtt", ".srt", ".mov"}


def load_s3_credentials(credential_dir):
    """Load S3 credentials from file or environment."""
    # Check environment first
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("S3_ENDPOINT")
    bucket = os.environ.get("S3_BUCKET")

    if access_key and secret_key and endpoint and bucket:
        return {"endpoint": endpoint, "bucket": bucket, "access_key": access_key, "secret_key": secret_key}

    # Read from credential file
    cred_file = os.path.join(credential_dir, "s3_credentials")
    if not os.path.isfile(cred_file):
        print("Error: S3 credentials not found. Set environment variables or create "
              f"{cred_file}", file=sys.stderr)
        sys.exit(1)

    creds = {}
    with open(cred_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()

    required = ["endpoint", "bucket", "access_key", "secret_key"]
    for key in required:
        if key not in creds:
            print(f"Error: missing '{key}' in {cred_file}", file=sys.stderr)
            sys.exit(1)

    return creds


def discover_files(folder_path):
    """Find files to upload from the folder."""
    files = []
    for name in os.listdir(folder_path):
        path = os.path.join(folder_path, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in UPLOAD_EXTENSIONS:
            continue
        # Skip deepgram raw JSON
        if name.startswith("deepgram_"):
            continue
        content_type = MIME_TYPES.get(ext, "application/octet-stream")
        files.append({"name": name, "path": path, "content_type": content_type})
    return files


def upload_file(file_info, s3_path, creds):
    """Upload a single file to S3. Returns (name, success, message)."""
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = creds["access_key"]
    env["AWS_SECRET_ACCESS_KEY"] = creds["secret_key"]

    cmd = [
        "aws", "--endpoint-url", creds["endpoint"],
        "s3", "cp", file_info["path"],
        f"s3://{creds['bucket']}/{s3_path}/{file_info['name']}",
        "--content-type", file_info["content_type"],
    ]

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return (file_info["name"], True, "uploaded")
        else:
            return (file_info["name"], False, result.stderr.strip())
    except subprocess.TimeoutExpired:
        return (file_info["name"], False, "timeout")
    except Exception as e:
        return (file_info["name"], False, str(e))


def main():
    parser = argparse.ArgumentParser(description="Upload video folder to S3")
    parser.add_argument("folder", help="Path to video folder")
    parser.add_argument("--key", required=True, help="Registry key (used as S3 folder name)")
    parser.add_argument("--credential-dir", required=True, help="Path to credential directory")
    parser.add_argument("--s3-prefix", default="sharing-videos", help="S3 prefix (default: sharing-videos)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel upload workers (default: 4)")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"Error: {args.folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    creds = load_s3_credentials(args.credential_dir)
    files = discover_files(args.folder)

    if not files:
        print("Error: no uploadable files found", file=sys.stderr)
        sys.exit(1)

    s3_path = f"{args.s3_prefix}/{args.key}"
    total = len(files)
    print(f"[PROGRESS] Uploading {total} files to s3://{creds['bucket']}/{s3_path}/", flush=True)

    completed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(upload_file, f, s3_path, creds): f
            for f in files
        }
        for future in as_completed(futures):
            name, success, msg = future.result()
            completed += 1
            if success:
                print(f"[PROGRESS] Uploaded {completed}/{total}: {name}", flush=True)
            else:
                failed += 1
                print(f"[ERROR] Failed {name}: {msg}", flush=True)

    # Build public URL
    # Hetzner format: https://<bucket>.<region>.your-objectstorage.com/<path>
    endpoint = creds["endpoint"].replace("https://", "")
    base_url = f"https://{creds['bucket']}.{endpoint}/{s3_path}/index.html"

    if failed > 0:
        print(f"\n[ERROR] {failed}/{total} files failed to upload", flush=True)
        sys.exit(1)

    print(f"\n[RESULT] All {total} files uploaded successfully", flush=True)
    print(f"[URL] {base_url}", flush=True)


if __name__ == "__main__":
    main()
