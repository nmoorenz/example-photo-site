#!/usr/bin/env python3
"""
photo_sync.py — Photo site CLI tool

Usage:
    python scripts/photo_sync.py sync       # Sync local photos to S3 + regenerate manifest
    python scripts/photo_sync.py manifest   # Regenerate manifest from S3 (no upload)
    python scripts/photo_sync.py init       # Create albums.json template if missing

Prerequisites:
    pip install boto3 python-dotenv

Config: copy .env.example to .env and fill in your values.

Captions:
    Add a captions.json file inside any album folder:

    photos/
    └── tokyo-2024/
        ├── captions.json
        ├── 001.jpg
        └── 002.jpg

    captions.json format:
    {
      "001.jpg": "Senso-ji temple at dawn",
      "002.jpg": "Ramen in Shinjuku"
    }

    captions.json is uploaded to S3 alongside photos and read when
    generating the manifest. Captions are optional per-photo — omit
    a filename to leave that photo without a caption.
"""

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

BUCKET      = os.environ.get("S3_BUCKET")
REGION      = os.environ.get("AWS_REGION", "ap-southeast-2")
PHOTOS_DIR  = Path(os.environ.get("LOCAL_PHOTOS_DIR", "./photos"))
ALBUMS_META = Path("./albums.json")

IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

if not BUCKET:
    print("❌  S3_BUCKET not set in .env", file=sys.stderr)
    sys.exit(1)

