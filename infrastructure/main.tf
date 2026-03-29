terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: use S3 backend for remote state
  # backend "s3" {
  #   bucket = "my-terraform-state"
  #   key    = "photo-site/terraform.tfstate"
  #   region  = "ap-southeast-2"
  #   profile = "your-aws-profile"
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = "your-aws-profile"
}

# CloudFront requires ACM certificates to be in us-east-1 regardless of
# where your bucket is. This second provider alias handles that.
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = "your-aws-profile"
}

# ─── Variables ───────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-2"
}

variable "bucket_name" {
  description = "S3 bucket name for photo storage (must be globally unique)"
  type        = string
}

variable "cdn_domain" {
  description = "Subdomain for CloudFront CDN — serves photos and manifest"
  type        = string
  default     = "cdn.example.com"
}

variable "allowed_origins" {
  description = "Origins allowed to access the bucket via CORS (your site domains)"
  type        = list(string)
  default     = []
}

# ─── S3 Bucket ───────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "photos" {
  bucket = var.bucket_name

  tags = {
    Project = "photo-site"
  }
}

# Bucket is fully private — CloudFront OAC is the only way in
resource "aws_s3_bucket_public_access_block" "photos" {
  bucket = aws_s3_bucket.photos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Disables object-level ACLs — bucket policy is the sole access control mechanism
resource "aws_s3_bucket_ownership_controls" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# CORS allows the browser (at photos.example.com) to fetch from cdn.example.com
resource "aws_s3_bucket_cors_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# ─── CloudFront Origin Access Control ────────────────────────────────────────
#
# OAC is the modern replacement for OAI. It grants CloudFront permission to
# read from the private S3 bucket using SigV4 request signing.

resource "aws_cloudfront_origin_access_control" "photos" {
  name                              = "${var.bucket_name}-oac"
  description                       = "OAC for photo site S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ─── S3 Bucket Policy (allow CloudFront OAC only) ────────────────────────────

resource "aws_s3_bucket_policy" "photos_cloudfront_read" {
  bucket     = aws_s3_bucket.photos.id
  depends_on = [aws_s3_bucket_public_access_block.photos]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.photos.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.photos.arn
          }
        }
      }
    ]
  })
}

# ─── ACM Certificate ─────────────────────────────────────────────────────────
#
# Must live in us-east-1 — required by CloudFront regardless of bucket region.
# After terraform apply, validate by adding the output CNAME at your registrar.
# Wait for status "Issued" in ACM console (us-east-1) before running apply again.

resource "aws_acm_certificate" "photos" {
  provider          = aws.us_east_1
  domain_name       = var.cdn_domain
  validation_method = "DNS"

  tags = {
    Project = "photo-site"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ─── CloudFront Distribution ──────────────────────────────────────────────────
#
# Serves photos and manifest from S3 via cdn.example.com.
# The Netlify site at photos.example.com fetches from here.

resource "aws_cloudfront_distribution" "photos" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "Photo site CDN — ${var.cdn_domain}"
  aliases         = [var.cdn_domain]

  origin {
    domain_name              = aws_s3_bucket.photos.bucket_regional_domain_name
    origin_id                = "s3-${var.bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.photos.id
  }

  # Default: cache photos aggressively (1 year, immutable)
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
    response_headers_policy_id = "60669652-455b-4ae9-85a4-c4c02393f86c" # Managed-SimpleCORS
  }

  # manifest.json: never cache so updates propagate immediately
  ordered_cache_behavior {
    path_pattern           = "manifest.json"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.photos.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Project = "photo-site"
  }
}

# ─── IAM User for CLI uploads ─────────────────────────────────────────────────

resource "aws_iam_user" "uploader" {
  name = "${var.bucket_name}-uploader"

  tags = {
    Project = "photo-site"
  }
}

resource "aws_iam_user_policy" "uploader" {
  name = "${var.bucket_name}-uploader-policy"
  user = aws_iam_user.uploader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.photos.arn,
          "${aws_s3_bucket.photos.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_access_key" "uploader" {
  user = aws_iam_user.uploader.name
}

# ─── Outputs ─────────────────────────────────────────────────────────────────

output "bucket_name" {
  value       = aws_s3_bucket.photos.bucket
  description = "S3 bucket name"
}

output "cloudfront_domain" {
  value       = aws_cloudfront_distribution.photos.domain_name
  description = "CloudFront domain — add as CNAME for cdn.example.com at your registrar"
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.photos.id
  description = "CloudFront distribution ID"
}

output "acm_certificate_validation_options" {
  value       = aws_acm_certificate.photos.domain_validation_options
  description = "CNAME record to add at your registrar to validate the ACM certificate"
}

output "manifest_url" {
  value       = "https://${var.cdn_domain}/manifest.json"
  description = "Set this as S3_MANIFEST_URL in Netlify environment variables"
}

output "uploader_access_key_id" {
  value       = aws_iam_access_key.uploader.id
  description = "AWS Access Key ID for CLI uploader — put in .env"
  sensitive   = true
}

output "uploader_secret_access_key" {
  value       = aws_iam_access_key.uploader.secret
  description = "AWS Secret Access Key for CLI uploader — put in .env"
  sensitive   = true
}
