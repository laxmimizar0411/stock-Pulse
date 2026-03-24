"""
Stock Pulse Brain — Central Intelligence System

The Brain is the core AI-powered analysis and prediction engine for Stock Pulse.
It implements:
  - Event-driven architecture (async event bus, Kafka-compatible)
  - Feature engineering pipeline (50+ features)
  - AI/ML prediction models (XGBoost, LightGBM, ARIMA, GARCH)
  - Multi-signal fusion with confidence scoring
  - FinBERT + LLM sentiment analysis pipeline
  - Market regime detection (HMM — bull/bear/sideways)
  - Risk management and position sizing
  - SHAP-based prediction explanations
  - LLM multi-agent research system (planned)
  - Options/derivatives intelligence (planned)

All Brain modules live under `backend/brain/` and communicate
via the event bus, maintaining clean separation from the existing
`backend/services/` and `backend/data_extraction/` code.
"""

__version__ = "0.1.0"
__author__ = "Stock Pulse Team"
