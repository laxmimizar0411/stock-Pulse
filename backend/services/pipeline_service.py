"""
Data Pipeline Service for StockPulse
Manages data extraction pipelines, scheduling, and monitoring
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class PipelineStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    SCHEDULED = "scheduled"


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineJob:
    """Represents a data extraction job"""
    job_id: str
    pipeline_type: str
    symbols: List[str]
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_symbols: int = 0
    processed_symbols: int = 0
    successful_symbols: int = 0
    failed_symbols: int = 0
    errors: List[Dict] = field(default_factory=list)
    results: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "pipeline_type": self.pipeline_type,
            "status": self.status.value,
            "symbols": self.symbols,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_symbols": self.total_symbols,
            "processed_symbols": self.processed_symbols,
            "successful_symbols": self.successful_symbols,
            "failed_symbols": self.failed_symbols,
            "progress_percent": round((self.processed_symbols / self.total_symbols * 100) if self.total_symbols > 0 else 0, 2),
            "errors": self.errors[-10:],  # Last 10 errors
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds() 
                if self.completed_at and self.started_at else None
            )
        }


@dataclass
class PipelineMetrics:
    """Aggregated pipeline metrics"""
    total_jobs_run: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    total_symbols_processed: int = 0
    total_data_points_extracted: int = 0
    last_run_time: Optional[datetime] = None
    next_scheduled_run: Optional[datetime] = None
    avg_job_duration_seconds: float = 0
    uptime_since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Data volume tracking
    expected_daily_symbols: int = 0
    received_daily_symbols: int = 0
    missing_symbols: List[str] = field(default_factory=list)
    delayed_symbols: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "total_jobs_run": self.total_jobs_run,
            "successful_jobs": self.successful_jobs,
            "failed_jobs": self.failed_jobs,
            "job_success_rate": round((self.successful_jobs / self.total_jobs_run * 100) if self.total_jobs_run > 0 else 0, 2),
            "total_symbols_processed": self.total_symbols_processed,
            "total_data_points_extracted": self.total_data_points_extracted,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "next_scheduled_run": self.next_scheduled_run.isoformat() if self.next_scheduled_run else None,
            "avg_job_duration_seconds": round(self.avg_job_duration_seconds, 2),
            "uptime_seconds": (datetime.now(timezone.utc) - self.uptime_since).total_seconds(),
            "expected_daily_symbols": self.expected_daily_symbols,
            "received_daily_symbols": self.received_daily_symbols,
            "data_completeness_percent": round(
                (self.received_daily_symbols / self.expected_daily_symbols * 100) 
                if self.expected_daily_symbols > 0 else 0, 2
            ),
            "missing_symbols_count": len(self.missing_symbols),
            "missing_symbols": self.missing_symbols[:20],  # First 20
            "delayed_symbols_count": len(self.delayed_symbols),
            "delayed_symbols": self.delayed_symbols[:20]  # First 20
        }


class DataPipelineService:
    """
    Central service for managing data extraction pipelines
    Handles scheduling, execution, and monitoring
    """
    
    # Default Indian stock symbols for extraction - NIFTY 50 + NIFTY Next 50 + Popular Mid-caps
    DEFAULT_SYMBOLS = [
        # NIFTY 50 Stocks
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "HINDUNILVR", "SBIN", "BHARTIARTL", "KOTAKBANK", "ITC",
        "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
        "HCLTECH", "WIPRO", "ULTRACEMCO", "TITAN", "NESTLEIND",
        "SUNPHARMA", "BAJAJFINSV", "ONGC", "NTPC", "POWERGRID",
        "M&M", "TATASTEEL", "ADANIENT", "TECHM", "JSWSTEEL",
        "TATAMOTOR", "INDUSINDBK", "COALINDIA", "HINDALCO", "GRASIM",
        "ADANIPORTS", "DRREDDY", "APOLLOHOSP", "CIPLA", "EICHERMOT",
        "BPCL", "DIVISLAB", "BRITANNIA", "HEROMOTOCO", "SBILIFE",
        "HDFCLIFE", "TATACONSUM", "BAJAJ-AUTO", "SHRIRAMFIN", "LTIM",
        
        # NIFTY Next 50 Stocks
        "ADANIGREEN", "AMBUJACEM", "BANKBARODA", "BEL", "BERGEPAINT",
        "BOSCHLTD", "CANBK", "CHOLAFIN", "COLPAL", "DLF",
        "DMART", "GAIL", "GODREJCP", "HAVELLS", "ICICIGI",
        "ICICIPRULI", "IDEA", "INDHOTEL", "INDIGO", "IOC",
        "IRCTC", "JINDALSTEL", "JUBLFOOD", "LTF", "LUPIN",
        "MARICO", "MCDOWELL-N", "MOTHERSON", "MUTHOOTFIN", "NAUKRI",
        "NHPC", "OFSS", "PAGEIND", "PAYTM", "PFC",
        "PIDILITIND", "PNB", "POLYCAB", "RECLTD", "SAIL",
        "SBICARD", "SRF", "TATAELXSI", "TATAPOWER", "TORNTPHARM",
        "TRENT", "UPL", "VEDL", "VBL", "ZOMATO",
        
        # Popular Mid-cap & Small-cap Stocks
        "AUROPHARMA", "BANDHANBNK", "CANFINHOME", "CROMPTON", "CUMMINSIND",
        "DEEPAKNTR", "ESCORTS", "EXIDEIND", "FEDERALBNK", "GLENMARK",
        "GMRINFRA", "HINDPETRO", "IBULHSGFIN", "IDFCFIRSTB", "IEX",
        "IRFC", "KALYANKJIL", "LALPATHLAB", "LICHSGFIN", "MANAPPURAM",
        "MRF", "NAM-INDIA", "NATIONALUM", "NMDC", "OBEROIRLTY",
        "PERSISTENT", "PETRONET", "PIIND", "PVRINOX", "RAMCOCEM",
        "RBLBANK", "SUNTV", "TATACOMM", "TATACHEM", "THERMAX",
        "TORNTPOWER", "TVSMOTOR", "UNIONBANK", "UBL", "VOLTAS",
        "WHIRLPOOL", "ZEEL", "ZYDUSLIFE"
    ]
    
    # Scheduler configuration
    DEFAULT_SCHEDULER_INTERVAL = 15  # minutes
    AUTO_START_SCHEDULER = True  # Auto-start on initialization
    
    def __init__(self, db=None, grow_extractor=None, ts_store=None):
        """
        Initialize the data pipeline service

        Args:
            db: MongoDB database instance
            grow_extractor: GrowwAPIExtractor instance
            ts_store: TimeSeriesStore instance for PostgreSQL persistence
        """
        self.db = db
        self.grow_extractor = grow_extractor
        self.ts_store = ts_store  # PostgreSQL time-series store
        
        # Pipeline state
        self.status = PipelineStatus.IDLE
        self.current_job: Optional[PipelineJob] = None
        
        # Job management
        self._jobs: Dict[str, PipelineJob] = {}
        self._job_history: List[Dict] = []
        
        # Metrics
        self.metrics = PipelineMetrics()
        self.metrics.expected_daily_symbols = len(self.DEFAULT_SYMBOLS)
        
        # Scheduler
        self._scheduler_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Extraction logs
        self._extraction_logs: List[Dict] = []
        
    async def initialize(self):
        """Initialize the pipeline service"""
        logger.info("Initializing Data Pipeline Service")
        
        if self.grow_extractor:
            await self.grow_extractor.initialize()
        
        # Load job history from database if available
        if self.db is not None:
            try:
                history = await self.db.pipeline_jobs.find(
                    {}, {"_id": 0}
                ).sort("created_at", -1).limit(100).to_list(100)
                self._job_history = history
            except Exception as e:
                logger.warning(f"Could not load job history: {e}")
        
        # Auto-start scheduler for continuous data collection
        if self.AUTO_START_SCHEDULER and self.grow_extractor:
            logger.info(f"Auto-starting scheduler with {self.DEFAULT_SCHEDULER_INTERVAL} minute interval")
            await self.start_scheduler(interval_minutes=self.DEFAULT_SCHEDULER_INTERVAL)
        
        logger.info(f"Data Pipeline Service initialized with {len(self.DEFAULT_SYMBOLS)} symbols")
    
    async def start_scheduler(self, interval_minutes: int = 30):
        """Start the automatic extraction scheduler"""
        if self._scheduler_task and not self._scheduler_task.done():
            logger.warning("Scheduler already running")
            return
        
        self._is_running = True
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(interval_minutes)
        )
        self.status = PipelineStatus.SCHEDULED
        self.metrics.next_scheduled_run = datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)
        
        logger.info(f"Pipeline scheduler started with {interval_minutes} minute interval")
    
    async def stop_scheduler(self):
        """Stop the automatic extraction scheduler"""
        self._is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        self.status = PipelineStatus.IDLE
        self.metrics.next_scheduled_run = None
        logger.info("Pipeline scheduler stopped")
    
    async def _scheduler_loop(self, interval_minutes: int):
        """Internal scheduler loop"""
        while self._is_running:
            try:
                # Run extraction
                await self.run_extraction(self.DEFAULT_SYMBOLS)
                
                # Update next run time
                self.metrics.next_scheduled_run = datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)
                
                # Wait for next interval
                await asyncio.sleep(interval_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                self._log_event("scheduler_error", {"error": str(e)})
                # Wait a bit before retrying
                await asyncio.sleep(60)
    
    async def run_extraction(
        self,
        symbols: Optional[List[str]] = None,
        extraction_type: str = "quotes"
    ) -> PipelineJob:
        """
        Run a data extraction job
        
        Args:
            symbols: List of stock symbols to extract (defaults to DEFAULT_SYMBOLS)
            extraction_type: Type of extraction ("quotes" or "historical")
            
        Returns:
            PipelineJob with extraction results
        """
        if symbols is None:
            symbols = self.DEFAULT_SYMBOLS
        
        # Create job
        job = PipelineJob(
            job_id=str(uuid.uuid4())[:12],
            pipeline_type=extraction_type,
            symbols=symbols,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            total_symbols=len(symbols)
        )
        
        self._jobs[job.job_id] = job
        self.current_job = job
        self.status = PipelineStatus.RUNNING
        
        self._log_event("job_started", {
            "job_id": job.job_id,
            "type": extraction_type,
            "symbol_count": len(symbols)
        })
        
        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            
            if not self.grow_extractor:
                raise Exception("Groww extractor not initialized")
            
            # Run extraction based on type
            if extraction_type == "quotes":
                results = await self.grow_extractor.extract_bulk_quotes(symbols)
            else:
                # For historical data, we'd need more parameters
                results = await self.grow_extractor.extract_bulk_quotes(symbols)
            
            # Initialize cache service for saving data
            from services.cache_service import get_cache_service
            cache = get_cache_service()
            
            # Process results
            received_symbols = []
            for symbol, result in results.items():
                job.processed_symbols += 1
                
                if result.status.value == "success":
                    job.successful_symbols += 1
                    received_symbols.append(symbol)
                    job.results[symbol] = result.data
                    
                    # Store live data in Redis!
                    if cache:
                        # Store as full JSON document
                        cache.set_price(symbol, result.data)
                        # Store as HASH for partial field reads
                        cache.set_stock_hash(symbol, result.data)
                        # Publish to WebSocket PUB/SUB
                        cache.publish_price(symbol, result.data)
                else:
                    job.failed_symbols += 1
                    job.errors.append({
                        "symbol": symbol,
                        "error": result.error,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            
            # Update top gainers and losers in Redis
            if cache and received_symbols:
                gainers = {}
                losers = {}
                for sym, data in job.results.items():
                    pct = data.get("price_change_percent", 0)
                    if pct > 0:
                        gainers[sym] = pct
                    elif pct < 0:
                        losers[sym] = pct
                
                # Sort and send top 50 to Redis
                gainers = dict(sorted(gainers.items(), key=lambda item: item[1], reverse=True)[:50])
                losers = dict(sorted(losers.items(), key=lambda item: item[1])[:50])
                cache.update_top_movers(gainers, losers)
            
            # Update metrics
            self.metrics.received_daily_symbols = len(received_symbols)
            self.metrics.missing_symbols = [s for s in symbols if s not in received_symbols]
            
            # Determine job status
            if job.successful_symbols == job.total_symbols:
                job.status = JobStatus.SUCCESS
            elif job.successful_symbols > 0:
                job.status = JobStatus.PARTIAL_SUCCESS
            else:
                job.status = JobStatus.FAILED
            
            job.completed_at = datetime.now(timezone.utc)
            
            # Update metrics
            self.metrics.total_jobs_run += 1
            if job.status in [JobStatus.SUCCESS, JobStatus.PARTIAL_SUCCESS]:
                self.metrics.successful_jobs += 1
            else:
                self.metrics.failed_jobs += 1
            
            self.metrics.total_symbols_processed += job.successful_symbols
            self.metrics.last_run_time = job.completed_at
            
            # Update average duration
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                total_duration = self.metrics.avg_job_duration_seconds * (self.metrics.total_jobs_run - 1)
                self.metrics.avg_job_duration_seconds = (total_duration + duration) / self.metrics.total_jobs_run
            
            self._log_event("job_completed", {
                "job_id": job.job_id,
                "status": job.status.value,
                "successful": job.successful_symbols,
                "failed": job.failed_symbols
            })
            
            # Persist price data to PostgreSQL time-series store
            if self.ts_store and job.results:
                await self._persist_to_timeseries(job.results)

            # Store job record in MongoDB
            if self.db is not None:
                try:
                    await self.db.pipeline_jobs.insert_one({**job.to_dict()})
                except Exception as e:
                    logger.warning(f"Could not store job in database: {e}")
            
            # Add to history
            self._job_history.insert(0, job.to_dict())
            if len(self._job_history) > 100:
                self._job_history = self._job_history[:100]
            
        except Exception as e:
            logger.error(f"Extraction job failed: {e}")
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.errors.append({
                "type": "job_error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            self.metrics.failed_jobs += 1
            self.metrics.total_jobs_run += 1
            
            self._log_event("job_failed", {
                "job_id": job.job_id,
                "error": str(e)
            })
        
        finally:
            self.current_job = None
            self.status = PipelineStatus.SCHEDULED if self._is_running else PipelineStatus.IDLE
        
        return job
    
    def _log_event(self, event_type: str, data: Dict):
        """Log a pipeline event"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **data
        }
        self._extraction_logs.append(log_entry)
        
        # Keep only last 1000 logs
        if len(self._extraction_logs) > 1000:
            self._extraction_logs = self._extraction_logs[-1000:]
        
        logger.info(f"Pipeline event: {event_type} - {data}")
    
    def get_status(self) -> Dict:
        """Get current pipeline status"""
        return {
            "status": self.status.value,
            "is_running": self._is_running,
            "current_job": self.current_job.to_dict() if self.current_job else None,
            "metrics": self.metrics.to_dict(),
            "extractor_metrics": self.grow_extractor.get_metrics() if self.grow_extractor else None,
            "default_symbols_count": len(self.DEFAULT_SYMBOLS),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get a specific job by ID"""
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None
    
    def get_jobs(self, limit: int = 20) -> List[Dict]:
        """Get recent jobs"""
        jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]
    
    def get_job_history(self, limit: int = 50) -> List[Dict]:
        """Get job history"""
        return self._job_history[:limit]
    
    def get_logs(self, limit: int = 100, event_type: Optional[str] = None) -> List[Dict]:
        """Get extraction logs"""
        logs = self._extraction_logs
        if event_type:
            logs = [l for l in logs if l.get("event_type") == event_type]
        return logs[-limit:]
    
    def get_data_summary(self) -> Dict:
        """Get summary of extracted data"""
        # Aggregate data from recent successful jobs
        symbols_data = {}
        
        for job_dict in self._job_history[:10]:  # Last 10 jobs
            if job_dict.get("status") in ["success", "partial_success"]:
                results = job_dict.get("results", {})
                for symbol, data in results.items() if isinstance(results, dict) else []:
                    if symbol not in symbols_data:
                        symbols_data[symbol] = data
        
        return {
            "unique_symbols_extracted": len(symbols_data),
            "data_by_symbol": symbols_data,
            "last_extraction_time": self.metrics.last_run_time.isoformat() if self.metrics.last_run_time else None
        }
    
    def add_symbols(self, symbols: List[str]) -> Dict:
        """Add new symbols to the tracking list"""
        added = []
        already_exists = []
        
        for symbol in symbols:
            symbol = symbol.upper().strip()
            if symbol and symbol not in self.DEFAULT_SYMBOLS:
                self.DEFAULT_SYMBOLS.append(symbol)
                added.append(symbol)
            else:
                already_exists.append(symbol)
        
        self.metrics.expected_daily_symbols = len(self.DEFAULT_SYMBOLS)
        
        return {
            "added": added,
            "already_exists": already_exists,
            "total_symbols": len(self.DEFAULT_SYMBOLS)
        }
    
    def remove_symbols(self, symbols: List[str]) -> Dict:
        """Remove symbols from the tracking list"""
        removed = []
        not_found = []
        
        for symbol in symbols:
            symbol = symbol.upper().strip()
            if symbol in self.DEFAULT_SYMBOLS:
                self.DEFAULT_SYMBOLS.remove(symbol)
                removed.append(symbol)
            else:
                not_found.append(symbol)
        
        self.metrics.expected_daily_symbols = len(self.DEFAULT_SYMBOLS)
        
        return {
            "removed": removed,
            "not_found": not_found,
            "total_symbols": len(self.DEFAULT_SYMBOLS)
        }
    
    def get_symbol_categories(self) -> Dict:
        """Get symbols organized by category"""
        # First 50 are NIFTY 50, next 50 are NIFTY Next 50, rest are mid/small caps
        nifty50 = self.DEFAULT_SYMBOLS[:50] if len(self.DEFAULT_SYMBOLS) >= 50 else self.DEFAULT_SYMBOLS
        nifty_next50 = self.DEFAULT_SYMBOLS[50:100] if len(self.DEFAULT_SYMBOLS) >= 100 else self.DEFAULT_SYMBOLS[50:]
        others = self.DEFAULT_SYMBOLS[100:] if len(self.DEFAULT_SYMBOLS) > 100 else []
        
        return {
            "nifty_50": {
                "symbols": nifty50,
                "count": len(nifty50)
            },
            "nifty_next_50": {
                "symbols": nifty_next50,
                "count": len(nifty_next50)
            },
            "mid_small_caps": {
                "symbols": others,
                "count": len(others)
            },
            "total_symbols": len(self.DEFAULT_SYMBOLS)
        }
    
    async def _persist_to_timeseries(self, results: Dict[str, Any]):
        """
        Persist extracted data to PostgreSQL time-series tables.

        Builds records for all applicable tables from pipeline results:
        - prices_daily, technical_indicators, fundamentals_quarterly, shareholding_quarterly
        - valuation_daily, derived_metrics_daily, ml_features_daily, risk_metrics
        - corporate_actions, macro_indicators, derivatives_daily
        - intraday_metrics, weekly_metrics (when data is available)
        """
        if not self.ts_store:
            return

        price_records = []
        technical_records = []
        fundamental_records = []
        shareholding_records = []
        valuation_records = []
        derived_records = []
        ml_feature_records = []
        risk_records = []
        corporate_records = []

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for symbol, data in results.items():
            if not isinstance(data, dict):
                continue

            sym_date = data.get("date", today_str)

            # 1. Price data
            if any(k in data for k in ["close", "ltp", "current_price", "open", "high", "low"]):
                price_records.append({
                    "symbol": symbol,
                    "date": sym_date,
                    "open": data.get("open", data.get("day_open", 0)),
                    "high": data.get("high", data.get("day_high", 0)),
                    "low": data.get("low", data.get("day_low", 0)),
                    "close": data.get("close", data.get("ltp", data.get("current_price", 0))),
                    "prev_close": data.get("prev_close", data.get("previous_close", 0)),
                    "volume": data.get("volume", data.get("total_traded_volume", 0)),
                    "turnover": data.get("turnover", 0),
                })

            # 2. Technical indicators (all schema columns)
            tech_fields = [
                "rsi_14", "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "macd",
                "macd_signal", "macd_histogram", "bollinger_upper", "bollinger_lower",
                "atr_14", "adx_14", "obv", "support_level", "resistance_level",
                "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b",
                "stoch_k", "stoch_d", "cci_20", "williams_r", "cmf",
            ]
            if any(k in data for k in tech_fields):
                technical_records.append({
                    "symbol": symbol,
                    "date": sym_date,
                    **{k: data.get(k) for k in tech_fields if k in data}
                })

            # 3. Fundamentals (all schema columns)
            fund_detect = ["revenue", "net_profit", "eps", "roe", "debt_to_equity"]
            fund_cols = [
                "revenue", "revenue_growth_yoy", "revenue_growth_qoq",
                "operating_profit", "operating_margin", "gross_profit", "gross_margin",
                "net_profit", "net_profit_margin", "eps", "eps_growth_yoy",
                "interest_expense", "depreciation", "ebitda", "ebit",
                "other_income", "tax_expense", "effective_tax_rate",
                "total_assets", "total_equity", "total_debt", "long_term_debt",
                "short_term_debt", "cash_and_equiv", "net_debt",
                "current_assets", "current_liabilities", "inventory",
                "receivables", "payables", "fixed_assets", "intangible_assets",
                "reserves_and_surplus", "book_value_per_share", "contingent_liabilities",
                "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
                "capital_expenditure", "free_cash_flow", "dividends_paid",
                "debt_repayment", "equity_raised",
                "roe", "roa", "roic", "debt_to_equity", "interest_coverage",
                "current_ratio", "quick_ratio", "asset_turnover",
                "inventory_turnover", "receivables_turnover", "dividend_payout_ratio",
                "earnings_surprise_pct", "analyst_rating_consensus",
                "target_price_consensus", "num_analysts",
                "revenue_5y_cagr", "eps_5y_cagr", "roe_5y_avg", "fcf_3y_avg",
            ]
            if any(k in data for k in fund_detect):
                fundamental_records.append({
                    "symbol": symbol,
                    "period_end": data.get("period_end", sym_date),
                    "period_type": data.get("period_type", "quarterly"),
                    **{k: data.get(k) for k in fund_cols if k in data}
                })

            # 4. Shareholding
            share_fields = ["promoter_holding", "fii_holding", "dii_holding"]
            share_cols = [
                "promoter_holding", "promoter_pledging", "fii_holding",
                "dii_holding", "public_holding", "promoter_holding_change",
                "fii_holding_change", "num_shareholders", "mf_holding",
                "insurance_holding",
            ]
            if any(k in data for k in share_fields):
                shareholding_records.append({
                    "symbol": symbol,
                    "quarter_end": data.get("quarter_end", sym_date),
                    **{k: data.get(k) for k in share_cols if k in data}
                })

            # 5. Valuation metrics (if present in data)
            val_detect = ["pe_ratio", "pb_ratio", "market_cap", "dividend_yield", "ev_to_ebitda"]
            val_cols = [
                "market_cap", "enterprise_value", "pe_ratio", "pe_ratio_forward",
                "peg_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda", "ev_to_sales",
                "dividend_yield", "fcf_yield", "earnings_yield",
                "sector_avg_pe", "sector_avg_roe", "industry_avg_pe",
                "historical_pe_median", "sector_performance",
            ]
            if any(k in data for k in val_detect):
                valuation_records.append({
                    "symbol": symbol,
                    "date": sym_date,
                    **{k: data.get(k) for k in val_cols if k in data}
                })

            # 6. ML features (if present)
            ml_detect = ["realized_volatility_10d", "momentum_rank_sector", "volume_zscore"]
            ml_cols = [
                "realized_volatility_10d", "realized_volatility_20d",
                "return_1d_pct", "return_3d_pct", "return_10d_pct",
                "momentum_rank_sector", "price_vs_sma20_pct", "price_vs_sma50_pct",
                "volume_zscore", "volatility_percentile_1y",
                "turnover_20d_avg", "free_float_market_cap",
                "days_since_earnings", "days_to_earnings", "trading_day_of_week",
                "nifty_50_return_1m", "fii_net_activity_daily", "dii_net_activity_daily",
                "sp500_return_1d", "nasdaq_return_1d",
            ]
            if any(k in data for k in ml_detect):
                ml_feature_records.append({
                    "symbol": symbol,
                    "date": sym_date,
                    **{k: data.get(k) for k in ml_cols if k in data}
                })

            # 7. Risk metrics (if present)
            risk_detect = ["beta_1y", "sharpe_ratio_1y", "max_drawdown_1y"]
            risk_cols = [
                "beta_1y", "beta_3y", "max_drawdown_1y",
                "sharpe_ratio_1y", "sortino_ratio_1y", "information_ratio_1y",
                "rolling_volatility_30d", "downside_deviation_1y",
            ]
            if any(k in data for k in risk_detect):
                risk_records.append({
                    "symbol": symbol,
                    "date": sym_date,
                    **{k: data.get(k) for k in risk_cols if k in data}
                })

            # 8. Corporate actions (if present)
            corp_detect = ["dividend_per_share", "stock_split_ratio", "bonus_ratio", "action_type"]
            if any(k in data for k in corp_detect):
                corporate_records.append({
                    "symbol": symbol,
                    "action_type": data.get("action_type", "dividend"),
                    "action_date": data.get("action_date", sym_date),
                    **{k: data.get(k) for k in [
                        "ex_date", "record_date", "dividend_per_share",
                        "stock_split_ratio", "bonus_ratio", "rights_issue_ratio",
                        "buyback_details", "next_earnings_date", "pending_events",
                        "stock_status", "sebi_investigation",
                    ] if k in data}
                })

        # Upsert to PostgreSQL — all table writes in same try block
        try:
            if price_records:
                count = await self.ts_store.upsert_prices(price_records)
                self._log_event("pg_prices_upserted", {"count": count})

            if technical_records:
                count = await self.ts_store.upsert_technicals(technical_records)
                self._log_event("pg_technicals_upserted", {"count": count})

            if fundamental_records:
                count = await self.ts_store.upsert_fundamentals(fundamental_records)
                self._log_event("pg_fundamentals_upserted", {"count": count})

            if shareholding_records:
                count = await self.ts_store.upsert_shareholding(shareholding_records)
                self._log_event("pg_shareholding_upserted", {"count": count})

            if valuation_records:
                count = await self.ts_store.upsert_valuation(valuation_records)
                self._log_event("pg_valuation_upserted", {"count": count})

            if derived_records:
                count = await self.ts_store.upsert_derived_metrics(derived_records)
                self._log_event("pg_derived_upserted", {"count": count})

            if ml_feature_records:
                count = await self.ts_store.upsert_ml_features(ml_feature_records)
                self._log_event("pg_ml_features_upserted", {"count": count})

            if risk_records:
                count = await self.ts_store.upsert_risk_metrics(risk_records)
                self._log_event("pg_risk_upserted", {"count": count})

            if corporate_records:
                for rec in corporate_records:
                    await self.ts_store.insert_corporate_action(rec)
                self._log_event("pg_corporate_actions_inserted", {"count": len(corporate_records)})

            # Corporate actions / macro indicators / derivatives / intraday / weekly:
            # To be filled by separate extractors or derivation jobs when data
            # sources become available (NSE F&O, RBI macro, intraday feed).

        except Exception as e:
            logger.warning(f"PostgreSQL persistence error: {e}")
            self._log_event("pg_persist_error", {"error": str(e)})

    def update_scheduler_config(self, interval_minutes: int = None, auto_start: bool = None) -> Dict:
        """Update scheduler configuration"""
        if interval_minutes is not None:
            self.DEFAULT_SCHEDULER_INTERVAL = interval_minutes
        
        if auto_start is not None:
            self.AUTO_START_SCHEDULER = auto_start
        
        return {
            "interval_minutes": self.DEFAULT_SCHEDULER_INTERVAL,
            "auto_start": self.AUTO_START_SCHEDULER,
            "is_running": self._is_running
        }


# Global service instance
_pipeline_service: Optional[DataPipelineService] = None


def get_pipeline_service() -> Optional[DataPipelineService]:
    """Get the global pipeline service instance"""
    return _pipeline_service


def init_pipeline_service(db=None, totp_token: Optional[str] = None, secret_key: Optional[str] = None, api_key: Optional[str] = None, ts_store=None) -> DataPipelineService:
    """Initialize the global pipeline service"""
    global _pipeline_service

    from data_extraction.extractors.grow_extractor import GrowwAPIExtractor

    grow_extractor = None
    if totp_token and secret_key:
        grow_extractor = GrowwAPIExtractor(totp_token=totp_token, secret_key=secret_key, db=db)
    elif api_key:
        # Legacy fallback - won't work for TOTP-based auth but keeps backward compatibility
        grow_extractor = GrowwAPIExtractor(totp_token=api_key, secret_key='', db=db)

    _pipeline_service = DataPipelineService(db=db, grow_extractor=grow_extractor, ts_store=ts_store)

    return _pipeline_service

