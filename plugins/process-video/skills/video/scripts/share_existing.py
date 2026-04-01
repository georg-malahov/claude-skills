#!/usr/bin/env python3
"""
Share an already-processed video folder via S3 or tunnel.

Expects a folder containing at minimum index.html and a video file.
Registers in the share registry and uploads to S3 if requested.

Usage:
    python3 share_existing.py <folder_path> \\
        --share-folder <dir> \\
        --credential-dir <dir> \\
        [--share s3|tunnel|both] \\
        [--passcode <code>]
"""

import sys
import os
import json
import argparse
import subprocess

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run_script(cmd, timeout=600):
    """Run a script, return (success, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode == 0, result.stdout, result.stderr


def copy_to_clipboard(text):
    try:
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Share an already-processed video folder")
    parser.add_argument("folder", help="Path to processed video folder")
    parser.add_argument("--share-folder", required=True, help="Root folder for shared videos")
    parser.add_argument("--credential-dir", default=os.path.expanduser("~/.config/video-skill"))
    parser.add_argument("--share", default="s3", choices=["s3", "tunnel", "both"])
    parser.add_argument("--passcode", default=None)
    args = parser.parse_args()

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Validate folder has required files
    index_path = os.path.join(folder, "index.html")
    if not os.path.isfile(index_path):
        print(f"Error: no index.html in {folder}. Process the video first.", file=sys.stderr)
        sys.exit(1)

    # Find video file
    video_file = None
    for name in os.listdir(folder):
        ext = os.path.splitext(name)[1].lower()
        if ext in (".mp4", ".webm", ".mkv", ".mov"):
            video_file = name
            break
    if not video_file:
        print(f"Error: no video file found in {folder}", file=sys.stderr)
        sys.exit(1)

    folder_name = os.path.basename(folder)

    # Try to read title from metadata.json or share_metadata.json
    title = folder_name
    for meta_name in ("metadata.json", "share_metadata.json"):
        meta_path = os.path.join(folder, meta_name)
        if os.path.isfile(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            title = meta.get("title", folder_name)
            break

    # Register
    reg_cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "manage_registry.py"),
        "add",
        "--share-folder", args.share_folder,
        "--folder", folder_name,
        "--title", title,
        "--method", args.share,
    ]
    if args.passcode:
        reg_cmd += ["--passcode", args.passcode]

    ok, stdout, stderr = run_script(reg_cmd)
    if not ok:
        print(f"Error registering: {stderr}", file=sys.stderr)
        sys.exit(1)

    reg_result = json.loads(stdout.strip())
    key = reg_result["key"]
    is_existing = reg_result.get("existing", False)
    print(f"[PROGRESS] {'Already registered' if is_existing else 'Registered'} with key: {key}", flush=True)

    # Upload to S3 if requested
    s3_url = None
    if args.share in ("s3", "both"):
        upload_cmd = [
            sys.executable, os.path.join(SCRIPTS_DIR, "upload_s3.py"),
            folder,
            "--key", key,
            "--credential-dir", args.credential_dir,
        ]
        ok, stdout, stderr = run_script(upload_cmd, timeout=600)
        if stdout.strip():
            print(stdout.strip(), flush=True)
        if not ok:
            print(f"[ERROR] S3 upload failed: {stderr[:500]}", flush=True)
            sys.exit(1)

        # Extract URL
        for line in stdout.split("\n"):
            if line.startswith("[URL]"):
                s3_url = line.split(" ", 1)[1].strip()

        # Update registry with S3 URL
        if s3_url:
            update_cmd = [
                sys.executable, os.path.join(SCRIPTS_DIR, "manage_registry.py"),
                "add",
                "--share-folder", args.share_folder,
                "--folder", folder_name,
                "--title", title,
                "--method", args.share,
                "--s3-url", s3_url,
            ]
            run_script(update_cmd)

    # Final output
    share_url = s3_url or f"(start tunnel with /video start to get URL)"
    clipboard_text = f"{title}\n{share_url}"
    if args.passcode:
        clipboard_text += f"\nPasscode: {args.passcode}"

    copy_to_clipboard(clipboard_text)

    print(f"\n{'='*60}", flush=True)
    print(f"[DONE] Video shared!", flush=True)
    print(f"  Title: {title}", flush=True)
    print(f"  Key: {key}", flush=True)
    print(f"  URL: {share_url}", flush=True)
    if args.passcode:
        print(f"  Passcode: {args.passcode}", flush=True)
    print(f"  Copied to clipboard.", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
