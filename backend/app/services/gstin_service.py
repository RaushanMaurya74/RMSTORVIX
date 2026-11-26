"""Indian GSTIN format/checksum validation, state extraction, and optional API lookup."""

import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.schemas.customer import GstinVerifyResponse

_GSTIN_FORMAT_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

INDIAN_STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}


def compute_gstin_check_char(prefix14: str) -> str:
    """Compute the 15th GSTIN check character using the official mod-36 algorithm."""
    total = 0
    for idx, ch in enumerate(prefix14):
        code = _ALPHABET.index(ch)
        factor = 2 if idx % 2 == 1 else 1
        product = code * factor
        total += (product // 36) + (product % 36)
    check_val = (36 - (total % 36)) % 36
    return _ALPHABET[check_val]


def verify_gstin_checksum(gstin: str) -> bool:
    """Validate 15-character GSTIN format, state code, and mod-36 check digit."""
    cleaned = gstin.strip().upper()
    if not _GSTIN_FORMAT_RE.match(cleaned):
        return False
    if cleaned[:2] not in INDIAN_STATE_CODES:
        return False
    return compute_gstin_check_char(cleaned[:14]) == cleaned[14]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_provider_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    """Normalize common GSP / GSTIN API JSON response shapes safely."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return {}

    company_name = (
        _clean_text(data.get("tradeNam"))
        or _clean_text(data.get("trade_name"))
        or _clean_text(data.get("company_name"))
        or _clean_text(data.get("lgnm"))
        or _clean_text(data.get("legal_name"))
    )

    pradr = data.get("pradr") if isinstance(data.get("pradr"), dict) else {}
    addr = pradr.get("addr") if isinstance(pradr.get("addr"), dict) else data.get("address")
    if isinstance(addr, dict):
        line1_parts = [
            _clean_text(addr.get("bno")),
            _clean_text(addr.get("flno")),
            _clean_text(addr.get("bnm")),
            _clean_text(addr.get("st")),
        ]
        line1 = ", ".join(p for p in line1_parts if p) or _clean_text(addr.get("address_line1"))
        line2 = _clean_text(addr.get("loc")) or _clean_text(addr.get("address_line2"))
        city = _clean_text(addr.get("dst")) or _clean_text(addr.get("city"))
        state = _clean_text(addr.get("stcd")) or _clean_text(addr.get("state"))
        postal = _clean_text(addr.get("pncd")) or _clean_text(addr.get("postal_code"))
    else:
        line1 = _clean_text(data.get("address_line1"))
        line2 = _clean_text(data.get("address_line2"))
        city = _clean_text(data.get("city"))
        state = _clean_text(data.get("state"))
        postal = _clean_text(data.get("postal_code"))

    return {
        "company_name": company_name,
        "address_line1": line1,
        "address_line2": line2,
        "city": city,
        "state": state,
        "postal_code": postal,
    }


def verify_and_lookup_gstin(
    gstin: str,
    *,
    settings: Settings | None = None,
) -> GstinVerifyResponse:
    """Verify GSTIN format/checksum, extract state/PAN, and optionally query an external API."""
    active_settings = settings or get_settings()
    cleaned = gstin.strip().upper()

    if not _GSTIN_FORMAT_RE.match(cleaned):
        return GstinVerifyResponse(
            gstin=cleaned,
            valid=False,
            checksum_valid=False,
            lookup_source="offline_checksum",
            message="Invalid GSTIN format. Expected 15 characters (e.g. 27AAACP1234A1Z5).",
        )

    state_code = cleaned[:2]
    state_name = INDIAN_STATE_CODES.get(state_code)
    if state_name is None:
        return GstinVerifyResponse(
            gstin=cleaned,
            valid=False,
            checksum_valid=False,
            state_code=state_code,
            lookup_source="offline_checksum",
            message=f"Unrecognized GST state code '{state_code}'.",
        )

    checksum_ok = verify_gstin_checksum(cleaned)
    if not checksum_ok:
        return GstinVerifyResponse(
            gstin=cleaned,
            valid=False,
            checksum_valid=False,
            state_code=state_code,
            state=state_name,
            country="India",
            pan=cleaned[2:12],
            lookup_source="offline_checksum",
            message="GSTIN check digit failed verification. Please double-check the number.",
        )

    pan = cleaned[2:12]
    api_url_template = active_settings.gstin_api_url.strip()
    if api_url_template:
        target_url = (
            api_url_template.replace("{gstin}", cleaned)
            if "{gstin}" in api_url_template
            else f"{api_url_template.rstrip('/')}/{cleaned}"
        )
        headers: dict[str, str] = {"Accept": "application/json"}
        api_key = active_settings.effective_gstin_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["x-api-key"] = api_key
        try:
            with httpx.Client(timeout=active_settings.gstin_api_timeout_seconds) as client:
                resp = client.get(target_url, headers=headers)
            if resp.status_code == 200:
                extracted = _extract_provider_fields(resp.json())
                return GstinVerifyResponse(
                    gstin=cleaned,
                    valid=True,
                    checksum_valid=True,
                    state_code=state_code,
                    state=extracted.get("state") or state_name,
                    country="India",
                    pan=pan,
                    company_name=extracted.get("company_name"),
                    address_line1=extracted.get("address_line1"),
                    address_line2=extracted.get("address_line2"),
                    city=extracted.get("city"),
                    postal_code=extracted.get("postal_code"),
                    lookup_source="external_api",
                    message="GSTIN verified and business details retrieved.",
                )
            return GstinVerifyResponse(
                gstin=cleaned,
                valid=True,
                checksum_valid=True,
                state_code=state_code,
                state=state_name,
                country="India",
                pan=pan,
                lookup_source="offline_checksum",
                message=(
                    f"GSTIN format & checksum verified ({state_name}), "
                    f"but external lookup returned status {resp.status_code}."
                ),
            )
        except Exception:
            return GstinVerifyResponse(
                gstin=cleaned,
                valid=True,
                checksum_valid=True,
                state_code=state_code,
                state=state_name,
                country="India",
                pan=pan,
                lookup_source="offline_checksum",
                message=(
                    f"GSTIN format & checksum verified ({state_name}). "
                    "External GSTIN lookup service was unreachable."
                ),
            )

    return GstinVerifyResponse(
        gstin=cleaned,
        valid=True,
        checksum_valid=True,
        state_code=state_code,
        state=state_name,
        country="India",
        pan=pan,
        lookup_source="offline_checksum",
        message=(
            f"GSTIN format & checksum verified (State: {state_name}, PAN: {pan}). "
            "Configure GSTIN_API_URL in .env for live business name and address lookup."
        ),
    )
