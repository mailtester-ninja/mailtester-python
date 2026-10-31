"""Official Python client for the MailTester Ninja email verification API."""

from .client import (
    DEFAULT_BASE_URL,
    FREE_KEY,
    FindResult,
    MailTester,
    MailTesterError,
    MailTesterKeyError,
    MailTesterRateLimitError,
    VerificationResult,
    __version__,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "FREE_KEY",
    "FindResult",
    "MailTester",
    "MailTesterError",
    "MailTesterKeyError",
    "MailTesterRateLimitError",
    "VerificationResult",
    "__version__",
]
