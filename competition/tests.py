from django.test import TestCase
from django.contrib.auth.models import User
from django.apps import apps


class PermissionViewTestCase(TestCase):

    def setUp(self):
        Organization = apps.get_model('leagues', 'Organization')
        Season = apps.get_model('leagues', 'Season')
        Division = apps.get_model('leagues', 'Division')
        Team = apps.get_model('leagues', 'Team')
        TeamMembership = apps.get_model('profiles', 'TeamMembership')

        self.org = Organization.objects.create(name="Test Org")
        self.season = Season.objects.create(organization=self.org, season="Spring", year=2026)
        self.div_a = Division.objects.create(season=self.season, name="10U")
        self.div_b = Division.objects.create(season=self.season, name="12U")

        self.team_a1 = Team.objects.create(name="Tigers", division=self.div_a, access_code="TIGER1")
        self.team_a2 = Team.objects.create(name="Bears", division=self.div_a, access_code="BEARS1")
        self.team_b1 = Team.objects.create(name="Wolves", division=self.div_b, access_code="WOLF1")
        self.team_b2 = Team.objects.create(name="Hawks", division=self.div_b, access_code="HAWK1")

        # Owner user — ORG_OWNER role, also seeded as COACH membership on team_a1
        self.owner = User.objects.create_user(
            username="owner", password="password123",
            email="owner@test.com", first_name="Owner", last_name="User"
        )
        self.owner.profile.role = "ORG_OWNER"
        self.owner.profile.organization = self.org
        self.owner.profile.save()
        TeamMembership.objects.create(user=self.owner, team=self.team_a1, role="COACH", is_active=True)
        self.team_a1.coaches.add(self.owner)

        # Coach user — COACH role, member of team_a1
        self.coach = User.objects.create_user(
            username="coach_a1", password="password123",
            email="coach@test.com", first_name="Coach", last_name="A1"
        )
        self.coach.profile.role = "COACH"
        self.coach.profile.organization = self.org
        self.coach.profile.save()
        TeamMembership.objects.create(user=self.coach, team=self.team_a1, role="COACH", is_active=True)
        self.team_a1.coaches.add(self.coach)

        # Sibling coach — COACH role, member of team_a2 (same division)
        self.sibling = User.objects.create_user(
            username="sibling_a2", password="password123",
            email="sibling@test.com", first_name="Sibling", last_name="A2"
        )
        self.sibling.profile.role = "COACH"
        self.sibling.profile.organization = self.org
        self.sibling.profile.save()
        TeamMembership.objects.create(user=self.sibling, team=self.team_a2, role="COACH", is_active=True)
        self.team_a2.coaches.add(self.sibling)

        # Cross-division coach — COACH role, member of team_b1 (different division)
        self.cross = User.objects.create_user(
            username="cross_b1", password="password123",
            email="cross@test.com", first_name="Cross", last_name="B1"
        )
        self.cross.profile.role = "COACH"
        self.cross.profile.organization = self.org
        self.cross.profile.save()
        TeamMembership.objects.create(user=self.cross, team=self.team_b1, role="COACH", is_active=True)
        self.team_b1.coaches.add(self.cross)

    # ------------------------------------------------------------------
    # CreateTeamEventView — GET permission checks
    # ------------------------------------------------------------------

    def test_owner_can_create_own_team_event(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/competitions/team/{self.team_a1.id}/events/new/")
        self.assertEqual(resp.status_code, 200)

    def test_coach_can_create_own_team_event(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_a1.id}/events/new/")
        self.assertEqual(resp.status_code, 200)

    def test_coach_cannot_create_sibling_team_event(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_a2.id}/events/new/")
        self.assertEqual(resp.status_code, 302)

    def test_coach_cannot_create_cross_div_team_event(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_b1.id}/events/new/")
        self.assertEqual(resp.status_code, 302)

    def test_owner_can_create_any_team_event(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/competitions/team/{self.team_b1.id}/events/new/")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # TeamEventsListView — can_create context
    # ------------------------------------------------------------------

    def test_owner_can_create_true_on_own_team_events(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/competitions/team/{self.team_a1.id}/events/")
        self.assertTrue(resp.context["can_create"])

    def test_owner_can_create_true_on_any_team_events(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/competitions/team/{self.team_b1.id}/events/")
        self.assertTrue(resp.context["can_create"])

    def test_coach_can_create_true_on_own_team_events(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_a1.id}/events/")
        self.assertTrue(resp.context["can_create"])

    def test_coach_can_create_false_on_sibling_team_events(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_a2.id}/events/")
        self.assertFalse(resp.context["can_create"])

    def test_coach_can_still_view_sibling_team_events(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/team/{self.team_a2.id}/events/")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # ScheduleEventChoiceView — coaching_teams vs viewable_teams
    # ------------------------------------------------------------------

    def test_owner_sees_all_teams_as_coaching(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/competitions/schedule/")
        self.assertCountEqual(
            [t.id for t in resp.context["coaching_teams"]],
            [self.team_a1.id, self.team_a2.id, self.team_b1.id, self.team_b2.id]
        )
        self.assertEqual(len(resp.context["viewable_teams"]), 0)

    def test_coach_sees_own_team_as_coaching(self):
        self.client.force_login(self.coach)
        resp = self.client.get("/competitions/schedule/")
        self.assertEqual(
            [t.id for t in resp.context["coaching_teams"]],
            [self.team_a1.id]
        )

    def test_coach_sees_sibling_teams_as_viewable(self):
        self.client.force_login(self.coach)
        resp = self.client.get("/competitions/schedule/")
        self.assertEqual(
            [t.id for t in resp.context["viewable_teams"]],
            [self.team_a2.id]
        )

    def test_coach_does_not_see_cross_div_teams(self):
        self.client.force_login(self.coach)
        resp = self.client.get("/competitions/schedule/")
        visible_ids = (
            [t.id for t in resp.context["coaching_teams"]]
            + [t.id for t in resp.context["viewable_teams"]]
        )
        self.assertNotIn(self.team_b1.id, visible_ids)
        self.assertNotIn(self.team_b2.id, visible_ids)

    # ------------------------------------------------------------------
    # Template rendering — button visibility
    # ------------------------------------------------------------------

    def test_division_new_event_button_shown_for_owner(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/competitions/division/{self.div_a.id}/events/")
        self.assertContains(resp, "+ New Event")

    def test_division_new_event_button_hidden_for_coach(self):
        self.client.force_login(self.coach)
        resp = self.client.get(f"/competitions/division/{self.div_a.id}/events/")
        self.assertNotContains(resp, "+ New Event")

    def test_organization_event_button_shown_for_owner(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/competitions/schedule/")
        self.assertContains(resp, "Organization Event")

    def test_organization_event_button_hidden_for_coach(self):
        self.client.force_login(self.coach)
        resp = self.client.get("/competitions/schedule/")
        self.assertNotContains(resp, "Organization Event")

    def test_division_schedule_section_shown_for_owner(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/competitions/schedule/")
        self.assertContains(resp, "Division Events")

    def test_division_schedule_section_hidden_for_coach(self):
        self.client.force_login(self.coach)
        resp = self.client.get("/competitions/schedule/")
        self.assertNotContains(resp, "Division Events")
