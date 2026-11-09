from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.profiles import get_or_create_user


def current_user(db: Session = Depends(get_db)) -> User:
    return get_or_create_user(db)
