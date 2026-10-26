import io
import json
import os
import urllib.error

import pytest

from mailtester_ninja import (
    MailTester,
    MailTesterError,
    MailTesterKeyError,
    MailTesterRateLimitError,
    VerificationResult,
)

OK = {"code": "ok", "message": "Accepted", "domain": "apple.com", "mx": "mx-in.g.apple.com",
      "connections": 1, "limit": 100000, "rate": 1, "email": "info@apple.com", "user": "Info"}


def fake(replies, calls=None):
    replies = list(replies)

    def _get(self, email):
        if calls is not None:
            calls.append(email)
        return replies.pop(0) if len(replies) > 1 else replies[0]
    return _get


def test_verify_returns_result(monkeypatch):
    monkeypatch.setattr(MailTester, "_get", fake([(200, json.dumps(OK))]))
    r = MailTester("sub_1").verify("info@apple.com")
    assert isinstance(r, VerificationResult)
    assert r.code == "ok" and r.message == "Accepted" and r.is_valid
    assert r.limit == 100000 and r.raw["mx"] == "mx-in.g.apple.com"


def test_key_handling(monkeypatch):
    monkeypatch.delenv("MAILTESTER_KEY", raising=False)
    assert MailTester().key == "free" and MailTester().is_free
    assert MailTester("{sub_abc}").key == "sub_abc"
    assert MailTester("mtf_x").is_free and not MailTester("sub_x").is_free
    monkeypatch.setenv("MAILTESTER_KEY", "sub_env")
    assert MailTester().key == "sub_env"


def test_request_url_and_headers(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["accept"] = req.get_header("Accept")
        return Resp(json.dumps(OK).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    MailTester("sub_1").verify(" info@apple.com ")
    assert seen["url"] == "https://happy.mailtester.ninja/ninja?email=info%40apple.com&key=sub_1"
    assert seen["accept"] == "application/json"


def test_http_error_body_is_read(monkeypatch):
    def urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"Missing email param"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(MailTesterError) as e:
        MailTester("sub_1").verify("")
    assert e.value.status == 403 and e.value.message == "Missing email param"


def test_network_error(monkeypatch):
    def urlopen(req, timeout=None):
        raise urllib.error.URLError("unreachable")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(MailTesterError, match="Network error"):
        MailTester("sub_1").verify("a@b.com")


def test_invalid_key(monkeypatch):
    body = dict(OK, code="--", message="Invalid Key", domain=None, limit=0)
    monkeypatch.setattr(MailTester, "_get", fake([(200, json.dumps(body))]))
    with pytest.raises(MailTesterKeyError):
        MailTester("bad").verify("info@apple.com")


def test_free_limit(monkeypatch):
    body = dict(OK, code="--", message="Free API: one request every 30 s, retry in 29 s. Unlimited speed: https://mailtester.ninja/verify-emails-unlimited/")
    monkeypatch.setattr(MailTester, "_get", fake([(429, json.dumps(body))]))
    with pytest.raises(MailTesterRateLimitError) as e:
        MailTester("free").verify("info@apple.com")
    assert e.value.retry_after == 29 and e.value.status == 429


def test_paid_rate_limit_plain_text(monkeypatch):
    monkeypatch.setattr(MailTester, "_get", fake([(429, "Too Many Requests - Your rate is now 25")]))
    with pytest.raises(MailTesterRateLimitError) as e:
        MailTester("sub_1").verify("a@b.com")
    assert e.value.retry_after is None and "Too Many Requests" in e.value.message


def test_is_deliverable(monkeypatch):
    monkeypatch.setattr(MailTester, "_get", fake([(200, json.dumps(dict(OK, code="ko", message="Rejected")))]))
    assert MailTester("sub_1").is_deliverable("a@b.com") is False


def test_verify_many_continues_after_errors(monkeypatch):
    calls = []
    replies = [(200, json.dumps(OK)), (403, "Missing email param"), (200, json.dumps(dict(OK, code="mb", message="Catch-All")))]
    monkeypatch.setattr(MailTester, "_get", fake(replies, calls))
    out = list(MailTester("sub_1").verify_many(["info@apple.com", "  ", "x@y.com", "c@d.com"], delay=0))
    assert [e for e, _, _ in out] == ["info@apple.com", "x@y.com", "c@d.com"]
    assert out[0][1].code == "ok" and isinstance(out[1][2], MailTesterError) and out[2][1].message == "Catch-All"


def test_verify_many_retries_after_free_limit(monkeypatch):
    limited = dict(OK, code="--", message="Free API: one request every 30 s, retry in 0 s.")
    monkeypatch.setattr(MailTester, "_get", fake([(429, json.dumps(limited)), (200, json.dumps(OK))]))
    monkeypatch.setattr("time.sleep", lambda s: None)
    out = list(MailTester("free").verify_many(["info@apple.com"], delay=0))
    assert len(out) == 1 and out[0][1].code == "ok"


@pytest.mark.skipif(os.environ.get("MAILTESTER_LIVE") != "1", reason="live test: set MAILTESTER_LIVE=1")
def test_live_free_tier():
    r = MailTester(os.environ.get("MAILTESTER_KEY") or "free").verify("info@apple.com")
    assert r.code in ("ok", "ko", "mb")
