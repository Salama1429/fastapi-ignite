"""Simple JWT authentication helpers."""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status

from src.core.config import settings


def require_auth(authorization: str = Header(...)) -> Dict[str, Any]:
    """Validate a bearer token and return decoded claims."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALG],
        )
    except jwt.InvalidTokenError as exc:  # pragma: no cover - dependency handles
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    if "tenant_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant missing in token",
        )

    try:
        tenant_uuid = UUID(str(payload["tenant_id"]))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant identifier",
        ) from exc

    payload["tenant_id"] = str(tenant_uuid)
    return {"tenant_id": tenant_uuid, "claims": payload}
