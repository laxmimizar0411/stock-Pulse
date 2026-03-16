"""
WebSocket Manager for Real-time Price Streaming
Handles WebSocket connections and broadcasts price updates to clients
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Set, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and subscriptions"""
    
    def __init__(self):
        # Active WebSocket connections
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Symbol subscriptions: symbol -> set of connection_ids
        self.subscriptions: Dict[str, Set[str]] = {}
        
        # Reverse mapping: connection_id -> set of symbols
        self.connection_subscriptions: Dict[str, Set[str]] = {}
        
        # Last known prices for caching
        self.price_cache: Dict[str, Dict] = {}
        
        # Background task reference
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, client_id: str):
        """Handle client disconnection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        
        # Clean up subscriptions
        if client_id in self.connection_subscriptions:
            for symbol in self.connection_subscriptions[client_id]:
                if symbol in self.subscriptions:
                    self.subscriptions[symbol].discard(client_id)
                    if not self.subscriptions[symbol]:
                        del self.subscriptions[symbol]
            del self.connection_subscriptions[client_id]
        
        logger.info(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")
    
    async def subscribe(self, client_id: str, symbols: List[str]):
        """Subscribe a client to price updates for given symbols"""
        for symbol in symbols:
            symbol = symbol.upper()
            
            if symbol not in self.subscriptions:
                self.subscriptions[symbol] = set()
            
            self.subscriptions[symbol].add(client_id)
            self.connection_subscriptions[client_id].add(symbol)
        
        logger.info(f"Client {client_id} subscribed to: {symbols}")
        
        # Send last known prices immediately
        await self._send_cached_prices(client_id, symbols)
    
    async def unsubscribe(self, client_id: str, symbols: List[str]):
        """Unsubscribe a client from specific symbols"""
        for symbol in symbols:
            symbol = symbol.upper()
            
            if symbol in self.subscriptions:
                self.subscriptions[symbol].discard(client_id)
                if not self.subscriptions[symbol]:
                    del self.subscriptions[symbol]
            
            if client_id in self.connection_subscriptions:
                self.connection_subscriptions[client_id].discard(symbol)
        
        logger.info(f"Client {client_id} unsubscribed from: {symbols}")
    
    async def _send_cached_prices(self, client_id: str, symbols: List[str]):
        """Send cached prices for symbols to a specific client"""
        if client_id not in self.active_connections:
            return
        
        websocket = self.active_connections[client_id]
        prices = {}
        
        for symbol in symbols:
            symbol = symbol.upper()
            if symbol in self.price_cache:
                prices[symbol] = self.price_cache[symbol]
        
        if prices:
            try:
                await websocket.send_json({
                    "type": "price_update",
                    "data": prices,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error sending cached prices to {client_id}: {e}")
    
    async def broadcast_prices(self, prices: Dict[str, Dict]):
        """Broadcast price updates to all subscribed clients"""
        # Update cache
        for symbol, price_data in prices.items():
            self.price_cache[symbol] = price_data
        
        # Group updates by client
        client_updates: Dict[str, Dict] = {}
        
        for symbol, price_data in prices.items():
            if symbol in self.subscriptions:
                for client_id in self.subscriptions[symbol]:
                    if client_id not in client_updates:
                        client_updates[client_id] = {}
                    client_updates[client_id][symbol] = price_data
        
        # Send updates to each client
        for client_id, updates in client_updates.items():
            if client_id in self.active_connections:
                try:
                    websocket = self.active_connections[client_id]
                    await websocket.send_json({
                        "type": "price_update",
                        "data": updates,
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")
                    # Client might be disconnected
                    self.disconnect(client_id)
    
    async def send_personal_message(self, client_id: str, message: Dict):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {client_id}: {e}")
    
    def get_subscribed_symbols(self) -> Set[str]:
        """Get all currently subscribed symbols"""
        return set(self.subscriptions.keys())
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
    
    def get_subscription_stats(self) -> Dict[str, int]:
        """Get subscription statistics"""
        return {
            "total_connections": len(self.active_connections),
            "total_subscriptions": sum(len(subs) for subs in self.subscriptions.values()),
            "unique_symbols": len(self.subscriptions),
        }


class PriceBroadcaster:
    """Background service that fetches prices and broadcasts to clients.

    When Redis is available, prices are published to a Redis pub/sub channel
    (``channel:prices``) and cached with a 10-second TTL under ``ws:price:{SYMBOL}``.
    This enables multi-instance deployments where multiple workers share the
    same price feed via Redis.
    """

    REDIS_PRICE_TTL = 10  # seconds

    @staticmethod
    def _redis_prefix() -> str:
        import os
        return os.environ.get("REDIS_KEY_PREFIX", "stockpulse:")

    @classmethod
    def _channel_key(cls) -> str:
        return f"{cls._redis_prefix()}channel:prices"

    @classmethod
    def _price_key(cls, symbol: str) -> str:
        return f"{cls._redis_prefix()}ws:price:{symbol}"

    def __init__(self, manager: ConnectionManager, fetch_interval: float = 5.0):
        self.manager = manager
        self.fetch_interval = fetch_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._sub_task: Optional[asyncio.Task] = None
        self._redis = None
        self._redis_available = False

    def _init_redis(self):
        """Lazily initialise a Redis client for pub/sub.
        Reuses the CacheService connection pool when available."""
        if self._redis is not None:
            return
        try:
            import redis as _redis_lib
            import os

            # Try to reuse CacheService's connection pool
            pool = None
            try:
                from services.cache_service import get_cache_service
                cache_svc = get_cache_service()
                if cache_svc and cache_svc.get_connection_pool():
                    pool = cache_svc.get_connection_pool()
            except Exception:
                pass

            if pool:
                self._redis = _redis_lib.Redis(connection_pool=pool)
            else:
                url = os.environ.get("REDIS_URL", "redis://localhost:6379")
                connect_timeout = int(os.environ.get("REDIS_CONNECT_TIMEOUT", "5"))
                socket_timeout = int(os.environ.get("REDIS_SOCKET_TIMEOUT", "5"))
                self._redis = _redis_lib.Redis.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=connect_timeout,
                    socket_timeout=socket_timeout,
                )
            self._redis.ping()
            self._redis_available = True
            logger.info("PriceBroadcaster: Redis pub/sub connected" +
                        (" (shared pool)" if pool else " (standalone)"))
        except Exception as e:
            logger.debug(f"PriceBroadcaster: Redis not available ({e}), pub/sub disabled")
            self._redis_available = False

    async def start(self):
        """Start the price broadcast service and Redis subscriber"""
        if self._running:
            return

        self._init_redis()
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())

        # Start Redis Pub/Sub subscriber for multi-instance fan-out
        if self._redis_available:
            self._sub_task = asyncio.create_task(self._subscribe_loop())
            logger.info("Price subscriber started (multi-instance fan-out via Redis Pub/Sub)")

        logger.info(f"Price broadcaster started with {self.fetch_interval}s interval")

    async def stop(self):
        """Stop the price broadcast service and subscriber"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._sub_task:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass
        logger.info("Price broadcaster stopped")

    async def _broadcast_loop(self):
        """Main broadcast loop"""
        while self._running:
            try:
                # Get all subscribed symbols
                symbols = self.manager.get_subscribed_symbols()

                if symbols:
                    # Fetch current prices
                    prices = await self._fetch_prices(list(symbols))

                    if prices:
                        # Publish to Redis pub/sub + cache
                        self._publish_to_redis(prices)

                        # Broadcast to local WebSocket clients
                        await self.manager.broadcast_prices(prices)

                await asyncio.sleep(self.fetch_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(self.fetch_interval)

    def _publish_to_redis(self, prices: Dict[str, Dict]):
        """Publish price updates to Redis pub/sub and cache per-symbol."""
        if not self._redis_available:
            return
        try:
            # Publish aggregated update to the prices channel
            self._redis.publish(self._channel_key(), json.dumps(prices, default=str))

            # Cache each symbol individually with short TTL
            pipe = self._redis.pipeline(transaction=False)
            for symbol, data in prices.items():
                pipe.setex(self._price_key(symbol), self.REDIS_PRICE_TTL, json.dumps(data, default=str))
            pipe.execute()
        except Exception as e:
            logger.debug(f"Redis publish error: {e}")

    async def _subscribe_loop(self):
        """Subscribe to Redis Pub/Sub channel and broadcast received prices locally.

        This enables multi-instance deployments: Worker A publishes prices,
        Workers B/C/... receive them here and push to their local WebSocket clients.
        Uses a dedicated Redis connection to avoid blocking the main client.
        """
        try:
            import redis as _redis_lib
        except ImportError:
            return

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            sub_redis = _redis_lib.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=0,  # blocking subscribe
            )
            pubsub = sub_redis.pubsub()
            pubsub.subscribe(self._channel_key())
            logger.info(f"Subscribed to Redis channel: {self._channel_key()}")
        except Exception as e:
            logger.debug(f"Redis Pub/Sub subscribe failed: {e}")
            return

        while self._running:
            try:
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                )
                if msg is None:
                    continue
                if msg["type"] == "message":
                    try:
                        prices = json.loads(msg["data"])
                        # Broadcast to local WebSocket clients
                        await self.manager.broadcast_prices(prices)
                    except (json.JSONDecodeError, TypeError):
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Pub/Sub subscriber error: {e}")
                await asyncio.sleep(2)

        try:
            pubsub.unsubscribe()
            pubsub.close()
            sub_redis.close()
        except Exception:
            pass

    async def _fetch_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch current prices for symbols"""
        prices = {}

        try:
            # Try to use real market data service
            from services.market_data_service import get_bulk_quotes, is_real_data_available

            if is_real_data_available():
                quotes = await get_bulk_quotes(symbols)
                for symbol, quote in quotes.items():
                    if quote:
                        prices[symbol] = {
                            "price": quote.get("current_price", 0),
                            "change": quote.get("price_change", 0),
                            "change_percent": quote.get("price_change_percent", 0),
                            "volume": quote.get("volume", 0),
                            "high": quote.get("high", 0),
                            "low": quote.get("low", 0),
                        }
            else:
                # Fallback to mock data
                prices = self._generate_mock_prices(symbols)

        except ImportError:
            # Market data service not available, use mock
            prices = self._generate_mock_prices(symbols)
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            prices = self._generate_mock_prices(symbols)

        return prices

    def _generate_mock_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Generate mock price data for testing"""
        import random

        prices = {}
        for symbol in symbols:
            base_price = random.uniform(100, 5000)
            change = random.uniform(-3, 3)

            prices[symbol] = {
                "price": round(base_price, 2),
                "change": round(base_price * change / 100, 2),
                "change_percent": round(change, 2),
                "volume": random.randint(100000, 10000000),
                "high": round(base_price * 1.02, 2),
                "low": round(base_price * 0.98, 2),
            }

        return prices


# Global instances
connection_manager = ConnectionManager()
price_broadcaster = PriceBroadcaster(connection_manager, fetch_interval=10.0)


async def handle_websocket_message(websocket: WebSocket, client_id: str, message: str):
    """Handle incoming WebSocket messages"""
    try:
        data = json.loads(message)
        action = data.get("action", "")
        
        if action == "subscribe":
            symbols = data.get("symbols", [])
            if symbols:
                await connection_manager.subscribe(client_id, symbols)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": symbols
                })
        
        elif action == "unsubscribe":
            symbols = data.get("symbols", [])
            if symbols:
                await connection_manager.unsubscribe(client_id, symbols)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols
                })
        
        elif action == "ping":
            await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
        
        else:
            await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})
    
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})
