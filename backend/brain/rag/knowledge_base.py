"""RAG Knowledge Base (Qdrant) — Phase 3.5

Vector-based knowledge retrieval for:
- Financial regulations (SEBI circulars)
- Company filings (annual reports, quarterly results)
- News articles (for context augmentation)
- Research reports

Uses Qdrant in-memory mode (no external server needed).
Embeddings: sentence-transformers/all-MiniLM-L6-v2 (384-dim, fast).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_embedder = None


def _get_embedder():
    """Lazy-load sentence-transformer embedder."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("\u2705 Sentence-Transformers embedder loaded (all-MiniLM-L6-v2)")
        return _embedder
    except Exception as e:
        logger.warning(f"Failed to load embedder: {e}")
        return None


@dataclass
class KBDocument:
    """A document in the knowledge base."""
    doc_id: str = ""
    title: str = ""
    content: str = ""
    source: str = ""  # "sebi", "filing", "news", "research"
    category: str = ""
    symbols: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.doc_id:
            self.doc_id = str(uuid.uuid4())


@dataclass
class SearchResult:
    """A search result from the knowledge base."""
    doc_id: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    source: str = ""
    category: str = ""
    symbols: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content[:500],
            "score": round(self.score, 4),
            "source": self.source,
            "category": self.category,
            "symbols": self.symbols,
        }


class RAGKnowledgeBase:
    """Vector knowledge base using Qdrant (in-memory mode)."""

    def __init__(self, collection_name: str = "stockpulse_kb"):
        self._collection_name = collection_name
        self._client = None
        self._embedder = None
        self._doc_count = 0
        self._initialized = False
        self._stats = {"documents": 0, "queries": 0}

    def initialize(self):
        """Initialize Qdrant in-memory client and create collection."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(":memory:")
            self._embedder = _get_embedder()

            if self._embedder is None:
                logger.warning("Embedder not available, RAG will be limited")
                self._initialized = False
                return

            # Create collection
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

            # Seed with basic knowledge
            self._seed_knowledge()

            self._initialized = True
            logger.info(f"\u2705 RAG Knowledge Base: READY ({self._doc_count} documents)")

        except Exception as e:
            logger.warning(f"Failed to initialize RAG: {e}")
            self._initialized = False

    def _seed_knowledge(self):
        """Seed the knowledge base with fundamental Indian market knowledge."""
        seed_docs = [
            KBDocument(
                title="SEBI Margin Requirements",
                content="SEBI mandates VAR-based margins for equity trading. Group I stocks (F&O eligible) require 10% VAR margin + 3.5% ELM. Group II requires 20% VAR + 5% ELM. Delivery trades require additional 20-75% margin depending on group.",
                source="sebi", category="regulation",
            ),
            KBDocument(
                title="Circuit Breaker Rules India",
                content="NSE applies circuit breakers at 10%, 15%, and 20% movement in indices. Individual stock circuits: Group I at 20%, Group II at 10%, Group III at 5%. Trading halts when circuit is hit.",
                source="sebi", category="regulation",
            ),
            KBDocument(
                title="NIFTY 50 Composition",
                content="NIFTY 50 represents the top 50 companies by free-float market cap on NSE. Key sectors: Banking (30%), IT (15%), Energy (10%), FMCG (8%). Rebalanced semi-annually in March and September.",
                source="reference", category="index",
            ),
            KBDocument(
                title="FII/DII Flow Impact",
                content="Foreign Institutional Investors (FII) and Domestic Institutional Investors (DII) flows significantly impact Indian markets. FII net buying is bullish, while FII selling creates downward pressure. DII often provides counter-balance.",
                source="research", category="flows",
            ),
            KBDocument(
                title="Indian Market Timing",
                content="NSE trading hours: 9:15 AM to 3:30 PM IST. Pre-open session: 9:00-9:15 AM. Post-close: 3:40-4:00 PM. T+1 settlement cycle effective from January 2023.",
                source="reference", category="operations",
            ),
            KBDocument(
                title="Key Indian Financial Metrics",
                content="Important metrics for Indian stocks: P/E ratio, P/B ratio, Debt-to-Equity, ROE, ROCE, Promoter Holding %, Pledge %, Dividend Yield, EPS growth. SEBI requires quarterly results disclosure within 45 days.",
                source="reference", category="fundamentals",
            ),
        ]

        for doc in seed_docs:
            self.add_document(doc)

    def add_document(self, doc: KBDocument) -> bool:
        """Add a document to the knowledge base."""
        if not self._client or not self._embedder:
            return False

        try:
            from qdrant_client.models import PointStruct

            embedding = self._embedder.encode(f"{doc.title}. {doc.content}").tolist()

            self._client.upsert(
                collection_name=self._collection_name,
                points=[PointStruct(
                    id=self._doc_count,
                    vector=embedding,
                    payload={
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "content": doc.content,
                        "source": doc.source,
                        "category": doc.category,
                        "symbols": doc.symbols,
                    },
                )],
            )
            self._doc_count += 1
            self._stats["documents"] = self._doc_count
            return True

        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            return False

    def search(self, query: str, limit: int = 5, category: Optional[str] = None) -> List[SearchResult]:
        """Search the knowledge base."""
        if not self._client or not self._embedder:
            return []

        try:
            query_vector = self._embedder.encode(query).tolist()

            filters = None
            if category:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                filters = Filter(must=[
                    FieldCondition(key="category", match=MatchValue(value=category))
                ])

            results = self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                limit=limit,
                query_filter=filters,
            )

            search_results = []
            for point in results.points:
                payload = point.payload or {}
                search_results.append(SearchResult(
                    doc_id=payload.get("doc_id", ""),
                    title=payload.get("title", ""),
                    content=payload.get("content", ""),
                    score=point.score if hasattr(point, 'score') else 0.0,
                    source=payload.get("source", ""),
                    category=payload.get("category", ""),
                    symbols=payload.get("symbols", []),
                ))

            self._stats["queries"] += 1
            return search_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    @property
    def is_available(self) -> bool:
        return self._initialized

    def get_stats(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "document_count": self._doc_count,
            "collection": self._collection_name,
            "embedder": "all-MiniLM-L6-v2" if self._embedder else "not_loaded",
            **self._stats,
        }
