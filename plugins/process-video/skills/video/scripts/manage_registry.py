#!/usr/bin/env python3
"""
Share registry CRUD operations.

Subcommands:
    add      Register a video folder with a new short key
    remove   Remove a video by key
    list     List all registered videos as JSON
    get      Get a single entry by key or title substring
    migrate  Convert old .share_manifest.json to .share_registry.json

Usage:
    python3 manage_registry.py add --share-folder <dir> --folder <name> --title <title> [--passcode <code>] [--s3-url <url>]
    python3 manage_registry.py remove --share-folder <dir> --key <key>
    python3 manage_registry.py list --share-folder <dir>
    python3 manage_registry.py get --share-folder <dir> --key <key>
    python3 manage_registry.py migrate --share-folder <dir>
"""

import sys
import os
import json
import argparse
import secrets
from datetime import datetime

REGISTRY_FILE = ".share_registry.json"
OLD_MANIFEST_FILE = ".share_manifest.json"


def load_registry(share_folder):
    path = os.path.join(share_folder, REGISTRY_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_registry(share_folder, registry):
    path = os.path.join(share_folder, REGISTRY_FILE)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")


def generate_key(registry):
    """Generate a unique 8-char URL-safe key."""
    for _ in range(100):
        key = secrets.token_urlsafe(6)  # 8 chars
        if key not in registry:
            return key
    raise RuntimeError("Failed to generate unique key after 100 attempts")


def find_by_key_or_title(registry, query):
    """Find entry by exact key or title substring match."""
    if query in registry:
        return query, registry[query]
    query_lower = query.lower()
    for key, entry in registry.items():
        if query_lower in entry.get("title", "").lower():
            return key, entry
    return None, None


def cmd_add(args):
    registry = load_registry(args.share_folder)

    # Check if folder is already registered — update sharing info if so
    for key, entry in registry.items():
        if entry.get("folder") == args.folder:
            updated = False
            if args.s3_url and entry.get("sharing", {}).get("s3_url") != args.s3_url:
                entry.setdefault("sharing", {})["s3_url"] = args.s3_url
                entry["sharing"]["method"] = args.method or entry["sharing"].get("method", "s3")
                updated = True
            if args.passcode and entry.get("passcode") != args.passcode:
                entry["passcode"] = args.passcode
                updated = True
            if updated:
                save_registry(args.share_folder, registry)
            print(json.dumps({"key": key, "existing": True, **entry}))
            return

    key = generate_key(registry)
    entry = {
        "folder": args.folder,
        "title": args.title,
        "passcode": args.passcode,
        "created": datetime.now().isoformat(timespec="seconds"),
        "sharing": {
            "method": args.method or "s3",
            "s3_url": args.s3_url,
            "tunnel_url": None,
        },
    }
    registry[key] = entry
    save_registry(args.share_folder, registry)
    print(json.dumps({"key": key, "existing": False, **entry}))


def cmd_remove(args):
    registry = load_registry(args.share_folder)
    key, entry = find_by_key_or_title(registry, args.key)
    if key is None:
        print(f"Error: no entry found for '{args.key}'", file=sys.stderr)
        sys.exit(1)
    title = entry.get("title", "")
    del registry[key]
    save_registry(args.share_folder, registry)
    print(json.dumps({"removed": key, "title": title}))


def cmd_list(args):
    registry = load_registry(args.share_folder)
    print(json.dumps(registry, indent=2, ensure_ascii=False))


def cmd_get(args):
    registry = load_registry(args.share_folder)
    key, entry = find_by_key_or_title(registry, args.key)
    if key is None:
        print(f"Error: no entry found for '{args.key}'", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"key": key, **entry}, indent=2, ensure_ascii=False))


def cmd_migrate(args):
    old_path = os.path.join(args.share_folder, OLD_MANIFEST_FILE)
    if not os.path.exists(old_path):
        print("No .share_manifest.json found, nothing to migrate.", file=sys.stderr)
        sys.exit(1)

    with open(old_path) as f:
        old_manifest = json.load(f)

    registry = load_registry(args.share_folder)
    migrated = 0

    for video in old_manifest.get("videos", []):
        folder = video.get("folder", "")
        # Check if already registered
        already = False
        for entry in registry.values():
            if entry.get("folder") == folder:
                already = True
                break
        if already:
            continue

        key = generate_key(registry)
        registry[key] = {
            "folder": folder,
            "title": video.get("title", folder),
            "passcode": video.get("passcode"),
            "created": video.get("created", datetime.now().isoformat(timespec="seconds")),
            "sharing": {
                "method": "tunnel",
                "s3_url": None,
                "tunnel_url": None,
            },
        }
        migrated += 1

    save_registry(args.share_folder, registry)
    print(json.dumps({"migrated": migrated, "total": len(registry)}))


def main():
    parser = argparse.ArgumentParser(description="Share registry management")
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add")
    p_add.add_argument("--share-folder", required=True)
    p_add.add_argument("--folder", required=True, help="Folder name relative to share-folder")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--passcode", default=None)
    p_add.add_argument("--method", default="s3", choices=["s3", "tunnel", "both"])
    p_add.add_argument("--s3-url", default=None)

    # remove
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--share-folder", required=True)
    p_rm.add_argument("--key", required=True, help="Key or title substring")

    # list
    p_ls = sub.add_parser("list")
    p_ls.add_argument("--share-folder", required=True)

    # get
    p_get = sub.add_parser("get")
    p_get.add_argument("--share-folder", required=True)
    p_get.add_argument("--key", required=True, help="Key or title substring")

    # migrate
    p_mig = sub.add_parser("migrate")
    p_mig.add_argument("--share-folder", required=True)

    args = parser.parse_args()

    commands = {
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "get": cmd_get,
        "migrate": cmd_migrate,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
