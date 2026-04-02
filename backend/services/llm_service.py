import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


async def generate_stock_insight(stock_data: Dict, analysis_type: str = "full") -> str:
    """Generate LLM-powered insights for a stock"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return "LLM insights unavailable - API key not configured."
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"stock_analysis_{stock_data.get('symbol', 'unknown')}",
            system_message="""You are an expert Indian stock market analyst. Provide concise, actionable insights.
Focus on key factors affecting the stock. Be direct and avoid generic statements.
Format your response with clear sections using markdown."""
        ).with_model("openai", "gpt-4o")
        
        # Build context based on analysis type
        symbol = stock_data.get("symbol", "Unknown")
        name = stock_data.get("name", "Unknown")
        sector = stock_data.get("sector", "Unknown")
        price = stock_data.get("current_price", 0)
        change_pct = stock_data.get("price_change_percent", 0)
        
        fund = stock_data.get("fundamentals", {})
        val = stock_data.get("valuation", {})
        tech = stock_data.get("technicals", {})
        analysis = stock_data.get("analysis", {})
        
        if analysis_type == "score_explanation":
            prompt = f"""Explain why {name} ({symbol}) has these scores:
- Long-term Score: {analysis.get('long_term_score', 'N/A')}/100
- Short-term Score: {analysis.get('short_term_score', 'N/A')}/100
- Verdict: {analysis.get('verdict', 'N/A')}

Key metrics:
- ROE: {fund.get('roe', 'N/A')}%
- Revenue Growth: {fund.get('revenue_growth_yoy', 'N/A')}%
- P/E Ratio: {val.get('pe_ratio', 'N/A')}
- Debt/Equity: {fund.get('debt_to_equity', 'N/A')}
- RSI: {tech.get('rsi_14', 'N/A')}

Explain in 3-4 sentences why the score is high/low and what's driving it."""

        elif analysis_type == "risk_assessment":
            prompt = f"""Assess the key risks for {name} ({symbol}) in the {sector} sector:

Current metrics:
- Debt/Equity: {fund.get('debt_to_equity', 'N/A')}
- Interest Coverage: {fund.get('interest_coverage', 'N/A')}x
- Promoter Pledging: {stock_data.get('shareholding', {}).get('promoter_pledging', 'N/A')}%
- P/E vs Sector: {val.get('pe_ratio', 'N/A')}
- 52-week range: {tech.get('low_52_week', 'N/A')} - {tech.get('high_52_week', 'N/A')}

Identify top 3 risks in bullet points. Be specific to this company."""

        elif analysis_type == "news_summary":
            prompt = f"""Based on typical market dynamics for {name} ({symbol}):
- Sector: {sector}
- Recent price change: {change_pct}%
- Current technical position: RSI {tech.get('rsi_14', 50)}, Price vs 200-DMA

Provide a brief market sentiment summary (2-3 sentences) explaining likely factors driving recent price action."""

        else:  # full analysis
            prompt = f"""Provide a comprehensive analysis for {name} ({symbol}):

**Company Profile:**
- Sector: {sector}
- Current Price: ₹{price:,.2f} ({change_pct:+.2f}%)
- Market Cap Category: {stock_data.get('market_cap_category', 'N/A')}

**Fundamentals:**
- Revenue Growth (YoY): {fund.get('revenue_growth_yoy', 'N/A')}%
- ROE: {fund.get('roe', 'N/A')}%
- Operating Margin: {fund.get('operating_margin', 'N/A')}%
- Debt/Equity: {fund.get('debt_to_equity', 'N/A')}
- Free Cash Flow: ₹{fund.get('free_cash_flow', 0):,.0f} Cr

**Valuation:**
- P/E Ratio: {val.get('pe_ratio', 'N/A')}
- PEG Ratio: {val.get('peg_ratio', 'N/A')}
- EV/EBITDA: {val.get('ev_ebitda', 'N/A')}

**Technicals:**
- RSI (14): {tech.get('rsi_14', 'N/A')}
- Price vs 50-DMA: {('Above' if price > tech.get('sma_50', price) else 'Below')}
- Price vs 200-DMA: {('Above' if price > tech.get('sma_200', price) else 'Below')}

**Analysis Scores:**
- Long-term: {analysis.get('long_term_score', 'N/A')}/100
- Short-term: {analysis.get('short_term_score', 'N/A')}/100
- Verdict: {analysis.get('verdict', 'N/A')}

Provide:
1. **Investment Thesis** (2-3 sentences on why to consider this stock)
2. **Key Strengths** (2 bullet points)
3. **Key Risks** (2 bullet points)
4. **Actionable Recommendation** (1 sentence with specific action)"""
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response
        
    except Exception as e:
        logger.error(f"LLM insight generation failed: {str(e)}")
        return f"Unable to generate AI insights at this time. Error: {str(e)}"


async def summarize_news(news_items: list) -> str:
    """Summarize multiple news items into key takeaways"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return "News summarization unavailable."
        
        chat = LlmChat(
            api_key=api_key,
            session_id="news_summary",
            system_message="You are a financial news analyst. Summarize market news into actionable insights. Be concise."
        ).with_model("openai", "gpt-4o")
        
        news_text = "\n".join([
            f"- {item.get('title', '')} (Sentiment: {item.get('sentiment', 'NEUTRAL')})"
            for item in news_items[:10]
        ])
        
        prompt = f"""Summarize these Indian market news headlines into 3-4 key market takeaways:

{news_text}

Provide brief, actionable insights for an investor."""
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response
        
    except Exception as e:
        logger.error(f"News summarization failed: {str(e)}")
        return "News summarization unavailable."


async def analyze_sentiment(symbol: str, headlines: list) -> float:
    """
    Get LLM-based contextual sentiment score for a symbol.

    Takes recent headlines and returns a sentiment score [-1, +1]
    using the existing LLM service (GPT-4o via emergentintegrations).

    Used by the Brain sentiment aggregator as the LLM component
    in the 0.50×FinBERT + 0.20×VADER + 0.30×LLM ensemble.
    """
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return 0.0

        chat = LlmChat(
            api_key=api_key,
            session_id=f"sentiment_{symbol}",
            system_message=(
                "You are a financial sentiment analyst for the Indian stock market. "
                "Given recent news headlines about a stock, output ONLY a single "
                "floating-point number between -1.0 (extremely bearish) and +1.0 "
                "(extremely bullish). Output nothing else — just the number."
            ),
        ).with_model("openai", "gpt-4o")

        headlines_text = "\n".join(f"- {h}" for h in headlines[:10])
        prompt = f"Stock: {symbol}\n\nRecent headlines:\n{headlines_text}\n\nSentiment score:"

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        # Parse the float from response
        score = float(response.strip())
        return max(-1.0, min(1.0, score))

    except (ValueError, TypeError):
        logger.warning(f"LLM sentiment returned non-numeric response for {symbol}")
        return 0.0
    except Exception as e:
        logger.error(f"LLM sentiment analysis failed for {symbol}: {e}")
        return 0.0
