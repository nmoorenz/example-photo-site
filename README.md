# Photo Site

A personal photo gallery. Photos live in a private S3 bucket, served via CloudFront CDN, with the site hosted on Netlify. Password-protected, fully managed with a local Python CLI tool.

## Architecture

```
Browser → photos.example.com (Netlify — serves HTML/JS/CSS)
              ↓ fetches manifest + photos
          cdn.example.com (CloudFront → private S3 bucket)
                                           ↑
                                  photo_sync.py CLI (your machine)

GitHub (source) → Netlify (build + deploy on push)
```

- **S3** stores all photos + `manifest.json` (private — direct URLs return 403)
- **CloudFront** serves photos and manifest via `cdn.example.com`, caches at edge
- **OAC** (Origin Access Control) — the only thing allowed to read the private bucket
- **ACM** provides the SSL certificate for `cdn.example.com`
- **Netlify** hosts the static site at `photos.example.com`, injects secrets at build time
- **Terraform** provisions all AWS infrastructure
- **`photo_sync.py`** uploads photos to S3 and regenerates the manifest
- **Password gate** uses SHA-256 hashed password, checked client-side

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Terraform](https://developer.hashicorp.com/terraform/install)
- [AWS CLI](https://aws.amazon.com/cli/)
- An [AWS](https://aws.amazon.com) account
- A [Netlify](https://netlify.com) account

### 2. Clone and install Python deps

```bash
git clone https://github.com/you/photo-site
cd photo-site
pip install -r requirements.txt
```

### 3. Configure AWS CLI profile

```bash
aws configure --profile your-aws-profile
# Enter your personal admin AWS credentials when prompted
# Region: ap-southeast-2
# Output format: json
```

### 4. Provision the ACM certificate first

CloudFront requires a validated SSL certificate before it can be created.
Do this in two steps:

```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set your bucket_name
terraform init
terraform apply -target=aws_acm_certificate.photos
```

### 5. Validate the ACM certificate

```bash
terraform output acm_certificate_validation_options
```

Add the CNAME record at your registrar:

| Type | Host | Value |
|---|---|---|
| CNAME | `_abc123.cdn` | `_xyz456.acm-validations.aws.` |

Wait until AWS Console → Certificate Manager → **us-east-1** shows status **Issued** (usually 5–10 minutes).

### 6. Provision the rest of the infrastructure

```bash
terraform apply
```

This creates the S3 bucket, CloudFront distribution, bucket policies, OAC, and IAM uploader user.

### 7. Point DNS to CloudFront

```bash
terraform output cloudfront_domain
# Returns something like: d1234abcd.cloudfront.net
```

At your registrar add:

| Type | Host | Value |
|---|---|---|
| CNAME | `cdn` | `d1234abcd.cloudfront.net` |

Keep `photos` pointing to Netlify — CloudFront only handles `cdn.example.com`.

### 8. Configure local environment

```bash
cp .env.example .env
```

Fill in `.env` with the uploader credentials:

```bash
terraform output uploader_access_key_id
terraform output uploader_secret_access_key
```

Also set:
```
CLOUDFRONT_URL=https://cdn.example.com
```

### 9. Add albums and photos

Edit `albums.json`:
```json
{
  "my-trip": {
    "title": "My Trip",
    "description": "A description of this album.",
    "date": "January 2025",
    "cover": "001.jpg"
  }
}
```

Add photos to `./photos/` — one subfolder per album:
```
photos/
├── my-trip/
│   ├── 001.jpg
│   └── 002.jpg
└── another-album/
    └── 001.jpg
```

### 10. Add captions (optional)

```bash
python scripts/make_captions.py photos/album-name
# edit photos/album-name/captions.json
```

See the [Captions](#captions) section for details.

### 11. Upload to S3

```bash
python scripts/photo_sync.py sync
```

### 12. Deploy to Netlify

1. Push to GitHub, connect repo in Netlify
2. Set environment variables in **Netlify → Site configuration → Environment variables**:

| Variable | Value |
|---|---|
| `PHOTO_SITE_PASSWORD` | your chosen password |
| `S3_MANIFEST_URL` | `https://cdn.example.com/manifest.json` |

3. Netlify build settings:

| Setting | Value |
|---|---|
| Base directory | *(leave blank)* |
| Build command | `pip install -r requirements.txt && python scripts/generate_config.py` |
| Publish directory | `site` |

---

## Workflow: Adding New Photos

```bash
# 1. Drop photos into ./photos/album-name/
# 2. Update albums.json if it's a new album
# 3. Optionally add captions
python scripts/make_captions.py photos/album-name
# edit photos/album-name/captions.json
# 4. Upload
python scripts/photo_sync.py sync
# Live site updates immediately
```

---

## Captions

Add a `captions.json` file to any album folder. Captions are optional per-photo.

Generate a template:
```bash
python scripts/make_captions.py photos/tokyo-2024
```

Edit the generated file:
```json
{
  "001.jpg": "Senso-ji temple at dawn",
  "002.jpg": "Ramen in Shinjuku",
  "003.jpg": ""
}
```

Then run `photo_sync.py sync` as normal. Captions appear below the slider and in the lightbox.

---

## CLI Reference

```bash
python scripts/photo_sync.py sync           # Upload new photos + regenerate manifest
python scripts/photo_sync.py manifest       # Regenerate manifest only (no upload)
python scripts/photo_sync.py init           # Create a starter albums.json

python scripts/make_captions.py photos/album-name            # Create captions.json template
python scripts/make_captions.py photos/album-name --overwrite # Start fresh
```

---

## File Structure

```
photo-site/
├── site/                       # Static website (deployed to Netlify)
│   ├── index.html              # Albums grid
│   ├── album.html              # Photo slider
│   ├── style.css
│   ├── auth.js                 # Password gate
│   ├── app.js                  # Homepage logic
│   ├── album.js                # Slider + lightbox logic
│   └── config.js               # ← generated at build time, gitignored
│
├── scripts/
│   ├── photo_sync.py           # CLI: upload photos to S3 + generate manifest
│   ├── generate_config.py      # Netlify build step: write config.js
│   └── make_captions.py        # Generate captions.json template for an album
│
├── infrastructure/
│   ├── main.tf                 # Terraform: S3, CloudFront, ACM, IAM
│   └── terraform.tfvars.example
│
├── albums.json                 # Album titles, descriptions, dates — edit this
├── netlify.toml                # Netlify build config
├── requirements.txt            # Python deps: boto3, python-dotenv
├── .env.example
└── .gitignore
```

---

## DNS Summary

| Subdomain | Points to | Purpose |
|---|---|---|
| `photos.example.com` | Netlify | Serves the website |
| `cdn.example.com` | CloudFront | Serves photos + manifest from S3 |

---

## Security

**Password gate** — the Netlify site requires a password. The plaintext password lives only in Netlify's environment variables; only its SHA-256 hash is baked into the deployed site.

**Private S3 bucket** — all public access is blocked. `BucketOwnerEnforced` disables object ACLs so the bucket policy is the sole access mechanism. Direct S3 URLs return 403.

**CloudFront OAC** — Origin Access Control allows only the CloudFront distribution to read the bucket, using AWS SigV4 request signing.

---

## Customisation

- **Site title**: edit the `<h1>` in `site/index.html`
- **Colours / fonts**: edit CSS variables at the top of `site/style.css`
- **Photo order**: files are sorted alphabetically — name them `001.jpg`, `002.jpg` etc. for manual ordering
- **S3 region**: change `aws_region` in `infrastructure/terraform.tfvars`
- **CDN domain**: change `cdn_domain` in `infrastructure/terraform.tfvars`
