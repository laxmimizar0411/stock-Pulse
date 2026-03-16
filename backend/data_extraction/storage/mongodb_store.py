"""
MongoDB storage layer for the data extraction system.

Manages persistence of stock data records, extraction history,
and quality reports to MongoDB collections.

Collections:
    stock_data          - Current stock data (all 160 fields per symbol)
    price_history       - Time-series OHLCV data
    extraction_log      - Extraction run history and audit trail
    quality_reports     - Data quality assessments
    pipeline_jobs       - Pipeline execution records
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.extraction_models import (
    StockDataRecord, ExtractionRecord, PipelineJob, QualityReport,
)

logger = logging.getLogger(__name__)


class MongoDBStore:
    """
    Async MongoDB storage layer for stock data.

    Uses Motor (async MongoDB driver) for non-blocking operations.
    """

    def __init__(self, db):
        """
        Initialize with a Motor database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.db = db
        # Use app-level collections when set (majority write concern for 99.9% SLA)
        self.stock_data = getattr(db, "stock_data", db["stock_data"])
        self.pipeline_jobs = getattr(db, "pipeline_jobs", db["pipeline_jobs"])
        self.price_history = db["price_history"]
        self.extraction_log = db["extraction_log"]
        self.quality_reports = db["quality_reports"]

    async def ensure_indexes(self) -> None:
        """Create necessary indexes for efficient querying."""
        # Stock data - primary index on symbol
        await self.stock_data.create_index("symbol", unique=True)
        await self.stock_data.create_index("last_updated")
        await self.stock_data.create_index("stock_master.sector")
        await self.stock_data.create_index("stock_master.market_cap_category")

        # Price history - compound index for time-series queries
        await self.price_history.create_index(
            [("symbol", 1), ("date", -1)], unique=True
        )

        # Extraction log
        await self.extraction_log.create_index(
            [("symbol", 1), ("source", 1), ("started_at", -1)]
        )

        # Quality reports
        await self.quality_reports.create_index(
            [("symbol", 1), ("generated_at", -1)]
        )

        # Pipeline jobs
        await self.pipeline_jobs.create_index("job_id", unique=True)
        await self.pipeline_jobs.create_index("created_at")

        logger.info("MongoDB indexes created")

    # ===== Stock Data Operations =====

    async def upsert_stock_data(self, record: StockDataRecord) -> bool:
        """Insert or update a stock data record."""
        try:
            doc = record.to_dict()
            result = await self.stock_data.update_one(
                {"symbol": record.symbol},
                {"$set": doc},
                upsert=True,
            )
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error upserting stock data for {record.symbol}: {e}")
            return False

    async def get_stock_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieve stock data for a symbol."""
        return await self.stock_data.find_one(
            {"symbol": symbol}, {"_id": 0}
        )

    async def get_all_symbols(self) -> List[str]:
        """Get list of all symbols in the database."""
        cursor = self.stock_data.find({}, {"symbol": 1, "_id": 0})
        symbols: List[str] = []
        batch_size = 2000
        total_fetched = 0

        while True:
            batch = await cursor.to_list(length=batch_size)
            if not batch:
                break
            symbols.extend(d["symbol"] for d in batch if "symbol" in d)
            total_fetched += len(batch)

            # Safety hard-cap to avoid unbounded memory in extreme cases
            if total_fetched >= 100_000:
                logger.warning(
                    "get_all_symbols reached hard cap of 100000 symbols; results may be truncated"
                )
                break

        return symbols

    async def get_stocks_by_filter(
        self,
        sector: Optional[str] = None,
        cap_category: Optional[str] = None,
        min_completeness: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query stocks with filters."""
        query = {}
        if sector:
            query["stock_master.sector"] = sector
        if cap_category:
            query["stock_master.market_cap_category"] = cap_category

        cursor = self.stock_data.find(query, {"_id": 0}).limit(limit)
        results = await cursor.to_list(length=limit)

        if min_completeness is not None:
            results = [
                r for r in results
                if _calc_completeness(r) >= min_completeness
            ]

        return results

    # ===== Price History Operations =====

    async def upsert_price_history(
        self, symbol: str, history: List[Dict[str, Any]]
    ) -> int:
        """
        Insert or update price history records.

        Returns number of records upserted.
        """
        if not history:
            return 0

        operations = []
        for entry in history:
            operations.append({
                "filter": {"symbol": symbol, "date": entry["date"]},
                "update": {"$set": {**entry, "symbol": symbol}},
                "upsert": True,
            })

        from pymongo import UpdateOne

        count = 0
        # Batch in chunks of 500 with idempotent retry
        for i in range(0, len(operations), 500):
            batch = operations[i : i + 500]
            bulk_ops = [
                UpdateOne(op["filter"], op["update"], upsert=op["upsert"])
                for op in batch
            ]

            # Idempotent retry per batch: upserts can be safely retried.
            # If all retries fail for a batch, raise so the caller knows
            # the overall write was only partially successful.
            last_error: Optional[Exception] = None
            for attempt in range(3):
                try:
                    result = await self.price_history.bulk_write(
                        bulk_ops,
                        ordered=False,
                    )
                    count += result.upserted_count + result.modified_count
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Error upserting price history batch %s-%s for %s (attempt %s): %s",
                        i,
                        i + len(batch) - 1,
                        symbol,
                        attempt + 1,
                        e,
                    )
            if last_error is not None:
                logger.error(
                    "Failed to upsert price history batch %s-%s for %s after retries",
                    i,
                    i + len(batch) - 1,
                    symbol,
                    exc_info=last_error,
                )
                raise last_error

        return count

    async def get_price_history(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Retrieve price history for a symbol, newest first."""
        query = {"symbol": symbol}
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            query["date"] = date_filter

        cursor = (
            self.price_history
            .find(query, {"_id": 0, "symbol": 0})
            .sort("date", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    # ===== Extraction Log Operations =====

    async def log_extraction(self, record: ExtractionRecord) -> bool:
        """Log an extraction attempt."""
        try:
            doc = {
                "source": record.source,
                "symbol": record.symbol,
                "status": record.status.value,
                "fields_extracted": record.fields_extracted,
                "fields_failed": record.fields_failed,
                "started_at": record.started_at.isoformat(),
                "completed_at": (
                    record.completed_at.isoformat() if record.completed_at else None
                ),
                "duration_ms": record.duration_ms,
                "error_message": record.error_message,
                "retry_count": record.retry_count,
            }
            result = await self.extraction_log.insert_one(doc)
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error logging extraction: {e}")
            return False

    async def get_extraction_history(
        self,
        symbol: str,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get extraction history for a symbol."""
        query = {"symbol": symbol}
        if source:
            query["source"] = source

        cursor = (
            self.extraction_log
            .find(query, {"_id": 0})
            .sort("started_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    # ===== Quality Report Operations =====

    async def save_quality_report(self, report: QualityReport) -> bool:
        """Save a quality assessment report."""
        try:
            doc = {
                "symbol": report.symbol,
                "generated_at": report.generated_at.isoformat(),
                "completeness_score": report.completeness_score,
                "freshness_score": report.freshness_score,
                "source_agreement_score": report.source_agreement_score,
                "validation_score": report.validation_score,
                "overall_confidence": report.overall_confidence,
                "missing_critical_fields": report.missing_critical_fields,
                "stale_fields": report.stale_fields,
                "field_coverage_by_category": report.field_coverage_by_category,
            }
            result = await self.quality_reports.insert_one(doc)
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error saving quality report for {report.symbol}: {e}")
            return False

    # ===== Pipeline Job Operations =====

    async def save_pipeline_job(self, job: PipelineJob) -> bool:
        """Save a pipeline job record."""
        try:
            doc = {
                "job_id": job.job_id,
                "symbols": job.symbols,
                "sources": job.sources,
                "status": job.status.value,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "total_symbols": job.total_symbols,
                "processed_symbols": job.processed_symbols,
                "failed_symbols": job.failed_symbols,
                "errors": job.errors,
            }
            result = await self.pipeline_jobs.update_one(
                {"job_id": job.job_id},
                {"$set": doc},
                upsert=True,
            )
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error saving pipeline job {job.job_id}: {e}")
            return False


def _calc_completeness(doc: Dict[str, Any]) -> float:
    """Calculate completeness from a stock data document."""
    availability = doc.get("field_availability", {})
    total = len(availability)
    available = sum(1 for v in availability.values() if v)
    return (available / total * 100) if total > 0 else 0.0
