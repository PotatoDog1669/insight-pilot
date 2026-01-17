"""Standardized error codes and handling for insight-pilot."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests


class ErrorCode(str, Enum):
    """Standardized error codes for agent consumption."""

    # Project errors
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_ALREADY_EXISTS = "PROJECT_ALREADY_EXISTS"
    INVALID_PROJECT_STATE = "INVALID_PROJECT_STATE"

    # Input errors
    NO_INPUT_FILES = "NO_INPUT_FILES"
    NO_ITEMS_FILE = "NO_ITEMS_FILE"
    INVALID_INPUT_FORMAT = "INVALID_INPUT_FORMAT"
    MISSING_REQUIRED_ARG = "MISSING_REQUIRED_ARG"
    NO_KEYWORDS = "NO_KEYWORDS"

    # Source errors
    INVALID_SOURCE = "INVALID_SOURCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

    # Network errors
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"

    # Download errors
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    INVALID_PDF = "INVALID_PDF"
    ACCESS_DENIED = "ACCESS_DENIED"

    # Conversion errors
    CONVERSION_FAILED = "CONVERSION_FAILED"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"

    # System errors
    FILE_WRITE_ERROR = "FILE_WRITE_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNKNOWN = "UNKNOWN"


# Define which errors are retryable
RETRYABLE_ERRORS = {
    ErrorCode.NETWORK_ERROR,
    ErrorCode.RATE_LIMITED,
    ErrorCode.TIMEOUT,
    ErrorCode.DOWNLOAD_FAILED,
    ErrorCode.API_ERROR,
}


@dataclass
class SkillError(Exception):
    """Structured error for skill operations."""

    message: str
    code: ErrorCode = ErrorCode.UNKNOWN
    details: Optional[dict] = field(default=None)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_ERRORS

    def to_dict(self) -> dict:
        return {
            "status": "error",
            "message": self.message,
            "error_code": self.code.value,
            "retryable": self.retryable,
            "details": self.details or {},
        }


def classify_request_error(exc: Exception) -> ErrorCode:
    """Classify a requests exception into an error code."""
    if isinstance(exc, requests.Timeout):
        return ErrorCode.TIMEOUT
    if isinstance(exc, requests.HTTPError):
        if hasattr(exc, "response") and exc.response is not None:
            if exc.response.status_code == 429:
                return ErrorCode.RATE_LIMITED
            if exc.response.status_code in {401, 403}:
                return ErrorCode.ACCESS_DENIED
            if exc.response.status_code >= 500:
                return ErrorCode.API_ERROR
        return ErrorCode.NETWORK_ERROR
    if isinstance(exc, requests.RequestException):
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.UNKNOWN
