#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime
from typing import Dict, List, Any

class StockAnalysisPlatformTester:
    def __init__(self, base_url="https://multiagent-trader-ai.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, data: Dict = None, params: Dict = None) -> tuple:
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                self.passed_tests.append(name)
                try:
                    return success, response.json()
                except:
                    return success, response.text
            else:
                print(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "response": response.text[:500]
                })
                return False, {}

        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e)
            })
            return False, {}

    def test_health_endpoints(self):
        """Test basic health endpoints"""
        print("\n" + "="*50)
        print("TESTING HEALTH ENDPOINTS")
        print("="*50)
        
        self.run_test("API Root", "GET", "", 200)
        self.run_test("Health Check", "GET", "health", 200)

    def test_market_overview(self):
        """Test market overview endpoint"""
        print("\n" + "="*50)
        print("TESTING MARKET OVERVIEW")
        print("="*50)
        
        success, data = self.run_test("Market Overview", "GET", "market/overview", 200)
        if success and data:
            # Verify required fields
            required_fields = ['nifty_50', 'sensex', 'nifty_bank', 'india_vix', 'market_breadth', 'fii_dii']
            for field in required_fields:
                if field in data:
                    print(f"   ✓ Found {field}")
                else:
                    print(f"   ⚠️  Missing {field}")

    def test_stocks_endpoints(self):
        """Test stock-related endpoints"""
        print("\n" + "="*50)
        print("TESTING STOCKS ENDPOINTS")
        print("="*50)
        
        # Get all stocks
        success, stocks_data = self.run_test("Get All Stocks", "GET", "stocks", 200, params={"limit": 10})
        
        if success and stocks_data and len(stocks_data) > 0:
            # Test individual stock
            test_symbol = stocks_data[0]['symbol']
            print(f"   Using test symbol: {test_symbol}")
            
            self.run_test(f"Get Stock Details - {test_symbol}", "GET", f"stocks/{test_symbol}", 200)
            self.run_test(f"Get Stock Analysis - {test_symbol}", "GET", f"stocks/{test_symbol}/analysis", 200)
            
            # Test LLM insight
            llm_data = {"analysis_type": "full"}
            self.run_test(f"LLM Insight - {test_symbol}", "POST", f"stocks/{test_symbol}/llm-insight", 200, data=llm_data)
        
        # Test non-existent stock
        self.run_test("Non-existent Stock", "GET", "stocks/INVALID", 404)

    def test_screener_endpoints(self):
        """Test screener functionality"""
        print("\n" + "="*50)
        print("TESTING SCREENER ENDPOINTS")
        print("="*50)
        
        # Get presets
        self.run_test("Screener Presets", "GET", "screener/presets", 200)
        
        # Test screener with filters
        screener_data = {
            "filters": [
                {"metric": "roe", "operator": "gt", "value": 10}
            ],
            "sort_by": "market_cap",
            "sort_order": "desc",
            "limit": 10
        }
        success, results = self.run_test("Run Screener", "POST", "screener", 200, data=screener_data)
        if success and results:
            print(f"   Found {results.get('count', 0)} stocks matching criteria")

    def test_watchlist_endpoints(self):
        """Test watchlist functionality"""
        print("\n" + "="*50)
        print("TESTING WATCHLIST ENDPOINTS")
        print("="*50)
        
        # Get empty watchlist
        self.run_test("Get Watchlist", "GET", "watchlist", 200)
        
        # Add to watchlist
        watchlist_item = {
            "symbol": "RELIANCE",
            "name": "Reliance Industries Limited",
            "added_date": datetime.now().isoformat()
        }
        success, _ = self.run_test("Add to Watchlist", "POST", "watchlist", 200, data=watchlist_item)
        
        if success:
            # Get watchlist again
            self.run_test("Get Watchlist After Add", "GET", "watchlist", 200)
            
            # Update watchlist item
            update_data = {"target_price": 2500, "notes": "Test note"}
            self.run_test("Update Watchlist Item", "PUT", "watchlist/RELIANCE", 200, data=update_data)
            
            # Remove from watchlist
            self.run_test("Remove from Watchlist", "DELETE", "watchlist/RELIANCE", 200)

    def test_portfolio_endpoints(self):
        """Test portfolio functionality"""
        print("\n" + "="*50)
        print("TESTING PORTFOLIO ENDPOINTS")
        print("="*50)
        
        # Get empty portfolio
        self.run_test("Get Portfolio", "GET", "portfolio", 200)
        
        # Add holding
        holding_data = {
            "symbol": "TCS",
            "name": "Tata Consultancy Services",
            "quantity": 10,
            "avg_buy_price": 3500.0,
            "buy_date": "2024-01-01"
        }
        success, _ = self.run_test("Add Portfolio Holding", "POST", "portfolio", 200, data=holding_data)
        
        if success:
            # Get portfolio after add
            self.run_test("Get Portfolio After Add", "GET", "portfolio", 200)
            
            # Update holding
            update_data = {"quantity": 15}
            self.run_test("Update Portfolio Holding", "PUT", "portfolio/TCS", 200, data=update_data)
            
            # Remove holding
            self.run_test("Remove Portfolio Holding", "DELETE", "portfolio/TCS", 200)

    def test_news_endpoints(self):
        """Test news functionality"""
        print("\n" + "="*50)
        print("TESTING NEWS ENDPOINTS")
        print("="*50)
        
        # Get news
        success, news_data = self.run_test("Get News", "GET", "news", 200, params={"limit": 5})
        if success and news_data:
            print(f"   Found {len(news_data)} news items")
        
        # Get news summary
        self.run_test("Get News Summary", "GET", "news/summary", 200)
        
        # Filter by sentiment
        self.run_test("Filter News by Sentiment", "GET", "news", 200, params={"sentiment": "POSITIVE", "limit": 3})

    def test_reports_endpoints(self):
        """Test reports functionality"""
        print("\n" + "="*50)
        print("TESTING REPORTS ENDPOINTS")
        print("="*50)
        
        # Single stock report
        report_data = {
            "report_type": "single_stock",
            "symbols": ["RELIANCE"]
        }
        self.run_test("Single Stock Report", "POST", "reports/generate", 200, data=report_data)
        
        # Comparison report
        comparison_data = {
            "report_type": "comparison",
            "symbols": ["RELIANCE", "TCS"]
        }
        self.run_test("Comparison Report", "POST", "reports/generate", 200, data=comparison_data)
        
        # Portfolio health report
        portfolio_report_data = {
            "report_type": "portfolio_health",
            "symbols": []
        }
        self.run_test("Portfolio Health Report", "POST", "reports/generate", 200, data=portfolio_report_data)

    def test_search_endpoints(self):
        """Test search functionality"""
        print("\n" + "="*50)
        print("TESTING SEARCH ENDPOINTS")
        print("="*50)
        
        # Search stocks
        success, results = self.run_test("Search Stocks", "GET", "search", 200, params={"q": "REL"})
        if success and results:
            print(f"   Found {len(results)} search results")
        
        # Get sectors
        success, sectors = self.run_test("Get Sectors", "GET", "sectors", 200)
        if success and sectors:
            print(f"   Found {len(sectors)} sectors")

    def test_scoring_engine(self):
        """Test scoring engine implementation for StockPulse"""
        print("\n" + "="*60)
        print("TESTING SCORING ENGINE - STOCKPULSE ANALYSIS PLATFORM")
        print("="*60)
        
        # Test symbols as specified in the review request
        test_symbols = ["RELIANCE", "TCS", "HDFCBANK"]
        
        for symbol in test_symbols:
            print(f"\n🔍 Testing Scoring Engine for {symbol}")
            print("-" * 40)
            
            # Get stock analysis data
            success, stock_data = self.run_test(f"Get Stock Data - {symbol}", "GET", f"stocks/{symbol}", 200)
            
            if not success or not stock_data:
                print(f"❌ Failed to get stock data for {symbol}")
                continue
                
            # Verify analysis object exists
            analysis = stock_data.get("analysis")
            if not analysis:
                print(f"❌ No analysis object found for {symbol}")
                continue
                
            print(f"✅ Analysis object found for {symbol}")
            
            # =================================================================
            # TEST 1: DEAL-BREAKERS (D1-D10)
            # =================================================================
            print(f"\n📋 Testing Deal-Breakers (D1-D10) for {symbol}")
            
            deal_breakers = analysis.get("deal_breakers", [])
            if not deal_breakers:
                print(f"❌ No deal_breakers found for {symbol}")
                continue
                
            print(f"   Found {len(deal_breakers)} deal-breakers")
            
            # Check all D1-D10 codes are present
            expected_db_codes = [f"D{i}" for i in range(1, 11)]
            found_db_codes = [db.get("code") for db in deal_breakers]
            
            missing_codes = set(expected_db_codes) - set(found_db_codes)
            if missing_codes:
                print(f"❌ Missing deal-breaker codes: {missing_codes}")
            else:
                print(f"✅ All 10 deal-breaker codes (D1-D10) present")
            
            # Verify structure of each deal-breaker
            required_db_fields = ["code", "rule", "triggered", "value", "threshold", "description", "severity"]
            db_structure_valid = True
            
            for db in deal_breakers:
                for field in required_db_fields:
                    if field not in db:
                        print(f"❌ Deal-breaker {db.get('code', 'Unknown')} missing field: {field}")
                        db_structure_valid = False
                        
                # Verify triggered is boolean
                if not isinstance(db.get("triggered"), bool):
                    print(f"❌ Deal-breaker {db.get('code')} 'triggered' field is not boolean: {type(db.get('triggered'))}")
                    db_structure_valid = False
                    
                # Verify severity is CRITICAL
                if db.get("severity") != "CRITICAL":
                    print(f"⚠️  Deal-breaker {db.get('code')} severity is not CRITICAL: {db.get('severity')}")
            
            if db_structure_valid:
                print(f"✅ Deal-breaker structure validation passed")
            
            # Count triggered deal-breakers
            triggered_dbs = [db for db in deal_breakers if db.get("triggered")]
            print(f"   Triggered deal-breakers: {len(triggered_dbs)}")
            for tdb in triggered_dbs:
                print(f"     - {tdb.get('code')}: {tdb.get('description')}")
            
            # =================================================================
            # TEST 2: RISK PENALTIES (R1-R10)
            # =================================================================
            print(f"\n⚠️  Testing Risk Penalties (R1-R10) for {symbol}")
            
            risk_penalties = analysis.get("risk_penalties", {})
            if not risk_penalties:
                print(f"❌ No risk_penalties object found for {symbol}")
                continue
                
            # Check for long_term and short_term arrays
            lt_penalties = risk_penalties.get("long_term", [])
            st_penalties = risk_penalties.get("short_term", [])
            
            print(f"   Long-term penalties: {len(lt_penalties)}")
            print(f"   Short-term penalties: {len(st_penalties)}")
            
            # Verify structure of penalties
            required_penalty_fields = ["code", "rule", "description", "value", "threshold", "penalty"]
            penalty_structure_valid = True
            
            for penalty_list, penalty_type in [(lt_penalties, "long-term"), (st_penalties, "short-term")]:
                for penalty in penalty_list:
                    for field in required_penalty_fields:
                        if field not in penalty:
                            print(f"❌ {penalty_type} penalty {penalty.get('code', 'Unknown')} missing field: {field}")
                            penalty_structure_valid = False
                            
                    # Verify penalty is negative (it's a penalty)
                    penalty_value = penalty.get("penalty", 0)
                    if penalty_value > 0:
                        print(f"⚠️  {penalty_type} penalty {penalty.get('code')} has positive value: {penalty_value}")
            
            if penalty_structure_valid:
                print(f"✅ Risk penalty structure validation passed")
            
            # Check for expected R1-R10 codes in applied penalties
            expected_r_codes = [f"R{i}" for i in range(1, 11)]
            all_penalty_codes = [p.get("code") for p in lt_penalties + st_penalties]
            found_r_codes = set(all_penalty_codes) & set(expected_r_codes)
            print(f"   Applied penalty codes: {sorted(found_r_codes)}")
            
            # =================================================================
            # TEST 3: QUALITY BOOSTERS (Q1-Q9)
            # =================================================================
            print(f"\n⭐ Testing Quality Boosters (Q1-Q9) for {symbol}")
            
            quality_boosters = analysis.get("quality_boosters", {})
            if not quality_boosters:
                print(f"❌ No quality_boosters object found for {symbol}")
                continue
                
            # Check for long_term and short_term arrays
            lt_boosters = quality_boosters.get("long_term", [])
            st_boosters = quality_boosters.get("short_term", [])
            
            print(f"   Long-term boosters: {len(lt_boosters)}")
            print(f"   Short-term boosters: {len(st_boosters)}")
            
            # Verify structure of boosters
            required_booster_fields = ["code", "rule", "description", "value", "threshold", "boost"]
            booster_structure_valid = True
            
            for booster_list, booster_type in [(lt_boosters, "long-term"), (st_boosters, "short-term")]:
                for booster in booster_list:
                    for field in required_booster_fields:
                        if field not in booster:
                            print(f"❌ {booster_type} booster {booster.get('code', 'Unknown')} missing field: {field}")
                            booster_structure_valid = False
                            
                    # Verify boost is positive (it's a boost)
                    boost_value = booster.get("boost", 0)
                    if boost_value <= 0:
                        print(f"⚠️  {booster_type} booster {booster.get('code')} has non-positive value: {boost_value}")
            
            if booster_structure_valid:
                print(f"✅ Quality booster structure validation passed")
            
            # Check for expected Q1-Q9 codes in applied boosters
            expected_q_codes = [f"Q{i}" for i in range(1, 10)]
            all_booster_codes = [b.get("code") for b in lt_boosters + st_boosters]
            found_q_codes = set(all_booster_codes) & set(expected_q_codes)
            print(f"   Applied booster codes: {sorted(found_q_codes)}")
            
            # Verify boost cap at +30
            total_lt_boost = quality_boosters.get("lt_total_boost", 0)
            total_st_boost = quality_boosters.get("st_total_boost", 0)
            
            if total_lt_boost > 30:
                print(f"⚠️  Long-term boost exceeds cap: {total_lt_boost} > 30")
            if total_st_boost > 30:
                print(f"⚠️  Short-term boost exceeds cap: {total_st_boost} > 30")
            
            # =================================================================
            # TEST 4: CONFIDENCE SCORE
            # =================================================================
            print(f"\n🎯 Testing Confidence Score for {symbol}")
            
            # Check main confidence fields
            confidence_score = analysis.get("confidence_score")
            confidence_level = analysis.get("confidence_level")
            confidence_breakdown = analysis.get("confidence_breakdown", {})
            
            confidence_valid = True
            
            # Verify confidence_score is 0-100
            if confidence_score is None:
                print(f"❌ Missing confidence_score")
                confidence_valid = False
            elif not (0 <= confidence_score <= 100):
                print(f"❌ confidence_score out of range: {confidence_score}")
                confidence_valid = False
            else:
                print(f"✅ confidence_score: {confidence_score}")
            
            # Verify confidence_level is HIGH/MEDIUM/LOW
            valid_levels = ["HIGH", "MEDIUM", "LOW"]
            if confidence_level not in valid_levels:
                print(f"❌ Invalid confidence_level: {confidence_level}")
                confidence_valid = False
            else:
                print(f"✅ confidence_level: {confidence_level}")
            
            # Verify confidence_breakdown components
            required_breakdown_fields = ["data_completeness", "data_freshness", "source_agreement", "ml_confidence"]
            for field in required_breakdown_fields:
                value = confidence_breakdown.get(field)
                if value is None:
                    print(f"❌ Missing confidence breakdown field: {field}")
                    confidence_valid = False
                elif not (0 <= value <= 100):
                    print(f"❌ confidence breakdown {field} out of range: {value}")
                    confidence_valid = False
                else:
                    print(f"✅ {field}: {value}")
            
            if confidence_valid:
                print(f"✅ Confidence score validation passed")
            
            # =================================================================
            # TEST 5: OVERALL SCORING VALIDATION
            # =================================================================
            print(f"\n📊 Testing Overall Scoring for {symbol}")
            
            # Check main scores
            long_term_score = analysis.get("long_term_score")
            short_term_score = analysis.get("short_term_score")
            verdict = analysis.get("verdict")
            
            if long_term_score is None or not (0 <= long_term_score <= 100):
                print(f"❌ Invalid long_term_score: {long_term_score}")
            else:
                print(f"✅ long_term_score: {long_term_score}")
            
            if short_term_score is None or not (0 <= short_term_score <= 100):
                print(f"❌ Invalid short_term_score: {short_term_score}")
            else:
                print(f"✅ short_term_score: {short_term_score}")
            
            valid_verdicts = ["STRONG BUY", "BUY", "HOLD", "AVOID", "STRONG AVOID"]
            if verdict not in valid_verdicts:
                print(f"❌ Invalid verdict: {verdict}")
            else:
                print(f"✅ verdict: {verdict}")
            
            # Check if deal-breaker logic is working (scores should be capped at 35 if deal-breaker triggered)
            if triggered_dbs:
                if long_term_score > 35 or short_term_score > 35:
                    print(f"⚠️  Scores not capped at 35 despite triggered deal-breakers")
                    print(f"     LT: {long_term_score}, ST: {short_term_score}")
                else:
                    print(f"✅ Scores properly capped due to deal-breakers")
            
            print(f"\n✅ Scoring engine test completed for {symbol}")
            print("-" * 40)

    def test_investment_checklists(self):
        """Test Investment Checklists implementation for medium priority items"""
        print("\n" + "="*60)
        print("TESTING INVESTMENT CHECKLISTS - MEDIUM PRIORITY")
        print("="*60)
        
        # Test symbols as specified in the review request
        test_symbols = ["TCS", "RELIANCE"]
        
        for symbol in test_symbols:
            print(f"\n🔍 Testing Investment Checklists for {symbol}")
            print("-" * 40)
            
            # Get stock data
            success, stock_data = self.run_test(f"Get Stock Data - {symbol}", "GET", f"stocks/{symbol}", 200)
            
            if not success or not stock_data:
                print(f"❌ Failed to get stock data for {symbol}")
                continue
            
            # Check for investment_checklists object in analysis
            analysis = stock_data.get("analysis", {})
            investment_checklists = analysis.get("investment_checklists")
            if not investment_checklists:
                print(f"❌ No investment_checklists object found for {symbol}")
                print(f"   Available analysis keys: {list(analysis.keys())}")
                continue
                
            print(f"✅ Investment checklists object found for {symbol}")
            
            # =================================================================
            # TEST 1: SHORT-TERM CHECKLIST (10 items ST1-ST10)
            # =================================================================
            print(f"\n📋 Testing Short-Term Checklist for {symbol}")
            
            short_term = investment_checklists.get("short_term")
            if not short_term:
                print(f"❌ No short_term checklist found for {symbol}")
                continue
            
            # Check checklist array
            st_checklist = short_term.get("checklist", [])
            if len(st_checklist) != 10:
                print(f"❌ Short-term checklist should have 10 items, found {len(st_checklist)}")
            else:
                print(f"✅ Short-term checklist has correct 10 items")
            
            # Verify ST1-ST10 IDs
            expected_st_ids = [f"ST{i}" for i in range(1, 11)]
            found_st_ids = [item.get("id") for item in st_checklist]
            missing_st_ids = set(expected_st_ids) - set(found_st_ids)
            
            if missing_st_ids:
                print(f"❌ Missing short-term checklist IDs: {missing_st_ids}")
            else:
                print(f"✅ All short-term checklist IDs (ST1-ST10) present")
            
            # Verify structure of each checklist item
            required_checklist_fields = ["id", "criterion", "passed", "value", "is_deal_breaker", "importance"]
            st_structure_valid = True
            
            for item in st_checklist:
                for field in required_checklist_fields:
                    if field not in item:
                        print(f"❌ Short-term checklist item {item.get('id', 'Unknown')} missing field: {field}")
                        st_structure_valid = False
                        
                # Verify passed is boolean
                if not isinstance(item.get("passed"), bool):
                    print(f"❌ Short-term checklist item {item.get('id')} 'passed' field is not boolean: {type(item.get('passed'))}")
                    st_structure_valid = False
                    
                # Verify is_deal_breaker is boolean
                if not isinstance(item.get("is_deal_breaker"), bool):
                    print(f"❌ Short-term checklist item {item.get('id')} 'is_deal_breaker' field is not boolean: {type(item.get('is_deal_breaker'))}")
                    st_structure_valid = False
            
            if st_structure_valid:
                print(f"✅ Short-term checklist structure validation passed")
            
            # Check summary object
            st_summary = short_term.get("summary")
            if not st_summary:
                print(f"❌ No summary object found in short-term checklist for {symbol}")
            else:
                required_summary_fields = ["total", "passed", "failed", "deal_breaker_failures", "verdict", "score"]
                summary_valid = True
                
                for field in required_summary_fields:
                    if field not in st_summary:
                        print(f"❌ Short-term summary missing field: {field}")
                        summary_valid = False
                
                # Verify verdict is PASS/FAIL/CAUTION
                verdict = st_summary.get("verdict")
                valid_verdicts = ["PASS", "FAIL", "CAUTION"]
                if verdict not in valid_verdicts:
                    print(f"❌ Invalid short-term verdict: {verdict}")
                    summary_valid = False
                
                if summary_valid:
                    print(f"✅ Short-term summary structure validation passed")
                    print(f"   Total: {st_summary.get('total')}, Passed: {st_summary.get('passed')}, Verdict: {st_summary.get('verdict')}")
            
            # =================================================================
            # TEST 2: LONG-TERM CHECKLIST (13 items LT1-LT13)
            # =================================================================
            print(f"\n📋 Testing Long-Term Checklist for {symbol}")
            
            long_term = investment_checklists.get("long_term")
            if not long_term:
                print(f"❌ No long_term checklist found for {symbol}")
                continue
            
            # Check checklist array
            lt_checklist = long_term.get("checklist", [])
            if len(lt_checklist) != 13:
                print(f"❌ Long-term checklist should have 13 items, found {len(lt_checklist)}")
            else:
                print(f"✅ Long-term checklist has correct 13 items")
            
            # Verify LT1-LT13 IDs
            expected_lt_ids = [f"LT{i}" for i in range(1, 14)]
            found_lt_ids = [item.get("id") for item in lt_checklist]
            missing_lt_ids = set(expected_lt_ids) - set(found_lt_ids)
            
            if missing_lt_ids:
                print(f"❌ Missing long-term checklist IDs: {missing_lt_ids}")
            else:
                print(f"✅ All long-term checklist IDs (LT1-LT13) present")
            
            # Verify structure of each checklist item
            lt_structure_valid = True
            
            for item in lt_checklist:
                for field in required_checklist_fields:
                    if field not in item:
                        print(f"❌ Long-term checklist item {item.get('id', 'Unknown')} missing field: {field}")
                        lt_structure_valid = False
                        
                # Verify passed is boolean
                if not isinstance(item.get("passed"), bool):
                    print(f"❌ Long-term checklist item {item.get('id')} 'passed' field is not boolean: {type(item.get('passed'))}")
                    lt_structure_valid = False
                    
                # Verify is_deal_breaker is boolean
                if not isinstance(item.get("is_deal_breaker"), bool):
                    print(f"❌ Long-term checklist item {item.get('id')} 'is_deal_breaker' field is not boolean: {type(item.get('is_deal_breaker'))}")
                    lt_structure_valid = False
            
            if lt_structure_valid:
                print(f"✅ Long-term checklist structure validation passed")
            
            # Check summary object
            lt_summary = long_term.get("summary")
            if not lt_summary:
                print(f"❌ No summary object found in long-term checklist for {symbol}")
            else:
                summary_valid = True
                
                for field in required_summary_fields:
                    if field not in lt_summary:
                        print(f"❌ Long-term summary missing field: {field}")
                        summary_valid = False
                
                # Verify verdict is PASS/FAIL/CAUTION
                verdict = lt_summary.get("verdict")
                if verdict not in valid_verdicts:
                    print(f"❌ Invalid long-term verdict: {verdict}")
                    summary_valid = False
                
                if summary_valid:
                    print(f"✅ Long-term summary structure validation passed")
                    print(f"   Total: {lt_summary.get('total')}, Passed: {lt_summary.get('passed')}, Verdict: {lt_summary.get('verdict')}")
            
            print(f"\n✅ Investment checklists test completed for {symbol}")
            print("-" * 40)

    def test_data_extraction_pipeline(self):
        """Test Data Extraction Pipeline API endpoints for medium priority items"""
        print("\n" + "="*60)
        print("TESTING DATA EXTRACTION PIPELINE API - MEDIUM PRIORITY")
        print("="*60)
        
        # =================================================================
        # TEST 1: GET /api/extraction/status
        # =================================================================
        print(f"\n🔍 Testing GET /api/extraction/status")
        print("-" * 40)
        
        success, status_data = self.run_test("Extraction Status", "GET", "extraction/status", 200)
        
        if success and status_data:
            # Verify required fields
            required_status_fields = ["pipeline_available", "available_extractors", "features"]
            status_valid = True
            
            for field in required_status_fields:
                if field not in status_data:
                    print(f"❌ Missing field in extraction status: {field}")
                    status_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check pipeline_available is boolean
            pipeline_available = status_data.get("pipeline_available")
            if not isinstance(pipeline_available, bool):
                print(f"❌ pipeline_available should be boolean, got: {type(pipeline_available)}")
                status_valid = False
            else:
                print(f"✅ pipeline_available: {pipeline_available}")
            
            # Check available_extractors is list
            available_extractors = status_data.get("available_extractors")
            if not isinstance(available_extractors, list):
                print(f"❌ available_extractors should be list, got: {type(available_extractors)}")
                status_valid = False
            else:
                print(f"✅ available_extractors: {available_extractors}")
            
            # Check features object
            features = status_data.get("features")
            if not isinstance(features, dict):
                print(f"❌ features should be dict, got: {type(features)}")
                status_valid = False
            else:
                print(f"✅ features object found")
                # Check for expected feature counts
                expected_features = {
                    "field_definitions": 160,
                    "deal_breakers": 10,
                    "risk_penalties": 10,
                    "quality_boosters": 9
                }
                
                for feature, expected_count in expected_features.items():
                    actual_count = features.get(feature)
                    if actual_count != expected_count:
                        print(f"⚠️  Feature {feature}: expected {expected_count}, got {actual_count}")
                    else:
                        print(f"✅ Feature {feature}: {actual_count}")
            
            if status_valid:
                print(f"✅ Extraction status endpoint validation passed")
        
        # =================================================================
        # TEST 2: GET /api/extraction/fields
        # =================================================================
        print(f"\n🔍 Testing GET /api/extraction/fields")
        print("-" * 40)
        
        success, fields_data = self.run_test("Extraction Fields", "GET", "extraction/fields", 200)
        
        if success and fields_data:
            # Verify required fields
            required_fields_fields = ["total_fields", "categories", "fields_by_category"]
            fields_valid = True
            
            for field in required_fields_fields:
                if field not in fields_data:
                    print(f"❌ Missing field in extraction fields: {field}")
                    fields_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check total_fields is 160
            total_fields = fields_data.get("total_fields")
            if total_fields != 160:
                print(f"❌ Expected 160 total fields, got: {total_fields}")
                fields_valid = False
            else:
                print(f"✅ Total fields: {total_fields}")
            
            # Check categories is list with 13 categories
            categories = fields_data.get("categories", [])
            if not isinstance(categories, list):
                print(f"❌ categories should be list, got: {type(categories)}")
                fields_valid = False
            elif len(categories) != 13:
                print(f"❌ Expected 13 categories, got: {len(categories)}")
                fields_valid = False
            else:
                print(f"✅ Categories count: {len(categories)}")
                print(f"   Categories: {categories}")
            
            # Check fields_by_category structure
            fields_by_category = fields_data.get("fields_by_category", {})
            if not isinstance(fields_by_category, dict):
                print(f"❌ fields_by_category should be dict, got: {type(fields_by_category)}")
                fields_valid = False
            else:
                print(f"✅ fields_by_category object found")
                
                # Verify each category has fields with proper structure
                total_field_count = 0
                for category, fields in fields_by_category.items():
                    if not isinstance(fields, list):
                        print(f"❌ Category {category} should have list of fields, got: {type(fields)}")
                        fields_valid = False
                        continue
                    
                    total_field_count += len(fields)
                    print(f"   {category}: {len(fields)} fields")
                    
                    # Check structure of first field in each category
                    if fields:
                        field = fields[0]
                        required_field_attrs = ["name", "field_id", "data_type", "unit", "priority", "update_frequency", "source", "used_for"]
                        for attr in required_field_attrs:
                            if attr not in field:
                                print(f"❌ Field in {category} missing attribute: {attr}")
                                fields_valid = False
                
                # Verify total field count matches
                if total_field_count != 160:
                    print(f"❌ Sum of fields across categories ({total_field_count}) doesn't match total_fields (160)")
                    fields_valid = False
                else:
                    print(f"✅ Field count verification passed: {total_field_count}")
            
            if fields_valid:
                print(f"✅ Extraction fields endpoint validation passed")
        
        print(f"\n✅ Data extraction pipeline API test completed")
        print("-" * 40)

    def test_brain_phase3_2_sentiment_endpoints(self):
        """Test Brain Phase 3.2 FinBERT Sentiment Pipeline endpoints as specified in review request"""
        print("\n" + "="*60)
        print("TESTING BRAIN PHASE 3.2 - FINBERT SENTIMENT PIPELINE")
        print("="*60)
        
        # =================================================================
        # TEST 1: Phase 3.2 Summary - GET /api/brain/phase3_2/summary
        # =================================================================
        print(f"\n📋 Testing Phase 3.2 Summary - GET /api/brain/phase3_2/summary")
        print("-" * 50)
        
        success, summary_result = self.run_test("Phase 3.2 Summary", "GET", "brain/phase3_2/summary", 200)
        
        if success and summary_result:
            print(f"✅ Phase 3.2 summary endpoint successful")
            
            # Verify summary structure
            required_summary_fields = ["phase", "status", "components", "ensemble_weights", "nlp_pipeline"]
            summary_valid = True
            
            for field in required_summary_fields:
                if field not in summary_result:
                    print(f"❌ Missing field in summary: {field}")
                    summary_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check components - should have all 7 components
            components = summary_result.get("components", {})
            expected_components = ["finbert_analyzer", "vader_analyzer", "llm_sentiment", "news_scraper", "social_scraper", "entity_extractor", "earnings_analyzer"]
            
            for component in expected_components:
                if component in components:
                    print(f"✅ Component found: {component}")
                else:
                    print(f"❌ Missing component: {component}")
                    summary_valid = False
            
            # Check ensemble weights
            ensemble_weights = summary_result.get("ensemble_weights", {})
            expected_weights = {"finbert": 0.50, "vader": 0.20, "llm": 0.30}
            
            for model, expected_weight in expected_weights.items():
                actual_weight = ensemble_weights.get(model)
                if actual_weight == expected_weight:
                    print(f"✅ Ensemble weight correct: {model} = {actual_weight}")
                else:
                    print(f"❌ Ensemble weight incorrect: {model} expected {expected_weight}, got {actual_weight}")
                    summary_valid = False
            
            # Check nlp_pipeline has 7 steps
            nlp_pipeline = summary_result.get("nlp_pipeline", {})
            if isinstance(nlp_pipeline, dict):
                steps = nlp_pipeline.get("steps", [])
                if len(steps) == 7:
                    print(f"✅ NLP pipeline has correct 7 steps")
                else:
                    print(f"❌ NLP pipeline should have 7 steps, got {len(steps)}")
                    summary_valid = False
            elif isinstance(nlp_pipeline, list):
                if len(nlp_pipeline) == 7:
                    print(f"✅ NLP pipeline has correct 7 steps")
                else:
                    print(f"❌ NLP pipeline should have 7 steps, got {len(nlp_pipeline)}")
                    summary_valid = False
            else:
                print(f"❌ NLP pipeline should be dict or list, got {type(nlp_pipeline)}")
                summary_valid = False
            
            if summary_valid:
                print(f"✅ Phase 3.2 summary validation passed")
        
        # =================================================================
        # TEST 2: Sentiment Pipeline Status - GET /api/brain/sentiment/pipeline/status
        # =================================================================
        print(f"\n🔍 Testing Sentiment Pipeline Status - GET /api/brain/sentiment/pipeline/status")
        print("-" * 50)
        
        success, status_result = self.run_test("Sentiment Pipeline Status", "GET", "brain/sentiment/pipeline/status", 200)
        
        if success and status_result:
            print(f"✅ Sentiment pipeline status endpoint successful")
            
            # Check if components are nested under "components" key
            components = status_result.get("components", status_result)
            
            # Verify status structure
            required_status_fields = ["aggregator", "news_scraper", "social_scraper", "earnings_analyzer", "llm_service"]
            status_valid = True
            
            for field in required_status_fields:
                if field not in components:
                    print(f"❌ Missing component in status: {field}")
                    status_valid = False
                else:
                    print(f"✅ Found component: {field}")
            
            # Check llm_service details
            llm_service = components.get("llm_service", {})
            if llm_service:
                provider = llm_service.get("provider")
                api_key_configured = llm_service.get("api_key_configured")
                
                if provider == "google_gemini":
                    print(f"✅ LLM provider correct: {provider}")
                else:
                    print(f"❌ LLM provider incorrect: expected google_gemini, got {provider}")
                    status_valid = False
                
                if api_key_configured is True:
                    print(f"✅ API key configured: {api_key_configured}")
                else:
                    print(f"❌ API key not configured: {api_key_configured}")
                    status_valid = False
            
            if status_valid:
                print(f"✅ Sentiment pipeline status validation passed")
        
        # =================================================================
        # TEST 3: Symbol Sentiment Analysis - GET /api/brain/sentiment/RELIANCE
        # =================================================================
        print(f"\n📈 Testing Symbol Sentiment Analysis - GET /api/brain/sentiment/RELIANCE")
        print("-" * 50)
        
        success, sentiment_result = self.run_test("Symbol Sentiment - RELIANCE", "GET", "brain/sentiment/RELIANCE", 200)
        
        if success and sentiment_result:
            print(f"✅ Symbol sentiment analysis successful for RELIANCE")
            
            # Verify sentiment result structure
            required_sentiment_fields = ["sentiment_score", "label", "positive_prob", "negative_prob", "neutral_prob", "article_count", "source_breakdown", "latest_headlines", "computed_at"]
            sentiment_valid = True
            
            for field in required_sentiment_fields:
                if field not in sentiment_result:
                    print(f"❌ Missing field in sentiment result: {field}")
                    sentiment_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check sentiment_score is between -1 and 1
            sentiment_score = sentiment_result.get("sentiment_score")
            if sentiment_score is not None and -1 <= sentiment_score <= 1:
                print(f"✅ Valid sentiment score: {sentiment_score}")
            else:
                print(f"❌ Invalid sentiment score: {sentiment_score}")
                sentiment_valid = False
            
            # Check label is valid
            label = sentiment_result.get("label")
            valid_labels = ["positive", "negative", "neutral"]
            if label in valid_labels:
                print(f"✅ Valid sentiment label: {label}")
            else:
                print(f"❌ Invalid sentiment label: {label}")
                sentiment_valid = False
            
            # Check probabilities sum to ~1
            pos_prob = sentiment_result.get("positive_prob", 0)
            neg_prob = sentiment_result.get("negative_prob", 0)
            neu_prob = sentiment_result.get("neutral_prob", 0)
            prob_sum = pos_prob + neg_prob + neu_prob
            
            if 0.95 <= prob_sum <= 1.05:  # Allow small floating point errors
                print(f"✅ Valid probability distribution: {prob_sum:.3f}")
            else:
                print(f"❌ Invalid probability distribution sum: {prob_sum}")
                sentiment_valid = False
            
            if sentiment_valid:
                print(f"✅ Symbol sentiment analysis validation passed")
        
        # =================================================================
        # TEST 4: Market Overview Sentiment - GET /api/brain/sentiment/market/overview
        # =================================================================
        print(f"\n🌍 Testing Market Overview Sentiment - GET /api/brain/sentiment/market/overview")
        print("-" * 50)
        
        success, market_result = self.run_test("Market Overview Sentiment", "GET", "brain/sentiment/market/overview", 200)
        
        if success and market_result:
            print(f"✅ Market overview sentiment successful")
            
            # Should have similar structure to symbol sentiment but for "MARKET"
            market_valid = True
            
            for field in required_sentiment_fields:
                if field not in market_result:
                    print(f"❌ Missing field in market sentiment: {field}")
                    market_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            if market_valid:
                print(f"✅ Market overview sentiment validation passed")
        
        # =================================================================
        # TEST 5: Social Media Feed - GET /api/brain/sentiment/social/feed
        # =================================================================
        print(f"\n📱 Testing Social Media Feed - GET /api/brain/sentiment/social/feed")
        print("-" * 50)
        
        success, social_result = self.run_test("Social Media Feed", "GET", "brain/sentiment/social/feed", 200)
        
        if success and social_result:
            print(f"✅ Social media feed successful")
            
            # Verify social feed structure
            required_social_fields = ["post_count", "sentiment_score", "label"]
            social_valid = True
            
            for field in required_social_fields:
                if field not in social_result:
                    print(f"❌ Missing field in social feed: {field}")
                    social_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check for optional top_posts array
            if "top_posts" in social_result:
                top_posts = social_result["top_posts"]
                if isinstance(top_posts, list):
                    print(f"✅ Top posts array found with {len(top_posts)} posts")
                else:
                    print(f"❌ Top posts should be array, got {type(top_posts)}")
                    social_valid = False
            
            if social_valid:
                print(f"✅ Social media feed validation passed")
        
        # =================================================================
        # TEST 6: Social Media Symbol Filter - GET /api/brain/sentiment/social/RELIANCE
        # =================================================================
        print(f"\n📱 Testing Social Media Symbol Filter - GET /api/brain/sentiment/social/RELIANCE")
        print("-" * 50)
        
        success, social_symbol_result = self.run_test("Social Media Symbol - RELIANCE", "GET", "brain/sentiment/social/RELIANCE", 200)
        
        if success and social_symbol_result:
            print(f"✅ Social media symbol filter successful for RELIANCE")
            
            # Should have similar structure to general social feed
            social_symbol_valid = True
            
            for field in required_social_fields:
                if field not in social_symbol_result:
                    print(f"❌ Missing field in social symbol result: {field}")
                    social_symbol_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            if social_symbol_valid:
                print(f"✅ Social media symbol filter validation passed")
        
        # =================================================================
        # TEST 7: Earnings Call Analysis - POST /api/brain/sentiment/earnings-call
        # =================================================================
        print(f"\n💼 Testing Earnings Call Analysis - POST /api/brain/sentiment/earnings-call")
        print("-" * 50)
        
        earnings_data = {
            "symbol": "RELIANCE",
            "transcript": "Good evening, ladies and gentlemen. Welcome to Reliance Industries Q1 FY26 earnings conference call. We are pleased to report strong quarterly performance. Revenue grew by 15% year-over-year driven by robust demand across our retail and digital segments. EBITDA margin expanded by 200 basis points to 32%. Our Jio platform now serves over 480 million subscribers. The petrochemicals segment saw improvement despite global headwinds. Management expects continued growth momentum in the coming quarters with capex plans of Rs 75,000 crores. Question and Answer Session: Analyst from Morgan Stanley: Can you provide guidance on margin sustainability given rising crude prices? Management: We remain confident in our margin trajectory. The downstream integration provides natural hedging. Analyst from Goldman Sachs: What is the outlook for new energy business? Management: Our new energy investments are on track. We expect the green hydrogen facility to be operational by FY27.",
            "quarter": "Q1FY26"
        }
        
        success, earnings_result = self.run_test("Earnings Call Analysis", "POST", "brain/sentiment/earnings-call", 200, data=earnings_data)
        
        if success and earnings_result:
            print(f"✅ Earnings call analysis successful")
            
            # Verify earnings result structure
            required_earnings_fields = ["management_sentiment", "qa_sentiment", "tone_divergence", "overall_sentiment", "guidance_direction", "key_positives", "key_negatives", "forward_looking_statements"]
            earnings_valid = True
            
            for field in required_earnings_fields:
                if field not in earnings_result:
                    print(f"❌ Missing field in earnings result: {field}")
                    earnings_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check sentiment scores are valid
            mgmt_sentiment = earnings_result.get("management_sentiment")
            qa_sentiment = earnings_result.get("qa_sentiment")
            overall_sentiment = earnings_result.get("overall_sentiment")
            
            for sentiment_name, sentiment_value in [("management", mgmt_sentiment), ("qa", qa_sentiment), ("overall", overall_sentiment)]:
                if sentiment_value is not None and -1 <= sentiment_value <= 1:
                    print(f"✅ Valid {sentiment_name} sentiment: {sentiment_value}")
                else:
                    print(f"❌ Invalid {sentiment_name} sentiment: {sentiment_value}")
                    earnings_valid = False
            
            # Check guidance_direction is valid
            guidance = earnings_result.get("guidance_direction")
            valid_guidance = ["positive", "negative", "neutral", "mixed", "maintained", "raised", "lowered"]
            if guidance in valid_guidance:
                print(f"✅ Valid guidance direction: {guidance}")
            else:
                print(f"❌ Invalid guidance direction: {guidance}")
                earnings_valid = False
            
            if earnings_valid:
                print(f"✅ Earnings call analysis validation passed")
        
        # =================================================================
        # TEST 8: Batch Sentiment Analysis - POST /api/brain/sentiment/batch
        # =================================================================
        print(f"\n📊 Testing Batch Sentiment Analysis - POST /api/brain/sentiment/batch")
        print("-" * 50)
        
        batch_data = {
            "symbols": ["RELIANCE", "TCS", "INFY"]
        }
        
        success, batch_result = self.run_test("Batch Sentiment Analysis", "POST", "brain/sentiment/batch", 200, data=batch_data)
        
        if success and batch_result:
            print(f"✅ Batch sentiment analysis successful")
            
            # Verify batch result structure
            required_batch_fields = ["symbols_processed", "results"]
            batch_valid = True
            
            for field in required_batch_fields:
                if field not in batch_result:
                    print(f"❌ Missing field in batch result: {field}")
                    batch_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check symbols_processed count
            symbols_processed = batch_result.get("symbols_processed")
            if symbols_processed == 3:
                print(f"✅ Correct symbols processed count: {symbols_processed}")
            else:
                print(f"❌ Incorrect symbols processed count: expected 3, got {symbols_processed}")
                batch_valid = False
            
            # Check results dict
            results = batch_result.get("results", {})
            if isinstance(results, dict):
                print(f"✅ Results dict found with {len(results)} entries")
                
                # Check each symbol has sentiment data
                for symbol in ["RELIANCE", "TCS", "INFY"]:
                    if symbol in results:
                        symbol_result = results[symbol]
                        if "sentiment_score" in symbol_result and "label" in symbol_result:
                            print(f"✅ Valid sentiment data for {symbol}")
                        else:
                            print(f"❌ Invalid sentiment data for {symbol}")
                            batch_valid = False
                    else:
                        print(f"❌ Missing results for symbol: {symbol}")
                        batch_valid = False
            else:
                print(f"❌ Results should be dict, got {type(results)}")
                batch_valid = False
            
            if batch_valid:
                print(f"✅ Batch sentiment analysis validation passed")
        
        print(f"\n✅ Brain Phase 3.2 FinBERT Sentiment Pipeline testing completed")
        print("="*60)

    def test_brain_phase2_endpoints(self):
        """Test Brain Phase 2 API endpoints as specified in review request"""
        print("\n" + "="*60)
        print("TESTING BRAIN PHASE 2 - AI/ML MODELS & SIGNAL GENERATION")
        print("="*60)
        
        # Test symbols with seeded data
        test_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
        
        # =================================================================
        # TEST 1: Model Training (HIGH PRIORITY)
        # =================================================================
        print(f"\n🧠 Testing Model Training - POST /api/brain/models/train")
        print("-" * 50)
        
        # Test model training for RELIANCE
        train_data = {"symbol": "RELIANCE", "horizon": 5}
        success, train_result = self.run_test("Model Training - RELIANCE", "POST", "brain/models/train", 200, data=train_data)
        
        if success and train_result:
            print(f"✅ Model training successful for RELIANCE")
            
            # Verify training result structure
            required_train_fields = ["symbol", "samples", "features", "results"]
            train_valid = True
            
            for field in required_train_fields:
                if field not in train_result:
                    print(f"❌ Missing field in training result: {field}")
                    train_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check results contains expected models
            results = train_result.get("results", {})
            expected_models = ["xgboost", "lightgbm", "garch"]
            
            for model in expected_models:
                if model in results:
                    model_result = results[model]
                    status = model_result.get("status", "unknown")
                    model_name = model_result.get("model_name", "unknown")
                    print(f"✅ Model trained: {model} ({model_name}) - Status: {status}")
                    
                    # Check for accuracy metrics if completed
                    if status == "completed" and "metrics" in model_result:
                        metrics = model_result["metrics"]
                        if "accuracy" in metrics:
                            print(f"   Accuracy: {metrics['accuracy']}")
                        else:
                            print(f"   Metrics: {list(metrics.keys())}")
                    elif status == "failed":
                        error = model_result.get("metrics", {}).get("error", "Unknown error")
                        print(f"   Error: {error}")
                else:
                    print(f"⚠️  Expected model not found: {model}")
            
            if train_valid:
                print(f"✅ Model training result validation passed")
        
        # =================================================================
        # TEST 2: Model Status (HIGH PRIORITY)
        # =================================================================
        print(f"\n📊 Testing Model Status - GET /api/brain/models/status")
        print("-" * 50)
        
        success, status_result = self.run_test("Model Status", "GET", "brain/models/status", 200)
        
        if success and status_result:
            print(f"✅ Model status endpoint successful")
            
            # Verify status result structure
            required_status_fields = ["status", "loaded_models", "stats"]
            status_valid = True
            
            for field in required_status_fields:
                if field not in status_result:
                    print(f"❌ Missing field in status result: {field}")
                    status_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check loaded_models includes expected models
            loaded_models = status_result.get("loaded_models", [])
            expected_loaded = ["xgboost_direction", "lightgbm_direction"]
            
            for model in expected_loaded:
                if model in loaded_models:
                    print(f"✅ Loaded model found: {model}")
                else:
                    print(f"⚠️  Expected loaded model not found: {model}")
            
            if status_valid:
                print(f"✅ Model status validation passed")
        
        # =================================================================
        # TEST 3: Signal Generation (HIGH PRIORITY)
        # =================================================================
        print(f"\n🎯 Testing Signal Generation - POST /api/brain/signals/generate")
        print("-" * 50)
        
        # Test signal generation for RELIANCE
        signal_data = {"symbol": "RELIANCE", "current_price": 2800}
        success, signal_result = self.run_test("Signal Generation - RELIANCE", "POST", "brain/signals/generate", 200, data=signal_data)
        
        if success and signal_result:
            print(f"✅ Signal generation successful for RELIANCE")
            
            # Verify signal result structure
            required_signal_fields = ["symbol", "direction", "confidence", "entry_price", "target_price", "stop_loss", "contributing_factors"]
            signal_valid = True
            
            for field in required_signal_fields:
                if field not in signal_result:
                    print(f"❌ Missing field in signal result: {field}")
                    signal_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check direction is valid
            direction = signal_result.get("direction")
            valid_directions = ["BUY", "SELL", "HOLD"]
            if direction not in valid_directions:
                print(f"❌ Invalid direction: {direction}")
                signal_valid = False
            else:
                print(f"✅ Valid direction: {direction}")
            
            # Check confidence is 0-100
            confidence = signal_result.get("confidence")
            if confidence is None or not (0 <= confidence <= 100):
                print(f"❌ Invalid confidence: {confidence}")
                signal_valid = False
            else:
                print(f"✅ Valid confidence: {confidence}")
            
            # Check price fields are numeric
            price_fields = ["entry_price", "target_price", "stop_loss"]
            for field in price_fields:
                value = signal_result.get(field)
                if not isinstance(value, (int, float)) or value <= 0:
                    print(f"❌ Invalid {field}: {value}")
                    signal_valid = False
                else:
                    print(f"✅ Valid {field}: {value}")
            
            if signal_valid:
                print(f"✅ Signal generation validation passed")
        
        # =================================================================
        # TEST 4: Active Signals (HIGH PRIORITY)
        # =================================================================
        print(f"\n📈 Testing Active Signals - GET /api/brain/signals/active")
        print("-" * 50)
        
        success, active_result = self.run_test("Active Signals", "GET", "brain/signals/active", 200)
        
        if success and active_result:
            print(f"✅ Active signals endpoint successful")
            
            # Verify active signals structure
            required_active_fields = ["count", "signals"]
            active_valid = True
            
            for field in required_active_fields:
                if field not in active_result:
                    print(f"❌ Missing field in active signals: {field}")
                    active_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check count is numeric
            count = active_result.get("count")
            if not isinstance(count, int) or count < 0:
                print(f"❌ Invalid count: {count}")
                active_valid = False
            else:
                print(f"✅ Valid count: {count}")
            
            # Check signals structure
            signals = active_result.get("signals", {})
            if not isinstance(signals, dict):
                print(f"❌ Signals should be dict, got: {type(signals)}")
                active_valid = False
            else:
                print(f"✅ Signals object valid with {len(signals)} active signals")
            
            if active_valid:
                print(f"✅ Active signals validation passed")
        
        # =================================================================
        # TEST 5: Backtesting (HIGH PRIORITY)
        # =================================================================
        print(f"\n📊 Testing Backtesting - POST /api/brain/backtest/run")
        print("-" * 50)
        
        # Test backtesting for RELIANCE
        backtest_data = {"symbol": "RELIANCE", "horizon": 5}
        success, backtest_result = self.run_test("Backtesting - RELIANCE", "POST", "brain/backtest/run", 200, data=backtest_data)
        
        if success and backtest_result:
            print(f"✅ Backtesting successful for RELIANCE")
            
            # Verify backtest result structure
            required_backtest_fields = ["symbol", "metrics", "trades", "total_trades"]
            backtest_valid = True
            
            for field in required_backtest_fields:
                if field not in backtest_result:
                    print(f"❌ Missing field in backtest result: {field}")
                    backtest_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check metrics contains expected fields
            metrics = backtest_result.get("metrics", {})
            expected_metrics = ["sharpe_ratio", "sortino_ratio", "max_drawdown_pct", "win_rate_pct", "profit_factor"]
            
            for metric in expected_metrics:
                if metric in metrics:
                    print(f"✅ Metric found: {metric} = {metrics[metric]}")
                else:
                    print(f"❌ Missing metric: {metric}")
                    backtest_valid = False
            
            # Check trades is list
            trades = backtest_result.get("trades", [])
            if not isinstance(trades, list):
                print(f"❌ Trades should be list, got: {type(trades)}")
                backtest_valid = False
            else:
                print(f"✅ Trades list with {len(trades)} trades")
            
            # Check total_trades matches trades length
            total_trades = backtest_result.get("total_trades", 0)
            if total_trades != len(trades):
                print(f"⚠️  Total trades ({total_trades}) doesn't match trades list length ({len(trades)})")
            else:
                print(f"✅ Total trades count verified: {total_trades}")
            
            if backtest_valid:
                print(f"✅ Backtesting validation passed")
        
        # =================================================================
        # TEST 6: Phase 2 Summary
        # =================================================================
        print(f"\n📋 Testing Phase 2 Summary - GET /api/brain/phase2/summary")
        print("-" * 50)
        
        success, summary_result = self.run_test("Phase 2 Summary", "GET", "brain/phase2/summary", 200)
        
        if success and summary_result:
            print(f"✅ Phase 2 summary endpoint successful")
            
            # Verify summary structure
            required_summary_fields = ["phase", "status", "components"]
            summary_valid = True
            
            for field in required_summary_fields:
                if field not in summary_result:
                    print(f"❌ Missing field in summary: {field}")
                    summary_valid = False
                else:
                    print(f"✅ Found field: {field}")
            
            # Check components
            components = summary_result.get("components", {})
            expected_components = ["model_manager", "signal_pipeline", "backtest_engine"]
            
            for component in expected_components:
                if component in components:
                    print(f"✅ Component found: {component}")
                else:
                    print(f"❌ Missing component: {component}")
                    summary_valid = False
            
            if summary_valid:
                print(f"✅ Phase 2 summary validation passed")
        
        # =================================================================
        # TEST 7: Health Check (verify Phase 2 added)
        # =================================================================
        print(f"\n🏥 Testing Health Check - GET /api/brain/health")
        print("-" * 50)
        
        success, health_result = self.run_test("Brain Health Check", "GET", "brain/health", 200)
        
        if success and health_result:
            print(f"✅ Brain health check successful")
            
            # Check for Phase 2 subsystems
            subsystems = health_result.get("subsystems", {})
            phase2_subsystems = ["model_manager", "signal_pipeline", "backtest_engine"]
            
            for subsystem in phase2_subsystems:
                if subsystem in subsystems:
                    status = subsystems[subsystem].get("status", "unknown")
                    print(f"✅ Phase 2 subsystem found: {subsystem} ({status})")
                else:
                    print(f"⚠️  Phase 2 subsystem not found in health check: {subsystem}")
        
        print(f"\n✅ Brain Phase 2 testing completed")
        print("="*60)

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 Starting Stock Analysis Platform API Tests")
        print(f"Base URL: {self.base_url}")
        
        try:
            # Test basic health endpoints first
            self.test_health_endpoints()
            
            # Test Brain Phase 3.2 FinBERT Sentiment Pipeline endpoints (HIGH PRIORITY)
            self.test_brain_phase3_2_sentiment_endpoints()
            
        except KeyboardInterrupt:
            print("\n⚠️  Tests interrupted by user")
        except Exception as e:
            print(f"\n💥 Unexpected error: {str(e)}")
        
        # Print final results
        self.print_results()
        
        return 0 if self.tests_passed == self.tests_run else 1

    def print_results(self):
        """Print test results summary"""
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        print(f"📊 Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {len(self.failed_tests)}")
        print(f"📈 Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"   {i}. {test.get('test', 'Unknown')}")
                if 'error' in test:
                    print(f"      Error: {test['error']}")
                else:
                    print(f"      Expected: {test.get('expected')}, Got: {test.get('actual')}")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS:")
            for i, test in enumerate(self.passed_tests, 1):
                print(f"   {i}. {test}")

def main():
    tester = StockAnalysisPlatformTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())