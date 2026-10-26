"""Official Python client for the MailTester Ninja email verification API.

https://mailtester.ninja/api/
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, Optional

__version__ = "1.0.0"

DEFAULT_BASE_URL = "https://happy.mailtester.ninja"
FREE_KEY = "free"  # keyless free tier: 10 checks a day per IP, one request every 30 seconds


class MailTesterError(Exception):
    """Any error returned by the API or the network. Never a verdict: do not drop the address on it."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class MailTesterKeyError(MailTesterError):
    """The key is invalid or disabled (``code`` "--")."""


class MailTesterRateLimitError(MailTesterError):
    """A limit was reached (HTTP 429). ``retry_after`` is set when the API says how long to wait."""

    def __init__(self, message: str, retry_after: Optional[int] = None) -> None:
        super().__init__(message, 429)
        self.retry_after = retry_after


@dataclass(frozen=True)
class VerificationResult:
    """Verdict for one address.

    ``code``: "ok" valid and deliverable, "ko" invalid, "mb" uncertain (catch-all or not probeable).
    ``message``: human-readable label (Accepted, Rejected, Catch-All, No MX, Disposable, Timeout...).
    """

    code: str
    message: str
    email: str
    user: str = ""
    domain: Optional[str] = None
    mx: str = ""
    connections: int = 0
    limit: int = 0
    rate: int = 0
    raw: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_valid(self) -> bool:
        return self.code == "ok"

    @property
    def is_invalid(self) -> bool:
        return self.code == "ko"

    @property
    def is_uncertain(self) -> bool:
        return self.code == "mb"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        def as_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        return cls(
            code=str(data.get("code", "")),
            message=str(data.get("message", "")),
            email=str(data.get("email", "")),
            user=str(data.get("user") or ""),
            domain=data.get("domain"),
            mx=str(data.get("mx") or ""),
            connections=as_int(data.get("connections")),
            limit=as_int(data.get("limit")),
            rate=as_int(data.get("rate")),
            raw=dict(data),
        )


def _retry_after(message: str) -> Optional[int]:
    match = re.search(r"retry in (\d+)\s*s", message, re.IGNORECASE)
    return int(match.group(1)) if match else None


class MailTester:
    """Client for the MailTester Ninja API.

    ``key``: "free" (no signup), a free token "mtf_..." from
    https://mailtester.ninja/free-email-verification-api/, or a subscription key "sub_...".
    Defaults to the MAILTESTER_KEY environment variable, then to "free".
    """

    def __init__(self, key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0) -> None:
        raw_key = key if key is not None else (os.environ.get("MAILTESTER_KEY") or FREE_KEY)
        self.key = raw_key.strip().strip("{}")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def is_free(self) -> bool:
        """True on the free tier ("free" or a free token), limited to one request every 30 seconds."""
        return self.key == FREE_KEY or self.key.startswith("mtf_")

    def _get(self, email: str) -> "tuple[int, str]":
        query = urllib.parse.urlencode({"email": email.strip(), "key": self.key})
        request = urllib.request.Request(
            f"{self.base_url}/ninja?{query}",
            headers={"Accept": "application/json", "User-Agent": f"mailtester-ninja-python/{__version__}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as err:
            reason = getattr(err, "reason", err)
            raise MailTesterError(f"Network error: {reason}") from err

    def verify(self, email: str) -> VerificationResult:
        """Verify one address. Returns a verdict, raises a MailTesterError when there is none."""
        status, text = self._get(email)
        try:
            body = json.loads(text)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            body = None
        message = str(body.get("message", "")) if body else text.strip()
        if status == 429:
            raise MailTesterRateLimitError(message, _retry_after(message))
        if status >= 400:
            raise MailTesterError(message or f"HTTP {status}", status)
        if body is None:
            raise MailTesterError("Unexpected response from the API", status)
        if body.get("code") == "--":
            raise MailTesterKeyError(message, status)
        return VerificationResult.from_dict(body)

    def is_deliverable(self, email: str) -> bool:
        """True only when the address is clearly valid and deliverable ("ok")."""
        return self.verify(email).is_valid

    def verify_many(
        self, emails: Iterable[str], delay: Optional[float] = None, retry_on_limit: bool = True
    ) -> Iterator["tuple[str, Optional[VerificationResult], Optional[MailTesterError]]"]:
        """Verify a list one address at a time, pacing the calls to respect the rate limit.

        Yields ``(email, result, None)`` or ``(email, None, error)`` for each non-empty address.
        ``delay`` defaults to 30 seconds on the free tier and 1 second with a paid key.
        """
        pause = delay if delay is not None else (30.0 if self.is_free else 1.0)
        first = True
        for raw in emails:
            email = str(raw).strip()
            if not email:
                continue
            if not first and pause > 0:
                time.sleep(pause)
            first = False
            try:
                yield email, self.verify(email), None
            except MailTesterRateLimitError as err:
                if retry_on_limit and err.retry_after is not None:
                    time.sleep(err.retry_after + 1)
                    try:
                        yield email, self.verify(email), None
                    except MailTesterError as err2:
                        yield email, None, err2
                else:
                    yield email, None, err
            except MailTesterError as err:
                yield email, None, err
