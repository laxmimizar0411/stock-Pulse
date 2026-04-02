#!/usr/bin/env python3
"""
Test DHAN API with provided credentials and list all response parameters.
Uses API key + secret for OAuth flow, or direct access token if set.

Usage:
  # Option A: Use access token from web.dhan.co (easiest)
  export DHAN_ACCESS_TOKEN="<24h token from web.dhan.co>"
  export DHAN_CLIENT_ID="<your numeric client id>"
  python scripts/dhan_api_test.py

  # Option B: OAuth with API key/secret (need Dhan Client ID for Step 1)
  export DHAN_API_KEY=c3f73cb5
  export DHAN_API_SECRET=multiagent-trader-ai
  export DHAN_CLIENT_ID="<your dhan client id from web.dhan.co>"
  python scripts/dhan_api_test.py   # Step 1: prints login URL
  # After browser login, get tokenId from redirect URL and:
  export DHAN_TOKEN_ID="<tokenId from redirect>"
  python scripts/dhan_api_test.py   # Step 3 + data tests
"""

import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv
import requests

load_dotenv()

# Base URLs
AUTH_BASE = "https://auth.dhan.co"
API_BASE = "https://api.dhan.co/v2"

# Sample NSE EQ security ID (e.g. 1333 = Reliance, 11536 = another scrip)
SAMPLE_NSE_EQ_ID = "1333"
SAMPLE_NSE_FNO_IDS = [49081, 49082]


