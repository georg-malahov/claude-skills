#!/usr/bin/env python3
"""Shared S3 helpers for the video skill — credential loading + cp/rm/url.

Credentials are read from the credential dir's `s3_credentials` file (or env
vars), never from CLI args.
"""
import os
import subprocess
import sys


def load_s3_credentials(credential_dir):
    """Load S3 credentials from env vars first, then `<dir>/s3_credentials`.
    Returns dict with endpoint, bucket, access_key, secret_key. Exits on error."""
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("S3_ENDPOINT")
    bucket = os.environ.get("S3_BUCKET")
    if access_key and secret_key and endpoint and bucket:
        return {"endpoint": endpoint, "bucket": bucket,
                "access_key": access_key, "secret_key": secret_key}

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

    for key in ("endpoint", "bucket", "access_key", "secret_key"):
        if key not in creds:
            print(f"Error: missing '{key}' in {cred_file}", file=sys.stderr)
            sys.exit(1)
    return creds


def aws_env(creds):
    """Return an environment dict with the AWS keys injected (no CLI exposure)."""
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = creds["access_key"]
    env["AWS_SECRET_ACCESS_KEY"] = creds["secret_key"]
    return env


def public_url(creds, path):
    """Build the public object URL for a bucket-relative path."""
    endpoint = creds["endpoint"].replace("https://", "")
    return f"https://{creds['bucket']}.{endpoint}/{path}"


def cp(creds, src, key, content_type="application/octet-stream", timeout=600):
    """Upload a local file to s3://<bucket>/<key>. Returns the public URL.
    Raises subprocess.CalledProcessError on failure."""
    cmd = ["aws", "--endpoint-url", creds["endpoint"], "s3", "cp", src,
           f"s3://{creds['bucket']}/{key}", "--content-type", content_type]
    subprocess.run(cmd, env=aws_env(creds), check=True,
                   capture_output=True, text=True, timeout=timeout)
    return public_url(creds, key)


def rm(creds, key):
    """Delete s3://<bucket>/<key> (best-effort)."""
    subprocess.run(["aws", "--endpoint-url", creds["endpoint"], "s3", "rm",
                    f"s3://{creds['bucket']}/{key}"], env=aws_env(creds),
                   capture_output=True, text=True)
