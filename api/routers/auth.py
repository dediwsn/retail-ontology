"""Cognito OAuth callback (/api/auth/callback).

Lambda@Edge redirects unauthenticated browsers to the Cognito Hosted UI;
Cognito redirects back here with ?code=XXX. We exchange the code for tokens
and set them as cookies, then redirect to /.

All Cognito identifiers come from required env vars wired by the ECS task
definition (`infra-cdk/lib/compute-stack.ts`). No hardcoded fallbacks —
falling back to a literal default would silently exchange auth codes against
the wrong identity provider if the User Pool were ever recreated.
"""
from __future__ import annotations

import base64
import json as _json
import os
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"])


def _required_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"required env var missing: {key}. "
            f"Compute stack must inject all Cognito identifiers; falling back "
            f"to a hardcoded default would silently exchange auth codes against "
            f"the wrong identity provider."
        )
    return val


PROJECT = _required_env("ONTOLOGY_PROJECT")
ENV_NAME = _required_env("ONTOLOGY_ENV")
ACCOUNT = _required_env("AWS_ACCOUNT_ID")
REGION = _required_env("AWS_REGION")
CLIENT_ID = _required_env("COGNITO_USER_POOL_CLIENT_ID")
COGNITO_DOMAIN = f"{PROJECT}-{ENV_NAME}-{ACCOUNT}.auth.{REGION}.amazoncognito.com"

# `redirect_uri` for the OAuth token exchange must match exactly what was
# sent during the /authorize redirect AND must be in Cognito's Hosted UI
# callback allowlist. We derive it from the PUBLIC_DOMAIN env (set by the
# infra layer) — NOT from the request Host header — for two reasons:
#   1. CloudFront's Managed-AllViewerExceptHostHeader policy strips Host
#      before forwarding to ALB, so the API would only ever see the ALB
#      DNS and Host-based logic would always fail.
#   2. PUBLIC_DOMAIN comes from the ECS task env (infra-controlled). The
#      Host header is client-influenced — using it for redirect_uri creation
#      would expand attack surface (Host spoofing, alternate-alias misconfig,
#      direct-to-ALB if the SG ever loosens). Defense-in-depth still relies
#      on Cognito's own redirect_uri allowlist as the second gate.
PUBLIC_DOMAIN = _required_env("PUBLIC_DOMAIN")
# Multiple comma-separated hosts permitted (e.g. apex + www); first one
# becomes the canonical redirect target.
_PRIMARY_DOMAIN = next((h.strip() for h in PUBLIC_DOMAIN.split(",") if h.strip()), "")
if not _PRIMARY_DOMAIN:
    raise RuntimeError("PUBLIC_DOMAIN env is empty after parsing")


@router.get("/auth/login")
def auth_login() -> RedirectResponse:
    """Redirect to Cognito Hosted UI /oauth2/authorize. Used by the sidebar
    re-login link and by Lambda@Edge as the unauthenticated landing page."""
    redirect_uri = f"https://{_PRIMARY_DOMAIN}/api/auth/callback"
    authorize_url = (
        f"https://{COGNITO_DOMAIN}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&scope=openid+email+profile"
        f"&redirect_uri={redirect_uri}"
    )
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/auth/whoami")
def auth_whoami(request: Request) -> Dict[str, Any]:
    """Return identity claims from the id_token cookie.

    Always returns JSON 200 — the SidebarAuth widget reads the
    `authenticated` boolean to render the right state. Returning 401
    here would fight with the auth middleware bypass for /api/auth/*
    and force the client into noisy error handling for what is a
    completely normal "logged-out" UI state. Mirrors mfg-ontology's
    pattern (see ADR-0004 + their api/routers/auth.py).
    """
    id_token = request.cookies.get("id_token")
    if not id_token:
        return {"authenticated": False}
    parts = id_token.split(".")
    if len(parts) != 3:
        return {"authenticated": False, "error": "malformed id_token"}
    # JWT base64url decoding requires padding adjustment.
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, _json.JSONDecodeError):
        return {"authenticated": False, "error": "invalid id_token payload"}
    return {
        "authenticated": True,
        "sub":      claims.get("sub"),
        "email":    claims.get("email"),
        "username": claims.get("cognito:username") or claims.get("preferred_username"),
        "groups":   claims.get("cognito:groups") or [],
    }


@router.get("/auth/logout")
def auth_logout() -> RedirectResponse:
    """Clear auth cookies and redirect to Cognito Hosted UI logout.

    Mirrors mfg-ontology pattern: the Cognito App Client must list
    `https://<PUBLIC_DOMAIN>/` (with trailing slash) as a LogoutURL.
    We strip+re-add exactly one trailing slash to avoid drift if
    PUBLIC_DOMAIN ever changes shape.
    """
    logout_redirect = f"https://{_PRIMARY_DOMAIN.rstrip('/')}/"
    cognito_logout = (
        f"https://{COGNITO_DOMAIN}/logout"
        f"?client_id={CLIENT_ID}"
        f"&logout_uri={logout_redirect}"
    )
    response = RedirectResponse(url=cognito_logout, status_code=302)
    # Clear all 3 cookies set on /callback. path="/" matches what
    # set_cookie used (default), so the deletion fires.
    for name in ("id_token", "access_token", "refresh_token"):
        response.delete_cookie(name, path="/")
    return response


@router.get("/auth/callback")
def auth_callback(code: Optional[str] = None) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="missing code parameter")
    redirect_uri = f"https://{_PRIMARY_DOMAIN}/api/auth/callback"
    resp = requests.post(
        f"https://{COGNITO_DOMAIN}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"token exchange failed: {resp.text[:200]}")
    tokens = resp.json()
    redir = RedirectResponse(url="/", status_code=302)
    # Set tokens as HttpOnly Secure cookies. Lambda@Edge reads id_token /
    # access_token cookies for structural validation. Production should
    # also set SameSite=Strict; demo uses Lax to allow OAuth redirect flow.
    cookie_kwargs = {"httponly": True, "secure": True, "samesite": "lax", "max_age": 3600}
    if "id_token" in tokens:
        redir.set_cookie("id_token", tokens["id_token"], **cookie_kwargs)
    if "access_token" in tokens:
        redir.set_cookie("access_token", tokens["access_token"], **cookie_kwargs)
    if "refresh_token" in tokens:
        redir.set_cookie("refresh_token", tokens["refresh_token"], httponly=True, secure=True,
                          samesite="lax", max_age=7 * 24 * 3600)
    return redir
