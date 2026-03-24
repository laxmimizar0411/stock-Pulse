"""
Kafka Manager — Producer/Consumer wrapper for Stock Pulse Brain.

Provides a clean async interface for producing and consuming Kafka messages
with serialization, error handling, dead-letter queue support, and health checks.

Uses `aiokafka` for async Kafka operations within the FastAPI event loop.
Falls back to a no-op stub if Kafka is unavailable (development mode).
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("brain.events.kafka")


class KafkaConfig:
    """Kafka connection configuration."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        client_id: str = "stockpulse-brain",
        group_id: str = "stockpulse-brain-group",
        auto_offset_reset: str = "latest",
        enable_auto_commit: bool = True,
        max_poll_interval_ms: int = 300_000,
        session_timeout_ms: int = 30_000,
        request_timeout_ms: int = 40_000,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.group_id = group_id
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self.max_poll_interval_ms = max_poll_interval_ms
        self.session_timeout_ms = session_timeout_ms
        self.request_timeout_ms = request_timeout_ms


class KafkaManager:
    """
    Async Kafka producer/consumer manager.

    Usage:
        manager = KafkaManager(config)
        await manager.start()

        # Produce
        await manager.produce("stockpulse.signals", key="RELIANCE", value={...})

        # Consume (register handler before starting)
        manager.register_handler("stockpulse.signals", my_handler)

        await manager.stop()
    """

    def __init__(self, config: Optional[KafkaConfig] = None):
        self.config = config or KafkaConfig()
        self._producer = None
        self._consumers: dict[str, Any] = {}
        self._handlers: dict[str, list[Callable]] = {}
        self._consumer_tasks: list[asyncio.Task] = []
        self._running = False
        self._connected = False
        self._stats = {
            "messages_produced": 0,
            "messages_consumed": 0,
            "errors": 0,
            "dlq_messages": 0,
        }

    async def start(self) -> bool:
        """Start the Kafka producer and all registered consumers."""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.config.bootstrap_servers,
                client_id=self.config.client_id,
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                compression_type="lz4",
                acks="all",
                request_timeout_ms=self.config.request_timeout_ms,
                linger_ms=5,  # Small batch window for latency/throughput balance
            )
            await self._producer.start()
            self._connected = True
            self._running = True
            logger.info(
                "Kafka producer connected to %s", self.config.bootstrap_servers
            )

            # Start consumer tasks for registered handlers
            for topic in self._handlers:
                task = asyncio.create_task(self._consume_loop(topic))
                self._consumer_tasks.append(task)

            return True

        except ImportError:
            logger.warning(
                "aiokafka not installed — running in stub mode (no Kafka). "
                "Install with: pip install aiokafka"
            )
            self._connected = False
            self._running = True
            return False

        except Exception as e:
            logger.error("Failed to connect to Kafka: %s", e)
            self._connected = False
            self._running = True
            return False

    async def stop(self):
        """Gracefully stop producer and all consumers."""
        self._running = False

        # Cancel consumer tasks
        for task in self._consumer_tasks:
            task.cancel()
        if self._consumer_tasks:
            await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        self._consumer_tasks.clear()

        # Stop consumers
        for consumer in self._consumers.values():
            try:
                await consumer.stop()
            except Exception as e:
                logger.error("Error stopping consumer: %s", e)
        self._consumers.clear()

        # Stop producer
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as e:
                logger.error("Error stopping producer: %s", e)
            self._producer = None

        self._connected = False
        logger.info("Kafka manager stopped")

    async def produce(
        self,
        topic: str,
        value: dict,
        key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Produce a message to a Kafka topic.

        Args:
            topic: Kafka topic name
            value: Message payload (dict, will be JSON-serialized)
            key: Optional partition key (e.g., stock symbol)
            headers: Optional message headers

        Returns:
            True if successfully sent, False otherwise
        """
        if not self._connected or not self._producer:
            # Stub mode — log and return
            logger.debug("[STUB] Would produce to %s: key=%s", topic, key)
            self._stats["messages_produced"] += 1
            return True

        try:
            kafka_headers = None
            if headers:
                kafka_headers = [
                    (k, v.encode("utf-8")) for k, v in headers.items()
                ]

            # Add standard metadata
            value["_meta"] = {
                "timestamp": time.time(),
                "source": self.config.client_id,
                "topic": topic,
            }

            await self._producer.send_and_wait(
                topic=topic,
                key=key,
                value=value,
                headers=kafka_headers,
            )
            self._stats["messages_produced"] += 1
            return True

        except Exception as e:
            logger.error("Failed to produce to %s: %s", topic, e)
            self._stats["errors"] += 1
            await self._send_to_dlq(topic, value, key, str(e))
            return False

    def register_handler(
        self,
        topic: str,
        handler: Callable,
    ):
        """
        Register a message handler for a topic.

        The handler is a coroutine: async def handler(key, value, headers)

        Must be called BEFORE start().
        """
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)
        logger.info("Registered handler for topic: %s", topic)

    async def _consume_loop(self, topic: str):
        """Internal consumer loop for a single topic."""
        try:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.config.bootstrap_servers,
                group_id=f"{self.config.group_id}-{topic.split('.')[-1]}",
                auto_offset_reset=self.config.auto_offset_reset,
                enable_auto_commit=self.config.enable_auto_commit,
                key_deserializer=lambda k: k.decode("utf-8") if k else None,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                max_poll_interval_ms=self.config.max_poll_interval_ms,
                session_timeout_ms=self.config.session_timeout_ms,
            )
            await consumer.start()
            self._consumers[topic] = consumer
            logger.info("Consumer started for topic: %s", topic)

            async for msg in consumer:
                if not self._running:
                    break
                try:
                    handlers = self._handlers.get(topic, [])
                    for handler in handlers:
                        await handler(
                            key=msg.key,
                            value=msg.value,
                            headers=dict(msg.headers) if msg.headers else {},
                        )
                    self._stats["messages_consumed"] += 1

                except Exception as e:
                    logger.error(
                        "Error processing message from %s: %s", topic, e
                    )
                    self._stats["errors"] += 1
                    await self._send_to_dlq(
                        topic, msg.value, msg.key, str(e)
                    )

        except asyncio.CancelledError:
            logger.info("Consumer for %s cancelled", topic)
        except ImportError:
            logger.warning("aiokafka not available for consumer on %s", topic)
        except Exception as e:
            logger.error("Consumer loop error for %s: %s", topic, e)

    async def _send_to_dlq(
        self,
        original_topic: str,
        value: Any,
        key: Optional[str],
        error: str,
    ):
        """Send failed messages to the dead-letter queue."""
        if not self._connected or not self._producer:
            logger.debug("[STUB] DLQ: %s -> %s", original_topic, error)
            self._stats["dlq_messages"] += 1
            return

        try:
            from brain.events.topics import DEAD_LETTER_QUEUE

            dlq_message = {
                "original_topic": original_topic,
                "original_key": key,
                "original_value": value,
                "error": error,
                "timestamp": time.time(),
            }
            await self._producer.send_and_wait(
                topic=DEAD_LETTER_QUEUE.name,
                key=key,
                value=dlq_message,
            )
            self._stats["dlq_messages"] += 1

        except Exception as e:
            logger.error("Failed to send to DLQ: %s", e)

    async def create_topics(self):
        """
        Create all defined topics if they don't exist.
        Requires kafka-python or confluent-kafka admin client.
        """
        try:
            from aiokafka.admin import AIOKafkaAdminClient, NewTopic
            from brain.events.topics import ALL_TOPICS

            admin = AIOKafkaAdminClient(
                bootstrap_servers=self.config.bootstrap_servers,
            )
            await admin.start()

            new_topics = [
                NewTopic(
                    name=t.name,
                    num_partitions=t.partitions,
                    replication_factor=t.replication_factor,
                )
                for t in ALL_TOPICS
            ]

            try:
                await admin.create_topics(new_topics)
                logger.info("Created %d Kafka topics", len(new_topics))
            except Exception as e:
                # Topics may already exist
                logger.info("Topics may already exist: %s", e)

            await admin.close()

        except ImportError:
            logger.warning(
                "aiokafka admin not available — skip topic creation"
            )
        except Exception as e:
            logger.error("Failed to create topics: %s", e)

    def get_stats(self) -> dict:
        """Return producer/consumer statistics."""
        return {
            **self._stats,
            "connected": self._connected,
            "running": self._running,
            "active_consumers": len(self._consumers),
            "registered_topics": list(self._handlers.keys()),
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health_check(self) -> dict:
        """Return health status of Kafka connection."""
        return {
            "status": "healthy" if self._connected else "degraded",
            "mode": "live" if self._connected else "stub",
            "bootstrap_servers": self.config.bootstrap_servers,
            "stats": self.get_stats(),
        }
