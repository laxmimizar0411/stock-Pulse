"""
Brain Engine — Lifecycle management for the Stock Pulse Brain.

Handles startup, shutdown, and provides access to all Brain subsystems.
This is the main entry point for integrating the Brain with the FastAPI app.
"""

import asyncio
import logging
from typing import Optional

from brain.config import BrainConfig, brain_config
from brain.events.kafka_manager import KafkaConfig, KafkaManager

logger = logging.getLogger("brain.engine")


class BrainEngine:
    """
    Central Brain engine — manages all subsystems.

    Usage in FastAPI:
        brain = BrainEngine()

        @app.on_event("startup")
        async def startup():
            await brain.start()

        @app.on_event("shutdown")
        async def shutdown():
            await brain.stop()
    """

    def __init__(self, config: Optional[BrainConfig] = None):
        self.config = config or brain_config
        self._started = False

        # Core subsystems (initialized on start)
        self.kafka: Optional[KafkaManager] = None

        # Future subsystems (Phase 2+)
        # self.feature_store = None
        # self.model_server = None
        # self.signal_generator = None
        # self.risk_manager = None
        # self.agent_orchestrator = None

    async def start(self):
        """Start all Brain subsystems."""
        if self._started:
            logger.warning("Brain engine already started")
            return

        logger.info("=" * 60)
        logger.info("Starting Stock Pulse Brain v%s", self.config.version)
        logger.info("=" * 60)

        # 1. Start Kafka event bus
        if self.config.kafka.enabled:
            kafka_config = KafkaConfig(
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                client_id=self.config.kafka.client_id,
                group_id=self.config.kafka.group_id,
            )
            self.kafka = KafkaManager(kafka_config)
            connected = await self.kafka.start()

            if connected:
                # Create topics if they don't exist
                await self.kafka.create_topics()
                logger.info("✅ Kafka event bus: CONNECTED")
            else:
                logger.warning("⚠️  Kafka event bus: STUB MODE (no broker available)")
        else:
            logger.info("⏭️  Kafka event bus: DISABLED by config")
            self.kafka = KafkaManager()  # Stub instance

        # 2. Future: Feature Store
        # logger.info("Starting feature store...")

        # 3. Future: Model Server
        # logger.info("Starting model server...")

        # 4. Future: Signal Generator
        # logger.info("Starting signal generator...")

        # 5. Future: Risk Manager
        # logger.info("Starting risk manager...")

        # 6. Future: Agent Orchestrator
        # logger.info("Starting agent orchestrator...")

        self._started = True
        logger.info("=" * 60)
        logger.info("Stock Pulse Brain READY")
        logger.info("=" * 60)

    async def stop(self):
        """Gracefully stop all Brain subsystems."""
        if not self._started:
            return

        logger.info("Shutting down Stock Pulse Brain...")

        # Stop in reverse order of startup
        if self.kafka:
            await self.kafka.stop()

        self._started = False
        logger.info("Stock Pulse Brain stopped")

    async def health_check(self) -> dict:
        """Return health status of all Brain subsystems."""
        health = {
            "brain_version": self.config.version,
            "started": self._started,
            "subsystems": {},
        }

        if self.kafka:
            health["subsystems"]["kafka"] = await self.kafka.health_check()

        # Overall status
        all_healthy = all(
            s.get("status") == "healthy"
            for s in health["subsystems"].values()
        )
        health["status"] = "healthy" if (all_healthy and self._started) else "degraded"

        return health

    def get_config_summary(self) -> dict:
        """Return a summary of the brain configuration."""
        return self.config.to_dict()


# Global Brain engine singleton
brain_engine = BrainEngine()
