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
        """Seed the knowledge base with comprehensive Indian market knowledge."""
        seed_docs = [
            KBDocument(
                title="SEBI Margin Requirements",
                content="SEBI mandates VAR-based margins for equity trading. Group I stocks (F&O eligible) require 10% VAR margin + 3.5% ELM. Group II requires 20% VAR + 5% ELM. Delivery trades require additional 20-75% margin depending on group. Peak margin reporting is mandatory since Dec 2020. Brokers must report margins 4 times daily.",
                source="sebi", category="regulation",
            ),
            KBDocument(
                title="Circuit Breaker Rules India",
                content="NSE applies market-wide circuit breakers at 10%, 15%, and 20% movement in NIFTY 50 or SENSEX. Individual stock circuits: Group I at 20%, Group II at 10%, Group III at 5%. Trading halts for 15-45 minutes when triggered. Price bands are revised quarterly based on volatility.",
                source="sebi", category="regulation",
            ),
            KBDocument(
                title="NIFTY 50 Composition and Methodology",
                content="NIFTY 50 represents the top 50 companies by free-float market cap on NSE. Key sectors: Banking (30%), IT (15%), Energy (10%), FMCG (8%). Rebalanced semi-annually in March and September. Stocks must meet minimum float-adjusted market cap, trading frequency, and impact cost criteria. Maximum weight cap of 33% for single stock and 20% from a single sector.",
                source="reference", category="index",
            ),
            KBDocument(
                title="FII/DII Flow Impact on Indian Markets",
                content="Foreign Institutional Investors (FII) and Domestic Institutional Investors (DII) flows significantly impact Indian markets. FII net buying is bullish, while FII selling creates downward pressure. DII (mutual funds, insurance, pensions) often provides counter-balance. SEBI mandates daily FII/DII flow disclosure. FII flows are influenced by US dollar strength, global risk appetite, and India's relative valuation. Monthly SIP inflows (Rs 20,000+ crores) provide structural DII support.",
                source="research", category="flows",
            ),
            KBDocument(
                title="Indian Market Trading Hours and Settlement",
                content="NSE trading hours: 9:15 AM to 3:30 PM IST. Pre-open session: 9:00-9:15 AM (price discovery). Post-close session: 3:40-4:00 PM (closing price). T+1 settlement cycle effective from January 2023. Commodity trading: 9:00 AM to 11:30 PM. Currency trading: 9:00 AM to 5:00 PM. ASM (Additional Surveillance Measure) and GSM (Graded Surveillance Measure) lists are published fortnightly.",
                source="reference", category="operations",
            ),
            KBDocument(
                title="Key Financial Metrics for Indian Equities",
                content="Important metrics: P/E ratio (vs industry median), P/B ratio, Debt-to-Equity, ROE (>15% considered good), ROCE (>18% preferred), Promoter Holding % (>50% preferred), Pledge % (<20% safe), Dividend Yield, EPS growth (3yr CAGR), Cash Flow from Operations, Interest Coverage Ratio, Current Ratio. SEBI requires quarterly results disclosure within 45 days of quarter-end. Annual results within 60 days.",
                source="reference", category="fundamentals",
            ),
            KBDocument(
                title="RBI Monetary Policy Framework",
                content="Reserve Bank of India (RBI) conducts monetary policy through the Monetary Policy Committee (MPC) which meets 6 times a year (bi-monthly). Key rates: Repo Rate (main policy rate), Reverse Repo Rate, CRR (Cash Reserve Ratio), SLR (Statutory Liquidity Ratio). RBI targets 4% CPI inflation with +/-2% band. Rate cuts are bullish for banking, real estate, and auto sectors. RBI also manages forex reserves, government borrowings, and rupee stability.",
                source="rbi", category="monetary_policy",
            ),
            KBDocument(
                title="Indian Tax on Stock Market Investments",
                content="Short-term capital gains (STCG) tax on listed equity: 20% (if held less than 12 months). Long-term capital gains (LTCG) tax: 12.5% on gains exceeding Rs 1.25 lakh per year. Securities Transaction Tax (STT) applies on all equity transactions. Dividend income taxed as per income slab. No STT on commodity futures. F&O income/loss treated as business income. Tax loss harvesting is commonly used before March 31.",
                source="reference", category="taxation",
            ),
            KBDocument(
                title="Promoter Holding and Pledge Analysis",
                content="Promoter holding indicates insider confidence. Above 50% is considered strong. Declining promoter holding is a negative signal. Promoter pledge (shares pledged as collateral for loans) above 20% is a red flag. If stock price falls below trigger price, pledged shares may be sold by lenders, creating a downward spiral. SEBI mandates quarterly disclosure of pledge data. Major promoter pledge reductions are treated as positive triggers.",
                source="research", category="governance",
            ),
            KBDocument(
                title="Indian IPO Market and Process",
                content="Indian IPO process: DRHP filing with SEBI, SEBI review (30-75 days), roadshow, price band announcement, subscription period (3 days for retail, 1 for anchor), allotment (6 days post close), listing (T+3 after allotment). IPO categories: QIB (50%), NII/HNI (15%), Retail (35%). Key metrics: GMP (Grey Market Premium), subscription ratio by category, PE vs listed peers. SEBI mandates minimum 10% retail allocation.",
                source="sebi", category="ipo",
            ),
            KBDocument(
                title="Technical Analysis Patterns in Indian Markets",
                content="Common technical patterns in Indian equities: Support/Resistance at round numbers, Gap-up/Gap-down analysis important for NIFTY. Moving averages: 20-DMA (short-term), 50-DMA (medium), 200-DMA (long-term trend). India VIX below 13 indicates low volatility (bullish), above 20 indicates fear. Put-Call Ratio (PCR) above 1.2 is bullish, below 0.8 is bearish. Open Interest analysis at strike prices helps identify NIFTY support/resistance. F&O expiry (last Thursday) often causes volatility.",
                source="research", category="technical",
            ),
            KBDocument(
                title="Sector Analysis: Indian Banking",
                content="Indian banking sector includes PSU banks (SBI, BOB, PNB), private banks (HDFC, ICICI, Kotak, Axis), and NBFCs (Bajaj Finance, HDFC Ltd). Key metrics: NIM (Net Interest Margin), GNPA/NNPA ratios, CASA ratio, Credit growth, Provision Coverage Ratio. RBI rate decisions directly impact NIMs. PSU bank reforms and privatization are ongoing themes. Credit growth above 15% is bullish for the sector.",
                source="research", category="sector",
            ),
            KBDocument(
                title="Sector Analysis: Indian IT Services",
                content="Indian IT sector is export-driven (90%+ revenue from US/Europe). Key players: TCS, Infosys, Wipro, HCL Tech, Tech Mahindra. Key metrics: Revenue growth (CC terms), EBIT margin, deal wins (TCV), attrition rate, utilization rate. Rupee depreciation benefits IT companies. US recession fears and AI disruption are key risks. Q1 (Apr-Jun) is traditionally weak due to furloughs ending. Guidance upgrades are strong positive triggers.",
                source="research", category="sector",
            ),
            KBDocument(
                title="Indian Market Seasonality",
                content="Known Indian market seasonal patterns: Pre-budget rally (Jan), Budget volatility (Feb 1), March tax-loss selling, April-May pre-election rally in election years, Monsoon impact on FMCG/Agri (Jul-Sep), Festive season boost for auto/consumer (Oct-Nov), FII tax-harvesting selling (Dec). Muhurat trading on Diwali is traditionally bullish. Samvat year analysis is followed by some traders.",
                source="research", category="seasonality",
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
