from data_pipeline.sources.amfi.parser import RawNavRecord
from data_pipeline.validation.nav_validation import validate_navall_records


def _raw(**overrides) -> RawNavRecord:
    defaults = dict(
        scheme_code="900001",
        isin_growth="SAMPLE-ISIN-01",
        isin_div_reinvestment=None,
        scheme_name="Sample Fixture Fund - Direct - Growth",
        nav_raw="123.4567",
        date_raw="12-Sep-2026",
        amc_name="Sample Fixture Mutual Fund",
        category="Open Ended Schemes(Equity Scheme)",
        line_number=1,
    )
    defaults.update(overrides)
    return RawNavRecord(**defaults)


def test_accepts_a_well_formed_record():
    result = validate_navall_records([_raw()])
    assert len(result.accepted) == 1
    assert result.rejected == []
    accepted = result.accepted[0]
    assert accepted.nav == 123.4567
    assert accepted.nav_date.isoformat() == "2026-09-12"


def test_rejects_missing_scheme_code():
    result = validate_navall_records([_raw(scheme_code="")])
    assert result.accepted == []
    assert result.rejected[0].reason == "missing_scheme_code"


def test_rejects_na_nav():
    result = validate_navall_records([_raw(nav_raw="N.A.")])
    assert result.rejected[0].reason == "nav_not_available"


def test_rejects_non_numeric_nav():
    result = validate_navall_records([_raw(nav_raw="not-a-number")])
    assert result.rejected[0].reason == "invalid_nav_format"


def test_rejects_negative_and_zero_nav():
    assert validate_navall_records([_raw(nav_raw="-5.0")]).rejected[0].reason == "non_positive_nav"
    assert validate_navall_records([_raw(nav_raw="0")]).rejected[0].reason == "non_positive_nav"


def test_rejects_invalid_date_format():
    result = validate_navall_records([_raw(date_raw="2026/09/12")])
    assert result.rejected[0].reason == "invalid_date_format"


def test_rejects_duplicate_scheme_code_in_same_batch():
    result = validate_navall_records([_raw(), _raw()])
    assert len(result.accepted) == 1
    assert result.rejected[0].reason == "duplicate_in_batch"


def test_mixed_batch_counts_reconcile():
    records = [
        _raw(scheme_code="900001"),
        _raw(scheme_code="900002", nav_raw="N.A."),
        _raw(scheme_code=""),
        _raw(scheme_code="900003", date_raw="bad-date"),
    ]
    result = validate_navall_records(records)
    assert len(result.accepted) == 1
    assert len(result.rejected) == 3
    assert len(result.accepted) + len(result.rejected) == len(records)
