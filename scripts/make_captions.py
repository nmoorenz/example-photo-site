#!/usr/bin/env python3
"""
make_captions.py — Generate a captions.json template for a photo album folder.

Usage:
    python scripts/make_captions.py photos/tokyo-2024
    python scripts/make_captions.py photos/tokyo-2024 --overwrite

Creates captions.json in the given folder with an empty string for each photo,
sorted by filename. Edit the file to add your captions, then run sync.

If captions.json already exists, existing captions are preserved and only
new photos (not already in the file) are added. Use --overwrite to start fresh.

Sorting matches Windows Explorer: case-insensitive, natural number order
(so IMG_9.jpg comes before IMG_10.jpg, not after IMG_2.jpg).
"""

import argparse
import json
import re
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def windows_sort_key(filename: str):
    """
    Sort key that matches Windows Explorer order:
    - Case-insensitive
    - Natural number sorting (IMG_10 after IMG_9, not IMG_2)
    """
    parts = re.split(r"(\d+)", filename.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def sorted_windows(filenames):
    return sorted(filenames, key=windows_sort_key)


def make_captions(folder: Path, overwrite: bool = False) -> None:
    if not folder.exists() or not folder.is_dir():
        print(f"❌  Not a directory: {folder}")
        return

    photos = sorted_windows(
        p.name for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )

    if not photos:
        print(f"❌  No photos found in {folder}")
        return

    captions_file = folder / "captions.json"

    if captions_file.exists() and not overwrite:
        # Merge: keep existing captions, add new photos with empty strings
        existing = json.loads(captions_file.read_text())
        added = 0
        for photo in photos:
            if photo not in existing:
                existing[photo] = ""
                added += 1
        # Re-sort using Windows order
        captions = {k: existing[k] for k in sorted_windows(existing)}
        captions_file.write_text(json.dumps(captions, indent=2))
        print(f"✅  Updated {captions_file}")
        print(f"   {len(captions)} total photos, {added} newly added")
    else:
        # Fresh file
        captions = {photo: "" for photo in photos}
        captions_file.write_text(json.dumps(captions, indent=2))
        print(f"✅  Created {captions_file}")
        print(f"   {len(captions)} photos ready for captions")

    if any(v == "" for v in captions.values()):
        print(f"   ✏️  Open {captions_file} and fill in your captions")
        print(f"   Then run: python scripts/photo_sync.py sync")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate captions.json for a photo album")
    parser.add_argument("folder", type=Path, help="Path to album folder, e.g. photos/tokyo-2024")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing captions.json entirely")
    args = parser.parse_args()

    make_captions(args.folder, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
