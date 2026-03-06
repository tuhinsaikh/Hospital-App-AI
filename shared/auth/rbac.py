"""
RBAC (Role-Based Access Control) — shared across all services.

Roles:
  super_admin  — Platform operator, can onboard/manage all hospitals
  hospital_admin — Hospital-level admin, manages own hospital only
  staff        — Hospital staff (doctors/nurses), read-only access
  (end_user is handled separately by the end-user app)
"""
from enum import Enum
from functools import wraps
from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from shared.auth.jwt_handler import decode_token

bearer_scheme = HTTPBearer()


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"
    STAFF = "staff"

    # Hierarchy: super_admin > hospital_admin > staff
    @classmethod
    def hierarchy(cls) -> List["Role"]:
        return [cls.SUPER_ADMIN, cls.HOSPITAL_ADMIN, cls.STAFF]

    def has_permission_for(self, required: "Role") -> bool:
        """Returns True if this role meets or exceeds the required role."""
        hierarchy = Role.hierarchy()
        return hierarchy.index(self) <= hierarchy.index(required)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency — extracts and validates JWT, returns payload dict."""
    payload = decode_token(credentials.credentials)
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity.",
        )
    return payload


def require_role(*roles: Role):
    """
    FastAPI dependency factory — ensures the authenticated user has one of the given roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(Role.SUPER_ADMIN))])
    """
    def dependency(user: dict = Depends(get_current_user)):
        user_role_str = user.get("role", "")
        try:
            user_role = Role(user_role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unknown role: {user_role_str}",
            )
        if not any(user_role.has_permission_for(r) for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required: {[r.value for r in roles]}",
            )
        return user
    return dependency
