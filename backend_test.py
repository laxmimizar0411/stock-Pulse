#!/usr/bin/env python3
"""
Comprehensive Phase 3 Production Verification Test Suite
Tests ALL 22 Phase 3 endpoints for StockPulse Brain
"""

import requests
import json
import time
from typing import Dict, Any, List, Tuple

# Backend URL from environment
BACKEND_URL = "https://multiagent-trader-ai.preview.emergentagent.com"

class Phase3TestSuite:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def log_result(self, test_name: str, passed: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "status": status,
            "passed": passed,
            "details": details,
            "response_data": response_data
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"{status}: {test_name}")
        if details:
            print(f"   Details: {details}")
        print()

    def make_request(self, method: str, endpoint: str, data: Dict = None, timeout: int = 30) -> Tuple[bool, Any, str]:
        """Make HTTP request with error handling"""
        url = f"{BACKEND_URL}{endpoint}"
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, timeout=timeout)
            else:
                return False, None, f"Unsupported method: {method}"
            
            if response.status_code == 200:
                try:
                    return True, response.json(), ""
                except json.JSONDecodeError:
                    return False, None, f"Invalid JSON response: {response.text[:200]}"
            else:
                return False, None, f"HTTP {response.status_code}: {response.text[:200]}"
                
        except requests.exceptions.Timeout:
            return False, None, f"Request timeout after {timeout}s"
        except requests.exceptions.RequestException as e:
            return False, None, f"Request error: {str(e)}"

    def validate_sentiment_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate sentiment analysis response structure"""
        required_fields = ["sentiment_score", "label", "article_count"]
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        # Validate sentiment_score is float in range [-1, 1]
        score = data.get("sentiment_score")
        if not isinstance(score, (int, float)) or not (-1 <= score <= 1):
            return False, f"Invalid sentiment_score: {score} (must be float in [-1,1])"
        
        # Validate label
        label = data.get("label")
        if label not in ["positive", "negative", "neutral"]:
            return False, f"Invalid label: {label} (must be positive/negative/neutral)"
        
        return True, "Valid sentiment response structure"

    def validate_agent_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate agent analysis response structure"""
        required_fields = ["final_signal", "analyst_results", "bull_case", "bear_case", 
                          "synthesis", "trade_plan", "risk_review", "report", "stages_completed"]
        
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        # Validate analyst_results has 4 items
        analyst_results = data.get("analyst_results", [])
        if not isinstance(analyst_results, list) or len(analyst_results) != 4:
            return False, f"analyst_results must have 4 items, got {len(analyst_results)}"
        
        return True, "Valid agent response structure"

    def validate_var_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate VaR response structure"""
        required_keys = ["historical", "parametric", "monte_carlo"]
        for key in required_keys:
            if key not in data:
                return False, f"Missing VaR method: {key}"
            
            method_data = data[key]
            if "var_1d" not in method_data or "cvar_1d" not in method_data:
                return False, f"Missing var_1d or cvar_1d in {key}"
        
        return True, "Valid VaR response structure"

    def validate_stress_test_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate stress test response structure"""
        # Check if we have scenario objects (not array)
        scenario_keys = [key for key in data.keys() if key not in ["computed_at", "metadata"]]
        
        if len(scenario_keys) < 3:  # Expect at least 3 scenarios
            return False, f"Expected at least 3 scenarios, got {len(scenario_keys)}"
        
        # Check for banking sector multiplier > 1.0 for some scenarios
        banking_multipliers = []
        for scenario_key in scenario_keys:
            scenario = data[scenario_key]
            if isinstance(scenario, dict):
                if "sector_multiplier" in scenario:
                    banking_multipliers.append(scenario["sector_multiplier"])
        
        if not any(mult > 1.0 for mult in banking_multipliers):
            return False, "No banking sector multiplier > 1.0 found"
        
        return True, "Valid stress test response structure"

    def validate_sebi_margin_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate SEBI margin response structure"""
        required_fields = ["var_margin", "elm_margin", "delivery_margin", "compliant"]
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        return True, "Valid SEBI margin response structure"

    def validate_hrp_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate HRP response structure"""
        if "weights" not in data:
            return False, "Missing weights field"
        
        weights = data["weights"]
        if not isinstance(weights, dict):
            return False, "Weights must be a dictionary"
        
        # Check all 4 symbols have weights
        expected_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY"]
        for symbol in expected_symbols:
            if symbol not in weights:
                return False, f"Missing weight for symbol: {symbol}"
        
        # Check weights sum to ~1.0
        total_weight = sum(weights.values())
        if not (0.95 <= total_weight <= 1.05):
            return False, f"Weights sum to {total_weight}, expected ~1.0"
        
        return True, "Valid HRP response structure"

    def validate_rag_search_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate RAG search response structure"""
        if "results" not in data:
            return False, "Missing results field"
        
        results = data["results"]
        if not isinstance(results, list):
            return False, "Results must be a list"
        
        # Check that results have score > 0
        for result in results:
            if "score" not in result or result["score"] <= 0:
                return False, f"Invalid score in result: {result.get('score')}"
        
        return True, "Valid RAG search response structure"

    def validate_governance_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate governance score response structure"""
        required_fields = ["total_score", "grade"]
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        return True, "Valid governance response structure"

    def validate_sector_rotation_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate sector rotation response structure"""
        if "scores" not in data:
            return False, "Missing scores field"
        
        scores = data["scores"]
        if not isinstance(scores, list):
            return False, "Scores must be a list"
        
        # Check that each score has required fields
        for score in scores:
            if not all(field in score for field in ["sector", "score", "rank"]):
                return False, "Missing required fields in score object"
        
        return True, "Valid sector rotation response structure"

    def validate_dividend_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate dividend analysis response structure"""
        required_fields = ["grade", "sustainability_score", "current_yield_pct"]
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        return True, "Valid dividend response structure"

    def validate_calendar_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate calendar response structure"""
        if "events" not in data:
            return False, "Missing events field"
        
        events = data["events"]
        if not isinstance(events, list):
            return False, "Events must be a list"
        
        return True, "Valid calendar response structure"

    def validate_health_response(self, data: Dict) -> Tuple[bool, str]:
        """Validate health response structure"""
        if "subsystems" not in data:
            return False, "Missing subsystems field"
        
        subsystems = data["subsystems"]
        if not isinstance(subsystems, dict):
            return False, "Subsystems must be a dictionary"
        
        # Check for key subsystems mentioned in review
        expected_subsystems = [
            "sentiment_pipeline", "social_scraper", "earnings_analyzer", 
            "agent_orchestrator", "rag_knowledge_base", "governance_scorer",
            "sector_rotation", "dividend_intelligence", "regulatory_calendar", 
            "explainability_engine"
        ]
        
        for subsystem in expected_subsystems:
            if subsystem not in subsystems:
                return False, f"Missing expected subsystem: {subsystem}"
        
        return True, "Valid health response structure"

    def run_phase3_2_sentiment_tests(self):
        """Test Phase 3.2 - Sentiment Pipeline (5 tests)"""
        print("=== Phase 3.2 - Sentiment Pipeline Tests ===")
        
        # Test 1: Symbol sentiment with force refresh
        success, data, error = self.make_request("GET", "/api/brain/sentiment/RELIANCE?force_refresh=true", timeout=30)
        if success:
            valid, msg = self.validate_sentiment_response(data)
            self.log_result("3.2.1 - Symbol Sentiment (RELIANCE)", valid, msg, data)
        else:
            self.log_result("3.2.1 - Symbol Sentiment (RELIANCE)", False, error)
        
        # Test 2: Market overview sentiment
        success, data, error = self.make_request("GET", "/api/brain/sentiment/market/overview", timeout=30)
        if success:
            valid, msg = self.validate_sentiment_response(data)
            self.log_result("3.2.2 - Market Overview Sentiment", valid, msg, data)
        else:
            self.log_result("3.2.2 - Market Overview Sentiment", False, error)
        
        # Test 3: Social media feed
        success, data, error = self.make_request("GET", "/api/brain/sentiment/social/feed")
        if success:
            has_post_count = "post_count" in data
            self.log_result("3.2.3 - Social Media Feed", has_post_count, 
                          f"post_count present: {has_post_count}", data)
        else:
            self.log_result("3.2.3 - Social Media Feed", False, error)
        
        # Test 4: Earnings call analysis
        earnings_body = {
            "symbol": "TCS",
            "transcript": "Ladies and gentlemen welcome to TCS Q1 FY26 earnings. Management Discussion: We are pleased to report revenue of Rs 62000 crores up 8 percent year on year. EBIT margin at 26 percent. Deal TCV at 12.2 billion USD. Attrition improved to 12 percent. Digital revenue now 35 percent of total. We see strong demand in cloud migration and AI services. Capex guidance remains at 5 percent of revenue. Question and Answer Session: Analyst from JP Morgan: What is the outlook for BFSI vertical given US banking concerns? Management: We see continued investment in core modernization. Our banking clients are prioritizing efficiency through technology.",
            "quarter": "Q1FY26"
        }
        success, data, error = self.make_request("POST", "/api/brain/sentiment/earnings-call", earnings_body)
        if success:
            required_fields = ["management_sentiment", "qa_sentiment", "tone_divergence"]
            has_all_fields = all(field in data for field in required_fields)
            self.log_result("3.2.4 - Earnings Call Analysis", has_all_fields,
                          f"Required fields present: {has_all_fields}", data)
        else:
            self.log_result("3.2.4 - Earnings Call Analysis", False, error)
        
        # Test 5: Pipeline status
        success, data, error = self.make_request("GET", "/api/brain/sentiment/pipeline/status")
        if success:
            has_components = "components" in data or len(data) > 0
            self.log_result("3.2.5 - Pipeline Status", has_components,
                          f"Components present: {has_components}", data)
        else:
            self.log_result("3.2.5 - Pipeline Status", False, error)

    def run_phase3_3_agent_tests(self):
        """Test Phase 3.3 - Agent System (1 test)"""
        print("=== Phase 3.3 - Agent System Tests ===")
        
        # Test 6: Agent analysis with 90s timeout
        agent_body = {
            "symbol": "TCS",
            "context": {
                "regime": "bull_trend",
                "current_price": 4200
            }
        }
        success, data, error = self.make_request("POST", "/api/brain/agents/analyze", agent_body, timeout=90)
        if success:
            valid, msg = self.validate_agent_response(data)
            self.log_result("3.3.1 - Agent Analysis (TCS)", valid, msg, data)
        else:
            self.log_result("3.3.1 - Agent Analysis (TCS)", False, error)

    def run_phase3_4_risk_tests(self):
        """Test Phase 3.4 - Risk Management (4 tests)"""
        print("=== Phase 3.4 - Risk Management Tests ===")
        
        # Test 7: VaR calculation
        var_body = {
            "symbol": "RELIANCE",
            "returns": [0.01,-0.02,0.015,-0.005,0.008,-0.012,0.003,0.02,-0.01,0.007,-0.015,0.005,0.01,-0.008,0.012,-0.003,0.018,-0.007,0.009,-0.011,0.005,-0.01,0.008,0.003,-0.015,0.012,-0.005,0.01,0.007,-0.008],
            "portfolio_value": 1000000
        }
        success, data, error = self.make_request("POST", "/api/brain/risk/var", var_body)
        if success:
            valid, msg = self.validate_var_response(data)
            self.log_result("3.4.1 - VaR Calculation", valid, msg, data)
        else:
            self.log_result("3.4.1 - VaR Calculation", False, error)
        
        # Test 8: Stress testing
        stress_body = {
            "symbol": "HDFCBANK",
            "portfolio_value": 2000000,
            "sector": "banking"
        }
        success, data, error = self.make_request("POST", "/api/brain/risk/stress-test", stress_body)
        if success:
            valid, msg = self.validate_stress_test_response(data)
            self.log_result("3.4.2 - Stress Testing", valid, msg, data)
        else:
            self.log_result("3.4.2 - Stress Testing", False, error)
        
        # Test 9: SEBI margin requirements
        sebi_body = {
            "symbol": "INFY",
            "trade_value": 750000,
            "is_delivery": True,
            "current_price": 1850,
            "prev_close": 1820,
            "portfolio_value": 5000000
        }
        success, data, error = self.make_request("POST", "/api/brain/risk/sebi-margin", sebi_body)
        if success:
            valid, msg = self.validate_sebi_margin_response(data)
            self.log_result("3.4.3 - SEBI Margin Requirements", valid, msg, data)
        else:
            self.log_result("3.4.3 - SEBI Margin Requirements", False, error)
        
        # Test 10: HRP portfolio optimization
        hrp_body = {
            "symbols": ["RELIANCE", "TCS", "HDFCBANK", "INFY"],
            "returns_matrix": [
                [0.01,-0.005,0.008,0.003],
                [0.015,0.01,-0.003,-0.005],
                [-0.02,0.012,0.005,0.008],
                [0.008,-0.003,0.01,0.015],
                [0.005,0.015,-0.008,-0.01],
                [-0.01,0.008,0.012,0.007],
                [0.003,-0.01,0.007,0.005],
                [0.02,0.005,-0.005,0.01],
                [-0.015,0.01,0.008,-0.003],
                [0.01,-0.008,0.015,0.012],
                [0.007,0.012,-0.003,0.008],
                [-0.005,0.003,0.01,-0.005]
            ]
        }
        success, data, error = self.make_request("POST", "/api/brain/risk/hrp", hrp_body)
        if success:
            valid, msg = self.validate_hrp_response(data)
            self.log_result("3.4.4 - HRP Portfolio Optimization", valid, msg, data)
        else:
            self.log_result("3.4.4 - HRP Portfolio Optimization", False, error)

    def run_phase3_5_rag_tests(self):
        """Test Phase 3.5 - RAG Knowledge Base (3 tests)"""
        print("=== Phase 3.5 - RAG Knowledge Base Tests ===")
        
        # Test 11: RAG search
        search_body = {
            "query": "What are RBI monetary policy impact on banking sector",
            "limit": 5
        }
        success, data, error = self.make_request("POST", "/api/brain/rag/search", search_body)
        if success:
            valid, msg = self.validate_rag_search_response(data)
            self.log_result("3.5.1 - RAG Search", valid, msg, data)
        else:
            self.log_result("3.5.1 - RAG Search", False, error)
        
        # Test 12: Add document to RAG
        add_body = {
            "title": "Reliance Industries Overview",
            "content": "Reliance Industries Ltd is India largest private sector company by revenue. Key businesses: O2C petrochemicals, Retail, Digital Jio Platforms. Market cap exceeds Rs 17 lakh crore.",
            "source": "research",
            "category": "company",
            "symbols": ["RELIANCE"]
        }
        success, data, error = self.make_request("POST", "/api/brain/rag/add", add_body)
        if success:
            has_success = data.get("success", False)
            self.log_result("3.5.2 - RAG Add Document", has_success,
                          f"Success: {has_success}", data)
        else:
            self.log_result("3.5.2 - RAG Add Document", False, error)
        
        # Test 13: Search for added document
        search_reliance_body = {
            "query": "Reliance Industries business overview",
            "limit": 3
        }
        success, data, error = self.make_request("POST", "/api/brain/rag/search", search_reliance_body)
        if success:
            valid, msg = self.validate_rag_search_response(data)
            found_doc = any("Reliance" in str(result) for result in data.get("results", []))
            self.log_result("3.5.3 - RAG Search Added Document", valid and found_doc,
                          f"Found added document: {found_doc}", data)
        else:
            self.log_result("3.5.3 - RAG Search Added Document", False, error)

    def run_phase3_6_governance_tests(self):
        """Test Phase 3.6 - Governance (2 tests)"""
        print("=== Phase 3.6 - Governance Tests ===")
        
        # Test 14: Good governance score
        good_gov_body = {
            "symbol": "RELIANCE",
            "promoter_holding_pct": 50.3,
            "promoter_pledge_pct": 0,
            "board_independence_ratio": 0.55,
            "big4_auditor": True,
            "auditor_tenure_years": 5,
            "related_party_txn_pct": 8.0,
            "regulatory_penalties": 0,
            "dividend_consistency_years": 10,
            "mgmt_turnover_3yr": 1,
            "timely_disclosures": True
        }
        success, data, error = self.make_request("POST", "/api/brain/governance/score", good_gov_body)
        if success:
            valid, msg = self.validate_governance_response(data)
            score = data.get("total_score", 0)
            grade = data.get("grade", "")
            good_score = score >= 70 and grade in ["A", "A+", "B+"]
            self.log_result("3.6.1 - Good Governance Score", valid and good_score,
                          f"Score: {score}, Grade: {grade}", data)
        else:
            self.log_result("3.6.1 - Good Governance Score", False, error)
        
        # Test 15: Bad governance score
        bad_gov_body = {
            "symbol": "BADCORP",
            "promoter_holding_pct": 15,
            "promoter_pledge_pct": 45,
            "board_independence_ratio": 0.25,
            "big4_auditor": False,
            "related_party_txn_pct": 20,
            "regulatory_penalties": 5
        }
        success, data, error = self.make_request("POST", "/api/brain/governance/score", bad_gov_body)
        if success:
            valid, msg = self.validate_governance_response(data)
            score = data.get("total_score", 100)
            grade = data.get("grade", "A")
            flags = data.get("flags", [])
            bad_score = score < 40 and grade in ["C", "D"] and len(flags) > 1
            self.log_result("3.6.2 - Bad Governance Score", valid and bad_score,
                          f"Score: {score}, Grade: {grade}, Flags: {len(flags)}", data)
        else:
            self.log_result("3.6.2 - Bad Governance Score", False, error)

    def run_phase3_7_sector_tests(self):
        """Test Phase 3.7 - Sector Rotation (1 test)"""
        print("=== Phase 3.7 - Sector Rotation Tests ===")
        
        # Test 16: Sector rotation analysis
        sector_body = {
            "sector_returns": {
                "banking": {"1m": 5.2, "3m": 12.0, "6m": 18.5},
                "it": {"1m": -2.1, "3m": 3.5, "6m": 8.0},
                "pharma": {"1m": 3.0, "3m": 7.5, "6m": 15.0},
                "auto": {"1m": 4.5, "3m": 10.0, "6m": 20.0},
                "fmcg": {"1m": 1.0, "3m": 4.0, "6m": 6.0},
                "energy": {"1m": 6.0, "3m": 15.0, "6m": 22.0},
                "metals": {"1m": -3.0, "3m": -1.0, "6m": 5.0}
            },
            "business_cycle": "expansion"
        }
        success, data, error = self.make_request("POST", "/api/brain/sector/rotation", sector_body)
        if success:
            valid, msg = self.validate_sector_rotation_response(data)
            # Check if banking/auto have high scores (expansion cycle)
            scores = data.get("scores", [])
            banking_auto_high = any(
                score.get("sector") in ["banking", "auto"] and score.get("rank", 10) <= 3
                for score in scores
            )
            self.log_result("3.7.1 - Sector Rotation Analysis", valid and banking_auto_high,
                          f"Banking/Auto high ranks: {banking_auto_high}, Valid structure: {valid}", data)
        else:
            self.log_result("3.7.1 - Sector Rotation Analysis", False, error)

    def run_phase3_8_dividend_tests(self):
        """Test Phase 3.8 - Dividends (1 test)"""
        print("=== Phase 3.8 - Dividend Tests ===")
        
        # Test 17: Dividend analysis
        dividend_body = {
            "symbol": "ITC",
            "current_price": 450,
            "eps": 15.0,
            "consecutive_years": 12,
            "dividends": [
                {"amount": 6.25, "type": "final"},
                {"amount": 5.75, "type": "interim"},
                {"amount": 5.5, "type": "final"},
                {"amount": 5.0, "type": "interim"},
                {"amount": 4.5, "type": "final"},
                {"amount": 4.0, "type": "interim"}
            ]
        }
        success, data, error = self.make_request("POST", "/api/brain/dividends/analyze", dividend_body)
        if success:
            valid, msg = self.validate_dividend_response(data)
            grade = data.get("grade", "")
            sustainability = data.get("sustainability_score", 0)
            yield_pct = data.get("current_yield_pct", 0)
            aristocrat = grade == "Aristocrat" and sustainability > 50 and yield_pct > 0
            self.log_result("3.8.1 - Dividend Analysis", valid and aristocrat,
                          f"Grade: {grade}, Sustainability: {sustainability}, Yield: {yield_pct}%", data)
        else:
            self.log_result("3.8.1 - Dividend Analysis", False, error)

    def run_phase3_9_calendar_tests(self):
        """Test Phase 3.9 - Calendar (2 tests)"""
        print("=== Phase 3.9 - Calendar Tests ===")
        
        # Test 18: Upcoming events
        success, data, error = self.make_request("GET", "/api/brain/calendar/upcoming?days=180")
        if success:
            valid, msg = self.validate_calendar_response(data)
            events = data.get("events", [])
            has_events = len(events) > 0
            self.log_result("3.9.1 - Upcoming Events", valid and has_events,
                          f"Events count: {len(events)}", data)
        else:
            self.log_result("3.9.1 - Upcoming Events", False, error)
        
        # Test 19: Expiry events
        success, data, error = self.make_request("GET", "/api/brain/calendar/by-type/expiry")
        if success:
            valid, msg = self.validate_calendar_response(data)
            events = data.get("events", [])
            all_expiry = all(event.get("type") == "expiry" for event in events)
            self.log_result("3.9.2 - Expiry Events", valid and all_expiry,
                          f"All events are expiry type: {all_expiry}", data)
        else:
            self.log_result("3.9.2 - Expiry Events", False, error)

    def run_phase3_overall_tests(self):
        """Test Phase 3 Overall (3 tests)"""
        print("=== Phase 3 Overall Tests ===")
        
        # Test 20: Phase 3.10 summary
        success, data, error = self.make_request("GET", "/api/brain/phase3_10/summary")
        if success:
            has_status = "status" in data
            has_methods = "methods" in data
            self.log_result("3.10.1 - Phase 3.10 Summary", has_status and has_methods,
                          f"Status: {has_status}, Methods: {has_methods}", data)
        else:
            self.log_result("3.10.1 - Phase 3.10 Summary", False, error)
        
        # Test 21: Complete Phase 3 summary
        success, data, error = self.make_request("GET", "/api/brain/phase3/complete-summary")
        if success:
            sub_phases = data.get("sub_phases", {})
            expected_phases = ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10"]
            all_phases_present = all(phase in sub_phases for phase in expected_phases)
            self.log_result("3.11.1 - Complete Phase 3 Summary", all_phases_present,
                          f"All 10 sub-phases present: {all_phases_present}", data)
        else:
            self.log_result("3.11.1 - Complete Phase 3 Summary", False, error)
        
        # Test 22: Brain health
        success, data, error = self.make_request("GET", "/api/brain/health")
        if success:
            valid, msg = self.validate_health_response(data)
            self.log_result("3.12.1 - Brain Health", valid, msg, data)
        else:
            self.log_result("3.12.1 - Brain Health", False, error)

    def run_all_tests(self):
        """Run all Phase 3 tests"""
        print("🧠 Starting Comprehensive Phase 3 Production Verification")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test phases
        self.run_phase3_2_sentiment_tests()
        self.run_phase3_3_agent_tests()
        self.run_phase3_4_risk_tests()
        self.run_phase3_5_rag_tests()
        self.run_phase3_6_governance_tests()
        self.run_phase3_7_sector_tests()
        self.run_phase3_8_dividend_tests()
        self.run_phase3_9_calendar_tests()
        self.run_phase3_overall_tests()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Print summary
        print("=" * 60)
        print("🏁 PHASE 3 PRODUCTION VERIFICATION COMPLETE")
        print("=" * 60)
        print(f"Total Tests: {self.passed + self.failed}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"⏱️  Total Time: {total_time:.2f} seconds")
        print(f"📊 Success Rate: {(self.passed / (self.passed + self.failed) * 100):.1f}%")
        print()
        
        # Print failed tests details
        if self.failed > 0:
            print("❌ FAILED TESTS:")
            for result in self.results:
                if not result["passed"]:
                    print(f"   • {result['test']}: {result['details']}")
            print()
        
        return self.passed, self.failed, self.results

if __name__ == "__main__":
    test_suite = Phase3TestSuite()
    passed, failed, results = test_suite.run_all_tests()
    
    # Exit with error code if any tests failed
    exit(0 if failed == 0 else 1)