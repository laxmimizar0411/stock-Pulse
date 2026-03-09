"""
PDF Service for StockPulse
Generates PDF reports for stocks, comparisons, and portfolio health
Uses ReportLab for PDF generation
"""

import io
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ReportLab imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("ReportLab not installed. PDF generation will not be available.")
    # Provide stubs so module-level references don't crash
    import types
    colors = types.SimpleNamespace(
        HexColor=lambda x: None, Color=type(None),
        grey=None, white=None
    )
    TA_CENTER = TA_LEFT = TA_RIGHT = 0
    class _Stub:
        def __init__(self, *a, **kw): pass
    SimpleDocTemplate = Paragraph = Spacer = Table = TableStyle = _Stub
    PageBreak = Image = HRFlowable = _Stub
    A4 = letter = (0, 0)
    inch = cm = 1
    def getSampleStyleSheet(): return {}
    ParagraphStyle = _Stub


# Custom colors for the dark theme report
if PDF_AVAILABLE:
    COLORS = {
        "primary": colors.HexColor("#3B82F6"),
        "success": colors.HexColor("#22C55E"),
        "danger": colors.HexColor("#EF4444"),
        "warning": colors.HexColor("#F59E0B"),
        "text": colors.HexColor("#333333"),
        "muted": colors.HexColor("#666666"),
        "light": colors.HexColor("#F4F4F5"),
        "dark": colors.HexColor("#18181B"),
    }
else:
    COLORS = {}


def is_pdf_available() -> bool:
    """Check if PDF generation is available"""
    return PDF_AVAILABLE


def _get_styles():
    """Get custom paragraph styles"""
    styles = getSampleStyleSheet()
    
    # Custom title style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=COLORS["primary"],
        spaceAfter=30,
    ))
    
    # Section header style
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=COLORS["primary"],
        spaceBefore=20,
        spaceAfter=12,
    ))
    
    # Metric label style
    styles.add(ParagraphStyle(
        name='MetricLabel',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLORS["muted"],
    ))
    
    # Metric value style
    styles.add(ParagraphStyle(
        name='MetricValue',
        parent=styles['Normal'],
        fontSize=12,
        textColor=COLORS["text"],
        fontName='Helvetica-Bold',
    ))
    
    return styles


def _format_currency(value: float) -> str:
    """Format value as Indian currency"""
    if value is None:
        return "N/A"
    
    if abs(value) >= 10000000:
        return f"₹{value/10000000:.2f} Cr"
    elif abs(value) >= 100000:
        return f"₹{value/100000:.2f} L"
    else:
        return f"₹{value:,.2f}"


def _format_percent(value: float) -> str:
    """Format value as percentage"""
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _get_score_color(score: float) -> colors.Color:
    """Get color based on score"""
    if score >= 70:
        return COLORS["success"]
    elif score >= 40:
        return COLORS["warning"]
    else:
        return COLORS["danger"]


def _create_metrics_table(metrics: Dict[str, Any], title: str = None) -> Table:
    """Create a styled table for metrics"""
    data = []
    
    if title:
        data.append([Paragraph(f"<b>{title}</b>", _get_styles()['Normal'])])
    
    for key, value in metrics.items():
        label = key.replace("_", " ").title()
        
        if isinstance(value, float):
            if "percent" in key.lower() or "growth" in key.lower() or "yield" in key.lower():
                formatted = _format_percent(value)
            elif "price" in key.lower() or "cap" in key.lower() or "value" in key.lower():
                formatted = _format_currency(value)
            else:
                formatted = f"{value:.2f}"
        else:
            formatted = str(value) if value is not None else "N/A"
        
        data.append([label, formatted])
    
    table = Table(data, colWidths=[3*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLORS["light"]),
        ('TEXTCOLOR', (0, 0), (-1, -1), COLORS["text"]),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, COLORS["light"]),
    ]))
    
    return table