s3 = boto3.client(
    "s3",
    region_name=REGION,
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_albums_meta() -> dict:
    if not ALBUMS_META.exists():
        print(f"⚠️  {ALBUMS_META} not found — album descriptions will be empty.")
        print(f"   Run: python scripts/photo_sync.py init")
        return {}
    return json.loads(ALBUMS_META.read_text())


def get_local_albums() -> list[Path]:
    if not PHOTOS_DIR.exists():
        print(f"❌  Photos directory not found: {PHOTOS_DIR}", file=sys.stderr)
        sys.exit(1)
    return sorted(p for p in PHOTOS_DIR.iterdir() if p.is_dir())


def get_photos_in_dir(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def file_exists_in_s3(key: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except ClientError:
        return False


def fetch_s3_captions(slug: str) -> dict:
    """Fetch captions.json from S3 for a given album slug."""
    try:
        resp = s3.get_object(Bucket=BUCKET, Key=f"{slug}/captions.json")
        return json.loads(resp["Body"].read())
    except ClientError:
        return {}


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_file(local_path: Path, s3_key: str) -> None:
    s3.upload_file(
        str(local_path),
        BUCKET,
        s3_key,
        ExtraArgs={
            "ContentType": mime_type(local_path),
            "CacheControl": "public, max-age=31536000, immutable",
        },
    )


def upload_captions(local_path: Path, s3_key: str) -> None:
    """Upload captions.json with a short cache TTL so edits propagate quickly."""
    s3.upload_file(
        str(local_path),
        BUCKET,
        s3_key,
        ExtraArgs={
            "ContentType": "application/json",
            "CacheControl": "public, max-age=300",  # 5 minutes
        },
    )


# ── Manifest ──────────────────────────────────────────────────────────────────

def generate_manifest() -> None:
    print("\n📋 Generating manifest from S3...")
    meta = load_albums_meta()

    # List all objects
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET):
        objects.extend(page.get("Contents", []))

    # Group by album, note which albums have captions.json
    album_map: dict[str, list[str]] = {}
    albums_with_captions: set[str] = set()

    for obj in objects:
        parts = obj["Key"].split("/")
        if len(parts) < 2:
            continue
        album, filename = parts[0], parts[1]
        if not filename:
            continue
        if filename == "captions.json":
            albums_with_captions.add(album)
            continue
        if Path(filename).suffix.lower() not in IMAGE_EXTS:
            continue
        album_map.setdefault(album, []).append(obj["Key"])

    base_url = os.environ.get("CLOUDFRONT_URL", f"https://{BUCKET}.s3.{REGION}.amazonaws.com")

    albums = []
    for slug in sorted(album_map):
        keys     = sorted(album_map[slug])
        captions = fetch_s3_captions(slug) if slug in albums_with_captions else {}

        photos = [
            {
                "url":      f"{base_url}/{k}",
                "filename": k.split("/")[-1],
                "caption":  captions.get(k.split("/")[-1], ""),
            }
            for k in keys
        ]

        m     = meta.get(slug, {})
        cover = f"{base_url}/{slug}/{m['cover']}" if m.get("cover") else (photos[0]["url"] if photos else "")
        title = m.get("title") or slug.replace("-", " ").title()

        albums.append({
            "slug":        slug,
            "title":       title,
            "description": m.get("description", ""),
            "date":        m.get("date", ""),
            "cover":       cover,
            "photos":      photos,
        })

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "albums":    albums,
    }
    json_str = json.dumps(manifest, indent=2)

    s3.put_object(
        Bucket=BUCKET,
        Key="manifest.json",
        Body=json_str.encode(),
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )

    Path("./manifest.json").write_text(json_str)

    total_photos = sum(len(a["photos"]) for a in albums)
    print(f"✅  Manifest written: {len(albums)} album(s), {total_photos} photo(s)")
    for a in albums:
        captioned = sum(1 for p in a["photos"] if p["caption"])
        caption_note = f" 💬 {captioned} captions" if captioned else ""
        print(f"   📁 {a['slug']} ({len(a['photos'])} photos{caption_note})")


# ── Sync ──────────────────────────────────────────────────────────────────────

def sync() -> None:
    print(f"\n🔄 Syncing photos from {PHOTOS_DIR} → s3://{BUCKET}\n")
    albums = get_local_albums()

    if not albums:
        print(f"No album folders found in {PHOTOS_DIR}")
        return

    uploaded = skipped = 0

    for album_dir in albums:
        photos        = get_photos_in_dir(album_dir)
        captions_file = album_dir / "captions.json"
        print(f"📁 {album_dir.name} ({len(photos)} photos)")

        # Always re-upload captions.json so edits propagate
        if captions_file.exists():
            print(f"   💬 captions.json ...", end="", flush=True)
            upload_captions(captions_file, f"{album_dir.name}/captions.json")
            print(" done")

        for photo in photos:
            s3_key = f"{album_dir.name}/{photo.name}"
            if file_exists_in_s3(s3_key):
                print(f"   ⏭  {photo.name} (already exists)")
                skipped += 1
            else:
                print(f"   ⬆  {photo.name} ...", end="", flush=True)
                upload_file(photo, s3_key)
                print(" done")
                uploaded += 1

    print(f"\n✅  Sync complete: {uploaded} uploaded, {skipped} skipped")
    generate_manifest()


# ── Init ──────────────────────────────────────────────────────────────────────

def init() -> None:
    if ALBUMS_META.exists():
        print(f"ℹ️  {ALBUMS_META} already exists — not overwriting.")
        return
    example = {
        "my-first-album": {
            "title": "My First Album",
            "description": "A short description of what this album is about.",
            "date": "2024-01",
            "cover": "001.jpg",
        },
        "another-album": {
            "title": "Another Album",
            "description": "Description here.",
            "date": "2024-06",
            "cover": "001.jpg",
        },
    }
    ALBUMS_META.write_text(json.dumps(example, indent=2))
    print(f"✅  Created {ALBUMS_META} — edit this to add album titles and descriptions.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Photo site CLI")
    parser.add_argument(
        "command",
        choices=["sync", "manifest", "init"],
        help="sync: upload photos + regenerate manifest | manifest: regenerate only | init: create albums.json",
    )
    args = parser.parse_args()

    if args.command == "sync":
        sync()
    elif args.command == "manifest":
        generate_manifest()
    elif args.command == "init":
        init()


if __name__ == "__main__":
    main()
