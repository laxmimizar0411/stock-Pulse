"""
Kafka Bridge — Connects existing extractors to the Brain event pipeline.

Bridges the gap between the existing data extraction layer
(backend/data_extraction/) and the Brain's Kafka-based event pipeline.
Ingested data is normalized, quality-checked, and published to Kafka topics.

Usage:
    bridge = KafkaBridge(kafka_manager)
    await bridge.publish_ohlcv(raw_df, source="yfinance", symbol="RELIANCE")
    await bridge.publish_tick(raw_dict, source="dhan", symbol="TCS")
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from brain.ingestion.normalizer import DataNormalizer
from brain.ingestion.data_quality import DataQualityEngine, QualityReport

logger = logging.getLogger("brain.ingestion.kafka_bridge")


class KafkaBridge:
    """
    Bridge between existing extractors and the Brain Kafka event pipeline.

    Flow: Raw data → Normalizer → Quality Check → Kafka topic
    """

    def __init__(self, kafka_manager=None):
        """
        Args:
            kafka_manager: Optional KafkaManager instance. If None, operates
                          in standalone mode (normalize + validate only).
        """
        self.kafka = kafka_manager
        self.normalizer = DataNormalizer()
        self.quality_engine = DataQualityEngine()
        self._stats = {
            "bars_published": 0,
            "ticks_published": 0,
            "quality_rejections": 0,
            "publish_errors": 0,
        }

    async def publish_ohlcv(
        self,
        raw_df: pd.DataFrame,
        source: str,
        symbol: str,
        timeframe: str = "1d",
    ) -> QualityReport:
        """
        Normalize, validate, and publish OHLCV data to Kafka.

        Args:
            raw_df: Raw DataFrame from any extractor.
            source: Data source identifier (yfinance, dhan, groww, nse_bhavcopy).
            symbol: Stock symbol.
            timeframe: Candle timeframe.

        Returns:
            QualityReport from the validation step.
        """
        # Step 1: Normalize
        bars = self.normalizer.normalize_ohlcv(raw_df, source, symbol, timeframe)
        if not bars:
            report = QualityReport(
                symbol=symbol, source=source, total_records=0,
            )
            report.is_acceptable = False
            return report

        # Step 2: Quality check
        report = self.quality_engine.validate_ohlcv_bars(bars, symbol, source)

        if not report.is_acceptable:
            logger.warning(
                "Data quality check failed for %s (%s): %s",
                symbol, source, report.summary(),
            )
            self._stats["quality_rejections"] += 1

            # Route to DLQ if Kafka is available
            if self.kafka:
                await self.kafka.produce(
                    topic="stockpulse.dlq",
                    key=symbol,
                    value={
                        "reason": "quality_check_failed",
                        "symbol": symbol,
                        "source": source,
                        "report": report.summary(),
                    },
                )
            return report

        # Step 3: Publish to Kafka
        if self.kafka:
            for bar in bars:
                success = await self.kafka.produce(
                    topic="stockpulse.normalized-ohlcv",
                    key=bar.symbol,
                    value=bar.model_dump(mode="json"),
                )
                if success:
                    self._stats["bars_published"] += 1
                else:
                    self._stats["publish_errors"] += 1
        else:
            # Standalone mode — just count as published
            self._stats["bars_published"] += len(bars)
            logger.debug(
                "[STANDALONE] Would publish %d bars for %s to Kafka",
                len(bars), symbol,
            )

        return report

    async def publish_tick(
        self,
        raw_data: Dict,
        source: str,
        symbol: str,
    ) -> bool:
        """
        Normalize and publish a single tick to Kafka.

        Args:
            raw_data: Raw tick data dict.
            source: Data source identifier.
            symbol: Stock symbol.

        Returns:
            True if tick was successfully published.
        """
        tick = self.normalizer.normalize_tick(raw_data, source, symbol)
        if tick is None:
            return False

        if self.kafka:
            success = await self.kafka.produce(
                topic="stockpulse.raw-ticks",
                key=tick.symbol,
                value=tick.model_dump(mode="json"),
            )
            if success:
                self._stats["ticks_published"] += 1
            else:
                self._stats["publish_errors"] += 1
            return success
        else:
            self._stats["ticks_published"] += 1
            return True

    async def publish_batch(
        self,
        raw_dfs: Dict[str, pd.DataFrame],
        source: str,
        timeframe: str = "1d",
    ) -> Dict[str, QualityReport]:
        """
        Publish OHLCV data for multiple symbols in batch.

        Args:
            raw_dfs: Dict mapping symbol → raw DataFrame.
            source: Data source identifier.
            timeframe: Candle timeframe.

        Returns:
            Dict mapping symbol → QualityReport.
        """
        reports = {}
        for symbol, df in raw_dfs.items():
            try:
                report = await self.publish_ohlcv(df, source, symbol, timeframe)
                reports[symbol] = report
            except Exception:
                logger.exception("Error publishing batch data for %s", symbol)
                reports[symbol] = QualityReport(
                    symbol=symbol, source=source, total_records=0,
                )
                reports[symbol].is_acceptable = False

        logger.info(
            "Batch publish complete: %d symbols, %d acceptable, %d rejected",
            len(reports),
            sum(1 for r in reports.values() if r.is_acceptable),
            sum(1 for r in reports.values() if not r.is_acceptable),
        )
        return reports

    def get_stats(self) -> Dict:
        """Return bridge processing statistics."""
        return {**self._stats}
