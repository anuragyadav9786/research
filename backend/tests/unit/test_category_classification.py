from data_pipeline.normalization.category_classification import classify_asset_class, classify_equity_style


def test_full_amfi_wording_equity():
    assert classify_asset_class("Equity Scheme - Large Cap Fund") == "Equity"
    assert classify_equity_style("Equity Scheme - Large Cap Fund") == "Large Cap"


def test_simplified_seed_wording_equity():
    assert classify_asset_class("Equity - Mid Cap") == "Equity"
    assert classify_equity_style("Equity - Mid Cap") == "Mid Cap"


def test_debt_category():
    assert classify_asset_class("Debt Scheme - Liquid Fund") == "Debt"
    assert classify_equity_style("Debt Scheme - Liquid Fund") is None


def test_hybrid_category():
    assert classify_asset_class("Hybrid Scheme - Aggressive Hybrid Fund") == "Hybrid"


def test_gold_category():
    assert classify_asset_class("Other Scheme - Gold ETF") == "Gold"


def test_other_scheme_index_fund_not_reclassified_as_equity():
    # AMFI's own "Other Scheme" bucket is respected as stated, not
    # silently reclassified into Equity just because index funds are
    # usually equity-heavy -- that would be guessing from the scheme's
    # likely composition, not its stated category.
    assert classify_asset_class("Other Scheme - Index Funds") == "Other"


def test_solution_oriented_is_other_not_guessed():
    assert classify_asset_class("Solution Oriented Schemes - Retirement Fund") == "Other"


def test_unrecognized_category_is_unclassified_not_guessed():
    assert classify_asset_class("Some Entirely New Category Nobody Has Seen") == "Unclassified"


def test_large_and_mid_cap_not_misread_as_plain_mid_cap():
    assert classify_equity_style("Equity Scheme - Large & Mid Cap Fund") == "Large & Mid Cap"
    assert classify_equity_style("Equity Scheme - Large and Mid Cap Fund") == "Large & Mid Cap"


def test_flexi_cap_and_multi_cap_distinct():
    assert classify_equity_style("Equity Scheme - Flexi Cap Fund") == "Flexi Cap"
    assert classify_equity_style("Equity Scheme - Multi Cap Fund") == "Multi Cap"


def test_elss_recognized():
    assert classify_equity_style("Equity Scheme - ELSS") == "ELSS"


def test_sectoral_thematic_recognized():
    assert classify_equity_style("Equity Scheme - Sectoral/Thematic Fund") == "Sectoral/Thematic"


def test_unrecognized_equity_style_is_other():
    assert classify_equity_style("Equity Scheme - Some New Style Nobody Has Seen") == "Other"
