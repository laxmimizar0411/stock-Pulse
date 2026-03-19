import { useEffect, useRef, useState, useCallback } from 'react';

const RECONNECT_INTERVAL = 3000; // 3 seconds
const MAX_RECONNECT_ATTEMPTS = 5;

/**
 * Custom hook for WebSocket connection to receive real-time price updates
 * @param {Object} options - Configuration options
 * @param {string} options.url - WebSocket URL (optional, uses default if not provided)
 * @param {Function} options.onPriceUpdate - Callback when prices are updated
 * @param {Function} options.onConnectionChange - Callback when connection status changes
 * @param {boolean} options.autoConnect - Whether to connect automatically (default: true)
 */
export function useWebSocket({
    url,
    onPriceUpdate,
    onAlertNotification,
    onConnectionChange,
    autoConnect = true,
} = {}) {
    const ws = useRef(null);
    const reconnectAttempts = useRef(0);
    const reconnectTimeout = useRef(null);

    const [isConnected, setIsConnected] = useState(false);
    const [subscribedSymbols, setSubscribedSymbols] = useState([]);
    const [prices, setPrices] = useState({});
    const [error, setError] = useState(null);

    // Get WebSocket URL
    const getWebSocketUrl = useCallback(() => {
        if (url) return url;

        const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
        // Convert http to ws, https to wss
        const wsUrl = backendUrl.replace(/^http/, 'ws');
        return `${wsUrl}/ws/prices`;
    }, [url]);

    // Connect to WebSocket
    const connect = useCallback(() => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            return;
        }

        const wsUrl = getWebSocketUrl();
        console.log('Connecting to WebSocket:', wsUrl);

        try {
            ws.current = new WebSocket(wsUrl);

            ws.current.onopen = () => {
                console.log('WebSocket connected');
                setIsConnected(true);
                setError(null);
                reconnectAttempts.current = 0;
                onConnectionChange?.(true);

                // Re-subscribe to previously subscribed symbols
                if (subscribedSymbols.length > 0) {
                    ws.current.send(JSON.stringify({
                        action: 'subscribe',
                        symbols: subscribedSymbols,
                    }));
                }
            };

            ws.current.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);

                    if (message.type === 'price_update') {
                        const newPrices = message.data;
                        setPrices((prev) => ({ ...prev, ...newPrices }));
                        onPriceUpdate?.(newPrices);
                    } else if (message.type === 'alert_notification') {
                        onAlertNotification?.(message.data);
                    } else if (message.type === 'subscribed') {
                        console.log('Subscribed to:', message.symbols);
                    } else if (message.type === 'unsubscribed') {
                        console.log('Unsubscribed from:', message.symbols);
                    } else if (message.type === 'pong') {
                        // Heartbeat response
                    } else if (message.type === 'error') {
                        console.error('WebSocket error:', message.message);
                        setError(message.message);
                    }
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e);
                }
            };

            ws.current.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                setIsConnected(false);
                onConnectionChange?.(false);

                // Attempt to reconnect
                if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts.current += 1;
                    console.log(`Reconnecting... Attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS}`);

                    reconnectTimeout.current = setTimeout(() => {
                        connect();
                    }, RECONNECT_INTERVAL);
                } else {
                    setError('Connection lost. Please refresh the page.');
                }
            };

            ws.current.onerror = (event) => {
                console.error('WebSocket error:', event);
                setError('Connection error');
            };
        } catch (e) {
            console.error('Error creating WebSocket:', e);
            setError(e.message);
        }
    }, [getWebSocketUrl, onAlertNotification, onConnectionChange, onPriceUpdate, subscribedSymbols]);

    // Disconnect from WebSocket
    const disconnect = useCallback(() => {
        if (reconnectTimeout.current) {
            clearTimeout(reconnectTimeout.current);
        }

        if (ws.current) {
            ws.current.close();
            ws.current = null;
        }

        setIsConnected(false);
        reconnectAttempts.current = MAX_RECONNECT_ATTEMPTS; // Prevent auto-reconnect
    }, []);

    // Subscribe to symbols
    const subscribe = useCallback((symbols) => {
        if (!Array.isArray(symbols)) {
            symbols = [symbols];
        }

        symbols = symbols.map(s => s.toUpperCase());

        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                action: 'subscribe',
                symbols: symbols,
            }));
        }

        setSubscribedSymbols((prev) => {
            const newSymbols = [...new Set([...prev, ...symbols])];
            return newSymbols;
        });
    }, []);

    // Unsubscribe from symbols
    const unsubscribe = useCallback((symbols) => {
        if (!Array.isArray(symbols)) {
            symbols = [symbols];
        }

        symbols = symbols.map(s => s.toUpperCase());

        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                action: 'unsubscribe',
                symbols: symbols,
            }));
        }

        setSubscribedSymbols((prev) => prev.filter(s => !symbols.includes(s)));
    }, []);

    // Send ping for keep-alive
    const ping = useCallback(() => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ action: 'ping' }));
        }
    }, []);

    // Get price for a specific symbol
    const getPrice = useCallback((symbol) => {
        return prices[symbol.toUpperCase()];
    }, [prices]);

    // Auto-connect on mount
    useEffect(() => {
        if (autoConnect) {
            connect();
        }

        // Cleanup on unmount
        return () => {
            disconnect();
        };
    }, [autoConnect]); // eslint-disable-line react-hooks/exhaustive-deps

    // Set up heartbeat
    useEffect(() => {
        if (!isConnected) return;

        const heartbeatInterval = setInterval(() => {
            ping();
        }, 30000); // Ping every 30 seconds

        return () => clearInterval(heartbeatInterval);
    }, [isConnected, ping]);

    return {
        isConnected,
        prices,
        subscribedSymbols,
        error,
        connect,
        disconnect,
        subscribe,
        unsubscribe,
        getPrice,
    };
}

// Context for sharing WebSocket connection across components
import { createContext, useContext } from 'react';

const WebSocketContext = createContext(null);

export function WebSocketProvider({ children, onAlertNotification }) {
    const websocket = useWebSocket({
        autoConnect: true,
        onAlertNotification,
    });

    return (
        <WebSocketContext.Provider value={websocket}>
            {children}
        </WebSocketContext.Provider>
    );
}

export function useWebSocketContext() {
    const context = useContext(WebSocketContext);
    if (!context) {
        throw new Error('useWebSocketContext must be used within a WebSocketProvider');
    }
    return context;
}

export default useWebSocket;
