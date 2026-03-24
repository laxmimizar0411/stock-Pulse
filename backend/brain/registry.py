"""
Brain Service Registry

Manages Brain module lifecycle — initialization, health checks,
and dependency injection into the FastAPI application.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.config import BrainConfig, get_brain_config
from brain.event_bus import EventBus, get_event_bus, init_event_bus, shutdown_event_bus
from brain.models.signals import BrainStatus

logger = logging.getLogger(__name__)


class BrainRegistry:
    """
    Central registry for all Brain modules.

    Handles startup/shutdown ordering and provides
    health status for the /api/brain/status endpoint.
    """

    def __init__(self):
        self._config: Optional[BrainConfig] = None
        self._event_bus: Optional[EventBus] = None
        self._modules: Dict[str, Any] = {}
        self._started = False
        self._start_time: Optional[float] = None

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def config(self) -> BrainConfig:
        if self._config is None:
            self._config = get_brain_config()
        return self._config

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = get_event_bus()
        return self._event_bus

    def register_module(self, name: str, module: Any):
        """Register a Brain module by name."""
        self._modules[name] = module
        logger.info("Brain module registered: %s", name)

    def get_module(self, name: str) -> Optional[Any]:
        """Get a registered module by name."""
        return self._modules.get(name)

    async def startup(self):
        """Initialize all Brain modules in dependency order."""
        if self._started:
            return

        self._start_time = time.monotonic()
        self._config = get_brain_config()

        # 1. Start event bus
        self._event_bus = await init_event_bus()
        logger.info("Brain EventBus initialized")

        # 2. Initialize enabled modules (to be populated in later phases)
        # Each phase will add its module initialization here
        enabled = []
        disabled = []

        module_checks = [
            ("features", self._config.modules.features_enabled),
            ("regime", self._config.modules.regime_enabled),
            ("ml_models", self._config.modules.ml_models_enabled),
            ("signal_fusion", self._config.modules.signal_fusion_enabled),
            ("sentiment", self._config.modules.sentiment_enabled),
            ("agents", self._config.modules.agents_enabled),
            ("risk_engine", self._config.modules.risk_engine_enabled),
            ("options", self._config.modules.options_enabled),
            ("tax", self._config.modules.tax_enabled),
            ("rag", self._config.modules.rag_enabled),
            ("deep_learning", self._config.modules.deep_learning_enabled),
        ]

        for name, is_enabled in module_checks:
            if is_enabled:
                enabled.append(name)
            else:
                disabled.append(name)

        self._started = True
        logger.info(
            "Brain started — enabled modules: %s | disabled: %s",
            enabled,
            disabled,
        )

    async def shutdown(self):
        """Shut down all Brain modules in reverse order."""
        if not self._started:
            return

        # Shutdown modules in reverse registration order
        for name in reversed(list(self._modules.keys())):
            module = self._modules[name]
            if hasattr(module, "shutdown"):
                try:
                    await module.shutdown()
                except Exception:
                    logger.exception("Error shutting down module: %s", name)

        # Stop event bus
        await shutdown_event_bus()
        self._event_bus = None

        self._started = False
        logger.info("Brain shut down")

    def get_status(self) -> BrainStatus:
        """Get current Brain status for the API."""
        config = self.config
        uptime = time.monotonic() - self._start_time if self._start_time else 0.0

        module_flags = {
            "features": config.modules.features_enabled,
            "regime": config.modules.regime_enabled,
            "ml_models": config.modules.ml_models_enabled,
            "signal_fusion": config.modules.signal_fusion_enabled,
            "sentiment": config.modules.sentiment_enabled,
            "agents": config.modules.agents_enabled,
            "risk_engine": config.modules.risk_engine_enabled,
            "options": config.modules.options_enabled,
            "tax": config.modules.tax_enabled,
            "rag": config.modules.rag_enabled,
            "deep_learning": config.modules.deep_learning_enabled,
        }

        return BrainStatus(
            version="0.1.0",
            status="operational" if self._started else "stopped",
            modules=module_flags,
            current_regime=None,  # Will be populated by regime module
            active_signals_count=0,  # Will be populated by signal module
            models_loaded=list(self._modules.keys()),
            last_feature_computation=None,
            last_model_prediction=None,
            uptime_seconds=uptime,
        )


# Singleton
_registry: Optional[BrainRegistry] = None


def get_brain_registry() -> BrainRegistry:
    """Get or create the Brain registry singleton."""
    global _registry
    if _registry is None:
        _registry = BrainRegistry()
    return _registry


async def init_brain() -> BrainRegistry:
    """Initialize the Brain and return the registry."""
    registry = get_brain_registry()
    await registry.startup()
    return registry


async def shutdown_brain():
    """Shut down the Brain."""
    global _registry
    if _registry is not None:
        await _registry.shutdown()
        _registry = None
