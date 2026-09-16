import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApplicationError
from app.models import Profile
from app.schemas import Login, ProfileOut, SessionOut, Signup

bearer = HTTPBearer(auto_error=False)


def sign_token(settings: Settings, subject: UUID, purpose: str, minutes: int = 900) -> str:
    return jwt.encode(
        {
            "sub": str(subject),
            "purpose": purpose,
            "iss": "linktoon",
            "aud": "linktoon-api",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=minutes),
        },
        settings.local_auth_secret,
        algorithm="HS256",
    )


def verify_token(settings: Settings, token: str, purpose: str) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.local_auth_secret,
            algorithms=["HS256"],
            audience="linktoon-api",
            issuer="linktoon",
            options={"require": ["sub", "purpose", "exp", "iat"]},
        )
        if claims["purpose"] != purpose:
            raise ValueError("Invalid purpose")
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ApplicationError("Session expired or invalid", "unauthorized", 401) from exc


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}:{digest.hex()}"


def require_local(settings: Settings) -> None:
    if settings.auth_mode != "local" or settings.app_env == "production":
        raise ApplicationError("Use Supabase Auth to sign in", "local_auth_disabled", 404)


def create_session(user: Profile, settings: Settings) -> SessionOut:
    return SessionOut(
        access_token=sign_token(settings, user.id, "session"), user=ProfileOut.model_validate(user)
    )


def signup(db: Session, settings: Settings, data: Signup) -> SessionOut:
    require_local(settings)
    user = Profile(
        email=str(data.email).lower(),
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApplicationError("Email is already registered", "email_exists", 409) from exc
    return create_session(user, settings)


def login(db: Session, settings: Settings, data: Login) -> SessionOut:
    require_local(settings)
    user = db.scalar(select(Profile).where(Profile.email == str(data.email).lower()))
    stored = user.password_hash if user and user.password_hash else hash_password("dummy-password")
    if not hmac.compare_digest(stored, hash_password(data.password, stored.split(":")[0])):
        raise ApplicationError("Email or password is incorrect", "invalid_credentials", 401)
    if not user or not user.password_hash:
        raise ApplicationError("Email or password is incorrect", "invalid_credentials", 401)
    return create_session(user, settings)


def supabase_identity(token: str, settings: Settings) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code in (401, 403):
            raise ApplicationError("Session expired or invalid", "unauthorized", 401)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        UUID(payload["id"])
        if not payload.get("email"):
            raise ValueError("An email identity is required")
        return payload
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ApplicationError(
            "Authentication service is unavailable", "auth_unavailable", 503
        ) from exc


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Profile:
    if not credentials:
        raise ApplicationError("Sign in to continue", "unauthorized", 401)
    if settings.auth_mode == "local":
        subject = verify_token(settings, credentials.credentials, "session")
        user = db.get(Profile, subject)
        if not user:
            raise ApplicationError("User not found", "unauthorized", 401)
        return user
    identity = supabase_identity(credentials.credentials, settings)
    subject = UUID(identity["id"])
    user = db.get(Profile, subject)
    if not user:
        user = Profile(
            id=subject,
            email=identity["email"].lower(),
            display_name=(
                identity.get("user_metadata", {}).get("display_name")
                or identity["email"].split("@")[0]
            )[:80],
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.get(Profile, subject)
            if not existing:
                raise ApplicationError(
                    "Account identity conflict", "identity_conflict", 409
                ) from None
            user = existing
    return user


DB = Annotated[Session, Depends(get_db)]
User = Annotated[Profile, Depends(current_user)]
Config = Annotated[Settings, Depends(get_settings)]
