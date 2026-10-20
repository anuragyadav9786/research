"""Unit tests for the AMFI portal NAV-history client/parser — the real
confirmed response shape (see portal_history.py's module docstring; a
real sample was captured and parsed in this session, 8,448 of 8,556 real
rows accepted)."""
import httpx
import pytest

from data_pipeline.sources.amfi.portal_history import (
    PortalHistoryFetchError,
    fetch_portal_history_for_date,
    parse_portal_history_navs,
)

REAL_SHAPE_SAMPLE = """Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

Open Ended Schemes ( Equity Scheme - Multi Cap Fund )


Aditya Birla Sun Life Mutual Fund
148921;Aditya Birla Sun Life Multi-Cap Fund-Direct Growth;Direct Plan;GROWTH;INF209KB1Y49;;21.73;19-Oct-2026
148920;Aditya Birla Sun Life Multi-Cap Fund-Direct IDCW Payout;Direct Plan;IDCW Payout;INF209KB1Y56;;17.88;19-Oct-2026
148918;Aditya Birla Sun Life Multi-Cap Fund-Regular Growth;Regular Plan;Growth;INF209KB1Y30;;20.21;19-Oct-2026
"""


def test_parses_real_confirmed_shape():
    navs = parse_portal_history_navs(REAL_SHAPE_SAMPLE)
    assert navs == {"148921": 21.73, "148920": 17.88, "148918": 20.21}


def test_ignores_category_and_amc_header_lines():
    navs = parse_portal_history_navs(REAL_SHAPE_SAMPLE)
    # Only the 3 real data rows should appear — header/category/AMC/blank
    # lines must never be mistaken for a scheme row.
    assert len(navs) == 3


def test_skips_rows_with_non_positive_or_unparseable_nav():
    text = (
        "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date\n"
        "111;Some Fund;Regular Plan;Growth;ISIN1;;0.0;19-Oct-2026\n"
        "222;Some Fund;Regular Plan;Growth;ISIN2;;-5.0;19-Oct-2026\n"
        "333;Some Fund;Regular Plan;Growth;ISIN3;;N/A;19-Oct-2026\n"
        "444;Some Fund;Regular Plan;Growth;ISIN4;;12.34;19-Oct-2026\n"
    )
    assert parse_portal_history_navs(text) == {"444": 12.34}


def test_empty_text_returns_empty_dict():
    assert parse_portal_history_navs("") == {}


def test_fetch_raises_on_timeout(monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx, "get", _raise_timeout)
    with pytest.raises(PortalHistoryFetchError):
        from datetime import date

        fetch_portal_history_for_date(date(2026, 10, 19))


def test_fetch_raises_on_empty_body(monkeypatch):
    class _FakeResponse:
        text = "   "

        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(PortalHistoryFetchError):
        from datetime import date

        fetch_portal_history_for_date(date(2026, 10, 19))
