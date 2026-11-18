from typing import Any

from fastapi.responses import JSONResponse

from app.logging_config import request_id_var


class AppError(Exception):
    """An error that maps directly onto the API error envelope."""

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: list[Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


def error_response(status_code: int, code: str, message: str, details: list[Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": request_id_var.get(),
            }
        },
    )
