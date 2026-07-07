from http import HTTPStatus

import pytest

from app.web.utils.metrics import (
    REFERER_COUNTER,
    increment_referer_counter,
    normalize_referer,
)


@pytest.mark.parametrize(
    "referer,expected",
    [
        (None, "none"),
        ("", "none"),
        (
            "https://auto-archiver.bellingcat.com/page?id=1",
            "https://auto-archiver.bellingcat.com",
        ),
        ("http://localhost:8081/x", "http://localhost:8081"),
        ("chrome-extension://abcdef/popup.html", "chrome-extension://abcdef"),
        ("not-a-valid-referer", "other"),
        ("/relative/path", "other"),
    ],
)
def test_normalize_referer(referer, expected):
    assert normalize_referer(referer) == expected


def test_increment_referer_counter():
    def value_for(origin: str) -> float:
        return (
            REFERER_COUNTER.labels(referer=origin)._value.get()  # type: ignore[attr-defined]
        )

    before = value_for("https://example.net")
    increment_referer_counter("https://example.net/some/path?q=1")
    increment_referer_counter("https://example.net/another")
    assert value_for("https://example.net") == before + 2

    before_none = value_for("none")
    increment_referer_counter(None)
    assert value_for("none") == before_none + 1


def test_referer_counter_via_middleware(client_with_token):
    # any request flows through the logging middleware, which records the
    # normalized referer; scrape /metrics (token-protected) to verify it.
    r = client_with_token.get(
        "/health",
        headers={"Referer": "https://referer-test.example/dashboard?x=1"},
    )
    assert r.status_code == HTTPStatus.OK

    metrics = client_with_token.get("/metrics")
    assert metrics.status_code == HTTPStatus.OK
    assert (
        'referer_total{referer="https://referer-test.example"} 1.0'
        in metrics.text
    )
