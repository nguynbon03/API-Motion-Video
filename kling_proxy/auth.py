"""JWT HS256 token generation for Kling AI API."""

import time

import jwt


def generate_token(access_key: str, secret_key: str, expires_in: int = 1800) -> str:
    """Generate a JWT Bearer token for Kling API.

    Args:
        access_key: Kling Access Key (used as 'iss' claim).
        secret_key: Kling Secret Key (used for HS256 signing).
        expires_in: Token lifetime in seconds (default 30 minutes).

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "iss": access_key,
        "iat": now,
        "exp": now + expires_in,
        "nbf": now - 5,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")
