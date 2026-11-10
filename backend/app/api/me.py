from fastapi import APIRouter, Depends

from app.api.identity import current_user

router = APIRouter()


@router.get("/me")
def me(identity: dict = Depends(current_user)) -> dict:
    """Protected route proving Cognito authentication works end to end."""
    return identity
