#!/usr/bin/env python3
"""Re-render + re-upload an already-shared video folder in one step.

Wraps the recurring partial-update dance (edit metadata/subtitles → render_page →
upload_s3) and looks the S3 key up from the share registry by folder name, so you
don't have to find it yourself. Forwards the registered passcode to render_page.py
so a protected page is never silently re-rendered unprotected.

Usage:
    python3 partial_update.py <output_folder> [--share-folder <dir>] [--key <key>] \
        [--credential-dir ~/.config/video-skill]

If --share-folder is omitted it defaults to the parent of <output_folder>.
If --key is omitted it is resolved from <share_folder>/.share_registry.json by
matching the entry whose "folder" equals the output folder's basename.
"""
import argparse, json, os, subprocess, sys

REGISTRY_FILE = ".share_registry.json"
SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def resolve(share_folder, output_folder, key):
    reg_path = os.path.join(share_folder, REGISTRY_FILE)
    entry = {}
    if os.path.isfile(reg_path):
        registry = json.load(open(reg_path))
        if key:
            entry = registry.get(key, {})
        else:
            base = os.path.basename(os.path.normpath(output_folder))
            for k, e in registry.items():
                if e.get("folder") == base:
                    key, entry = k, e
                    break
    if not key:
        sys.exit("Error: could not resolve S3 key — pass --key explicitly "
                 f"(no registry match for '{output_folder}' in {reg_path})")
    return key, entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output_folder")
    ap.add_argument("--share-folder")
    ap.add_argument("--key")
    ap.add_argument("--credential-dir", default=os.path.expanduser("~/.config/video-skill"))
    args = ap.parse_args()

    out = args.output_folder
    if not os.path.isdir(out):
        sys.exit(f"Error: {out} is not a directory")
    share_folder = args.share_folder or os.path.dirname(os.path.normpath(out)) or "."
    key, entry = resolve(share_folder, out, args.key)
    passcode = entry.get("passcode")

    template = os.path.join(SCRIPTS, "player.html")
    metadata = os.path.join(out, "metadata.json")

    render = ["python3", os.path.join(SCRIPTS, "render_page.py"),
              "--output-dir", out, "--template", template, "--metadata", metadata]
    if passcode:
        render += ["--passcode", str(passcode)]
    print(f"[PROGRESS] re-rendering {out} (key {key}{', passcode preserved' if passcode else ''})", flush=True)
    r = subprocess.run(render)
    if r.returncode != 0:
        sys.exit(r.returncode)

    upload = ["python3", os.path.join(SCRIPTS, "upload_s3.py"), out,
              "--key", key, "--credential-dir", args.credential_dir]
    print(f"[PROGRESS] re-uploading to key {key}", flush=True)
    sys.exit(subprocess.run(upload).returncode)


if __name__ == "__main__":
    main()
