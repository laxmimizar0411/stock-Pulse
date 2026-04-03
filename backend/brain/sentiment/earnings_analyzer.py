"""
Earnings Call Analyzer — Phase 3.2

Analyzes earnings call transcripts for sentiment signals:
1. Management Discussion section vs Q&A section separation
2. Tone divergence detection (management optimism vs analyst skepticism)
3. Forward-looking statement extraction
4. Key metric mentions and guidance changes

Uses FinBERT for section-level sentiment + Gemini LLM for deeper analysis.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EarningsSection:
    """A section of an earnings call."""
    section_type: str  # "management_discussion", "qa_session", "opening", "closing"
    text: str = ""
    speaker: str = ""
    sentiment_score: float = 0.0  # [-1, +1]
    sentiment_label: str = "neutral"
    key_phrases: List[str] = field(default_factory=list)
    forward_looking: List[str] = field(default_factory=list)


@dataclass
class EarningsCallAnalysis:
    """Complete analysis of an earnings call."""
    symbol: str
    quarter: str  # e.g., "Q1FY26"
    date: Optional[datetime] = None
    
    # Section-level analysis
    management_sentiment: float = 0.0  # [-1, +1]
    qa_sentiment: float = 0.0  # [-1, +1]
    tone_divergence: float = 0.0  # management - qa (positive = management more optimistic)
    
    # Overall
    overall_sentiment: float = 0.0
    overall_label: str = "neutral"
    confidence: float = 0.5
    
    # Extracted insights
    guidance_direction: str = "maintained"  # "raised", "lowered", "maintained", "withdrawn"
    key_positives: List[str] = field(default_factory=list)
    key_negatives: List[str] = field(default_factory=list)
    forward_looking_statements: List[str] = field(default_factory=list)
    
    # Metrics mentioned
    revenue_mention: Optional[str] = None
    profit_mention: Optional[str] = None
    margin_mention: Optional[str] = None
    
    sections: List[EarningsSection] = field(default_factory=list)
    
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quarter": self.quarter,
            "date": self.date.isoformat() if self.date else None,
            "management_sentiment": round(self.management_sentiment, 4),
            "qa_sentiment": round(self.qa_sentiment, 4),
            "tone_divergence": round(self.tone_divergence, 4),
            "overall_sentiment": round(self.overall_sentiment, 4),
            "overall_label": self.overall_label,
            "confidence": round(self.confidence, 4),
            "guidance_direction": self.guidance_direction,
            "key_positives": self.key_positives[:5],
            "key_negatives": self.key_negatives[:5],
            "forward_looking_statements": self.forward_looking_statements[:5],
            "revenue_mention": self.revenue_mention,
            "profit_mention": self.profit_mention,
            "margin_mention": self.margin_mention,
            "section_count": len(self.sections),
            "analyzed_at": self.analyzed_at.isoformat(),
        }


# Patterns for detecting sections in earnings call transcripts
MANAGEMENT_PATTERNS = [
    r"(?i)management\s+discussion",
    r"(?i)opening\s+remarks",
    r"(?i)ceo\s+(?:address|speech|remarks)",
    r"(?i)md\s+(?:address|speech|remarks)",
    r"(?i)chairman['s]?\s+(?:address|speech|remarks)",
    r"(?i)presentation\s+by\s+management",
    r"(?i)(?:financial|business)\s+highlights",
]

QA_PATTERNS = [
    r"(?i)question\s+and\s+answer",
    r"(?i)q\s*&\s*a\s+session",
    r"(?i)analyst\s+questions",
    r"(?i)(?:we\s+)?(?:now\s+)?open\s+(?:the\s+)?(?:floor|session)\s+for\s+questions",
    r"(?i)(?:operator|moderator).*(?:first|next)\s+question",
]

# Forward-looking statement indicators
FORWARD_LOOKING_KEYWORDS = [
    "guidance", "outlook", "forecast", "expect", "anticipate",
    "project", "target", "plan to", "aim to", "intend to",
    "next quarter", "next year", "FY", "going forward",
    "pipeline", "order book", "capex plan", "expansion",
    "ramp up", "growth trajectory", "momentum",
]

# Positive business indicators
POSITIVE_INDICATORS = [
    "record revenue", "record profit", "highest ever", "beat estimates",
    "strong growth", "margin expansion", "market share gain",
    "order win", "new contract", "capacity addition", "debt reduction",
    "dividend increase", "guidance raised", "upgrade", "outperform",
    "robust demand", "healthy pipeline", "strong momentum",
]

# Negative business indicators
NEGATIVE_INDICATORS = [
    "miss estimates", "below expectations", "margin pressure",
    "slowdown", "headwinds", "challenging", "difficult environment",
    "debt increase", "impairment", "write-off", "restructuring",
    "guidance lowered", "cautious outlook", "uncertainty",
    "supply chain issues", "cost inflation", "attrition",
    "regulatory concern", "one-time charge", "exceptional item",
]


def _split_into_sections(transcript: str) -> List[EarningsSection]:
    """Split an earnings call transcript into management discussion and Q&A sections."""
    sections = []
    
    if not transcript:
        return sections
    
    # Find Q&A section boundary
    qa_start = -1
    for pattern in QA_PATTERNS:
        match = re.search(pattern, transcript)
        if match:
            qa_start = match.start()
            break
    
    if qa_start > 0:
        # Management discussion is everything before Q&A
        mgmt_text = transcript[:qa_start].strip()
        qa_text = transcript[qa_start:].strip()
        
        if mgmt_text:
            sections.append(EarningsSection(
                section_type="management_discussion",
                text=mgmt_text[:5000],  # Limit size
            ))
        
        if qa_text:
            sections.append(EarningsSection(
                section_type="qa_session",
                text=qa_text[:5000],
            ))
    else:
        # Can't find Q&A boundary — treat entire text as single section
        sections.append(EarningsSection(
            section_type="full_transcript",
            text=transcript[:8000],
        ))
    
    return sections


def _extract_forward_looking(text: str) -> List[str]:
    """Extract forward-looking statements from text."""
    statements = []
    sentences = re.split(r'[.!?]+', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20:
            continue
        
        sentence_lower = sentence.lower()
        for keyword in FORWARD_LOOKING_KEYWORDS:
            if keyword in sentence_lower:
                statements.append(sentence[:200])
                break
    
    return statements[:10]  # Limit to 10


def _extract_key_mentions(text: str) -> Dict[str, Optional[str]]:
    """Extract key financial metric mentions."""
    text_lower = text.lower()
    mentions = {}
    
    # Revenue mentions
    rev_patterns = [
        r"revenue\s+(?:of|at|was|stood at)\s+([\w\s,.₹$]+(?:crore|billion|million|lakh))",
        r"(?:top\s*line|sales)\s+(?:grew|increased|declined|fell)\s+([\w\s,.%]+)",
    ]
    for pat in rev_patterns:
        match = re.search(pat, text_lower)
        if match:
            mentions["revenue"] = match.group(0)[:100]
            break
    
    # Profit mentions
    profit_patterns = [
        r"(?:net\s+)?profit\s+(?:of|at|was|stood at)\s+([\w\s,.₹$]+(?:crore|billion|million|lakh))",
        r"(?:bottom\s*line|pat|pbt)\s+(?:grew|increased|declined|fell)\s+([\w\s,.%]+)",
    ]
    for pat in profit_patterns:
        match = re.search(pat, text_lower)
        if match:
            mentions["profit"] = match.group(0)[:100]
            break
    
    # Margin mentions
    margin_patterns = [
        r"(?:ebitda|operating|net)\s+margin[s]?\s+(?:at|of|was|improved to|declined to)\s+([\w\s,.%]+)",
        r"margin\s+(?:expansion|compression|improvement|deterioration)\s+(?:of\s+)?([\w\s,.%]+)",
    ]
    for pat in margin_patterns:
        match = re.search(pat, text_lower)
        if match:
            mentions["margin"] = match.group(0)[:100]
            break
    
    return mentions


def _detect_guidance_direction(text: str) -> str:
    """Detect whether management guidance was raised, lowered, or maintained."""
    text_lower = text.lower()
    
    raised_keywords = ["guidance raised", "raised guidance", "upgraded outlook",
                       "revised upward", "increased target", "beat guidance",
                       "above guidance", "upgraded forecast"]
    lowered_keywords = ["guidance lowered", "lowered guidance", "downgraded outlook",
                        "revised downward", "reduced target", "below guidance",
                        "cut forecast", "trimmed guidance"]
    withdrawn_keywords = ["guidance withdrawn", "suspended guidance", "no guidance"]
    
    for kw in raised_keywords:
        if kw in text_lower:
            return "raised"
    for kw in lowered_keywords:
        if kw in text_lower:
            return "lowered"
    for kw in withdrawn_keywords:
        if kw in text_lower:
            return "withdrawn"
    
    return "maintained"


class EarningsCallAnalyzer:
    """
    Analyzes earnings call transcripts for sentiment signals.
    
    Key features:
    - Management vs Q&A section separation
    - Tone divergence detection
    - Forward-looking statement extraction
    - Guidance direction detection
    
    Usage:
        analyzer = EarningsCallAnalyzer(finbert_analyzer=finbert)
        result = analyzer.analyze_transcript(symbol="RELIANCE", transcript=text, quarter="Q1FY26")
    """

    def __init__(self, finbert_analyzer=None, llm_fn=None):
        """
        Args:
            finbert_analyzer: FinBERTAnalyzer instance for sentiment scoring
            llm_fn: Async function for LLM-based analysis (Gemini)
        """
        self._finbert = finbert_analyzer
        self._llm_fn = llm_fn
        self._stats = {
            "transcripts_analyzed": 0,
            "sections_processed": 0,
        }

    def analyze_transcript(
        self,
        symbol: str,
        transcript: str,
        quarter: str = "",
        date: Optional[datetime] = None,
    ) -> EarningsCallAnalysis:
        """
        Analyze an earnings call transcript.
        
        Returns comprehensive analysis with management vs Q&A tone divergence.
        """
        analysis = EarningsCallAnalysis(
            symbol=symbol.upper(),
            quarter=quarter,
            date=date,
        )

        if not transcript or len(transcript) < 100:
            logger.warning(f"Transcript too short for {symbol}")
            return analysis

        # 1. Split into sections
        sections = _split_into_sections(transcript)
        
        # 2. Analyze each section with FinBERT
        mgmt_scores = []
        qa_scores = []
        
        for section in sections:
            # Break section into sentences for FinBERT
            sentences = re.split(r'[.!?]+', section.text)
            sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]
            
            if sentences and self._finbert:
                results = self._finbert.analyze(sentences[:30])  # Limit to 30 sentences
                if results:
                    avg_score = sum(r.score for r in results) / len(results)
                    section.sentiment_score = avg_score
                    section.sentiment_label = (
                        "positive" if avg_score > 0.1
                        else "negative" if avg_score < -0.1
                        else "neutral"
                    )
                    
                    if section.section_type == "management_discussion":
                        mgmt_scores.append(avg_score)
                    elif section.section_type == "qa_session":
                        qa_scores.append(avg_score)
                    else:
                        mgmt_scores.append(avg_score)  # default to management
            
            # Extract forward-looking statements
            section.forward_looking = _extract_forward_looking(section.text)
            
            analysis.sections.append(section)
            self._stats["sections_processed"] += 1

        # 3. Compute aggregate scores
        if mgmt_scores:
            analysis.management_sentiment = sum(mgmt_scores) / len(mgmt_scores)
        if qa_scores:
            analysis.qa_sentiment = sum(qa_scores) / len(qa_scores)
        
        # 4. Tone divergence (positive = management more optimistic than analysts)
        if mgmt_scores and qa_scores:
            analysis.tone_divergence = analysis.management_sentiment - analysis.qa_sentiment
        
        # 5. Overall sentiment (weighted: 60% management, 40% Q&A)
        if mgmt_scores and qa_scores:
            analysis.overall_sentiment = 0.6 * analysis.management_sentiment + 0.4 * analysis.qa_sentiment
        elif mgmt_scores:
            analysis.overall_sentiment = analysis.management_sentiment
        elif qa_scores:
            analysis.overall_sentiment = analysis.qa_sentiment
        
        analysis.overall_label = (
            "positive" if analysis.overall_sentiment > 0.1
            else "negative" if analysis.overall_sentiment < -0.1
            else "neutral"
        )
        
        # 6. Extract insights from full text
        full_text = transcript[:10000]
        
        # Key positives
        text_lower = full_text.lower()
        for indicator in POSITIVE_INDICATORS:
            if indicator in text_lower:
                analysis.key_positives.append(indicator)
        
        # Key negatives
        for indicator in NEGATIVE_INDICATORS:
            if indicator in text_lower:
                analysis.key_negatives.append(indicator)
        
        # Forward-looking statements
        analysis.forward_looking_statements = _extract_forward_looking(full_text)
        
        # Guidance direction
        analysis.guidance_direction = _detect_guidance_direction(full_text)
        
        # Key metric mentions
        mentions = _extract_key_mentions(full_text)
        analysis.revenue_mention = mentions.get("revenue")
        analysis.profit_mention = mentions.get("profit")
        analysis.margin_mention = mentions.get("margin")
        
        # Confidence based on how much data we have
        confidence = 0.3  # base
        if mgmt_scores:
            confidence += 0.2
        if qa_scores:
            confidence += 0.2
        if analysis.key_positives or analysis.key_negatives:
            confidence += 0.15
        if analysis.forward_looking_statements:
            confidence += 0.15
        analysis.confidence = min(1.0, confidence)
        
        self._stats["transcripts_analyzed"] += 1
        
        return analysis

    async def analyze_with_llm(
        self,
        symbol: str,
        transcript: str,
        quarter: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Enhanced analysis using LLM (Gemini) for deeper insights.
        Runs after basic FinBERT analysis for additional context.
        """
        if not self._llm_fn:
            return None
        
        try:
            # Truncate transcript for LLM
            truncated = transcript[:4000]
            
            prompt = f"""Analyze this earnings call transcript excerpt for {symbol} ({quarter}).

Transcript:
{truncated}

Provide a JSON response with:
1. "management_tone": "bullish"/"bearish"/"neutral"
2. "key_themes": [list of 3-5 key themes discussed]
3. "risks_mentioned": [list of risks]
4. "growth_drivers": [list of growth drivers]
5. "guidance_summary": one sentence about forward guidance
6. "sentiment_score": float between -1 (very negative) and +1 (very positive)
"""
            
            result = await self._llm_fn(prompt)
            return result
            
        except Exception as e:
            logger.error(f"LLM earnings analysis failed for {symbol}: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
