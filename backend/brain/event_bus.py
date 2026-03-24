"""
Brain Event Bus

Async in-process event bus with a Kafka-compatible interface.
Uses asyncio.Queue per topic for publish/subscribe messaging.

The interface is designed so that migrating to Kafka later requires
only swapping this implementation — callers don't change.

Usage:
    bus = EventBus()
    await bus.start()

    # Subscribe
    async def on_signal(event):
        print(f"Signal: {event.symbol} {event.direction}")

    bus.subscribe("signal.generated", on_signal)

    # Publish
    await bus.publish("signal.generated", signal_event)

    # Cleanup
    await bus.stop()
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from brain.config import get_brain_config
from brain.models.events import BrainEvent

logger = logging.getLogger(__name__)

Callback = Callable[[BrainEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Async in-process event bus with topic-based pub/sub."""

    def __init__(self, max_queue_size: int = 0):
        config = get_brain_config()
        self._max_queue_size = max_queue_size or config.event_bus_max_queue_size
        self._subscribers: Dict[str, List[Callback]] = defaultdict(list)
        self._queues: Dict[str, asyncio.Queue] = {}
        self._consumer_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._event_count = 0
        self._error_count = 0
        self._started_at: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def topics(self) -> Set[str]:
        return set(self._subscribers.keys())

    async def start(self):
        """Start the event bus and all consumer loops."""
        if self._running:
            return
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("Brain EventBus started")

    async def stop(self):
        """Stop the event bus and cancel all consumer tasks."""
        self._running = False
        for topic, task in self._consumer_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()
        self._queues.clear()
        logger.info(
            "Brain EventBus stopped (processed %d events, %d errors)",
            self._event_count,
            self._error_count,
        )

    def subscribe(self, topic: str, callback: Callback):
        """
        Subscribe a callback to a topic.

        Args:
            topic: Topic name (e.g., "signal.generated", "regime.changed")
            callback: Async function that receives a BrainEvent
        """
        self._subscribers[topic].append(callback)

        # Ensure topic has a queue and consumer
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue(maxsize=self._max_queue_size)
            if self._running:
                self._consumer_tasks[topic] = asyncio.create_task(
                    self._consume_loop(topic)
                )

        logger.debug("Subscribed to topic '%s' (%d subscribers)", topic, len(self._subscribers[topic]))

    def unsubscribe(self, topic: str, callback: Callback):
        """Remove a callback from a topic."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(callback)
            except ValueError:
                pass

    async def publish(self, topic: str, event: BrainEvent):
        """
        Publish an event to a topic.

        Args:
            topic: Topic name
            event: The event to publish
        """
        if not self._running:
            logger.warning("EventBus not running, dropping event on '%s'", topic)
            return

        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue(maxsize=self._max_queue_size)
            self._consumer_tasks[topic] = asyncio.create_task(
                self._consume_loop(topic)
            )

        try:
            self._queues[topic].put_nowait(event)
            self._event_count += 1
        except asyncio.QueueFull:
            logger.warning(
                "EventBus queue full for topic '%s', dropping event %s",
                topic,
                event.event_id,
            )
            self._error_count += 1

    async def _consume_loop(self, topic: str):
        """Consumer loop for a single topic."""
        config = get_brain_config()
        queue = self._queues[topic]

        while self._running:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=config.event_bus_consumer_timeout
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            callbacks = self._subscribers.get(topic, [])
            for callback in callbacks:
                try:
                    await callback(event)
                except Exception:
                    self._error_count += 1
                    logger.exception(
                        "Error in subscriber callback for topic '%s'", topic
                    )

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            "running": self._running,
            "total_events": self._event_count,
            "total_errors": self._error_count,
            "topics": list(self._subscribers.keys()),
            "subscribers_per_topic": {
                t: len(cbs) for t, cbs in self._subscribers.items()
            },
            "queue_sizes": {
                t: q.qsize() for t, q in self._queues.items()
            },
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }


# Singleton instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def init_event_bus() -> EventBus:
    """Initialize and start the global EventBus."""
    bus = get_event_bus()
    await bus.start()
    return bus


async def shutdown_event_bus():
    """Stop and cleanup the global EventBus."""
    global _event_bus
    if _event_bus is not None:
        await _event_bus.stop()
        _event_bus = None
