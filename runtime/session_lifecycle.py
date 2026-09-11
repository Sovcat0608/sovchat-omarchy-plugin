"""Explicit, verifiable revocation of this client's session only."""
import copy
import time
from api import ApiError, Transport


def revoke(api, timeout=8):
    if not api.token: return
    target = copy.copy(api)
    if isinstance(getattr(target, "transport", None), Transport):
        target.transport = copy.copy(target.transport)
        target.transport.deadline = time.monotonic() + timeout
    try:
        target.request("/api/auth/logout", "POST")
    except ApiError as error:
        # The server deletes the database session before reconciling LiveKit.
        # Verification below distinguishes applied logout from a network failure.
        if error.code not in {"AUTH_REQUIRED", "VOICE_REVOCATION_PENDING"}: raise
    target.token = api.token
    try:
        target.request("/api/auth/session")
    except ApiError as error:
        if error.status == 401: return
        raise
    raise ApiError("LOGOUT_PENDING")
