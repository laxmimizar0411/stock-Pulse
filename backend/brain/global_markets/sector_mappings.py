"""
India-Specific Sector Mappings

Maps global market movements to Indian sector impacts.
"""

from typing import Dict, List

# India-specific sector correlation mappings
INDIA_SECTOR_MAPPINGS = {
    "CRUDE_WTI": {
        "positive_impact": [
            # Higher crude prices help these sectors
            ("Oil & Gas", "upstream", 0.8),  # Upstream oil producers benefit
            ("Oil Marketing", "OMCs", 0.6),  # OMCs benefit from inventory gains
        ],
        "negative_impact": [
            # Higher crude prices hurt these sectors
            ("Aviation", "airlines", -0.9),  # Airlines hurt by high fuel costs
            ("Paints", "chemicals", -0.5),   # Raw material cost pressure
            ("Tyres", "rubber", -0.5),       # Rubber/chemical cost pressure
            ("FMCG", "transportation", -0.3), # Transportation cost impact
            ("Logistics", "transportation", -0.6), # Direct fuel cost impact
        ]
    },
    
    "CRUDE_BRENT": {
        # Similar to WTI
        "positive_impact": [
            ("Oil & Gas", "upstream", 0.8),
            ("Oil Marketing", "OMCs", 0.6),
        ],
        "negative_impact": [
            ("Aviation", "airlines", -0.9),
            ("Paints", "chemicals", -0.5),
            ("Tyres", "rubber", -0.5),
            ("FMCG", "transportation", -0.3),
        ]
    },
    
    "DXY": {
        # US Dollar Index impact
        "positive_impact": [
            # Stronger dollar helps exporters
            ("IT Services", "exports", 0.7),  # IT exports benefit
            ("Pharma", "exports", 0.6),       # Pharma exports benefit
            ("Textiles", "exports", 0.5),     # Textile exports benefit
        ],
        "negative_impact": [
            # Stronger dollar hurts importers and EM flows
            ("Oil Marketing", "imports", -0.6), # Import cost pressure
            ("Banking", "EM_flows", -0.4),      # FII outflows
            ("NBFCs", "EM_flows", -0.4),        # FII outflows
            ("Real Estate", "EM_flows", -0.3),  # FII outflows
        ]
    },
    
    "GOLD": {
        "positive_impact": [
            ("Gold", "commodity", 0.9),       # Direct correlation
            ("Jewellery", "commodity", 0.7),  # Jewellery companies
        ],
        "negative_impact": [
            # Gold as risk-off indicator
            ("Banking", "risk_sentiment", -0.2),
            ("NBFCs", "risk_sentiment", -0.2),
        ]
    },
    
    "MSCI_EM": {
        # Emerging Markets sentiment
        "positive_impact": [
            # EM rally helps Indian equities
            ("Banking", "flows", 0.6),
            ("NBFCs", "flows", 0.6),
            ("Real Estate", "flows", 0.5),
            ("Consumer Durables", "flows", 0.4),
        ],
        "negative_impact": []
    },
    
    "SP500": {
        # US market sentiment impact
        "positive_impact": [
            # Risk-on sentiment
            ("IT Services", "sentiment", 0.5),
            ("Banking", "sentiment", 0.4),
            ("Auto", "sentiment", 0.4),
        ],
        "negative_impact": []
    },
    
    "NASDAQ": {
        # Tech-heavy index
        "positive_impact": [
            ("IT Services", "tech_sentiment", 0.6),
            ("Software", "tech_sentiment", 0.7),
        ],
        "negative_impact": []
    },
    
    "US_10Y": {
        # US Treasury Yield
        "positive_impact": [
            # Higher yields strengthen dollar, help IT
            ("IT Services", "dollar", 0.3),
        ],
        "negative_impact": [
            # Higher yields = EM outflows
            ("Banking", "EM_flows", -0.5),
            ("NBFCs", "EM_flows", -0.5),
            ("Real Estate", "EM_flows", -0.6),
            ("PSU Banks", "EM_flows", -0.4),
        ]
    },
    
    "NIKKEI": {
        # Japanese market (Auto, Electronics linkage)
        "positive_impact": [
            ("Auto", "regional", 0.5),
            ("Auto Components", "regional", 0.5),
            ("Electronics", "regional", 0.4),
        ],
        "negative_impact": []
    },
    
    "HANGSENG": {
        # Hong Kong/China market (Trade, Pharma, Metals)
        "positive_impact": [
            ("Pharma", "china_demand", 0.4),
            ("Metals", "china_demand", 0.5),
            ("Chemicals", "china_demand", 0.4),
        ],
        "negative_impact": []
    }
}


