"""Unified persistent file storage abstraction supporting local disk and Supabase Storage."""

from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status
import httpx

from app.core.config import Settings, get_settings


def _clean_object_path(namespace: str, storage_key: str) -> str:
    """Normalize object path under a fixed namespace while blocking path traversal."""
    normalized = storage_key.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset storage path.",
        )
    clean_ns = namespace.strip("/")
    return f"{clean_ns}/{'/'.join(parts)}"


def safe_local_path(base_dir: Path, storage_key: str, *, asset_label: str = "asset") -> Path:
    """Resolve storage_key strictly inside base_dir for local/tmp storage."""
    base_resolved = base_dir.resolve()
    target = (base_resolved / storage_key).resolve()
    if base_resolved != target and base_resolved not in target.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {asset_label} storage path.",
        )
    return target


def _supabase_headers(settings: Settings, extra: dict[str, str] | None = None) -> dict[str, str]:
    key = settings.supabase_service_role_key.get_secret_value().strip()
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if extra:
        headers.update(extra)
    return headers


def _supabase_object_url(settings: Settings, object_path: str) -> str:
    base = settings.supabase_url.strip().rstrip("/")
    bucket = quote(settings.supabase_storage_bucket.strip(), safe="")
    encoded_path = quote(object_path, safe="/")
    return f"{base}/storage/v1/object/{bucket}/{encoded_path}"


def put_stored_bytes(
    *,
    namespace: str,
    base_dir: Path,
    storage_key: str,
    data: bytes,
    content_type: str,
    asset_label: str = "asset",
    settings: Settings | None = None,
) -> None:
    """Store binary bytes cleanly in Supabase Storage (production) or local managed disk (dev/test)."""
    active_settings = settings or get_settings()
    if active_settings.effective_storage_backend == "supabase":
        object_path = _clean_object_path(namespace, storage_key)
        url = _supabase_object_url(active_settings, object_path)
        headers = _supabase_headers(
            active_settings,
            {
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, content=data)
            if resp.status_code not in {200, 201}:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Unable to save {asset_label} to persistent object storage.",
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Persistent storage service unavailable while saving {asset_label}.",
            ) from exc
        return

    target_path = safe_local_path(base_dir, storage_key, asset_label=asset_label)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)


def get_stored_bytes(
    *,
    namespace: str,
    base_dir: Path,
    storage_key: str,
    asset_label: str = "asset",
    settings: Settings | None = None,
) -> bytes | None:
    """Retrieve binary bytes from Supabase Storage or local disk; return None if missing."""
    active_settings = settings or get_settings()
    if active_settings.effective_storage_backend == "supabase":
        object_path = _clean_object_path(namespace, storage_key)
        url = _supabase_object_url(active_settings, object_path)
        headers = _supabase_headers(active_settings)
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.content
            if resp.status_code in {400, 404}:
                return None
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to read {asset_label} from persistent object storage.",
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Persistent storage service unavailable while reading {asset_label}.",
            ) from exc

    path = safe_local_path(base_dir, storage_key, asset_label=asset_label)
    if not path.is_file():
        return None
    return path.read_bytes()


def delete_stored_object(
    *,
    namespace: str,
    base_dir: Path,
    storage_key: str | None,
    asset_label: str = "asset",
    settings: Settings | None = None,
) -> None:
    """Remove an existing stored asset cleanly without failing on missing objects."""
    if not storage_key:
        return
    active_settings = settings or get_settings()
    if active_settings.effective_storage_backend == "supabase":
        object_path = _clean_object_path(namespace, storage_key)
        url = _supabase_object_url(active_settings, object_path)
        headers = _supabase_headers(active_settings)
        try:
            with httpx.Client(timeout=12.0) as client:
                client.delete(url, headers=headers)
        except httpx.HTTPError:
            return
        return

    path = safe_local_path(base_dir, storage_key, asset_label=asset_label)
    if path.is_file():
        path.unlink()


def create_signed_storage_url(
    *,
    namespace: str,
    storage_key: str | None,
    expires_in: int | None = None,
    settings: Settings | None = None,
) -> str | None:
    """Generate a short-lived signed URL for a Supabase Storage asset when Supabase Storage is active."""
    if not storage_key:
        return None
    active_settings = settings or get_settings()
    if active_settings.effective_storage_backend != "supabase":
        return None

    object_path = _clean_object_path(namespace, storage_key)
    base = active_settings.supabase_url.strip().rstrip("/")
    bucket = quote(active_settings.supabase_storage_bucket.strip(), safe="")
    encoded_path = quote(object_path, safe="/")
    ttl = expires_in or active_settings.supabase_storage_signed_url_ttl

    sign_endpoint = f"{base}/storage/v1/object/sign/{bucket}/{encoded_path}"
    headers = _supabase_headers(active_settings, {"Content-Type": "application/json"})
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(sign_endpoint, headers=headers, json={"expiresIn": ttl})
        if resp.status_code != 200:
            return None
        signed_part = resp.json().get("signedURL")
        if not signed_part:
            return None
        if signed_part.startswith("http"):
            return signed_part
        return f"{base}/storage/v1{signed_part}"
    except httpx.HTTPError:
        return None
