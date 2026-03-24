"""
Stock Pulse Brain — Central Intelligence System

The Brain is the core AI-powered analysis and prediction engine for Stock Pulse.
It implements:
  - Event-driven architecture (Kafka)
  - Feature engineering pipeline (Feast + Redis)
  - AI/ML prediction models (TFT, LSTM, XGBoost, GARCH)
  - Multi-signal fusion with confidence scoring
  - LLM multi-agent research system (LangGraph)
  - Risk management and position sizing
  - Market regime detection (HMM)
  - Options/derivatives intelligence
  - Real-time streaming and decision engine

All Brain modules live under `backend/brain/` and communicate
via Kafka events, maintaining clean separation from the existing
`backend/services/` and `backend/data_extraction/` code.
"""

__version__ = "0.1.0"
__author__ = "Stock Pulse Team"
