"""
Tests for Brain Ingestion Layer — Normalizer, Data Quality, Kafka Bridge.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ==================== Normalizer Tests ====================

class TestDataNormalizer:

    def _make_yfinance_df(self, rows: int = 10):
        """Create a YFinance-style DataFrame."""
        dates = pd.date_range("2025-01-01", periods=rows, freq="D")
        return pd.DataFrame({
            "Open": np.random.uniform(100, 200, rows),
            "High": np.random.uniform(200, 250, rows),
            "Low": np.random.uniform(80, 100, rows),
            "Close": np.random.uniform(100, 200, rows),
            "Volume": np.random.randint(100000, 1000000, rows),
        }, index=dates)

    def _make_nse_bhavcopy_df(self, rows: int = 5):
        """Create an NSE Bhavcopy-style DataFrame."""
        return pd.DataFrame({
            "SYMBOL": ["RELIANCE"] * rows,
            "OPEN": np.random.uniform(2400, 2500, rows),
            "HIGH": np.random.uniform(2500, 2600, rows),
            "LOW": np.random.uniform(2300, 2400, rows),
            "CLOSE": np.random.uniform(2400, 2500, rows),
            "TOTTRDQTY": np.random.randint(1000000, 5000000, rows),
            "TIMESTAMP": pd.date_range("2025-01-01", periods=rows, freq="D"),
            "DELIV_QTY": np.random.randint(500000, 2000000, rows),
            "DELIV_PER": np.random.uniform(30, 70, rows),
        })

    def test_normalize_yfinance(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        df = self._make_yfinance_df(10)
        bars = normalizer.normalize_ohlcv(df, source="yfinance", symbol="RELIANCE.NS")

        assert len(bars) == 10
        assert bars[0].symbol == "RELIANCE"
        assert bars[0].source == "yfinance"
        assert bars[0].exchange.value == "NSE"
        assert bars[0].timeframe == "1d"
        assert bars[0].open > 0
        assert bars[0].volume > 0

    def test_normalize_nse_bhavcopy(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        df = self._make_nse_bhavcopy_df(5)
        bars = normalizer.normalize_ohlcv(df, source="nse_bhavcopy", symbol="RELIANCE")

        assert len(bars) == 5
        assert bars[0].symbol == "RELIANCE"
        assert bars[0].delivery_volume is not None
        assert bars[0].delivery_pct is not None

    def test_normalize_empty_df(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        bars = normalizer.normalize_ohlcv(pd.DataFrame(), source="yfinance", symbol="TCS")
        assert bars == []

    def test_normalize_none_df(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        bars = normalizer.normalize_ohlcv(None, source="yfinance", symbol="TCS")
        assert bars == []

    def test_normalize_tick(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        tick = normalizer.normalize_tick(
            {"ltp": 2500.50, "volume": 100000},
            source="dhan",
            symbol="RELIANCE.NS",
        )
        assert tick is not None
        assert tick.symbol == "RELIANCE"
        assert tick.ltp == 2500.50
        assert tick.exchange.value == "NSE"

    def test_normalize_tick_no_ltp(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        tick = normalizer.normalize_tick(
            {"volume": 100000},
            source="dhan",
            symbol="TCS",
        )
        assert tick is None

    def test_exchange_inference(self):
        from brain.ingestion.normalizer import _infer_exchange, _clean_symbol
        from brain.schemas.market_data import Exchange

        assert _infer_exchange("RELIANCE.NS") == Exchange.NSE
        assert _infer_exchange("RELIANCE.BO") == Exchange.BSE
        assert _infer_exchange("RELIANCE") == Exchange.NSE  # default
        assert _clean_symbol("RELIANCE.NS") == "RELIANCE"
        assert _clean_symbol("TCS.BSE") == "TCS"

    def test_canonical_df_normalization(self):
        from brain.ingestion.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        df = pd.DataFrame({"Open": [100], "High": [110], "Low": [95], "Close": [105], "Volume": [10000]})
        result = normalizer.normalize_dataframe_to_canonical(df, source="yfinance")
        assert "open" in result.columns
        assert "close" in result.columns


# ==================== Data Quality Tests ====================

class TestDataQualityEngine:

    def _make_valid_bars(self, n: int = 5):
        from brain.schemas.market_data import OHLCVBar, Exchange
        ist = timezone(timedelta(hours=5, minutes=30))
        bars = []
        for i in range(n):
            bars.append(OHLCVBar(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                open=100 + i,
                high=110 + i,
                low=95 + i,
                close=105 + i,
                volume=100000 * (i + 1),
                timestamp=datetime(2025, 1, 1 + i, 15, 30, tzinfo=ist),
                source="test",
            ))
        return bars

    def test_valid_data_passes(self):
        from brain.ingestion.data_quality import DataQualityEngine
        engine = DataQualityEngine()
        bars = self._make_valid_bars(5)
        report = engine.validate_ohlcv_bars(bars)

        assert report.is_acceptable
        assert report.total_records == 5
        assert report.pass_rate > 0

    def test_ohlc_integrity_failure(self):
        from brain.schemas.market_data import OHLCVBar, Exchange
        from brain.ingestion.data_quality import DataQualityEngine

        ist = timezone(timedelta(hours=5, minutes=30))
        engine = DataQualityEngine()
        bars = [OHLCVBar(
            symbol="TEST",
            exchange=Exchange.NSE,
            timeframe="1d",
            open=100,
            high=90,  # High < Open — invalid!
            low=80,
            close=85,
            volume=10000,
            timestamp=datetime(2025, 1, 1, 15, 30, tzinfo=ist),
            source="test",
        )]
        report = engine.validate_ohlcv_bars(bars)

        # OHLC integrity check should fail
        ohlc_check = [r for r in report.results if r.check_name == "ohlc_integrity"]
        assert len(ohlc_check) == 1
        assert not ohlc_check[0].passed

    def test_negative_volume_fails(self):
        from brain.schemas.market_data import OHLCVBar, Exchange
        from brain.ingestion.data_quality import DataQualityEngine

        ist = timezone(timedelta(hours=5, minutes=30))
        engine = DataQualityEngine()
        bars = [OHLCVBar(
            symbol="TEST",
            exchange=Exchange.NSE,
            timeframe="1d",
            open=100,
            high=110,
            low=95,
            close=105,
            volume=-500,  # Negative volume!
            timestamp=datetime(2025, 1, 1, 15, 30, tzinfo=ist),
            source="test",
        )]
        report = engine.validate_ohlcv_bars(bars)
        assert not report.is_acceptable  # ERROR severity

    def test_empty_data_fails(self):
        from brain.ingestion.data_quality import DataQualityEngine
        engine = DataQualityEngine()
        report = engine.validate_ohlcv_bars([])
        assert not report.is_acceptable

    def test_single_bar_validation(self):
        from brain.ingestion.data_quality import DataQualityEngine
        engine = DataQualityEngine()
        bars = self._make_valid_bars(1)
        assert engine.validate_single_bar(bars[0])

    def test_quality_report_summary(self):
        from brain.ingestion.data_quality import DataQualityEngine
        engine = DataQualityEngine()
        bars = self._make_valid_bars(5)
        report = engine.validate_ohlcv_bars(bars)
        summary = report.summary()

        assert "symbol" in summary
        assert "pass_rate" in summary
        assert "is_acceptable" in summary
        assert summary["total_records"] == 5


# ==================== Kafka Bridge Tests ====================

class TestKafkaBridge:

    def _make_yfinance_df(self):
        dates = pd.date_range("2025-01-01", periods=5, freq="D")
        return pd.DataFrame({
            "Open": [100, 102, 104, 103, 105],
            "High": [110, 112, 114, 113, 115],
            "Low": [95, 97, 99, 98, 100],
            "Close": [105, 107, 109, 108, 110],
            "Volume": [100000, 120000, 110000, 130000, 115000],
        }, index=dates)

    @pytest.mark.asyncio
    async def test_bridge_standalone_mode(self):
        from brain.ingestion.kafka_bridge import KafkaBridge
        bridge = KafkaBridge(kafka_manager=None)  # No Kafka

        df = self._make_yfinance_df()
        report = await bridge.publish_ohlcv(df, source="yfinance", symbol="RELIANCE.NS")

        assert report.is_acceptable
        assert bridge.get_stats()["bars_published"] == 5

    @pytest.mark.asyncio
    async def test_bridge_empty_df(self):
        from brain.ingestion.kafka_bridge import KafkaBridge
        bridge = KafkaBridge(kafka_manager=None)

        report = await bridge.publish_ohlcv(pd.DataFrame(), source="yfinance", symbol="TCS")
        assert not report.is_acceptable

    @pytest.mark.asyncio
    async def test_bridge_tick_standalone(self):
        from brain.ingestion.kafka_bridge import KafkaBridge
        bridge = KafkaBridge(kafka_manager=None)

        success = await bridge.publish_tick(
            {"ltp": 3500.0, "volume": 50000},
            source="dhan",
            symbol="TCS",
        )
        assert success
        assert bridge.get_stats()["ticks_published"] == 1

    @pytest.mark.asyncio
    async def test_bridge_batch_publish(self):
        from brain.ingestion.kafka_bridge import KafkaBridge
        bridge = KafkaBridge(kafka_manager=None)

        dfs = {
            "RELIANCE": self._make_yfinance_df(),
            "TCS": self._make_yfinance_df(),
        }
        reports = await bridge.publish_batch(dfs, source="yfinance")

        assert len(reports) == 2
        assert all(r.is_acceptable for r in reports.values())
        assert bridge.get_stats()["bars_published"] == 10


# ==================== Feature Store Tests ====================

class TestFeatureStore:

    def test_feature_key_generation(self):
        from brain.features.feature_store import _feature_key, _feature_meta_key
        key = _feature_key("RELIANCE")
        assert "brain:features" in key
        assert "RELIANCE" in key

        meta_key = _feature_meta_key("TCS")
        assert "meta" in meta_key

    @pytest.mark.asyncio
    async def test_store_no_redis(self):
        from brain.features.feature_store import FeatureStore
        store = FeatureStore(redis_client=None)

        # Should work without Redis (returns True for put, None for get)
        result = await store.put_online("RELIANCE", {"rsi_14": 55.0, "macd": 0.5})
        assert result is True

        features = await store.get_online("RELIANCE")
        assert features is None

    @pytest.mark.asyncio
    async def test_store_no_pg(self):
        from brain.features.feature_store import FeatureStore
        store = FeatureStore(pg_pool=None)

        result = await store.put_historical(
            "RELIANCE",
            datetime.now(timezone.utc),
            {"rsi_14": 55.0},
        )
        assert result is True

        history = await store.get_historical(
            "RELIANCE",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert history == []

    def test_store_stats(self):
        from brain.features.feature_store import FeatureStore
        store = FeatureStore()
        stats = store.get_stats()
        assert "cache_hit_rate" in stats
        assert "current_ttl" in stats
        assert "version" in stats


# ==================== Storage Tests ====================

class TestParquetWriter:

    def test_roundtrip(self):
        from brain.storage.parquet_writer import ParquetWriter
        writer = ParquetWriter()

        df = pd.DataFrame({
            "symbol": ["RELIANCE"] * 5,
            "open": [100.0, 102.0, 104.0, 103.0, 105.0],
            "high": [110.0, 112.0, 114.0, 113.0, 115.0],
            "low": [95.0, 97.0, 99.0, 98.0, 100.0],
            "close": [105.0, 107.0, 109.0, 108.0, 110.0],
            "volume": [100000, 120000, 110000, 130000, 115000],
        })

        # Serialize
        parquet_bytes = writer.dataframe_to_parquet(df)
        assert parquet_bytes is not None
        assert len(parquet_bytes) > 0

        # Deserialize
        df_back = writer.parquet_to_dataframe(parquet_bytes)
        assert df_back is not None
        assert len(df_back) == 5
        assert list(df_back.columns) == list(df.columns)
        assert df_back["close"].iloc[0] == 105.0

    def test_empty_df(self):
        from brain.storage.parquet_writer import ParquetWriter
        writer = ParquetWriter()

        result = writer.dataframe_to_parquet(pd.DataFrame())
        assert result is None

    def test_none_input(self):
        from brain.storage.parquet_writer import ParquetWriter
        writer = ParquetWriter()

        assert writer.dataframe_to_parquet(None) is None
        assert writer.parquet_to_dataframe(None) is None
        assert writer.parquet_to_dataframe(b"") is None

    def test_ohlcv_bars_to_parquet(self):
        from brain.storage.parquet_writer import ParquetWriter
        from brain.schemas.market_data import OHLCVBar, Exchange

        ist = timezone(timedelta(hours=5, minutes=30))
        writer = ParquetWriter()
        bars = [
            OHLCVBar(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                open=100, high=110, low=95, close=105,
                volume=100000,
                timestamp=datetime(2025, 1, 1, 15, 30, tzinfo=ist),
                source="test",
            ),
        ]

        parquet_bytes = writer.ohlcv_bars_to_parquet(bars)
        assert parquet_bytes is not None

        df = writer.parquet_to_dataframe(parquet_bytes)
        assert len(df) == 1
        assert df["symbol"].iloc[0] == "RELIANCE"

    def test_parquet_metadata(self):
        from brain.storage.parquet_writer import ParquetWriter
        writer = ParquetWriter()

        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        parquet_bytes = writer.dataframe_to_parquet(df, validate_schema=False)
        meta = writer.get_parquet_metadata(parquet_bytes)

        assert meta is not None
        assert meta["num_rows"] == 3
        assert meta["num_columns"] == 2


class TestMinIOClient:

    def test_offline_mode(self):
        from brain.storage.minio_client import MinIOClient
        client = MinIOClient()
        # Without initialize(), client is in offline mode
        assert not client.is_connected

        result = client.upload_bytes("test-bucket", "test.txt", b"hello")
        assert result is False  # offline mode

        data = client.download_bytes("test-bucket", "test.txt")
        assert data is None

    def test_stats(self):
        from brain.storage.minio_client import MinIOClient
        client = MinIOClient()
        stats = client.get_stats()
        assert "connected" in stats
        assert stats["connected"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
