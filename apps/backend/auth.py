"""
auth.py — JWT verification for multi-tenant access.

The backend keeps the trusted service_role Supabase client (it bypasses RLS by
design) but no longer trusts a hardcoded DEFAULT_SME_ID or a URL path param.
Every protected endpoint now resolves sme_id from the caller's Supabase Auth
JWT, so a tenant can only ever touch their own workspace.
"""

import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException
from supabase import Client, create_client

load_dotenv()

# service_role client: used both to validate the caller's JWT against the auth
# API and to resolve their sme_id (bypassing RLS for the lookup).
_supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_API_KEY"],
)


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorization header."
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token.")
    return token


async def get_current_sme_id(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: validate the Bearer JWT and resolve the caller's sme_id.

    Raises 401 if the token is missing/invalid, 403 if the (valid) user has no
    workspace.
    """
    token = _bearer_token(authorization)

    try:
        user_resp = _supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = getattr(user_resp, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    rows = (
        _supabase.table("sme")
        .select("sme_id")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=403, detail="No workspace for this user.")
    return rows[0]["sme_id"]
