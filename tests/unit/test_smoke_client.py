from __future__ import annotations

from io import BytesIO
from typing import NoReturn
from urllib.error import HTTPError
from urllib.request import Request
from uuid import UUID

import pytest
from scripts import smoke


class FakeResponse(BytesIO):
    status = 200


def test_smoke_request_has_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def open_request(request: Request, *, timeout: int) -> FakeResponse:
        assert UUID(request.get_header("X-correlation-id"))
        assert timeout == 10
        return FakeResponse(b'{"status":"ready"}')

    monkeypatch.setattr(smoke, "urlopen", open_request)
    assert smoke.call("/health/ready") == {"status": "ready"}


@pytest.mark.parametrize("body", [b"[1,2]", b'"sensitive-value"', b"invalid sensitive-value"])
def test_smoke_invalid_responses_are_redacted(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    monkeypatch.setattr(smoke, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))
    with pytest.raises(RuntimeError, match="correlation_id=") as raised:
        smoke.call("/health/ready")
    assert "sensitive-value" not in str(raised.value)


def test_smoke_expected_rejection_is_not_silently_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke, "urlopen", lambda *_args, **_kwargs: FakeResponse(b"{}"))
    with pytest.raises(RuntimeError, match="Unexpected HTTP 200"):
        smoke.call("/api/v1/tasks/test/attempts", {}, expected_status=409)


def test_smoke_http_errors_do_not_expose_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise HTTPError("http://example.test", 500, "failure", None, BytesIO(b"sensitive-value"))

    monkeypatch.setattr(smoke, "urlopen", fail)
    with pytest.raises(RuntimeError, match="correlation_id=") as raised:
        smoke.call("/health/ready")
    assert "sensitive-value" not in str(raised.value)
