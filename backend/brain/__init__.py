"""
Stock Pulse Brain — Central Intelligence System

The Brain is the core intelligence engine that fuses ML models, LLM agents,
sentiment analysis, market regime detection, and risk management into
unified trading signals for the Indian stock market.

Modules:
    - event_bus: Async in-process event bus (Kafka-compatible interface)
    - features: Feature engineering pipeline (50+ features)
    - regime: HMM market regime detection (bull/bear/sideways)
    - models_ml: ML model ecosystem (statistical, gradient boosting, deep learning)
    - signals: Multi-signal fusion engine with confidence scoring
    - sentiment: FinBERT + LLM sentiment pipeline
    - agents: Multi-agent LLM system with dialectical debate
    - risk: Risk management (stop-loss, position sizing, VaR)
    - explainability: SHAP-based prediction explanations
    - rag: RAG knowledge base with vector search
    - options: Options & derivatives intelligence
    - tax: Indian tax optimization engine
"""

__version__ = "0.1.0"