def generate_single_stock_pdf(stock_data: Dict[str, Any]) -> bytes:
    """Generate PDF report for a single stock"""
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF generation not available. Install reportlab.")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )
    
    styles = _get_styles()
    story = []
    
    # Title
    symbol = stock_data.get("symbol", "Unknown")
    name = stock_data.get("name", symbol)
    story.append(Paragraph(f"{symbol} - {name}", styles['CustomTitle']))
    
    # Generated timestamp
    story.append(Paragraph(
        f"Report generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        styles['MetricLabel']
    ))
    story.append(Spacer(1, 20))
    
    # Summary Box
    current_price = stock_data.get("current_price", 0)
    price_change = stock_data.get("price_change_percent", 0)
    analysis = stock_data.get("analysis", {})
    score = analysis.get("long_term_score", 0)
    verdict = analysis.get("verdict", "N/A")
    
    summary_data = [
        ["Current Price", _format_currency(current_price)],
        ["Day Change", _format_percent(price_change)],
        ["Analysis Score", f"{score}/100"],
        ["Verdict", verdict],
        ["Sector", stock_data.get("sector", "Unknown")],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLORS["light"]),
        ('TEXTCOLOR', (0, 0), (-1, -1), COLORS["text"]),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 1, COLORS["primary"]),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 30))
    
    # Fundamentals Section
    fundamentals = stock_data.get("fundamentals", {})
    if fundamentals:
        story.append(Paragraph("Fundamental Analysis", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        fund_metrics = {
            "ROE": fundamentals.get("roe"),
            "Revenue Growth (YoY)": fundamentals.get("revenue_growth_yoy"),
            "Net Profit Margin": fundamentals.get("net_profit_margin"),
            "Debt to Equity": fundamentals.get("debt_to_equity"),
            "Current Ratio": fundamentals.get("current_ratio"),
        }
        story.append(_create_metrics_table(fund_metrics))
        story.append(Spacer(1, 20))
    
    # Valuation Section
    valuation = stock_data.get("valuation", {})
    if valuation:
        story.append(Paragraph("Valuation Metrics", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        val_metrics = {
            "P/E Ratio": valuation.get("pe_ratio"),
            "P/B Ratio": valuation.get("pb_ratio"),
            "Dividend Yield": valuation.get("dividend_yield"),
            "Market Cap": valuation.get("market_cap"),
        }
        story.append(_create_metrics_table(val_metrics))
        story.append(Spacer(1, 20))
    
    # Technical Section
    technicals = stock_data.get("technicals", {})
    if technicals:
        story.append(Paragraph("Technical Indicators", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        tech_metrics = {
            "RSI (14)": technicals.get("rsi_14"),
            "SMA 50": technicals.get("sma_50"),
            "SMA 200": technicals.get("sma_200"),
            "52-Week High": technicals.get("high_52_week"),
            "52-Week Low": technicals.get("low_52_week"),
        }
        story.append(_create_metrics_table(tech_metrics))
        story.append(Spacer(1, 20))
    
    # Analysis Details
    if analysis:
        story.append(Paragraph("Analysis Breakdown", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        analysis_metrics = {
            "Long-term Score": analysis.get("long_term_score"),
            "Short-term Score": analysis.get("short_term_score"),
            "Fundamental Score": analysis.get("fundamental_score"),
            "Technical Score": analysis.get("technical_score"),
            "Risk Level": analysis.get("risk_level", "N/A"),
        }
        story.append(_create_metrics_table(analysis_metrics))
        story.append(Spacer(1, 20))
    
    # LLM Insight (if available)
    llm_insight = stock_data.get("llm_insight")
    if llm_insight:
        story.append(Paragraph("AI-Powered Insight", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        story.append(Paragraph(llm_insight, styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Footer
    story.append(Spacer(1, 40))
    story.append(HRFlowable(color=colors.grey, width="100%", thickness=0.5))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report is generated by StockPulse for educational purposes only. "
        "It should not be considered as financial advice.",
        ParagraphStyle(name='Footer', fontSize=8, textColor=COLORS["muted"], alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_comparison_pdf(stocks_data: List[Dict[str, Any]]) -> bytes:
    """Generate PDF report comparing multiple stocks"""
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF generation not available. Install reportlab.")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=50,
        leftMargin=50,
        topMargin=72,
        bottomMargin=72,
    )
    
    styles = _get_styles()
    story = []
    
    # Title
    symbols = [s.get("symbol", "") for s in stocks_data]
    story.append(Paragraph(f"Stock Comparison: {' vs '.join(symbols)}", styles['CustomTitle']))
    story.append(Paragraph(
        f"Report generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        styles['MetricLabel']
    ))
    story.append(Spacer(1, 30))
    
    # Comparison table
    headers = ["Metric"] + symbols
    rows = [headers]
    
    # Add comparison rows
    metrics = [
        ("Current Price", lambda s: _format_currency(s.get("current_price", 0))),
        ("Day Change", lambda s: _format_percent(s.get("price_change_percent", 0))),
        ("P/E Ratio", lambda s: f"{s.get('valuation', {}).get('pe_ratio', 'N/A'):.2f}" if s.get('valuation', {}).get('pe_ratio') else "N/A"),
        ("ROE", lambda s: _format_percent(s.get("fundamentals", {}).get("roe", 0))),
        ("Debt/Equity", lambda s: f"{s.get('fundamentals', {}).get('debt_to_equity', 0):.2f}"),
        ("Score", lambda s: f"{s.get('analysis', {}).get('long_term_score', 0)}/100"),
        ("Verdict", lambda s: s.get("analysis", {}).get("verdict", "N/A")),
    ]
    
    for metric_name, extractor in metrics:
        row = [metric_name]
        for stock in stocks_data:
            row.append(extractor(stock))
        rows.append(row)
    
    col_widths = [1.5*inch] + [1.3*inch] * len(symbols)
    comparison_table = Table(rows, colWidths=col_widths)
    comparison_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLORS["light"]]),
    ]))
    
    story.append(comparison_table)
    story.append(Spacer(1, 30))
    
    # Footer
    story.append(HRFlowable(color=colors.grey, width="100%", thickness=0.5))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report is generated by StockPulse for educational purposes only.",
        ParagraphStyle(name='Footer', fontSize=8, textColor=COLORS["muted"], alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_portfolio_health_pdf(portfolio_data: Dict[str, Any]) -> bytes:
    """Generate PDF report for portfolio health analysis"""
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF generation not available. Install reportlab.")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )
    
    styles = _get_styles()
    story = []
    
    # Title
    story.append(Paragraph("Portfolio Health Report", styles['CustomTitle']))
    story.append(Paragraph(
        f"Report generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        styles['MetricLabel']
    ))
    story.append(Spacer(1, 30))
    
    portfolio = portfolio_data.get("portfolio", {})
    
    # Summary metrics
    summary_data = [
        ["Total Invested", _format_currency(portfolio.get("total_invested", 0))],
        ["Current Value", _format_currency(portfolio.get("current_value", 0))],
        ["Total P&L", _format_currency(portfolio.get("total_profit_loss", 0))],
        ["Return %", _format_percent(portfolio.get("total_profit_loss_percent", 0))],
        ["XIRR", _format_percent(portfolio.get("xirr", 0))],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLORS["light"]),
        ('TEXTCOLOR', (0, 0), (-1, -1), COLORS["text"]),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 1, COLORS["primary"]),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 30))
    
    # Holdings table
    holdings = portfolio.get("holdings", [])
    if holdings:
        story.append(Paragraph("Holdings Breakdown", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        holdings_data = [["Symbol", "Qty", "Avg Price", "Current", "P&L"]]
        for h in holdings:
            holdings_data.append([
                h.get("symbol", ""),
                str(h.get("quantity", 0)),
                _format_currency(h.get("avg_buy_price", 0)),
                _format_currency(h.get("current_price", 0)),
                _format_percent(h.get("profit_loss_percent", 0)),
            ])
        
        holdings_table = Table(holdings_data, colWidths=[1.2*inch, 0.8*inch, 1.2*inch, 1.2*inch, 1*inch])
        holdings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(holdings_table)
        story.append(Spacer(1, 20))
    
    # Health Assessment
    story.append(Paragraph("Health Assessment", styles['SectionHeader']))
    story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
    story.append(Spacer(1, 10))
    
    risk_assessment = portfolio_data.get("risk_assessment", "MODERATE")
    diversification_score = portfolio_data.get("diversification_score", 0)
    
    health_metrics = {
        "Risk Assessment": risk_assessment,
        "Diversification Score": f"{diversification_score}/100",
    }
    story.append(_create_metrics_table(health_metrics))
    story.append(Spacer(1, 20))
    
    # Recommendations
    recommendations = portfolio_data.get("recommendations", [])
    if recommendations:
        story.append(Paragraph("Recommendations", styles['SectionHeader']))
        story.append(HRFlowable(color=COLORS["primary"], width="100%", thickness=1))
        story.append(Spacer(1, 10))
        
        for rec in recommendations:
            story.append(Paragraph(f"• {rec}", styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Footer
    story.append(Spacer(1, 40))
    story.append(HRFlowable(color=colors.grey, width="100%", thickness=0.5))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report is generated by StockPulse for educational purposes only.",
        ParagraphStyle(name='Footer', fontSize=8, textColor=COLORS["muted"], alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
