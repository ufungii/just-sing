"""Error envelope from contracts/error.example.json. Never include provider details."""
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def error_response(request: Request, status: int, code: str, message: str, retryable: bool = False):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "retryable": retryable,
        "request_id": request.headers.get("x-request-id", uuid.uuid4().hex)}})
