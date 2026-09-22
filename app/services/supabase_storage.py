from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class SupabaseStorageClient:
    """Thin wrapper over Supabase Storage's REST API, scoped to one bucket.

    Shared by any service that stores private objects there (patient-facing
    uploads only ever touch metadata in Postgres -- the file itself lives
    here, addressed by `object_key`). Kept deliberately minimal: no retries,
    no caching, just the three calls services actually need.
    """

    def __init__(self, bucket: str):
        self.bucket = bucket

    def upload(self, object_key: str, content: bytes, content_type: str) -> None:
        self._ensure_configured()
        encoded = quote(object_key, safe="/")
        response = httpx.post(
            f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/{self.bucket}/{encoded}",
            headers={**self._headers(), "Content-Type": content_type, "x-upsert": "false"},
            content=content,
            timeout=30.0,
        )
        response.raise_for_status()

    def sign_url(self, object_key: str, ttl_seconds: int) -> str:
        self._ensure_configured()
        encoded = quote(object_key, safe="/")
        response = httpx.post(
            f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/sign/{self.bucket}/{encoded}",
            headers=self._headers(),
            json={"expiresIn": ttl_seconds},
            timeout=10.0,
        )
        response.raise_for_status()
        signed_path = response.json().get("signedURL") or response.json().get("signedUrl")
        if not signed_path:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="STORAGE_URL_UNAVAILABLE")
        if signed_path.startswith("http"):
            return signed_path
        return f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1{signed_path}"

    def delete(self, object_key: str) -> None:
        try:
            encoded = quote(object_key, safe="/")
            response = httpx.delete(
                f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/{self.bucket}/{encoded}",
                headers=self._headers(),
                timeout=10.0,
            )
            response.raise_for_status()
        except Exception:
            # The database row remains authoritative; operational cleanup can retry.
            pass

    def _headers(self) -> dict[str, str]:
        self._ensure_configured()
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }

    @staticmethod
    def _ensure_configured() -> None:
        if not settings.SUPABASE_PROJECT_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="STORAGE_NOT_CONFIGURED")
