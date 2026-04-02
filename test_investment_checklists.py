#!/usr/bin/env python3

import requests
import json

def test_investment_checklists():
    """Test investment checklists specifically"""
    base_url = "https://multiagent-trader-ai.preview.emergentagent.com"
    
    test_symbols = ["TCS", "RELIANCE"]
    
    for symbol in test_symbols:
        print(f"\n🔍 Testing Investment Checklists for {symbol}")
        print("-" * 50)
        
        try:
            response = requests.get(f"{base_url}/api/stocks/{symbol}", timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Failed to get data for {symbol}: {response.status_code}")
                continue
                
            data = response.json()
            
            # Check for investment_checklists in analysis
            analysis = data.get("analysis", {})
            investment_checklists = analysis.get("investment_checklists")
            if not investment_checklists:
                print(f"❌ No investment_checklists found for {symbol}")
                print(f"   Available analysis keys: {list(analysis.keys())}")
                continue
                
            print(f"✅ Investment checklists found for {symbol}")
            
            # Test short-term checklist
            short_term = investment_checklists.get("short_term", {})
            st_checklist = short_term.get("checklist", [])
            st_summary = short_term.get("summary", {})
            
            print(f"\n📋 Short-Term Checklist:")
            print(f"   Items: {len(st_checklist)}")
            print(f"   Expected: 10 items (ST1-ST10)")
            
            if len(st_checklist) == 10:
                print(f"   ✅ Correct number of items")
            else:
                print(f"   ❌ Wrong number of items")
            
            # Check IDs
            st_ids = [item.get("id") for item in st_checklist]
            expected_st_ids = [f"ST{i}" for i in range(1, 11)]
            missing_st = set(expected_st_ids) - set(st_ids)
            
            if not missing_st:
                print(f"   ✅ All ST1-ST10 IDs present")
            else:
                print(f"   ❌ Missing IDs: {missing_st}")
            
            # Check summary
            if st_summary:
                print(f"   Summary - Total: {st_summary.get('total')}, Passed: {st_summary.get('passed')}, Verdict: {st_summary.get('verdict')}")
            
            # Test long-term checklist
            long_term = investment_checklists.get("long_term", {})
            lt_checklist = long_term.get("checklist", [])
            lt_summary = long_term.get("summary", {})
            
            print(f"\n📋 Long-Term Checklist:")
            print(f"   Items: {len(lt_checklist)}")
            print(f"   Expected: 13 items (LT1-LT13)")
            
            if len(lt_checklist) == 13:
                print(f"   ✅ Correct number of items")
            else:
                print(f"   ❌ Wrong number of items")
            
            # Check IDs
            lt_ids = [item.get("id") for item in lt_checklist]
            expected_lt_ids = [f"LT{i}" for i in range(1, 14)]
            missing_lt = set(expected_lt_ids) - set(lt_ids)
            
            if not missing_lt:
                print(f"   ✅ All LT1-LT13 IDs present")
            else:
                print(f"   ❌ Missing IDs: {missing_lt}")
            
            # Check summary
            if lt_summary:
                print(f"   Summary - Total: {lt_summary.get('total')}, Passed: {lt_summary.get('passed')}, Verdict: {lt_summary.get('verdict')}")
            
            # Check structure of first item in each checklist
            if st_checklist:
                item = st_checklist[0]
                required_fields = ["id", "criterion", "passed", "value", "is_deal_breaker", "importance"]
                missing_fields = [f for f in required_fields if f not in item]
                if not missing_fields:
                    print(f"   ✅ Short-term item structure correct")
                else:
                    print(f"   ❌ Short-term missing fields: {missing_fields}")
            
            if lt_checklist:
                item = lt_checklist[0]
                required_fields = ["id", "criterion", "passed", "value", "is_deal_breaker", "importance"]
                missing_fields = [f for f in required_fields if f not in item]
                if not missing_fields:
                    print(f"   ✅ Long-term item structure correct")
                else:
                    print(f"   ❌ Long-term missing fields: {missing_fields}")
            
            print(f"\n✅ Investment checklists test completed for {symbol}")
            
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")

if __name__ == "__main__":
    test_investment_checklists()