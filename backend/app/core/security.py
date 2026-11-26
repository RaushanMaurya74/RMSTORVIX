"""Password hashing and opaque session token utilities."""

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64


def hash_password(password: str) -> str:
    """Hash a plaintext password using salted scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_b64}${hash_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored scrypt hash in constant time."""
    try:
        algorithm, n_str, r_str, p_str, salt_b64, expected_b64 = stored_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(expected_b64.encode("ascii"))
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_str),
            r=int(r_str),
            p=int(p_str),
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def generate_session_token() -> str:
    """Generate a high-entropy opaque session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute the SHA-256 hex digest stored in PostgreSQL for session lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
