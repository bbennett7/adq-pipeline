import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer = HTTPBearer()


async def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> None:
    if not hmac.compare_digest(credentials.credentials, get_settings().pipeline_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
