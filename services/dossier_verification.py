"""Signed handoff proving that a user started the source bot."""

from __future__ import annotations

import hashlib
import hmac
import re
import time

_PROOF_RE = re.compile(r"^p(\d{1,12})_(\d{1,12})_([A-Za-z0-9_-]{6,12})_([0-9a-f]{24})$")


def make_proof(secret: str, user_id: int, nonce: str, issued_at: int | None = None) -> str:
    timestamp = int(time.time()) if issued_at is None else issued_at
    body = f"{user_id}_{timestamp}_{nonce}"
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:24]
    return f"p{user_id}_{timestamp}_{nonce}_{signature}"


def verify_proof(secret: str, payload: str, user_id: int, *, max_age: int = 600) -> tuple[str, int] | None:
    match = _PROOF_RE.fullmatch(payload)
    if not match:
        return None
    proof_user, issued_at, nonce, signature = match.groups()
    if int(proof_user) != user_id:
        return None
    now = int(time.time())
    if int(issued_at) > now + 30 or now - int(issued_at) > max_age:
        return None
    body = f"{proof_user}_{issued_at}_{nonce}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(signature, expected):
        return None
    return nonce, int(issued_at)
