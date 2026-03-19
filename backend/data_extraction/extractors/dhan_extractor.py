"""
Dhan API Extractor for Indian Stock Market Data
Implements data extraction via DhanHQ REST API v2 with rate limiting,
retry logic, comprehensive logging, and security ID mapping.

API Documentation: https://dhanhq.co/docs/v2/
"""

import asyncio
import aiohttp
import csv
import io
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import os

logger = logging.getLogger(__name__)


class ExtractionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    RETRYING = "retrying"


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


@dataclass
class APIMetrics:
    """Tracks API call metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retry_count: int = 0
    rate_limit_hits: int = 0
    total_latency_ms: float = 0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0
    last_request_time: Optional[datetime] = None
    errors: List[Dict] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0
        return (self.successful_requests / self.total_requests) * 100

    def to_dict(self) -> Dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "retry_count": self.retry_count,
            "rate_limit_hits": self.rate_limit_hits,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float('inf') else 0,
            "max_latency_ms": round(self.max_latency_ms, 2),
            "success_rate": round(self.success_rate, 2),
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
            "recent_errors": self.errors[-10:]
        }


@dataclass
class ExtractionResult:
    """Result of an extraction operation"""
    status: ExtractionStatus
    symbol: str
    data: Optional[Dict] = None
    error: Optional[str] = None
    retries: int = 0
    latency_ms: float = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "symbol": self.symbol,
            "data": self.data,
            "error": self.error,
            "retries": self.retries,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp.isoformat()
        }


# ── NSE Symbol → Dhan Security ID mapping ──────────────────────────────
# This mapping covers NIFTY 50, NIFTY Next 50 and popular mid/small-cap stocks.
# The security IDs are Dhan's internal numeric identifiers for NSE_EQ instruments.
# The map is loaded once at import time; at runtime we also attempt to refresh
# via the /v2/instrument/NSE_EQ CSV endpoint.

SYMBOL_TO_SECURITY_ID: Dict[str, str] = {
    # NIFTY 50
    "RELIANCE": "2885",
    "TCS": "11536",
    "HDFCBANK": "1333",
    "INFY": "1594",
    "ICICIBANK": "4963",
    "HINDUNILVR": "1394",
    "SBIN": "3045",
    "BHARTIARTL": "10604",
    "KOTAKBANK": "1922",
    "ITC": "1660",
    "LT": "11483",
    "AXISBANK": "5900",
    "BAJFINANCE": "317",
    "ASIANPAINT": "236",
    "MARUTI": "10999",
    "HCLTECH": "7229",
    "WIPRO": "3787",
    "ULTRACEMCO": "11532",
    "TITAN": "3506",
    "NESTLEIND": "17963",
    "SUNPHARMA": "3411",
    "BAJAJFINSV": "16669",
    "ONGC": "2475",
    "NTPC": "11630",
    "POWERGRID": "14977",
    "M&M": "2031",
    "TATASTEEL": "3499",
    "ADANIENT": "25",
    "TECHM": "13538",
    "JSWSTEEL": "11723",
    "TATAMOTOR": "3456",
    "INDUSINDBK": "5258",
    "COALINDIA": "20374",
    "HINDALCO": "1363",
    "GRASIM": "1232",
    "ADANIPORTS": "15083",
    "DRREDDY": "881",
    "APOLLOHOSP": "157",
    "CIPLA": "694",
    "EICHERMOT": "910",
    "BPCL": "526",
    "DIVISLAB": "10940",
    "BRITANNIA": "547",
    "HEROMOTOCO": "1348",
    "SBILIFE": "21808",
    "HDFCLIFE": "467",
    "TATACONSUM": "3432",
    "BAJAJ-AUTO": "16770",
    "SHRIRAMFIN": "4306",
    "LTIM": "17818",
    # NIFTY Next 50
    "ADANIGREEN": "25945",
    "AMBUJACEM": "151",
    "BANKBARODA": "4668",
    "BEL": "383",
    "BERGEPAINT": "404",
    "BOSCHLTD": "2181",
    "CANBK": "10794",
    "CHOLAFIN": "685",
    "COLPAL": "15141",
    "DLF": "14732",
    "DMART": "21614",
    "GAIL": "4717",
    "GODREJCP": "10099",
    "HAVELLS": "17971",
    "ICICIGI": "21770",
    "ICICIPRULI": "18652",
    "IDEA": "14366",
    "INDHOTEL": "1512",
    "INDIGO": "11195",
    "IOC": "1624",
    "IRCTC": "27748",
    "JINDALSTEL": "6994",
    "JUBLFOOD": "18096",
    "LTF": "24948",
    "LUPIN": "10440",
    "MARICO": "4067",
    "MCDOWELL-N": "10447",
    "MOTHERSON": "16896",
    "MUTHOOTFIN": "23650",
    "NAUKRI": "13751",
    "NHPC": "2099",
    "OFSS": "10738",
    "PAGEIND": "14413",
    "PAYTM": "35999",
    "PFC": "14299",
    "PIDILITIND": "2664",
    "PNB": "10666",
    "POLYCAB": "24781",
    "RECLTD": "15355",
    "SAIL": "2963",
    "SBICARD": "27837",
    "SRF": "3273",
    "TATAELXSI": "3448",
    "TATAPOWER": "3426",
    "TORNTPHARM": "3518",
    "TRENT": "3527",
    "UPL": "11287",
    "VEDL": "3063",
    "VBL": "14439",
    "ZOMATO": "36458",
    # Popular Mid-cap / Small-cap
    "AUROPHARMA": "275",
    "BANDHANBNK": "22525",
    "CANFINHOME": "583",
    "CROMPTON": "17094",
    "CUMMINSIND": "793",
    "DEEPAKNTR": "14767",
    "ESCORTS": "958",
    "EXIDEIND": "676",
    "FEDERALBNK": "1023",
    "GLENMARK": "7406",
    "GMRINFRA": "13528",
    "HINDPETRO": "1406",
    "IBULHSGFIN": "30125",
    "IDFCFIRSTB": "11184",
    "IEX": "23187",
    "IRFC": "27274",
    "KALYANKJIL": "37809",
    "LALPATHLAB": "16218",
    "LICHSGFIN": "1997",
    "MANAPPURAM": "4836",
    "MRF": "2277",
    "NAM-INDIA": "18568",
    "NATIONALUM": "6364",
    "NMDC": "15332",
    "OBEROIRLTY": "20242",
    "PERSISTENT": "18365",
    "PETRONET": "11351",
    "PIIND": "11969",
    "PVRINOX": "13147",
    "RAMCOCEM": "2043",
    "RBLBANK": "18391",
    "SUNTV": "13685",
    "TATACOMM": "3429",
    "TATACHEM": "3405",
    "THERMAX": "3483",
    "TORNTPOWER": "13786",
    "TVSMOTOR": "8479",
    "UNIONBANK": "11431",
    "UBL": "16713",
    "VOLTAS": "3718",
    "WHIRLPOOL": "18011",
    "ZEEL": "3812",
    "ZYDUSLIFE": "7929",
}


class DhanAPIExtractor:
    """
    Dhan API Extractor with comprehensive error handling, retry mechanism,
    rate limiting, and monitoring capabilities.

    Authentication:
        Every request requires two headers:
        - access-token: JWT access token (valid ~24h)
        - client-id: Dhan client ID (numeric string)

    API Endpoints used:
        POST /v2/marketfeed/ltp    – Last Traded Price (up to 1000 instruments)
        POST /v2/marketfeed/ohlc   – OHLC + LTP
        POST /v2/marketfeed/quote  – Full quote (depth + OHLC + OI + volume)
        POST /v2/charts/historical – Daily OHLC candles
    """

    BASE_URL = "https://api.dhan.co"

    # Rate limits (conservative)
    MAX_REQUESTS_PER_SECOND = 20
    MAX_REQUESTS_PER_MINUTE = 250

    # Retry configuration
    MAX_RETRIES = 5
    INITIAL_BACKOFF_SECONDS = 2
    MAX_BACKOFF_SECONDS = 60
    BACKOFF_MULTIPLIER = 2

    # Batch sizes
    QUOTE_BATCH_SIZE = 100  # instruments per API call (max 1000)

    def __init__(
        self,
        access_token: str,
        client_id: str,
        db=None,
    ):
        self.access_token = access_token
        self.client_id = client_id
        self.db = db
        self.metrics = APIMetrics()
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_timestamps: List[float] = []
        self._symbol_map: Dict[str, str] = dict(SYMBOL_TO_SECURITY_ID)
        self._security_to_symbol: Dict[str, str] = {
            v: k for k, v in self._symbol_map.items()
        }

    # ── lifecycle ────────────────────────────────────────────────────────

    async def initialize(self):
        """Create HTTP session and optionally refresh security ID map."""
        if self.session and not self.session.closed:
            return

        self.session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "access-token": self.access_token,
                "client-id": self.client_id,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
        logger.info(
            "DhanAPIExtractor initialised – %d symbols mapped",
            len(self._symbol_map),
        )

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        logger.info("DhanAPIExtractor session closed")

    # ── rate limiting ────────────────────────────────────────────────────

    async def _enforce_rate_limit(self):
        now = time.monotonic()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < 60
        ]
        # per-minute
        if len(self._request_timestamps) >= self.MAX_REQUESTS_PER_MINUTE:
            wait = 60 - (now - self._request_timestamps[0])
            if wait > 0:
                logger.debug("Rate limit (per-min): sleeping %.1fs", wait)
                self.metrics.rate_limit_hits += 1
                await asyncio.sleep(wait)
        # per-second
        recent = [t for t in self._request_timestamps if now - t < 1]
        if len(recent) >= self.MAX_REQUESTS_PER_SECOND:
            wait = 1.0 - (now - recent[0])
            if wait > 0:
                await asyncio.sleep(wait)
        self._request_timestamps.append(time.monotonic())

    # ── low-level HTTP ───────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict, retries: int = 0) -> dict:
        """POST to Dhan API with retry + exponential backoff."""
        if not self.session:
            await self.initialize()

        url = f"{self.BASE_URL}{path}"
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            await self._enforce_rate_limit()
            start = time.monotonic()
            self.metrics.total_requests += 1
            self.metrics.last_request_time = datetime.now(timezone.utc)

            try:
                async with self.session.post(url, json=payload) as resp:
                    latency = (time.monotonic() - start) * 1000
                    self._update_latency(latency)

                    if resp.status == 200:
                        data = await resp.json()
                        self.metrics.successful_requests += 1
                        return data

                    body = await resp.text()

                    if resp.status == 429:
                        self.metrics.rate_limit_hits += 1
                        wait = self._backoff(attempt)
                        logger.warning("Dhan 429 rate-limited – waiting %.1fs", wait)
                        await asyncio.sleep(wait)
                        self.metrics.retry_count += 1
                        continue

                    if resp.status == 401:
                        self.metrics.failed_requests += 1
                        raise AuthenticationError(
                            f"Dhan API authentication failed (401): {body}"
                        )

                    if resp.status >= 500:
                        wait = self._backoff(attempt)
                        logger.warning(
                            "Dhan %d server error – retrying in %.1fs: %s",
                            resp.status, wait, body[:200],
                        )
                        self.metrics.retry_count += 1
                        await asyncio.sleep(wait)
                        continue

                    # 4xx other than 401/429
                    self.metrics.failed_requests += 1
                    last_error = f"HTTP {resp.status}: {body[:300]}"
                    logger.error("Dhan API error: %s", last_error)
                    break

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                latency = (time.monotonic() - start) * 1000
                self._update_latency(latency)
                last_error = str(exc)
                if attempt < self.MAX_RETRIES:
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Network error (%s) – retrying in %.1fs", exc, wait
                    )
                    self.metrics.retry_count += 1
                    await asyncio.sleep(wait)
                else:
                    self.metrics.failed_requests += 1

        error_msg = last_error or "Max retries exceeded"
        self._record_error("POST", path, error_msg)
        return {"status": "error", "error": error_msg}

    def _backoff(self, attempt: int) -> float:
        delay = min(
            self.INITIAL_BACKOFF_SECONDS * (self.BACKOFF_MULTIPLIER ** attempt),
            self.MAX_BACKOFF_SECONDS,
        )
        return delay

    def _update_latency(self, ms: float):
        self.metrics.total_latency_ms += ms
        if ms < self.metrics.min_latency_ms:
            self.metrics.min_latency_ms = ms
        if ms > self.metrics.max_latency_ms:
            self.metrics.max_latency_ms = ms

    def _record_error(self, method: str, path: str, error: str):
        self.metrics.errors.append({
            "method": method,
            "path": path,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.metrics.errors) > 100:
            self.metrics.errors = self.metrics.errors[-100:]

    # ── symbol helpers ───────────────────────────────────────────────────

    def get_security_id(self, symbol: str) -> Optional[str]:
        return self._symbol_map.get(symbol.upper())

    def get_symbol(self, security_id: str) -> Optional[str]:
        return self._security_to_symbol.get(security_id)

    def _security_id_for_marketfeed(self, sec_id: str):
        """Dhan marketfeed endpoints expect numeric security IDs."""
        try:
            return int(sec_id)
        except (TypeError, ValueError):
            return sec_id

    # ── public data methods ──────────────────────────────────────────────

    async def get_stock_quote(self, symbol: str) -> ExtractionResult:
        """Fetch full quote for a single symbol."""
        start = time.monotonic()
        sec_id = self.get_security_id(symbol)
        if not sec_id:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=f"Unknown symbol: {symbol} – no Dhan security ID mapped",
            )

        payload = {"NSE_EQ": [self._security_id_for_marketfeed(sec_id)]}
        resp = await self._post("/v2/marketfeed/quote", payload)
        latency = (time.monotonic() - start) * 1000

        if resp.get("status") == "error":
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=resp.get("error", "Unknown error"),
                latency_ms=latency,
            )

        try:
            data = self._parse_quote_response(symbol, sec_id, resp)
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                symbol=symbol,
                data=data,
                latency_ms=latency,
            )
        except Exception as exc:
            logger.error("Error parsing quote for %s: %s", symbol, exc)
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=str(exc),
                latency_ms=latency,
            )

    async def extract_bulk_quotes(
        self, symbols: List[str]
    ) -> Dict[str, ExtractionResult]:
        """Fetch quotes for many symbols in batches."""
        results: Dict[str, ExtractionResult] = {}
        # Map symbols to security IDs, skip unknowns
        valid = []
        for s in symbols:
            sec = self.get_security_id(s)
            if sec:
                valid.append((s, sec))
            else:
                results[s] = ExtractionResult(
                    status=ExtractionStatus.FAILED,
                    symbol=s,
                    error=f"No security ID for {s}",
                )

        # Batch into groups
        for i in range(0, len(valid), self.QUOTE_BATCH_SIZE):
            batch = valid[i : i + self.QUOTE_BATCH_SIZE]
            sec_ids = [self._security_id_for_marketfeed(sec) for _, sec in batch]
            payload = {"NSE_EQ": sec_ids}

            start = time.monotonic()
            resp = await self._post("/v2/marketfeed/quote", payload)
            latency = (time.monotonic() - start) * 1000

            if resp.get("status") == "error":
                for sym, _ in batch:
                    results[sym] = ExtractionResult(
                        status=ExtractionStatus.FAILED,
                        symbol=sym,
                        error=resp.get("error", "Batch request failed"),
                        latency_ms=latency,
                    )
                continue

            for sym, sec in batch:
                try:
                    data = self._parse_quote_response(sym, sec, resp)
                    results[sym] = ExtractionResult(
                        status=ExtractionStatus.SUCCESS,
                        symbol=sym,
                        data=data,
                        latency_ms=latency,
                    )
                except Exception as exc:
                    results[sym] = ExtractionResult(
                        status=ExtractionStatus.FAILED,
                        symbol=sym,
                        error=str(exc),
                        latency_ms=latency,
                    )

        return results

    async def get_historical_data(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> ExtractionResult:
        """Fetch daily OHLCV candles for a symbol.

        Args:
            symbol: Stock symbol (e.g. "RELIANCE")
            from_date: Start date "YYYY-MM-DD"
            to_date: End date "YYYY-MM-DD"
        """
        sec_id = self.get_security_id(symbol)
        if not sec_id:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=f"Unknown symbol: {symbol}",
            )

        payload = {
            "securityId": sec_id,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "expiryCode": 0,
            "oi": False,
            "fromDate": from_date,
            "toDate": to_date,
        }

        start = time.monotonic()
        resp = await self._post("/v2/charts/historical", payload)
        latency = (time.monotonic() - start) * 1000

        if resp.get("status") == "error":
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=resp.get("error", "Unknown error"),
                latency_ms=latency,
            )

        try:
            candles = self._parse_historical_response(symbol, resp)
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                symbol=symbol,
                data={"symbol": symbol, "candles": candles, "count": len(candles)},
                latency_ms=latency,
            )
        except Exception as exc:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=str(exc),
                latency_ms=latency,
            )

    async def get_ltp(self, symbols: List[str]) -> Dict[str, ExtractionResult]:
        """Lightweight LTP fetch for many symbols."""
        results: Dict[str, ExtractionResult] = {}
        valid = []
        for s in symbols:
            sec = self.get_security_id(s)
            if sec:
                valid.append((s, sec))
            else:
                results[s] = ExtractionResult(
                    status=ExtractionStatus.FAILED,
                    symbol=s,
                    error=f"No security ID for {s}",
                )

        for i in range(0, len(valid), self.QUOTE_BATCH_SIZE):
            batch = valid[i : i + self.QUOTE_BATCH_SIZE]
            sec_ids = [self._security_id_for_marketfeed(sec) for _, sec in batch]
            payload = {"NSE_EQ": sec_ids}

            resp = await self._post("/v2/marketfeed/ltp", payload)

            if resp.get("status") == "error":
                for sym, _ in batch:
                    results[sym] = ExtractionResult(
                        status=ExtractionStatus.FAILED,
                        symbol=sym,
                        error=resp.get("error", "LTP request failed"),
                    )
                continue

            nse_data = resp.get("data", resp).get("NSE_EQ", resp.get("NSE_EQ", {}))
            for sym, sec in batch:
                info = nse_data.get(sec, nse_data.get(int(sec), {})) if isinstance(nse_data, dict) else {}
                if not info:
                    # Try alternate response shapes
                    info = resp.get("data", {}).get("NSE_EQ", {}).get(str(sec), {})
                ltp = info.get("last_price", 0) if isinstance(info, dict) else 0
                results[sym] = ExtractionResult(
                    status=ExtractionStatus.SUCCESS if ltp else ExtractionStatus.FAILED,
                    symbol=sym,
                    data={"symbol": sym, "ltp": ltp, "last_price": ltp},
                    error=None if ltp else "No LTP data returned",
                )

        return results

    # ── response parsing ─────────────────────────────────────────────────

    def _parse_quote_response(
        self, symbol: str, sec_id: str, resp: dict
    ) -> Dict[str, Any]:
        """Parse /v2/marketfeed/quote response into standardised dict."""
        # Response shape: { "data": { "NSE_EQ": { "<sec_id>": { ... } } }, "status": "success" }
        # or sometimes just { "NSE_EQ": { ... }, "status": "success" }
        nse_data = {}
        if "data" in resp:
            nse_data = resp["data"].get("NSE_EQ", {})
        else:
            nse_data = resp.get("NSE_EQ", {})

        info = nse_data.get(sec_id, nse_data.get(int(sec_id), {})) if isinstance(nse_data, dict) else {}
        if not info:
            # Try string key
            info = nse_data.get(str(sec_id), {})

        if not info:
            raise ValueError(f"No data returned for {symbol} (sec_id={sec_id})")

        ohlc = info.get("ohlc", {})
        depth = info.get("depth", {})

        last_price = info.get("last_price", 0)
        open_price = ohlc.get("open", 0)
        high_price = ohlc.get("high", 0)
        low_price = ohlc.get("low", 0)
        close_price = ohlc.get("close", 0)
        prev_close = close_price  # prev close from OHLC close field

        # Use net_change from API when available, else compute
        net_change = info.get("net_change")
        if net_change is not None:
            price_change = net_change
            price_change_pct = (
                (price_change / prev_close * 100) if prev_close else 0
            )
        else:
            price_change = last_price - prev_close if prev_close else 0
            price_change_pct = (
                (price_change / prev_close * 100) if prev_close else 0
            )

        # Build standardised record matching pipeline_service expectations
        data = {
            "symbol": symbol,
            "security_id": sec_id,
            "exchange": "NSE",
            "current_price": last_price,
            "ltp": last_price,
            "last_price": last_price,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "prev_close": prev_close,
            "net_change": price_change,
            "price_change": round(price_change, 2),
            "price_change_percent": round(price_change_pct, 2),
            "volume": info.get("volume", 0),
            "average_price": info.get("average_price", 0),
            "last_quantity": info.get("last_quantity", 0),
            "buy_quantity": info.get("buy_quantity", 0),
            "sell_quantity": info.get("sell_quantity", 0),
            "open_interest": info.get("oi", 0),
            "oi_day_high": info.get("oi_day_high", 0),
            "oi_day_low": info.get("oi_day_low", 0),
            "upper_circuit_limit": info.get("upper_circuit_limit", 0),
            "lower_circuit_limit": info.get("lower_circuit_limit", 0),
            "last_trade_time": info.get("last_trade_time", None),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "dhan",
        }

        # Market depth (best 5 bid/ask)
        if depth:
            buy_levels = depth.get("buy", [])
            sell_levels = depth.get("sell", [])
            if buy_levels:
                data["bid_price"] = buy_levels[0].get("price", 0)
                data["bid_quantity"] = buy_levels[0].get("quantity", 0)
            if sell_levels:
                data["ask_price"] = sell_levels[0].get("price", 0)
                data["ask_quantity"] = sell_levels[0].get("quantity", 0)
            data["depth"] = depth

        return data

    def _parse_historical_response(
        self, symbol: str, resp: dict
    ) -> List[Dict[str, Any]]:
        """Parse /v2/charts/historical response into list of candles."""
        # Response shape: { "open": [...], "high": [...], "low": [...],
        #                    "close": [...], "volume": [...], "timestamp": [...] }
        opens = resp.get("open", [])
        highs = resp.get("high", [])
        lows = resp.get("low", [])
        closes = resp.get("close", [])
        volumes = resp.get("volume", [])
        timestamps = resp.get("timestamp", [])

        candles = []
        for i in range(len(timestamps)):
            ts = timestamps[i]
            # Dhan returns epoch seconds
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            candles.append({
                "symbol": symbol,
                "date": dt.strftime("%Y-%m-%d"),
                "open": opens[i] if i < len(opens) else 0,
                "high": highs[i] if i < len(highs) else 0,
                "low": lows[i] if i < len(lows) else 0,
                "close": closes[i] if i < len(closes) else 0,
                "volume": volumes[i] if i < len(volumes) else 0,
                "timestamp": dt.isoformat(),
            })
        return candles

    # ── intraday minute data ─────────────────────────────────────────────

    async def get_intraday_data(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> ExtractionResult:
        """Fetch intraday minute-level OHLCV candles for a symbol.

        Args:
            symbol: Stock symbol (e.g. "RELIANCE")
            from_date: Start date "YYYY-MM-DD"
            to_date: End date "YYYY-MM-DD"
        """
        sec_id = self.get_security_id(symbol)
        if not sec_id:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=f"Unknown symbol: {symbol}",
            )

        payload = {
            "securityId": sec_id,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "fromDate": from_date,
            "toDate": to_date,
        }

        start = time.monotonic()
        resp = await self._post("/v2/charts/intraday", payload)
        latency = (time.monotonic() - start) * 1000

        if resp.get("status") == "error":
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=resp.get("error", "Unknown error"),
                latency_ms=latency,
            )

        try:
            candles = self._parse_historical_response(symbol, resp)
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                symbol=symbol,
                data={"symbol": symbol, "candles": candles, "count": len(candles)},
                latency_ms=latency,
            )
        except Exception as exc:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                symbol=symbol,
                error=str(exc),
                latency_ms=latency,
            )

    # ── instrument list refresh ───────────────────────────────────────────

    async def refresh_instrument_map(self, exchange_segment: str = "NSE_EQ") -> int:
        """Refresh the symbol→security-ID mapping from the Dhan instrument CSV.

        GET /v2/instrument/{exchangeSegment} returns a CSV with columns:
        EXCH, SEC_ID, SEM_SMST_SECURITY_ID, SEM_TRADING_SYMBOL, ...

        Returns the number of symbols loaded.
        """
        if not self.session:
            await self.initialize()

        url = f"{self.BASE_URL}/v2/instrument/{exchange_segment}"
        await self._enforce_rate_limit()
        self.metrics.total_requests += 1
        self.metrics.last_request_time = datetime.now(timezone.utc)

        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Instrument list fetch failed: HTTP %d", resp.status
                    )
                    return 0

                text = await resp.text()
                self.metrics.successful_requests += 1

            reader = csv.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                # Common CSV column names from Dhan instrument files
                sec_id = (
                    row.get("SEM_SMST_SECURITY_ID")
                    or row.get("SEC_ID")
                    or row.get("SECURITY_ID")
                    or ""
                ).strip()
                trading_symbol = (
                    row.get("SEM_TRADING_SYMBOL")
                    or row.get("TRADING_SYMBOL")
                    or row.get("SYMBOL")
                    or ""
                ).strip()
                # Only add equity symbols, skip derivatives
                instrument = (
                    row.get("SEM_INSTRUMENT_NAME")
                    or row.get("INSTRUMENT")
                    or ""
                ).strip()
                if sec_id and trading_symbol and instrument in ("EQUITY", ""):
                    clean_sym = trading_symbol.replace("-EQ", "").replace("-BE", "").strip()
                    if clean_sym:
                        self._symbol_map[clean_sym] = sec_id
                        self._security_to_symbol[sec_id] = clean_sym
                        count += 1

            logger.info(
                "Instrument map refreshed: %d symbols from %s",
                count,
                exchange_segment,
            )
            return count

        except Exception as exc:
            self.metrics.failed_requests += 1
            logger.error("Failed to refresh instrument map: %s", exc)
            return 0

    # ── metrics ──────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict:
        return self.metrics.to_dict()
