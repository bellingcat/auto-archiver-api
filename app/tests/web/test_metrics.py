from http import HTTPStatus

import pytest

from app.web.utils.metrics import (
    _REFERER_MAX_ORIGINS,
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


def test_increment_referer_counter_cardinality_cap():
    """Once _REFERER_MAX_ORIGINS distinct origins are known, new ones map to 'other'."""
    # Fill _referer_seen to the cap with synthetic origins (avoid polluting
    # the real seen-set by working with a temporary monkeypatched copy).
    import app.web.utils.metrics as m

    original_seen = m._referer_seen.copy()
    try:
        m._referer_seen.clear()
        for i in range(_REFERER_MAX_ORIGINS):
            m._referer_seen.add(f"https://origin-{i}.example")

        def value_for(label: str) -> float:
            return REFERER_COUNTER.labels(referer=label)._value.get()  # type: ignore[attr-defined]

        before_other = value_for("other")
        # A brand-new origin beyond the cap must be counted as "other"
        increment_referer_counter("https://brand-new-beyond-cap.example/page")
        assert value_for("other") == before_other + 1
        assert "https://brand-new-beyond-cap.example" not in m._referer_seen
    finally:
        m._referer_seen.clear()
        m._referer_seen.update(original_seen)


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
