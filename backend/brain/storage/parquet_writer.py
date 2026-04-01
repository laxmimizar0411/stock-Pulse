"""
Parquet Writer — Serialization utilities for data lake archival.

Converts pandas DataFrames to/from Parquet format with schema validation
and compression. Used by MinIOClient for data lake operations.

Usage:
    writer = ParquetWriter()
    parquet_bytes = writer.dataframe_to_parquet(df)
    df_back = writer.parquet_to_dataframe(parquet_bytes)
"""

import io
import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("brain.storage.parquet_writer")

# Required columns for OHLCV data
OHLCV_REQUIRED_COLUMNS = {"symbol", "open", "high", "low", "close", "volume"}


class ParquetWriter:
    """
    Parquet serialization/deserialization with schema validation.
    """

    def __init__(self, compression: str = "snappy"):
        """
        Args:
            compression: Parquet compression codec (snappy, gzip, zstd, none).
        """
        self.compression = compression

    def dataframe_to_parquet(
        self,
        df: pd.DataFrame,
        validate_schema: bool = True,
    ) -> Optional[bytes]:
        """
        Serialize a DataFrame to Parquet bytes.

        Args:
            df: Input DataFrame.
            validate_schema: If True, validate OHLCV required columns exist.

        Returns:
            Parquet bytes, or None on error.
        """
        if df is None or df.empty:
            logger.warning("Empty DataFrame, skipping Parquet conversion")
            return None

        if validate_schema:
            df_cols = {c.lower() for c in df.columns}
            missing = OHLCV_REQUIRED_COLUMNS - df_cols
            if missing:
                logger.warning(
                    "DataFrame missing required columns: %s (has: %s)",
                    missing, list(df.columns),
                )
                # Don't fail — just warn. Partial data is still useful.

        try:
            buffer = io.BytesIO()
            df.to_parquet(
                buffer,
                engine="pyarrow",
                compression=self.compression,
                index=False,
            )
            parquet_bytes = buffer.getvalue()
            logger.debug(
                "Serialized DataFrame (%d rows, %d cols) to %d bytes Parquet (%s)",
                len(df), len(df.columns), len(parquet_bytes), self.compression,
            )
            return parquet_bytes

        except ImportError:
            logger.error(
                "pyarrow not installed — cannot write Parquet. "
                "Install with: pip install pyarrow"
            )
            return None

        except Exception:
            logger.exception("Error serializing DataFrame to Parquet")
            return None

    def parquet_to_dataframe(
        self,
        parquet_bytes: bytes,
        columns: Optional[List[str]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Deserialize Parquet bytes to a DataFrame.

        Args:
            parquet_bytes: Raw Parquet data.
            columns: Optional list of columns to read (for efficiency).

        Returns:
            DataFrame, or None on error.
        """
        if not parquet_bytes:
            return None

        try:
            buffer = io.BytesIO(parquet_bytes)
            df = pd.read_parquet(
                buffer,
                engine="pyarrow",
                columns=columns,
            )
            logger.debug(
                "Deserialized Parquet (%d bytes) to DataFrame (%d rows, %d cols)",
                len(parquet_bytes), len(df), len(df.columns),
            )
            return df

        except ImportError:
            logger.error("pyarrow not installed — cannot read Parquet")
            return None

        except Exception:
            logger.exception("Error deserializing Parquet data")
            return None

    def ohlcv_bars_to_parquet(
        self,
        bars: list,
    ) -> Optional[bytes]:
        """
        Convert a list of OHLCVBar Pydantic models to Parquet bytes.

        Args:
            bars: List of OHLCVBar objects.

        Returns:
            Parquet bytes.
        """
        if not bars:
            return None

        try:
            records = [bar.model_dump() for bar in bars]
            df = pd.DataFrame(records)

            # Ensure timestamp column is datetime
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])

            return self.dataframe_to_parquet(df, validate_schema=True)

        except Exception:
            logger.exception("Error converting OHLCVBar list to Parquet")
            return None

    def get_parquet_metadata(self, parquet_bytes: bytes) -> Optional[Dict]:
        """Get metadata from a Parquet file (row count, schema, size)."""
        if not parquet_bytes:
            return None

        try:
            import pyarrow.parquet as pq

            buffer = io.BytesIO(parquet_bytes)
            pf = pq.ParquetFile(buffer)
            metadata = pf.metadata

            return {
                "num_rows": metadata.num_rows,
                "num_columns": metadata.num_columns,
                "num_row_groups": metadata.num_row_groups,
                "schema": [str(col) for col in pf.schema],
                "size_bytes": len(parquet_bytes),
                "created_by": metadata.created_by,
            }

        except ImportError:
            return {"error": "pyarrow not installed"}
        except Exception:
            logger.exception("Error reading Parquet metadata")
            return None
