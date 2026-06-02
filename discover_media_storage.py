"""Stockage des illustrations Discover (S3/CDN ou fichiers locaux servis par FastAPI)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_BACKEND_ROOT = Path(__file__).resolve().parent
LOCAL_MEDIA_ROOT = _BACKEND_ROOT / "data" / "discover_media"


def _s3_configured() -> bool:
    return bool(
        (os.environ.get("AWS_S3_BUCKET") or os.environ.get("DISCOVER_S3_BUCKET") or "").strip()
        and (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
        and (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
    )


def _public_base_url() -> str:
    return (
        os.environ.get("DISCOVER_MEDIA_PUBLIC_BASE_URL")
        or os.environ.get("CDN_BASE_URL")
        or "http://127.0.0.1:8002"
    ).rstrip("/")


def _store_local(content: bytes, extension: str) -> str:
    LOCAL_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{extension.lstrip('.')}"
    path = LOCAL_MEDIA_ROOT / name
    path.write_bytes(content)
    return f"{_public_base_url()}/media/discover/{name}"


def _store_s3(content: bytes, extension: str, content_type: str) -> Optional[str]:
    try:
        import boto3
    except ImportError:
        return None

    bucket = (
        os.environ.get("AWS_S3_BUCKET") or os.environ.get("DISCOVER_S3_BUCKET") or ""
    ).strip()
    if not bucket:
        return None

    prefix = (os.environ.get("DISCOVER_S3_PREFIX") or "discover/pexels").strip().strip("/")
    key = f"{prefix}/{uuid.uuid4().hex}.{extension.lstrip('.')}"
    region = (os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-3").strip()

    client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        ACL=os.environ.get("DISCOVER_S3_ACL", "public-read"),
    )

    cdn_base = (os.environ.get("DISCOVER_MEDIA_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if cdn_base:
        return f"{cdn_base}/{key}"

    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


async def store_discover_image(
    content: bytes,
    *,
    extension: str = "jpg",
    content_type: str = "image/jpeg",
) -> Optional[str]:
    """Enregistre une image et renvoie son URL publique (S3 si configuré, sinon local)."""
    if not content:
        return None
    if _s3_configured():
        url = _store_s3(content, extension, content_type)
        if url:
            return url
    return _store_local(content, extension)