def collect_keys(obj: Any, prefix: str = "") -> set[str]:
    """Recursively collect all keys from a nested dict/list structure."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(f"{prefix}{k}" if prefix else k)
            keys.update(collect_keys(v, f"{prefix}{k}."))
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        for item in obj[:3]:  # sample first 3
            keys.update(collect_keys(item, prefix))
    return keys


def get_access_token_via_oauth(api_key: str, api_secret: str, client_id: str) -> tuple[str, str] | None:
    """Step 1: Generate consent and print login URL. Step 3: Consume tokenId and return (access_token, dhanClientId)."""
    token_id = os.environ.get("DHAN_TOKEN_ID")
    if token_id:
        # Step 3: Consume consent
        r = requests.post(
            f"{AUTH_BASE}/app/consumeApp-consent",
            params={"tokenId": token_id},
            headers={"app_id": api_key, "app_secret": api_secret},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return (data["accessToken"], data["dhanClientId"])
    # Step 1: Generate consent
    r = requests.post(
        f"{AUTH_BASE}/app/generate-consent",
        params={"client_id": client_id},
        headers={"app_id": api_key, "app_secret": api_secret},
        timeout=15,
    )
    r.raise_for_status()
    out = r.json()
    consent_app_id = out.get("consentAppId")
    if not consent_app_id:
        print("Unexpected response:", out, file=sys.stderr)
        return None
    login_url = f"{AUTH_BASE}/login/consentApp-login?consentAppId={consent_app_id}"
    print("Step 1 done. Open this URL in a browser and log in:")
    print(login_url)
    print("After login you will be redirected. Copy the 'tokenId' from the redirect URL and run:")
    print('  export DHAN_TOKEN_ID="<tokenId>"')
    print("  python scripts/dhan_api_test.py")
    return None


def main() -> None:
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    client_id = os.environ.get("DHAN_CLIENT_ID")
    api_key = os.environ.get("DHAN_API_KEY")
    api_secret = os.environ.get("DHAN_API_SECRET")

    if not access_token or not client_id:
        if api_key and api_secret and client_id:
            result = get_access_token_via_oauth(api_key, api_secret, client_id)
            if result:
                access_token, client_id = result
            else:
                sys.exit(0)
        if not client_id:
            print("Set DHAN_CLIENT_ID (from web.dhan.co profile) and either DHAN_ACCESS_TOKEN or DHAN_TOKEN_ID.", file=sys.stderr)
            sys.exit(1)
        if not access_token:
            print("Get Access Token from web.dhan.co (My Profile → Access DhanHQ APIs) or complete OAuth with DHAN_TOKEN_ID.", file=sys.stderr)
            sys.exit(1)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": access_token,
        "client-id": str(client_id),
    }

    all_params: OrderedDict[str, set[str]] = OrderedDict()
    endpoints_tested = []

    # 1) Profile
    try:
        r = requests.get(f"{API_BASE}/profile", headers={k: v for k, v in headers.items() if k != "Content-Type"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        keys = collect_keys(data)
        all_params["GET /profile"] = keys
        endpoints_tested.append(("GET /profile", data))
    except Exception as e:
        all_params["GET /profile"] = set()
        endpoints_tested.append(("GET /profile", {"error": str(e)}))

    # 2) LTP
    try:
        body = {"NSE_EQ": [int(SAMPLE_NSE_EQ_ID)]}
        r = requests.post(f"{API_BASE}/marketfeed/ltp", headers=headers, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()
        keys = collect_keys(data)
        all_params["POST /marketfeed/ltp"] = keys
        endpoints_tested.append(("POST /marketfeed/ltp", data))
    except Exception as e:
        all_params["POST /marketfeed/ltp"] = set()
        endpoints_tested.append(("POST /marketfeed/ltp", {"error": str(e)}))

    # 3) OHLC
    try:
        body = {"NSE_EQ": [int(SAMPLE_NSE_EQ_ID)]}
        r = requests.post(f"{API_BASE}/marketfeed/ohlc", headers=headers, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()
        keys = collect_keys(data)
        all_params["POST /marketfeed/ohlc"] = keys
        endpoints_tested.append(("POST /marketfeed/ohlc", data))
    except Exception as e:
        all_params["POST /marketfeed/ohlc"] = set()
        endpoints_tested.append(("POST /marketfeed/ohlc", {"error": str(e)}))

    # 4) Quote (market depth)
    try:
        body = {"NSE_EQ": [int(SAMPLE_NSE_EQ_ID)]}
        r = requests.post(f"{API_BASE}/marketfeed/quote", headers=headers, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()
        keys = collect_keys(data)
        all_params["POST /marketfeed/quote"] = keys
        endpoints_tested.append(("POST /marketfeed/quote", data))
    except Exception as e:
        all_params["POST /marketfeed/quote"] = set()
        endpoints_tested.append(("POST /marketfeed/quote", {"error": str(e)}))

    # 5) Historical daily
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        body = {
            "securityId": SAMPLE_NSE_EQ_ID,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "fromDate": from_date.strftime("%Y-%m-%d"),
            "toDate": to_date.strftime("%Y-%m-%d"),
        }
        r = requests.post(f"{API_BASE}/charts/historical", headers=headers, json=body, timeout=15)
        r.raise_for_status()
        data = r.json()
        keys = set(data.keys())
        all_params["POST /charts/historical"] = keys
        endpoints_tested.append(("POST /charts/historical", data))
    except Exception as e:
        all_params["POST /charts/historical"] = set()
        endpoints_tested.append(("POST /charts/historical", {"error": str(e)}))

    # 6) Intraday
    try:
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=1)
        body = {
            "securityId": SAMPLE_NSE_EQ_ID,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "interval": "15",
            "fromDate": from_dt.strftime("%Y-%m-%d 09:15:00"),
            "toDate": to_dt.strftime("%Y-%m-%d 15:30:00"),
        }
        r = requests.post(f"{API_BASE}/charts/intraday", headers=headers, json=body, timeout=15)
        r.raise_for_status()
        data = r.json()
        keys = set(data.keys())
        all_params["POST /charts/intraday"] = keys
        endpoints_tested.append(("POST /charts/intraday", data))
    except Exception as e:
        all_params["POST /charts/intraday"] = set()
        endpoints_tested.append(("POST /charts/intraday", {"error": str(e)}))

    # Report
    print("\n" + "=" * 60)
    print("DHAN API TEST – Response parameters per endpoint")
    print("=" * 60)

    total_unique = set()
    for endpoint, keys in all_params.items():
        total_unique |= keys
        sorted_keys = sorted(keys)
        print(f"\n{endpoint}")
        print(f"  Count: {len(keys)} parameter(s)")
        print(f"  Parameters: {', '.join(sorted_keys) if sorted_keys else '(none or error)'}")

    print("\n" + "-" * 60)
    print(f"Total unique parameter names across all endpoints: {len(total_unique)}")
    print("All unique parameters:", ", ".join(sorted(total_unique)))
    print("\nSample responses (first 500 chars each):")
    for name, data in endpoints_tested:
        snippet = json.dumps(data, indent=2)[:500]
        print(f"\n{name}:\n{snippet}...")
    print("\nDone.")


def print_docs_summary() -> None:
    """Print parameter summary from DHAN API docs (no live call)."""
    docs_params = {
        "GET /profile": {"dhanClientId", "tokenValidity", "activeSegment", "ddpi", "mtf", "dataPlan", "dataValidity"},
        "POST /marketfeed/ltp": {"data", "status", "data.*.last_price"},
        "POST /marketfeed/ohlc": {"data", "status", "data.*.last_price", "data.*.ohlc.open", "data.*.ohlc.high", "data.*.ohlc.low", "data.*.ohlc.close"},
        "POST /marketfeed/quote": {
            "data", "status",
            "data.*.average_price", "data.*.buy_quantity", "data.*.sell_quantity",
            "data.*.depth.buy", "data.*.depth.sell", "data.*.depth.buy.quantity", "data.*.depth.buy.orders", "data.*.depth.buy.price",
            "data.*.depth.sell.quantity", "data.*.depth.sell.orders", "data.*.depth.sell.price",
            "data.*.last_price", "data.*.last_quantity", "data.*.last_trade_time",
            "data.*.lower_circuit_limit", "data.*.upper_circuit_limit", "data.*.net_change",
            "data.*.volume", "data.*.oi", "data.*.oi_day_high", "data.*.oi_day_low",
            "data.*.ohlc.open", "data.*.ohlc.close", "data.*.ohlc.high", "data.*.ohlc.low",
        },
        "POST /charts/historical": {"open", "high", "low", "close", "volume", "timestamp", "open_interest"},
        "POST /charts/intraday": {"open", "high", "low", "close", "volume", "timestamp", "open_interest"},
    }
    total = set()
    print("\n" + "=" * 60)
    print("DHAN API – Parameters from official documentation (no live call)")
    print("=" * 60)
    for endpoint, params in docs_params.items():
        total |= params
        print(f"\n{endpoint}: {len(params)} parameter(s)")
        print("  ", ", ".join(sorted(params)))
    print("\n" + "-" * 60)
    print(f"Total unique parameter names (from docs): {len(total)}")
    print("Run with DHAN_ACCESS_TOKEN + DHAN_CLIENT_ID to verify live.\n")


if __name__ == "__main__":
    if os.environ.get("DHAN_DOCS_ONLY"):
        print_docs_summary()
    else:
        main()
