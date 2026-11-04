from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """Build an HTTPException whose body follows the shared error shape."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
