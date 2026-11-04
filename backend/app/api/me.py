from fastapi import APIRouter, Depends

from app.api.identity import gateway_identity

router = APIRouter()


@router.get("/me")
def me(identity: dict = Depends(gateway_identity)) -> dict:
    """Protected route proving Cognito authentication works end to end."""
    return identity
