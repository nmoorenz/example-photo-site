#!/usr/bin/env python3
"""
generate_config.py — Netlify build step

Reads environment variables and writes site/config.js so the browser
can find the S3 manifest URL and check the password hash.

Required Netlify environment variables:
    PHOTO_SITE_PASSWORD   plaintext password (hashed here, never exposed)
    S3_MANIFEST_URL       full URL to manifest.json in S3
"""

import hashlib
import json
import os
import sys
from pathlib import Path

password     = os.environ.get("PHOTO_SITE_PASSWORD", "")
manifest_url = os.environ.get("S3_MANIFEST_URL", "")

if not manifest_url:
    print("⚠️  S3_MANIFEST_URL is not set — site will not load photos.", file=sys.stderr)

pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""

if not pw_hash:
    print("⚠️  PHOTO_SITE_PASSWORD is not set — site will be unprotected.", file=sys.stderr)

config = {
    "pwHash":      pw_hash,
    "manifestUrl": manifest_url,
}

output = f"// Auto-generated at build time — do not edit or commit\nwindow.PHOTO_SITE_CONFIG = {json.dumps(config, indent=2)};\n"

Path("./site/config.js").write_text(output)

print("✅  config.js generated")
if pw_hash:
    print("   🔒 Password protection: enabled")
if manifest_url:
    print(f"   📦 Manifest URL: {manifest_url}")
