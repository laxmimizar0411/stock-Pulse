"""
Test script for the comprehensive yfinance extractor.

Runs a live extraction against the yfinance API and prints a
field-by-field coverage report.

Usage:
    cd backend
    python -m tests.test_yfinance_comprehensive                  # Test RELIANCE
    python -m tests.test_yfinance_comprehensive --symbol TCS     # Test TCS
    python -m tests.test_yfinance_comprehensive --global         # Test global market data
    python -m tests.test_yfinance_comprehensive --all            # Test stock + global
"""

import asyncio
import sys
import os

# Ensure imports work from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from data_extraction.extractors.yfinance_comprehensive_extractor import (
    YFinanceComprehensiveExtractor,
)
from data_extraction.models.extraction_models import StockDataRecord


# ──────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────

def _header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _category(name: str, fields: dict, expected_fields: list) -> None:
    """Print a category's field coverage."""
    print(f"\n  ── {name} ──")
    found = 0
    for field_name in expected_fields:
        val = fields.get(field_name)
        if val is not None:
            found += 1
            # Truncate long values
            val_str = str(val)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            print(f"    ✅ {field_name:.<35s} {val_str}")
        else:
            print(f"    ❌ {field_name:.<35s} NULL")
    pct = (found / len(expected_fields) * 100) if expected_fields else 0
    print(f"  → {found}/{len(expected_fields)} fields ({pct:.0f}%)")
    return found, len(expected_fields)


# ──────────────────────────────────────────────────────────────────────
# Test: single stock extraction
# ──────────────────────────────────────────────────────────────────────

async def test_stock(symbol: str) -> None:
    _header(f"COMPREHENSIVE yfinance EXTRACTION: {symbol}")

    extractor = YFinanceComprehensiveExtractor()
    await extractor.initialize()

    print(f"\n  Extracting data for {symbol} (this may take 10-30 seconds)...")
    report = await extractor.extract_full_report(symbol)

    # Summary
    print(f"\n  Status:          {report['extraction_status']}")
    print(f"  Duration:        {report['duration_ms']}ms")
    print(f"  Fields:          {report['field_count']}/{report['total_possible']} ({report['coverage_pct']}%)")
    print(f"  Price history:   {report['price_history_length']} days")
    print(f"  Quarterly data:  {report['quarterly_results_count']} periods")
    print(f"  Annual data:     {report['annual_results_count']} periods")
    if report['error']:
        print(f"  Errors:          {report['error']}")

    # Detailed field-by-field breakdown
    data = report["data"]
    total_found = 0
    total_expected = 0

    # Category: Stock Master
    f, e = _category("Stock Master (Cat 1)", data["stock_master"], [
        "company_name", "sector", "industry", "website",
        "shares_outstanding", "market_cap_category",
    ])
    total_found += f; total_expected += e

    # Category: Price & Volume
    f, e = _category("Price & Volume (Cat 2)", data["price_volume"], [
        "date", "open", "high", "low", "close",
        "adjusted_close", "volume", "prev_close",
    ])
    total_found += f; total_expected += e

    # Category: Income Statement
    f, e = _category("Income Statement (Cat 4)", data["income_statement"], [
        "revenue", "operating_profit", "gross_profit", "net_profit",
        "ebitda", "ebit", "interest_expense", "tax_expense", "eps",
        "operating_margin", "gross_margin", "net_profit_margin",
    ])
    total_found += f; total_expected += e

    # Category: Balance Sheet
    f, e = _category("Balance Sheet (Cat 5)", data["balance_sheet"], [
        "total_assets", "total_equity", "total_debt", "long_term_debt",
        "short_term_debt", "cash_and_equivalents", "current_assets",
        "current_liabilities", "inventory", "receivables", "payables",
        "intangible_assets", "book_value_per_share",
    ])
    total_found += f; total_expected += e

    # Category: Cash Flow
    f, e = _category("Cash Flow (Cat 6)", data["cash_flow"], [
        "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
        "capital_expenditure", "free_cash_flow", "dividends_paid",
        "debt_repayment",
    ])
    total_found += f; total_expected += e

    # Category: Financial Ratios
    f, e = _category("Financial Ratios (Cat 7)", data["financial_ratios"], [
        "roe", "roa", "debt_to_equity", "current_ratio",
    ])
    total_found += f; total_expected += e

    # Category: Valuation
    f, e = _category("Valuation (Cat 8)", data["valuation"], [
        "market_cap", "enterprise_value", "pe_ratio", "pe_ratio_forward",
        "peg_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda", "ev_to_sales",
        "dividend_yield", "earnings_yield",
    ])
    total_found += f; total_expected += e

    # Category: Shareholding
    f, e = _category("Shareholding (Cat 9) — approximated", data["shareholding"], [
        "promoter_holding", "fii_holding",
    ])
    total_found += f; total_expected += e

    # Category: Corporate Actions
    f, e = _category("Corporate Actions (Cat 10)", data["corporate_actions"], [
        "dividend_per_share", "ex_dividend_date", "stock_split_ratio",
        "next_earnings_date",
    ])
    total_found += f; total_expected += e

    # Grand total
    grand_pct = (total_found / total_expected * 100) if total_expected else 0
    _header(f"TOTAL: {total_found}/{total_expected} fields ({grand_pct:.0f}%)")

    # Price history sample
    if report["price_history_length"] > 0:
        ph = data.get("price_history", report["data"].get("price_history", []))
        # price_history is stored in record.price_history, not in the to_dict() output by default
        # Check if it's in the report
        print(f"\n  Latest 3 price records:")
        for entry in (ph or [])[:3]:
            print(f"    {entry.get('date')}: O={entry.get('open')} H={entry.get('high')} "
                  f"L={entry.get('low')} C={entry.get('close')} V={entry.get('volume')}")

    # Quarterly results sample
    qr = data.get("quarterly_results", [])
    if qr:
        print(f"\n  Latest quarterly result ({qr[0].get('period', 'N/A')}):")
        for k, v in list(qr[0].items())[:6]:
            print(f"    {k}: {v}")

    await extractor.close()


# ──────────────────────────────────────────────────────────────────────
# Test: global market data
# ──────────────────────────────────────────────────────────────────────

async def test_global() -> None:
    _header("GLOBAL MARKET DATA (yfinance)")

    extractor = YFinanceComprehensiveExtractor()
    await extractor.initialize()

    print(f"\n  Fetching global tickers (S&P500, Nasdaq, USDINR, Crude, Gold, VIX, Nifty)...")
    data = await extractor.extract_global_market_data()

    expected = [
        "sp500_return_1d", "nasdaq_return_1d", "usdinr_rate",
        "crude_brent_price", "gold_price", "copper_price",
        "india_vix", "nifty_50_return_1m",
    ]

    found = 0
    for field_name in expected:
        val = data.get(field_name)
        if val is not None:
            found += 1
            print(f"    ✅ {field_name:.<35s} {val}")
        else:
            print(f"    ❌ {field_name:.<35s} NULL")

    pct = (found / len(expected) * 100) if expected else 0
    print(f"\n  → {found}/{len(expected)} fields ({pct:.0f}%)")

    await extractor.close()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    symbol = "RELIANCE"
    run_stock = True
    run_global = False

    for i, arg in enumerate(args):
        if arg == "--symbol" and i + 1 < len(args):
            symbol = args[i + 1]
        elif arg == "--global":
            run_global = True
            run_stock = False
        elif arg == "--all":
            run_global = True
            run_stock = True

    if run_stock:
        await test_stock(symbol)
    if run_global:
        await test_global()

    print(f"\n{'=' * 60}")
    print("  TEST COMPLETE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
