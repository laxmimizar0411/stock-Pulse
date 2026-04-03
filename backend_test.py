#!/usr/bin/env python3
"""
StockPulse Brain Phase 3.4-3.10 Backend API Testing
Testing all endpoints for phases 3.4 through 3.10 as specified in review request.
"""

import requests
import json
import time
from typing import Dict, Any, List

# Backend URL from frontend/.env
BASE_URL = "https://multiagent-trader-ai.preview.emergentagent.com/api"

class BrainPhase3Tester:
    def __init__(self):
        self.results = []
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log_result(self, test_name: str, success: bool, response_data: Any = None, error: str = None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "response_data": response_data,
            "error": error
        }
        self.results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if error:
            print(f"   Error: {error}")
        if response_data and success:
            print(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Non-dict response'}")
    
    def test_endpoint(self, method: str, endpoint: str, data: Dict = None, test_name: str = None) -> bool:
        """Test a single endpoint"""
        if not test_name:
            test_name = f"{method} {endpoint}"
        
        try:
            url = f"{BASE_URL}{endpoint}"
            
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    self.log_result(test_name, True, response_data)
                    return True
                except json.JSONDecodeError:
                    self.log_result(test_name, False, error=f"Invalid JSON response: {response.text[:200]}")
                    return False
            else:
                self.log_result(test_name, False, error=f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result(test_name, False, error=f"Request failed: {str(e)}")
            return False
        except Exception as e:
            self.log_result(test_name, False, error=f"Unexpected error: {str(e)}")
            return False

    def test_phase_3_4_risk_management(self):
        """Test Phase 3.4 - Risk Management endpoints"""
        print("\n=== Testing Phase 3.4 - Risk Management ===")
        
        # 1. GET /api/brain/phase3_4/summary
        self.test_endpoint("GET", "/brain/phase3_4/summary", test_name="Phase 3.4 Summary")
        
        # 2. POST /api/brain/risk/var
        var_data = {
            "symbol": "RELIANCE",
            "returns": [0.01, -0.02, 0.015, -0.005, 0.008, -0.012, 0.003, 0.02, -0.01, 0.007, 
                       -0.015, 0.005, 0.01, -0.008, 0.012, -0.003, 0.018, -0.007, 0.009, -0.011],
            "portfolio_value": 1000000
        }
        self.test_endpoint("POST", "/brain/risk/var", var_data, "VaR Calculation")
        
        # 3. POST /api/brain/risk/stress-test
        stress_test_data = {
            "symbol": "RELIANCE",
            "portfolio_value": 1000000,
            "sector": "energy"
        }
        self.test_endpoint("POST", "/brain/risk/stress-test", stress_test_data, "Stress Test")
        
        # 4. GET /api/brain/risk/stress-test/scenarios
        self.test_endpoint("GET", "/brain/risk/stress-test/scenarios", test_name="Stress Test Scenarios")
        
        # 5. POST /api/brain/risk/sebi-margin
        sebi_margin_data = {
            "symbol": "RELIANCE",
            "trade_value": 500000
        }
        self.test_endpoint("POST", "/brain/risk/sebi-margin", sebi_margin_data, "SEBI Margin Requirements")
        
        # 6. POST /api/brain/risk/hrp
        hrp_data = {
            "symbols": ["RELIANCE", "TCS", "HDFCBANK"],
            "returns_matrix": [
                [0.01, -0.005, 0.008],
                [0.015, 0.01, -0.003],
                [-0.02, 0.012, 0.005],
                [0.008, -0.003, 0.01],
                [0.005, 0.015, -0.008],
                [-0.01, 0.008, 0.012],
                [0.003, -0.01, 0.007],
                [0.02, 0.005, -0.005],
                [-0.015, 0.01, 0.008],
                [0.01, -0.008, 0.015],
                [0.007, 0.012, -0.003],
                [-0.005, 0.003, 0.01]
            ]
        }
        self.test_endpoint("POST", "/brain/risk/hrp", hrp_data, "HRP Portfolio Optimization")

    def test_phase_3_5_rag(self):
        """Test Phase 3.5 - RAG endpoints"""
        print("\n=== Testing Phase 3.5 - RAG ===")
        
        # 7. GET /api/brain/phase3_5/summary
        self.test_endpoint("GET", "/brain/phase3_5/summary", test_name="Phase 3.5 Summary")
        
        # 8. POST /api/brain/rag/search
        rag_search_data = {
            "query": "SEBI margin requirements",
            "limit": 3
        }
        self.test_endpoint("POST", "/brain/rag/search", rag_search_data, "RAG Search")
        
        # 9. GET /api/brain/rag/status
        self.test_endpoint("GET", "/brain/rag/status", test_name="RAG Status")

    def test_phase_3_6_governance(self):
        """Test Phase 3.6 - Governance endpoints"""
        print("\n=== Testing Phase 3.6 - Governance ===")
        
        # 10. GET /api/brain/phase3_6/summary
        self.test_endpoint("GET", "/brain/phase3_6/summary", test_name="Phase 3.6 Summary")
        
        # 11. POST /api/brain/governance/score
        governance_data = {
            "symbol": "RELIANCE",
            "promoter_holding_pct": 50.3,
            "promoter_pledge_pct": 0,
            "board_independence_ratio": 0.55,
            "big4_auditor": True,
            "dividend_consistency_years": 10
        }
        self.test_endpoint("POST", "/brain/governance/score", governance_data, "Governance Score")

    def test_phase_3_7_sector(self):
        """Test Phase 3.7 - Sector endpoints"""
        print("\n=== Testing Phase 3.7 - Sector ===")
        
        # 12. GET /api/brain/phase3_7/summary
        self.test_endpoint("GET", "/brain/phase3_7/summary", test_name="Phase 3.7 Summary")
        
        # 13. POST /api/brain/sector/rotation
        sector_rotation_data = {
            "sector_returns": {
                "banking": {"1m": 5.2, "3m": 12.0, "6m": 18.5},
                "it": {"1m": -2.1, "3m": 3.5, "6m": 8.0},
                "pharma": {"1m": 3.0, "3m": 7.5, "6m": 15.0},
                "auto": {"1m": 4.5, "3m": 10.0, "6m": 20.0}
            },
            "business_cycle": "expansion"
        }
        self.test_endpoint("POST", "/brain/sector/rotation", sector_rotation_data, "Sector Rotation Analysis")
        
        # 14. GET /api/brain/sector/list
        self.test_endpoint("GET", "/brain/sector/list", test_name="Sector List")

    def test_phase_3_8_dividends(self):
        """Test Phase 3.8 - Dividends endpoints"""
        print("\n=== Testing Phase 3.8 - Dividends ===")
        
        # 15. GET /api/brain/phase3_8/summary
        self.test_endpoint("GET", "/brain/phase3_8/summary", test_name="Phase 3.8 Summary")
        
        # 16. POST /api/brain/dividends/analyze
        dividend_data = {
            "symbol": "ITC",
            "current_price": 450,
            "eps": 15.0,
            "consecutive_years": 12,
            "dividends": [
                {"amount": 6.25, "type": "final"},
                {"amount": 5.75, "type": "interim"},
                {"amount": 5.5, "type": "final"},
                {"amount": 5.0, "type": "interim"}
            ]
        }
        self.test_endpoint("POST", "/brain/dividends/analyze", dividend_data, "Dividend Analysis")

    def test_phase_3_9_calendar(self):
        """Test Phase 3.9 - Calendar endpoints"""
        print("\n=== Testing Phase 3.9 - Calendar ===")
        
        # 17. GET /api/brain/phase3_9/summary
        self.test_endpoint("GET", "/brain/phase3_9/summary", test_name="Phase 3.9 Summary")
        
        # 18. GET /api/brain/calendar/upcoming?days=90
        self.test_endpoint("GET", "/brain/calendar/upcoming?days=90", test_name="Upcoming Calendar Events")
        
        # 19. GET /api/brain/calendar/by-type/rbi
        self.test_endpoint("GET", "/brain/calendar/by-type/rbi", test_name="RBI Calendar Events")

    def test_phase_3_10_explainability(self):
        """Test Phase 3.10 - Explainability endpoints"""
        print("\n=== Testing Phase 3.10 - Explainability ===")
        
        # 20. GET /api/brain/phase3_10/summary
        self.test_endpoint("GET", "/brain/phase3_10/summary", test_name="Phase 3.10 Summary")

    def test_phase_3_complete(self):
        """Test Phase 3 Complete endpoints"""
        print("\n=== Testing Phase 3 Complete ===")
        
        # 21. GET /api/brain/phase3/complete-summary
        self.test_endpoint("GET", "/brain/phase3/complete-summary", test_name="Phase 3 Complete Summary")

    def run_all_tests(self):
        """Run all Phase 3.4-3.10 tests"""
        print("Starting StockPulse Brain Phase 3.4-3.10 Testing")
        print(f"Backend URL: {BASE_URL}")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test phases
        self.test_phase_3_4_risk_management()
        self.test_phase_3_5_rag()
        self.test_phase_3_6_governance()
        self.test_phase_3_7_sector()
        self.test_phase_3_8_dividends()
        self.test_phase_3_9_calendar()
        self.test_phase_3_10_explainability()
        self.test_phase_3_complete()
        
        end_time = time.time()
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Total Time: {end_time - start_time:.2f} seconds")
        
        if failed_tests > 0:
            print("\nFAILED TESTS:")
            for result in self.results:
                if not result["success"]:
                    print(f"❌ {result['test']}: {result['error']}")
        
        print("\nPASSED TESTS:")
        for result in self.results:
            if result["success"]:
                print(f"✅ {result['test']}")
        
        return self.results

if __name__ == "__main__":
    tester = BrainPhase3Tester()
    results = tester.run_all_tests()