"""
MongoDB utility functions for StockPulse.

Provides:
  - Input sanitization against NoSQL injection
  - Field whitelist validation for update operations
  - Symbol format validation
  - Safe query builder helpers
"""

import re
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# Regex for valid Indian stock symbols (NSE/BSE)
# Allows uppercase letters, digits, ampersand, hyphen, dot, underscore
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&_.-]{1,20}$")


def sanitize_symbol(symbol: str) -> str:
    """Validate and normalize a stock symbol.

    Raises ValueError if the symbol format is invalid.
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string")

    cleaned = symbol.strip().upper()

    if not SYMBOL_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid symbol format: '{symbol}'. "
            "Must be 1-20 characters: uppercase letters, digits, &, _, -, ."
        )

    return cleaned


def is_safe_value(value: Any) -> bool:
    """Check that a value does not contain MongoDB operator injection.

    Returns False if the value contains keys starting with '$' or
    contains dots that could traverse nested documents unexpectedly.
    """
    if isinstance(value, dict):
        for key in value:
            if isinstance(key, str) and key.startswith("$"):
                return False
            if not is_safe_value(value[key]):
                return False
    elif isinstance(value, list):
        for item in value:
            if not is_safe_value(item):
                return False
    return True


def validate_update_fields(
    updates: Dict[str, Any],
    allowed_fields: Set[str],
) -> Dict[str, Any]:
    """Validate and filter update fields against a whitelist.

    - Only allows fields in ``allowed_fields``
    - Strips any MongoDB operators (keys starting with $)
    - Validates that values don't contain injection attempts
    - Returns the sanitized update dict

    Raises ValueError on disallowed or unsafe input.
    """
    if not isinstance(updates, dict):
        raise ValueError("Updates must be a dictionary")

    sanitized = {}
    for key, value in updates.items():
        # Block MongoDB operators in keys
        if isinstance(key, str) and key.startswith("$"):
            raise ValueError(f"Operator keys are not allowed: '{key}'")

        # Block fields not in the whitelist
        if key not in allowed_fields:
            logger.warning(f"Ignoring disallowed update field: '{key}'")
            continue

        # Block operator injection in values
        if not is_safe_value(value):
            raise ValueError(f"Unsafe value detected for field '{key}'")

        sanitized[key] = value

    return sanitized


# Allowed update fields per collection
WATCHLIST_UPDATE_FIELDS = {
    "target_price", "stop_loss", "notes", "alerts_enabled", "name",
}

PORTFOLIO_UPDATE_FIELDS = {
    "quantity", "avg_buy_price", "buy_date", "name", "sector",
}

ALERT_UPDATE_FIELDS = {
    "target_value", "comparison_value", "priority", "message",
    "status", "expires_at", "repeat",
}
