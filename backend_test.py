#!/usr/bin/env python3
"""
GapHub AI Backend API Testing Script
Tests admin panel and scheduler endpoints as requested
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://click-hold-issue.preview.emergentagent.com"
ADMIN_EMAIL = "admin@gaphub.ai"
ADMIN_PASSWORD = "GapHub@2024"

class GapHubTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'GapHub-Test-Client/1.0'
        })
        self.admin_user = None
        self.test_results = []
        
    def log_test(self, test_name, success, details="", response_data=None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        if response_data and not success:
            print(f"   Response: {response_data}")
        print()
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'details': details,
            'response': response_data
        })
    
    def test_health_check(self):
        """Test basic health endpoint"""
        try:
            response = self.session.get(f"{BASE_URL}/api/health")
            if response.status_code == 200:
                data = response.json()
                self.log_test("Health Check", True, f"Status: {data.get('status')}")
                return True
            else:
                self.log_test("Health Check", False, f"Status code: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_login(self):
        """Test admin login and get session cookie"""
        try:
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(f"{BASE_URL}/api/auth/login", json=login_data)
            
            if response.status_code == 200:
                user_data = response.json()
                if user_data.get('role') == 'super_admin':
                    self.admin_user = user_data
                    self.log_test("Admin Login", True, f"Logged in as {user_data.get('email')} (role: {user_data.get('role')})")
                    return True
                else:
                    self.log_test("Admin Login", False, f"User role is {user_data.get('role')}, expected super_admin")
                    return False
            else:
                self.log_test("Admin Login", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Admin Login", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_stats(self):
        """Test GET /api/admin/stats"""
        try:
            response = self.session.get(f"{BASE_URL}/api/admin/stats")
            
            if response.status_code == 200:
                stats = response.json()
                required_fields = ['total_users', 'total_workspaces', 'total_agents', 'total_runs', 
                                 'completed_runs', 'failed_runs', 'success_rate', 'total_schedules', 
                                 'active_schedules', 'recent_users']
                
                missing_fields = [field for field in required_fields if field not in stats]
                if not missing_fields:
                    self.log_test("Admin Stats", True, f"Retrieved stats: {stats.get('total_users')} users, {stats.get('total_agents')} agents")
                    return True
                else:
                    self.log_test("Admin Stats", False, f"Missing fields: {missing_fields}")
                    return False
            else:
                self.log_test("Admin Stats", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Admin Stats", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_tenants(self):
        """Test GET /api/admin/tenants"""
        try:
            response = self.session.get(f"{BASE_URL}/api/admin/tenants")
            
            if response.status_code == 200:
                data = response.json()
                tenants = data.get('tenants', [])
                self.log_test("Admin Tenants List", True, f"Retrieved {len(tenants)} tenants")
                
                # Store first tenant for update test
                if tenants:
                    self.test_workspace_id = tenants[0].get('workspace_id')
                    return tenants[0]  # Return first tenant for further testing
                return True
            else:
                self.log_test("Admin Tenants List", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Admin Tenants List", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_tenant_update(self, workspace_id):
        """Test PUT /api/admin/tenants/{workspace_id}"""
        if not workspace_id:
            self.log_test("Admin Tenant Update", False, "No workspace_id available for testing")
            return False
            
        try:
            update_data = {
                "plan": "premium",
                "status": "active"
            }
            
            response = self.session.put(f"{BASE_URL}/api/admin/tenants/{workspace_id}", json=update_data)
            
            if response.status_code == 200:
                result = response.json()
                self.log_test("Admin Tenant Update", True, f"Updated tenant {workspace_id}: {result.get('message')}")
                return True
            else:
                self.log_test("Admin Tenant Update", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Admin Tenant Update", False, f"Exception: {str(e)}")
            return False
    
    def test_non_admin_access(self):
        """Test that admin endpoints return 403 for non-admin users"""
        # Create a temporary session without admin cookies
        temp_session = requests.Session()
        temp_session.headers.update({'Content-Type': 'application/json'})
        
        try:
            response = temp_session.get(f"{BASE_URL}/api/admin/stats")
            
            if response.status_code == 401:  # Unauthorized (no auth)
                self.log_test("Non-Admin Access Control", True, "Correctly returned 401 for unauthenticated request")
                return True
            elif response.status_code == 403:  # Forbidden (authenticated but not admin)
                self.log_test("Non-Admin Access Control", True, "Correctly returned 403 for non-admin user")
                return True
            else:
                self.log_test("Non-Admin Access Control", False, f"Expected 401/403, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Non-Admin Access Control", False, f"Exception: {str(e)}")
            return False
    
    def test_get_agents(self):
        """Test GET /api/agents to get list of agents"""
        try:
            response = self.session.get(f"{BASE_URL}/api/agents")
            
            if response.status_code == 200:
                data = response.json()
                agents = data.get('agents', [])
                self.log_test("Get Agents List", True, f"Retrieved {len(agents)} agents")
                
                # Store first agent for schedule testing
                if agents:
                    self.test_agent_id = agents[0].get('agent_id')
                    return agents[0]
                return True
            else:
                self.log_test("Get Agents List", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Get Agents List", False, f"Exception: {str(e)}")
            return False
    
    def test_get_schedules(self):
        """Test GET /api/schedules"""
        try:
            response = self.session.get(f"{BASE_URL}/api/schedules")
            
            if response.status_code == 200:
                data = response.json()
                schedules = data.get('schedules', [])
                self.log_test("Get Schedules", True, f"Retrieved {len(schedules)} schedules")
                return schedules
            else:
                self.log_test("Get Schedules", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Get Schedules", False, f"Exception: {str(e)}")
            return False
    
    def test_create_schedule(self, agent_id):
        """Test POST /api/schedules"""
        if not agent_id:
            self.log_test("Create Schedule", False, "No agent_id available for testing")
            return False
            
        try:
            schedule_data = {
                "agent_id": agent_id,
                "name": "Test Schedule",
                "cron_expression": "0 9 * * 1",  # Every Monday at 9 AM
                "input_message": "Execute weekly report",
                "active": True
            }
            
            response = self.session.post(f"{BASE_URL}/api/schedules", json=schedule_data)
            
            if response.status_code == 200:
                schedule = response.json()
                self.test_schedule_id = schedule.get('schedule_id')
                self.log_test("Create Schedule", True, f"Created schedule {self.test_schedule_id}")
                return schedule
            else:
                self.log_test("Create Schedule", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Create Schedule", False, f"Exception: {str(e)}")
            return False
    
    def test_update_schedule(self, schedule_id):
        """Test PUT /api/schedules/{schedule_id}"""
        if not schedule_id:
            self.log_test("Update Schedule", False, "No schedule_id available for testing")
            return False
            
        try:
            update_data = {
                "active": False,  # Toggle to inactive
                "name": "Updated Test Schedule"
            }
            
            response = self.session.put(f"{BASE_URL}/api/schedules/{schedule_id}", json=update_data)
            
            if response.status_code == 200:
                updated_schedule = response.json()
                self.log_test("Update Schedule", True, f"Updated schedule {schedule_id}, active: {updated_schedule.get('active')}")
                return True
            else:
                self.log_test("Update Schedule", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Update Schedule", False, f"Exception: {str(e)}")
            return False
    
    def test_delete_schedule(self, schedule_id):
        """Test DELETE /api/schedules/{schedule_id}"""
        if not schedule_id:
            self.log_test("Delete Schedule", False, "No schedule_id available for testing")
            return False
            
        try:
            response = self.session.delete(f"{BASE_URL}/api/schedules/{schedule_id}")
            
            if response.status_code == 200:
                result = response.json()
                self.log_test("Delete Schedule", True, f"Deleted schedule {schedule_id}: {result.get('message')}")
                return True
            else:
                self.log_test("Delete Schedule", False, f"Status code: {response.status_code}", response.text)
                return False
                
        except Exception as e:
            self.log_test("Delete Schedule", False, f"Exception: {str(e)}")
            return False
    
    def test_invalid_cron_expression(self):
        """Test schedule creation with invalid cron expression"""
        try:
            # Use a dummy agent_id since we're testing cron validation, not agent validation
            schedule_data = {
                "agent_id": "dummy_agent_for_cron_test",
                "name": "Invalid Cron Test",
                "cron_expression": "invalid cron",  # Invalid cron
                "input_message": "Test message",
                "active": True
            }
            
            response = self.session.post(f"{BASE_URL}/api/schedules", json=schedule_data)
            
            if response.status_code == 400:
                error = response.json()
                self.log_test("Invalid Cron Validation", True, f"Correctly rejected invalid cron: {error.get('detail')}")
                return True
            elif response.status_code == 422:
                # Pydantic validation error - also acceptable for invalid data
                error = response.json()
                self.log_test("Invalid Cron Validation", True, f"Correctly rejected invalid data (422): {error.get('detail')}")
                return True
            else:
                self.log_test("Invalid Cron Validation", False, f"Expected 400/422, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Invalid Cron Validation", False, f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting GapHub AI Backend API Tests")
        print("=" * 50)
        
        # Initialize test variables
        self.test_workspace_id = None
        self.test_agent_id = None
        self.test_schedule_id = None
        
        # Basic connectivity
        if not self.test_health_check():
            print("❌ Health check failed, aborting tests")
            return False
        
        # Authentication
        if not self.test_admin_login():
            print("❌ Admin login failed, aborting admin tests")
            return False
        
        # Admin endpoints
        self.test_admin_stats()
        tenant = self.test_admin_tenants()
        if tenant and isinstance(tenant, dict):
            self.test_admin_tenant_update(tenant.get('workspace_id'))
        
        # Authorization test
        self.test_non_admin_access()
        
        # Agent endpoints
        agent = self.test_get_agents()
        if agent and isinstance(agent, dict):
            self.test_agent_id = agent.get('agent_id')
        
        # Schedule endpoints
        self.test_get_schedules()
        
        # Schedule CRUD operations
        if hasattr(self, 'test_agent_id') and self.test_agent_id:
            schedule = self.test_create_schedule(self.test_agent_id)
            if schedule and isinstance(schedule, dict):
                schedule_id = schedule.get('schedule_id')
                self.test_update_schedule(schedule_id)
                self.test_delete_schedule(schedule_id)
        
        # Validation tests
        self.test_invalid_cron_expression()
        
        # Summary
        print("=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        
        if total - passed > 0:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        return passed == total

if __name__ == "__main__":
    tester = GapHubTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)