import pytest
from django.contrib.auth.models import User
from ninja.testing import TestClient
from config.api import api  # Import your central NinjaAPI instance

@pytest.mark.django_db
class TestOrganizationFlow:
    def setup_method(self):
        self.client = TestClient(api)
        # 1. Create a test user
        self.user = User.objects.create_user(username="coach_jim", password="password123")
        
        # 2. Ensure they have an ORG_OWNER role
        self.user.profile.role = "ORG_OWNER"
        self.user.profile.save()

    def get_token(self, username="coach_jim", password="password123"):
        # Use json= instead of data=
        response = self.client.post("/token/pair", json={
            "username": username,
            "password": password   
        })
        # It's good practice to check status here so you don't get a cryptic KeyError
        if response.status_code != 200:
            raise Exception(f"Login failed: {response.content}")
        return response.json()["access"]

    def test_create_organization_success(self):
            token = self.get_token()
            headers = {"Authorization": f"Bearer {token}"}
            
            payload = {
                "name": "Phoenix Bombers Baseball",
                "city": "Phoenix",
                "state": "AZ",
                "zip_code": "85001"
            }
            
            response = self.client.post(
                "/leagues/organizations", 
                json=payload, 
                headers=headers,
                content_type="application/json"
            )
            
            assert response.status_code == 201
            assert response.json()["name"] == "Phoenix Bombers Baseball"        

    def test_follower_cannot_create_org(self):
        # Create a "Fan" user
        fan_user = User.objects.create_user(username="baseball_fan", password="password123")
        fan_user.profile.role = "FOLLOWER"
        fan_user.profile.save()  # Don't forget to save after changing the role
        # Role defaults to FOLLOWER via our signal
        
        # Get token for the fan
        token = self.get_token(username="baseball_fan", password="password123")
        
        payload = {
            "name": "Illegal League",
            "city": "Phoenix",
            "state": "AZ",
            "zip_code": "85001"
        }
        
        response = self.client.post(
            "/leagues/organizations",
            json=payload, # Use json= instead of data= for consistency
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should be 403 Forbidden
        assert response.status_code == 403