import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from unittest.mock import MagicMock
import uuid

# Dynamically import or mock Team if leagues app isn't fully migrated yet
from django.apps import apps

class InvitationTDDTestCase(TestCase):

    def setUp(self):
        # 1. Setup an Admin/Coach to send invites
        self.coach_user = User.objects.create_user(username="coach_dan", email="dan@bombers.com", password="password123")
        self.coach_profile = self.coach_user.profile
        self.coach_profile.role = "COACH"
        self.coach_profile.save()

        # 2. Setup a non-privileged user
        self.parent_user = User.objects.create_user(username="existing_parent", email="returning@fan.com", password="password123")
        self.parent_user.profile.role = "PARENT"
        self.parent_user.profile.save()

        # 3. Create Mock Team and Player structures safely using the ORM
        # We look up models dynamically to avoid strict compile-time import blocks
        Organization = apps.get_model('leagues', 'Organization')
        Team = apps.get_model('leagues', 'Team')
        Division = apps.get_model('leagues', 'Division')
        Player = apps.get_model('profiles', 'Player')
        Invitation = apps.get_model('profiles', 'Invitation')
        Season = apps.get_model('leagues', 'Season')

        self.mock_org = Organization.objects.create(name="Test Org")
        self.mock_season = Season.objects.create(organization=self.mock_org, season="Spring", year=2026)
        self.mock_division = Division.objects.create(season=self.mock_season, name="Test Division")
        self.mock_team = Team.objects.create(name="12U Bombers", access_code="BOMBERS2026", division=self.mock_division)
        self.mock_player = Player.objects.create(first_name="Jonah", last_name="Holstine", guardian=self.coach_user)

    def _get_jwt_token(self, user):
        resp = self.client.post("/api/token/pair", json.dumps({
            "username": user.username, "password": "password123"
        }), content_type="application/json")
        return resp.json()["access"]

    def _auth_header(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_01_coach_can_create_invitation(self):
        """TDD: Verify authorized personnel can issue an invite payload."""
        token = self._get_jwt_token(self.coach_user)
        headers = self._auth_header(token)
        payload = {
            "email": "new_parent@example.com",
            "team_id": str(self.mock_team.id),
            "player_id": self.mock_player.id,
            "target_role": "PARENT"
        }
        response = self.client.post("/api/profiles/invitations", payload, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.json())

    def test_02_verify_valid_token_for_new_user(self):
        """TDD: Check token returns data and flags user_exists as False."""
        Invitation = apps.get_model('profiles', 'Invitation')
        invite = Invitation.objects.create(
            email="fresh_blood@example.com", team=self.mock_team, 
            player=self.mock_player, target_role="PARENT", invited_by=self.coach_user
        )
        
        response = self.client.get(f"/api/profiles/invitations/verify/{invite.token}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["user_exists"])
        self.assertEqual(response.json()["team_name"], "12U Bombers")

    def test_03_verify_valid_token_for_returning_user(self):
        """TDD: Check token flags user_exists as True if email matches an account."""
        Invitation = apps.get_model('profiles', 'Invitation')
        invite = Invitation.objects.create(
            email="returning@fan.com", team=self.mock_team, 
            player=self.mock_player, target_role="PARENT", invited_by=self.coach_user
        )
        
        response = self.client.get(f"/api/profiles/invitations/verify/{invite.token}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["user_exists"])

    def test_04_accept_invitation_creates_new_user_and_links(self):
        """TDD: Assert atomicity. Brand new user registers and claims player ownership."""
        Invitation = apps.get_model('profiles', 'Invitation')
        invite = Invitation.objects.create(
            email="brand_new_parent@example.com", team=self.mock_team, 
            player=self.mock_player, target_role="PARENT", invited_by=self.coach_user
        )

        payload = {
            "token": invite.token, "username": "jonahs_mom", "password": "supersecurepassword123",
            "first_name": "Kimber", "last_name": "Holstine"
        }
        response = self.client.post("/api/profiles/invitations/accept", payload, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        
        # Verify side effects
        self.assertTrue(User.objects.filter(username="jonahs_mom").exists())
        self.mock_player.refresh_from_db()
        self.assertEqual(self.mock_player.guardian.username, "jonahs_mom")

    def test_05_accept_invitation_handles_returning_user(self):
        """TDD: Assert that returning users skip account creation and append roster slots."""
        Invitation = apps.get_model('profiles', 'Invitation')
        TeamMembership = apps.get_model('profiles', 'TeamMembership')
        
        invite = Invitation.objects.create(
            email="returning@fan.com", team=self.mock_team, 
            player=self.mock_player, target_role="PARENT", invited_by=self.coach_user
        )

        payload = {
            "token": invite.token, "username": "", "password": "", "first_name": "", "last_name": ""
        }
        response = self.client.post("/api/profiles/invitations/accept", payload, content_type="application/json")
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TeamMembership.objects.filter(user=self.parent_user, team=self.mock_team).exists())

    def test_06_accept_invitation_assigns_organization_from_team(self):
        """TDD: Ensure invited users receive the organization link from their team assignment."""
        Organization = apps.get_model('leagues', 'Organization')
        Season = apps.get_model('leagues', 'Season')
        Division = apps.get_model('leagues', 'Division')
        Team = apps.get_model('leagues', 'Team')
        Invitation = apps.get_model('profiles', 'Invitation')

        organization = Organization.objects.create(name="Cactus Wren LL")
        season = Season.objects.create(organization=organization, season="Spring", year=2026)
        division = Division.objects.create(season=season, name="Test")
        team = Team.objects.create(name="12U Bombers", access_code="BOMBERS2027", division=division)

        invite = Invitation.objects.create(
            email="returning@fan.com", team=team,
            target_role="COACH", invited_by=self.coach_user
        )

        payload = {
            "token": invite.token,
            "username": "",
            "password": "",
            "first_name": "",
            "last_name": ""
        }
        response = self.client.post("/api/profiles/invitations/accept", payload, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.parent_user.refresh_from_db()
        self.assertEqual(self.parent_user.profile.organization, organization)

    def test_07_join_team_via_public_fan_code(self):
        """TDD: Fans can register to follow teams universally using alphanumeric codes."""
        token = self._get_jwt_token(self.parent_user)
        headers = self._auth_header(token)
        payload = {"access_code": "BOMBERS2026"}
        
        response = self.client.post("/api/profiles/teams/join-as-follower", payload, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200)
        
        TeamMembership = apps.get_model('profiles', 'TeamMembership')
        self.assertTrue(TeamMembership.objects.filter(user=self.parent_user, team=self.mock_team, role="FOLLOWER").exists())


from django.core import mail
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

class AdminWebviewInterfaceTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username="league_director", password="securepass123")
        self.client.force_login(self.admin_user)
        
        # Setup initial organization and season targets
        Team = apps.get_model('leagues', 'Team')
        Season = apps.get_model('leagues', 'Season')
        Organization = apps.get_model('leagues', 'Organization')
        
        self.org = Organization.objects.create(name="Cactus Wren LL")
        self.season = Season.objects.create(organization=self.org, season="Spring", year=2026)

    def test_dashboard_infers_organization_for_coach_membership(self):
        """Admins who also coach teams should see the organization context on the dashboard."""
        Organization = apps.get_model('leagues', 'Organization')
        Season = apps.get_model('leagues', 'Season')
        Division = apps.get_model('leagues', 'Division')
        Team = apps.get_model('leagues', 'Team')
        TeamMembership = apps.get_model('profiles', 'TeamMembership')

        organization = Organization.objects.create(name="Carter County LL")
        season = Season.objects.create(organization=organization, season="Fall", year=2026)
        division = Division.objects.create(season=season, name="10U")
        team = Team.objects.create(name="10U Tigers", access_code="TIGERS2026", division=division)

        coach_user = User.objects.create_user(username="coach_sam", password="password123")
        coach_user.profile.role = "COACH"
        coach_user.profile.save()
        TeamMembership.objects.create(user=coach_user, team=team, role="COACH", is_active=True)

        self.client.force_login(coach_user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carter County LL")
        self.assertContains(response, "10U Tigers")

    def test_manual_coach_entry_sends_console_email(self):
        """Verify that typing a single coach manually generates an invite and drops mail into the system."""
        payload = {
            'division_name': '10U',
            'team_name': '11U Mud Hens',
            'manual_email': 'assistant_coach@gmail.com',
            'manual_first_name': 'John',
            'manual_last_name': 'Holstine'
        }
        url = reverse('roster_onboarding', kwargs={'season_id': self.season.id})
        response = self.client.post(url, payload)
        
        # Check redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Inspect Django's test email outbox (mirrors console backend behavior)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], 'assistant_coach@gmail.com')
        self.assertIn('DiamondManager', mail.outbox[0].body)

    def test_bulk_csv_upload_processing(self):
        """Verify uploading an in-memory CSV generates multiple distinct targets cleanly."""
        csv_content = "email,first_name,last_name\ncoach1@test.com,Dan,Smith\ncoach2@test.com,Mark,Davis\n"
        uploaded_file = SimpleUploadedFile("roster.csv", csv_content.encode('utf-8'), content_type="text/csv")
        
        payload = {
            'division_name': '10U',
            'team_name': '9U Raptors',
            'spreadsheet_file': uploaded_file
        }
        url = reverse('roster_onboarding', kwargs={'season_id': self.season.id})
        response = self.client.post(url, payload)
        
        # Outbox should have grabbed exactly two entries
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to[0], 'coach1@test.com')
        self.assertEqual(mail.outbox[1].to[0], 'coach2@test.com')        