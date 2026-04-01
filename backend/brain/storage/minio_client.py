"""
MinIO Client — S3-compatible object storage for Stock Pulse data lake.

Manages raw data archival in Parquet format with date-partitioned paths:
    ohlcv/{symbol}/{year}/{month}/data.parquet

Falls back gracefully if MinIO is unavailable (logs and skips).

Usage:
    client = MinIOClient()
    await client.initialize()
    await client.upload_parquet("RELIANCE", "2025", "03", parquet_bytes)
    data = await client.download_parquet("RELIANCE", "2025", "03")
"""

import io
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("brain.storage.minio_client")

IST = timezone(timedelta(hours=5, minutes=30))

# Default configuration
DEFAULT_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
DEFAULT_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", os.getenv("MINIO_ROOT_USER", "stockpulse"))
DEFAULT_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", os.getenv("MINIO_ROOT_PASSWORD", "stockpulse123"))
DEFAULT_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Bucket names
OHLCV_BUCKET = "stockpulse-ohlcv"
FEATURES_BUCKET = "stockpulse-features"
RAW_BUCKET = "stockpulse-raw"


class MinIOClient:
    """
    MinIO (S3-compatible) client for data lake operations.

    Manages Parquet archival with date-partitioned paths.
    Falls back gracefully when MinIO is unavailable.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        access_key: str = DEFAULT_ACCESS_KEY,
        secret_key: str = DEFAULT_SECRET_KEY,
        secure: bool = DEFAULT_SECURE,
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self._client = None
        self._connected = False
        self._stats = {
            "uploads": 0,
            "downloads": 0,
            "errors": 0,
        }

    async def initialize(self) -> bool:
        """
        Initialize MinIO client and create required buckets.

        Returns True if connected, False if MinIO is unavailable.
        """
        try:
            from minio import Minio

            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

            # Test connectivity by listing buckets
            self._client.list_buckets()
            self._connected = True

            # Ensure required buckets exist
            for bucket in [OHLCV_BUCKET, FEATURES_BUCKET, RAW_BUCKET]:
                if not self._client.bucket_exists(bucket):
                    self._client.make_bucket(bucket)
                    logger.info("Created MinIO bucket: %s", bucket)

            logger.info("MinIO client connected to %s", self.endpoint)
            return True

        except ImportError:
            logger.warning(
                "minio package not installed — storage archival disabled. "
                "Install with: pip install minio"
            )
            return False

        except Exception as e:
            logger.warning(
                "MinIO unavailable at %s: %s — storage archival disabled",
                self.endpoint, e,
            )
            self._connected = False
            return False

    def upload_bytes(
        self,
        bucket: str,
        object_path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """
        Upload raw bytes to MinIO.

        Args:
            bucket: Bucket name.
            object_path: Object key/path within the bucket.
            data: Raw bytes to upload.
            content_type: MIME type of the data.

        Returns:
            True if successful.
        """
        if not self._connected or not self._client:
            logger.debug("[OFFLINE] Would upload %d bytes to %s/%s", len(data), bucket, object_path)
            return False

        try:
            self._client.put_object(
                bucket_name=bucket,
                object_name=object_path,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            self._stats["uploads"] += 1
            logger.debug("Uploaded %d bytes to %s/%s", len(data), bucket, object_path)
            return True

        except Exception:
            logger.exception("Error uploading to %s/%s", bucket, object_path)
            self._stats["errors"] += 1
            return False

    def upload_parquet(
        self,
        symbol: str,
        year: str,
        month: str,
        parquet_bytes: bytes,
        bucket: str = OHLCV_BUCKET,
    ) -> bool:
        """
        Upload Parquet data with date-partitioned path.

        Path format: ohlcv/{symbol}/{year}/{month}/data.parquet
        """
        object_path = f"{symbol.upper()}/{year}/{month}/data.parquet"
        return self.upload_bytes(
            bucket=bucket,
            object_path=object_path,
            data=parquet_bytes,
            content_type="application/octet-stream",
        )

    def download_bytes(
        self,
        bucket: str,
        object_path: str,
    ) -> Optional[bytes]:
        """
        Download raw bytes from MinIO.

        Returns None if object doesn't exist or MinIO is unavailable.
        """
        if not self._connected or not self._client:
            logger.debug("[OFFLINE] Would download %s/%s", bucket, object_path)
            return None

        try:
            response = self._client.get_object(bucket, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            self._stats["downloads"] += 1
            return data

        except Exception:
            logger.exception("Error downloading %s/%s", bucket, object_path)
            self._stats["errors"] += 1
            return None

    def download_parquet(
        self,
        symbol: str,
        year: str,
        month: str,
        bucket: str = OHLCV_BUCKET,
    ) -> Optional[bytes]:
        """
        Download Parquet data for a symbol/year/month.
        """
        object_path = f"{symbol.upper()}/{year}/{month}/data.parquet"
        return self.download_bytes(bucket, object_path)

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list:
        """List objects in a bucket with an optional prefix filter."""
        if not self._connected or not self._client:
            return []

        try:
            objects = self._client.list_objects(bucket, prefix=prefix, recursive=True)
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                }
                for obj in objects
            ]
        except Exception:
            logger.exception("Error listing objects in %s", bucket)
            return []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "connected": self._connected,
            "endpoint": self.endpoint,
        }

    async def health_check(self) -> dict:
        return {
            "status": "healthy" if self._connected else "unavailable",
            "endpoint": self.endpoint,
            "stats": self.get_stats(),
        }
