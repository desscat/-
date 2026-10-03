import math
import time


LOGIN_MEMORY_SECONDS = 30 * 24 * 60 * 60


def normalize_saved_login(value, now=None):
    """Accept only a bounded, unexpired browser login; never retain a password."""
    now = time.time() if now is None else now
    if not isinstance(value, dict) or value.get("version") != 1:
        return None
    username, token, expires_at = (
        value.get("username"), value.get("token"), value.get("expires_at")
    )
    if not isinstance(username, str) or len(username) > 128:
        return None
    if not isinstance(token, str) or not token.strip() or len(token) > 16384:
        return None
    if "\r" in token or "\n" in token:
        return None
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        return None
    if not math.isfinite(expires_at) or not now < expires_at <= now + LOGIN_MEMORY_SECONDS + 300:
        return None
    return {"version": 1, "username": username.strip(), "token": token.strip(), "expires_at": expires_at}