def get_sector_impact_from_global_move(
    global_market: str,
    global_move_pct: float
) -> List[Dict[str, any]]:
    """
    Get Indian sector impacts from a global market move.
    
    Args:
        global_market: Name of global market (e.g., "CRUDE_WTI")
        global_move_pct: Percentage move in global market
        
    Returns:
        List of sector impacts with direction and magnitude
    """
    if global_market not in INDIA_SECTOR_MAPPINGS:
        return []
    
    mapping = INDIA_SECTOR_MAPPINGS[global_market]
    impacts = []
    
    # Positive impacts
    for sector, reason, sensitivity in mapping.get("positive_impact", []):
        impact_pct = global_move_pct * sensitivity
        impacts.append({
            "sector": sector,
            "impact_direction": "positive" if global_move_pct > 0 else "negative",
            "impact_magnitude_pct": abs(impact_pct),
            "reason": reason,
            "sensitivity": sensitivity,
            "global_market": global_market,
            "global_move_pct": global_move_pct
        })
    
    # Negative impacts
    for sector, reason, sensitivity in mapping.get("negative_impact", []):
        impact_pct = global_move_pct * abs(sensitivity)
        impacts.append({
            "sector": sector,
            "impact_direction": "negative" if global_move_pct > 0 else "positive",
            "impact_magnitude_pct": abs(impact_pct),
            "reason": reason,
            "sensitivity": abs(sensitivity),
            "global_market": global_market,
            "global_move_pct": global_move_pct
        })
    
    # Sort by impact magnitude
    impacts.sort(key=lambda x: x["impact_magnitude_pct"], reverse=True)
    
    return impacts


def aggregate_sector_impacts(
    global_moves: Dict[str, float]
) -> Dict[str, Dict[str, float]]:
    """
    Aggregate impacts from multiple global markets.
    
    Args:
        global_moves: Dictionary of {market_name: percentage_move}
        
    Returns:
        Dictionary of {sector: {total_impact, contributing_markets}}
    """
    sector_impacts = {}
    
    for market, move_pct in global_moves.items():
        impacts = get_sector_impact_from_global_move(market, move_pct)
        
        for impact in impacts:
            sector = impact["sector"]
            
            if sector not in sector_impacts:
                sector_impacts[sector] = {
                    "total_impact_pct": 0.0,
                    "contributing_markets": []
                }
            
            # Aggregate impact (positive or negative)
            if impact["impact_direction"] == "positive":
                sector_impacts[sector]["total_impact_pct"] += impact["impact_magnitude_pct"]
            else:
                sector_impacts[sector]["total_impact_pct"] -= impact["impact_magnitude_pct"]
            
            sector_impacts[sector]["contributing_markets"].append({
                "market": market,
                "move_pct": move_pct,
                "impact_pct": impact["impact_magnitude_pct"] if impact["impact_direction"] == "positive" else -impact["impact_magnitude_pct"],
                "reason": impact["reason"]
            })
    
    # Sort contributing markets by absolute impact
    for sector in sector_impacts:
        sector_impacts[sector]["contributing_markets"].sort(
            key=lambda x: abs(x["impact_pct"]),
            reverse=True
        )
    
    return sector_impacts
