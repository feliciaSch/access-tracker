"""Username + password login. Passwords are hashed with bcrypt; logins get a signed JWT token."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import JWT_EXPIRES_MINUTES, JWT_SECRET
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user: User) -> str:
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def require_approver(user: User = Depends(current_user)) -> User:
    if user.role != "approver":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only approvers can change a request's status")
    return user
