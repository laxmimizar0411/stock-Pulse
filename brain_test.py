#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime
from typing import Dict, List, Any

class BrainPhase1Tester:
    def __init__(self, base_url="https://e9f186b4-9ef4-468e-8a06-45ab03aad004.preview.emergentagent.com"):
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

    def test_brain_health(self):
        """Test Brain Health endpoints (HIGH PRIORITY)"""
        print("\n" + "="*60)
        print("TESTING BRAIN HEALTH - HIGH PRIORITY")
        print("="*60)
        
        # Test GET /api/brain/health
        success, health_data = self.run_test("Brain Health Check", "GET", "brain/health", 200)
        
        if success and health_data:
            print(f"\n📊 Analyzing Brain Health Response...")
            
            # Verify main brain status
            brain_started = health_data.get("started")
            brain_status = health_data.get("status")
            
            print(f"   Brain started: {brain_started}")
            print(f"   Brain status: {brain_status}")
            
            # Verify subsystems
            subsystems = health_data.get("subsystems", {})
            expected_subsystems = ["kafka", "feature_pipeline", "feature_store", "batch_scheduler", "storage", "data_quality"]
            health_valid = True
            
            if not isinstance(subsystems, dict):
                print(f"❌ Subsystems should be a dict, got: {type(subsystems)}")
                health_valid = False
            else:
                for subsystem in expected_subsystems:
                    if subsystem not in subsystems:
                        print(f"❌ Missing subsystem: {subsystem}")
                        health_valid = False
                    else:
                        subsystem_data = subsystems[subsystem]
                        status = subsystem_data.get("status")
                        
                        print(f"   {subsystem}:")
                        print(f"     - status: {status}")
                        
                        # Verify status is "healthy" or "degraded"
                        if status not in ["healthy", "degraded"]:
                            print(f"❌ {subsystem} status should be 'healthy' or 'degraded', got: {status}")
                            health_valid = False
                        
                        # Show additional info if available
                        if "mode" in subsystem_data:
                            print(f"     - mode: {subsystem_data['mode']}")
                        if "running" in subsystem_data:
                            print(f"     - running: {subsystem_data['running']}")
            
            # Verify brain started is boolean
            if not isinstance(brain_started, bool):
                print(f"❌ Brain 'started' should be boolean, got: {type(brain_started)}")
                health_valid = False
            
            # Verify brain status is "healthy" or "degraded"
            if brain_status not in ["healthy", "degraded"]:
                print(f"❌ Brain status should be 'healthy' or 'degraded', got: {brain_status}")
                health_valid = False
            
            if health_valid:
                print(f"✅ Brain health check validation passed")
            else:
                print(f"❌ Brain health check validation failed")
        
        # Test GET /api/brain/config
        success, config_data = self.run_test("Brain Config Summary", "GET", "brain/config", 200)
        if success and config_data:
            print(f"✅ Brain config endpoint working")

    def test_feature_pipeline(self):
        """Test Feature Pipeline endpoints (HIGH PRIORITY)"""
        print("\n" + "="*60)
        print("TESTING FEATURE PIPELINE - HIGH PRIORITY")
        print("="*60)
        
        # Test GET /api/brain/features/status
        success, status_data = self.run_test("Feature Pipeline Status", "GET", "brain/features/status", 200)
        
        if success and status_data:
            print(f"\n📊 Analyzing Feature Pipeline Status...")
            
            # Verify required fields
            required_fields = ["status", "registered_features", "categories"]
            status_valid = True
            
            for field in required_fields:
                if field not in status_data:
                    print(f"❌ Missing field: {field}")
                    status_valid = False
                else:
                    value = status_data[field]
                    print(f"   {field}: {value}")
            
            # Verify status is "ready"
            if status_data.get("status") != "ready":
                print(f"❌ Expected status 'ready', got: {status_data.get('status')}")
                status_valid = False
            
            # Verify registered_features is 72
            registered_features = status_data.get("registered_features")
            if registered_features != 72:
                print(f"❌ Expected 72 registered features, got: {registered_features}")
                status_valid = False
            
            # Verify categories is a list
            categories = status_data.get("categories")
            if not isinstance(categories, list):
                print(f"❌ Categories should be a list, got: {type(categories)}")
                status_valid = False
            else:
                print(f"   Categories: {categories}")
            
            if status_valid:
                print(f"✅ Feature pipeline status validation passed")
        
        # Test GET /api/brain/features/RELIANCE?compute=true
        print(f"\n🔍 Testing Feature Computation for RELIANCE...")
        success, features_data = self.run_test("Compute Features - RELIANCE", "GET", "brain/features/RELIANCE", 200, params={"compute": "true"})
        
        if success and features_data:
            print(f"✅ Feature computation successful for RELIANCE")
            
            # Verify response structure
            required_fields = ["symbol", "features", "feature_count", "source"]
            for field in required_fields:
                if field not in features_data:
                    print(f"❌ Missing field in features response: {field}")
                else:
                    value = features_data[field]
                    if field == "features":
                        print(f"   {field}: {type(value)} with {len(value) if isinstance(value, dict) else 'N/A'} items")
                    else:
                        print(f"   {field}: {value}")
            
            # Note about YFinance limitations
            feature_count = features_data.get("feature_count", 0)
            if feature_count < 72:
                print(f"⚠️  Note: Only {feature_count} features computed (YFinance may be limited in this environment)")
        
        # Test POST /api/brain/features/compute
        print(f"\n🔍 Testing POST Feature Computation for TCS...")
        compute_data = {"symbol": "TCS"}
        success, compute_response = self.run_test("POST Compute Features - TCS", "POST", "brain/features/compute", 200, data=compute_data)
        
        if success and compute_response:
            print(f"✅ POST feature computation successful for TCS")
            
            # Verify response structure
            required_fields = ["success", "symbol", "feature_count", "features"]
            for field in required_fields:
                if field not in compute_response:
                    print(f"❌ Missing field in POST compute response: {field}")
                else:
                    value = compute_response[field]
                    if field == "features":
                        print(f"   {field}: {type(value)} with {len(value) if isinstance(value, dict) else 'N/A'} items")
                    else:
                        print(f"   {field}: {value}")

    def test_batch_scheduler(self):
        """Test Batch Scheduler endpoints (HIGH PRIORITY)"""
        print("\n" + "="*60)
        print("TESTING BATCH SCHEDULER - HIGH PRIORITY")
        print("="*60)
        
        # Test GET /api/brain/batch/status
        success, status_data = self.run_test("Batch Scheduler Status", "GET", "brain/batch/status", 200)
        
        if success and status_data:
            print(f"\n📊 Analyzing Batch Scheduler Status...")
            
            # Check for DAGs
            dags = status_data.get("dags", {})
            if not isinstance(dags, dict):
                print(f"❌ DAGs should be a dict, got: {type(dags)}")
            else:
                print(f"   Found {len(dags)} DAGs:")
                for dag_name, dag_info in dags.items():
                    schedule = dag_info.get("schedule", "Unknown")
                    print(f"     - {dag_name}: {schedule}")
                
                # Verify we have 5 DAGs
                if len(dags) != 5:
                    print(f"❌ Expected 5 DAGs, found {len(dags)}")
                else:
                    print(f"✅ Correct number of DAGs (5) found")
                
                # Verify expected DAG names
                expected_dags = ["daily_bhavcopy", "fii_dii_flows", "macro_data", "corporate_actions", "fundamentals"]
                found_dags = set(dags.keys())
                missing_dags = set(expected_dags) - found_dags
                
                if missing_dags:
                    print(f"❌ Missing DAGs: {missing_dags}")
                else:
                    print(f"✅ All expected DAGs present")
        
        # Test POST /api/brain/batch/trigger/fii_dii_flows
        print(f"\n🔍 Testing DAG Trigger - fii_dii_flows...")
        success, trigger_response = self.run_test("Trigger DAG - fii_dii_flows", "POST", "brain/batch/trigger/fii_dii_flows", 200)
        
        if success and trigger_response:
            print(f"✅ DAG trigger successful for fii_dii_flows")
            
            # Verify response structure
            required_fields = ["success", "run"]
            for field in required_fields:
                if field not in trigger_response:
                    print(f"❌ Missing field in trigger response: {field}")
                else:
                    value = trigger_response[field]
                    print(f"   {field}: {value}")
        
        # Test POST /api/brain/batch/trigger/macro_data
        print(f"\n🔍 Testing DAG Trigger - macro_data...")
        success, trigger_response = self.run_test("Trigger DAG - macro_data", "POST", "brain/batch/trigger/macro_data", 200)
        
        if success and trigger_response:
            print(f"✅ DAG trigger successful for macro_data")
        
        # Test GET /api/brain/batch/history
        success, history_data = self.run_test("Batch Run History", "GET", "brain/batch/history", 200)
        
        if success and history_data:
            print(f"✅ Batch history endpoint working")
            
            # Verify response structure
            history = history_data.get("history", [])
            if isinstance(history, list):
                print(f"   Found {len(history)} recent executions")
                
                # Show recent executions if any
                for i, execution in enumerate(history[:3]):  # Show first 3
                    dag_name = execution.get("dag_name", "Unknown")
                    status = execution.get("status", "Unknown")
                    started_at = execution.get("started_at", "Unknown")
                    print(f"     {i+1}. {dag_name}: {status} (started: {started_at})")
            else:
                print(f"❌ History should be a list, got: {type(history)}")

    def test_kafka_topics(self):
        """Test Kafka Topics endpoints (MEDIUM PRIORITY)"""
        print("\n" + "="*60)
        print("TESTING KAFKA TOPICS - MEDIUM PRIORITY")
        print("="*60)
        
        # Test GET /api/brain/kafka/topics
        success, topics_data = self.run_test("Kafka Topics List", "GET", "brain/kafka/topics", 200)
        
        if success and topics_data:
            print(f"\n📊 Analyzing Kafka Topics...")
            
            # Verify response structure
            topics = topics_data.get("topics", [])
            total_topics = topics_data.get("total_topics", 0)
            
            if not isinstance(topics, list):
                print(f"❌ Topics should be a list, got: {type(topics)}")
            else:
                print(f"   Found {len(topics)} topics")
                print(f"   Total topics reported: {total_topics}")
                
                # Verify we have 15 topics
                if len(topics) != 15:
                    print(f"❌ Expected 15 topics, found {len(topics)}")
                else:
                    print(f"✅ Correct number of topics (15) found")
                
                # Verify topic structure
                if topics:
                    topic = topics[0]
                    required_fields = ["name", "partitions", "replication_factor", "retention_hours", "compression", "description"]
                    topic_valid = True
                    
                    for field in required_fields:
                        if field not in topic:
                            print(f"❌ Topic missing field: {field}")
                            topic_valid = False
                    
                    if topic_valid:
                        print(f"✅ Topic structure validation passed")
                        
                        # Show a few topics
                        for i, topic in enumerate(topics[:5]):
                            name = topic.get("name", "Unknown")
                            partitions = topic.get("partitions", 0)
                            print(f"     {i+1}. {name} ({partitions} partitions)")
        
        # Test GET /api/brain/kafka/stats
        success, stats_data = self.run_test("Kafka Statistics", "GET", "brain/kafka/stats", 200)
        
        if success and stats_data:
            print(f"✅ Kafka statistics endpoint working")

    def test_storage_ingestion(self):
        """Test Storage & Ingestion endpoints (MEDIUM PRIORITY)"""
        print("\n" + "="*60)
        print("TESTING STORAGE & INGESTION - MEDIUM PRIORITY")
        print("="*60)
        
        # Test GET /api/brain/storage/status
        success, storage_data = self.run_test("Storage Status", "GET", "brain/storage/status", 200)
        
        if success and storage_data:
            print(f"\n📊 Analyzing Storage Status...")
            
            # Verify response structure
            status = storage_data.get("status")
            mode = storage_data.get("mode")
            
            print(f"   Status: {status}")
            print(f"   Mode: {mode}")
            
            # Verify mode is "filesystem" (as expected in review request)
            if mode != "filesystem":
                print(f"⚠️  Expected mode 'filesystem', got: {mode}")
            else:
                print(f"✅ Storage mode is filesystem as expected")
        
        # Test GET /api/brain/ingestion/status
        success, ingestion_data = self.run_test("Ingestion Status", "GET", "brain/ingestion/status", 200)
        
        if success and ingestion_data:
            print(f"\n📊 Analyzing Ingestion Status...")
            
            # Verify response structure
            required_fields = ["kafka_connected", "kafka_mode", "data_quality_available", "normalizer_available", "sources"]
            ingestion_valid = True
            
            for field in required_fields:
                if field not in ingestion_data:
                    print(f"❌ Missing field: {field}")
                    ingestion_valid = False
                else:
                    value = ingestion_data[field]
                    print(f"   {field}: {value}")
            
            # Check sources availability
            sources = ingestion_data.get("sources", {})
            if isinstance(sources, dict):
                print(f"   Source availability:")
                for source, available in sources.items():
                    print(f"     - {source}: {available}")
            
            if ingestion_valid:
                print(f"✅ Ingestion status validation passed")

    def test_phase1_summary(self):
        """Test Phase 1 Summary endpoint"""
        print("\n" + "="*60)
        print("TESTING PHASE 1 SUMMARY")
        print("="*60)
        
        # Test GET /api/brain/phase1/summary
        success, summary_data = self.run_test("Phase 1 Summary", "GET", "brain/phase1/summary", 200)
        
        if success and summary_data:
            print(f"\n📊 Analyzing Phase 1 Summary...")
            
            # Verify response structure
            required_fields = ["phase", "status", "components", "api_endpoints"]
            summary_valid = True
            
            for field in required_fields:
                if field not in summary_data:
                    print(f"❌ Missing field: {field}")
                    summary_valid = False
                else:
                    if field == "components":
                        components = summary_data[field]
                        print(f"   {field}: {len(components)} components")
                        
                        # Check key components
                        expected_components = ["kafka_event_bus", "feature_pipeline", "feature_store", "batch_scheduler", "storage_layer", "data_quality", "ingestion"]
                        for component in expected_components:
                            if component in components:
                                comp_status = components[component].get("status", "Unknown")
                                print(f"     - {component}: {comp_status}")
                            else:
                                print(f"❌ Missing component: {component}")
                                summary_valid = False
                    
                    elif field == "api_endpoints":
                        endpoints = summary_data[field]
                        print(f"   {field}: {len(endpoints)} endpoints listed")
                    
                    else:
                        value = summary_data[field]
                        print(f"   {field}: {value}")
            
            if summary_valid:
                print(f"✅ Phase 1 summary validation passed")

    def test_data_quality(self):
        """Test Data Quality endpoint"""
        print("\n" + "="*60)
        print("TESTING DATA QUALITY")
        print("="*60)
        
        # Test GET /api/brain/data-quality/RELIANCE
        success, quality_data = self.run_test("Data Quality - RELIANCE", "GET", "brain/data-quality/RELIANCE", 200)
        
        if success and quality_data:
            print(f"✅ Data quality endpoint working for RELIANCE")
            
            # Verify response structure
            symbol = quality_data.get("symbol")
            report = quality_data.get("report")
            
            print(f"   Symbol: {symbol}")
            print(f"   Report: {type(report)}")
            
            if symbol == "RELIANCE":
                print(f"✅ Correct symbol returned")

    def run_all_tests(self):
        """Run all Brain Phase 1 test suites"""
        print("🚀 Starting Stock Pulse Brain Phase 1 API Tests")
        print(f"Base URL: {self.base_url}")
        
        try:
            # HIGH PRIORITY TESTS
            self.test_brain_health()
            self.test_feature_pipeline()
            self.test_batch_scheduler()
            
            # MEDIUM PRIORITY TESTS
            self.test_kafka_topics()
            self.test_storage_ingestion()
            
            # OTHER TESTS
            self.test_phase1_summary()
            self.test_data_quality()
            
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
        print("BRAIN PHASE 1 TEST RESULTS SUMMARY")
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
    tester = BrainPhase1Tester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())