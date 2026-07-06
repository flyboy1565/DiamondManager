from django.test import TestCase
from django.contrib.auth.models import User
from django.apps import apps


class ScoringEngineTestCase(TestCase):
    """Tests for the scoring engine logic in api.py"""

    def setUp(self):
        Organization = apps.get_model('leagues', 'Organization')
        Season = apps.get_model('leagues', 'Season')
        Division = apps.get_model('leagues', 'Division')
        Team = apps.get_model('leagues', 'Team')
        Player = apps.get_model('profiles', 'Player')

        self.org = Organization.objects.create(name="Test Org")
        self.season = Season.objects.create(organization=self.org, season="Spring", year=2026)
        self.div = Division.objects.create(season=self.season, name="10U")
        self.home = Team.objects.create(name="Home", division=self.div, access_code="HOME1")
        self.away = Team.objects.create(name="Away", division=self.div, access_code="AWAY1")

        # Create a guardian user (required by Player model)
        self.guardian = User.objects.create_user(username="guardian", password="password123")

        # Create players
        self.batter = Player.objects.create(first_name="Test", last_name="Batter", guardian=self.guardian)
        self.runner1 = Player.objects.create(first_name="Runner", last_name="One", guardian=self.guardian)
        self.runner2 = Player.objects.create(first_name="Runner", last_name="Two", guardian=self.guardian)
        self.runner3 = Player.objects.create(first_name="Runner", last_name="Three", guardian=self.guardian)

        # Create a game with initial scoring data
        from .models import Game
        self.game = Game.objects.create(
            season=self.season,
            home_team=self.home,
            away_team=self.away,
            date_time="2026-06-01 10:00:00+00",
            location="Test Field",
        )
        self._init_game()

    def _init_game(self):
        """Initialize the game with lineup and start state."""
        from .api import _init_scoring_data
        _init_scoring_data(self.game)
        self.game.scoring_data['lineup_order'] = {
            'home': [self.batter.id, self.runner1.id, self.runner2.id, self.runner3.id],
            'away': [self.batter.id],
        }
        self.game.scoring_data['batting_order_idx'] = {'home': 0, 'away': 0}
        self.game.scoring_data['current_batter'] = {
            'side': 'home',
            'player_id': self.batter.id,
            'player_name': str(self.batter),
        }
        self.game.scoring_data['current_pitcher'] = {
            'home': {'player_id': self.runner1.id, 'player_name': str(self.runner1)},
            'away': {'player_id': self.runner2.id, 'player_name': str(self.runner2)},
        }
        self.game.is_live = True
        self.game.home_score = 0
        self.game.away_score = 0
        self.game.current_inning = 1
        self.game.is_top_inning = True
        self.game.outs = 0
        self.game.balls = 0
        self.game.strikes = 0
        self.game.pitch_count = 0
        self.game.scoring_data['runners'] = {'first': None, 'second': None, 'third': None}
        self.game.save()

    def _apply(self, pitch_type, extra=None):
        from .api import _apply_record_pitch
        _apply_record_pitch(self.game, pitch_type, extra=extra)
        self.game.save()

    def _set_runners(self, first=None, second=None, third=None):
        runners = {}
        if first:
            runners['first'] = {'player_id': first.id, 'player_name': str(first)}
        else:
            runners['first'] = None
        if second:
            runners['second'] = {'player_id': second.id, 'player_name': str(second)}
        else:
            runners['second'] = None
        if third:
            runners['third'] = {'player_id': third.id, 'player_name': str(third)}
        else:
            runners['third'] = None
        self.game.scoring_data['runners'] = runners

    def _get_runners(self):
        return self.game.scoring_data.get('runners', {})

    # === BALL / WALK ===
    def test_ball_increments_count(self):
        self._apply('ball')
        self.assertEqual(self.game.balls, 1)

    def test_walk_on_four_balls(self):
        self.game.balls = 3
        self._set_runners()
        self._apply('ball')
        self.assertEqual(self.game.balls, 0)
        self.assertEqual(self.game.strikes, 0)
        # Batter should be on first
        self.assertIsNotNone(self._get_runners().get('first'))
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)

    def test_walk_forces_runners(self):
        self.game.balls = 3
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('ball')
        # Runner2 forced to third, Runner1 forced to second, batter to first
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)
        self.assertEqual(self._get_runners()['third']['player_id'], self.runner2.id)

    def test_walk_with_bases_loaded_scores_run(self):
        self.game.balls = 3
        self._set_runners(first=self.runner1, second=self.runner2, third=self.runner3)
        self._apply('ball')
        self.assertEqual(self.game.away_score, 1)

    # === STRIKES / STRIKEOUT ===
    def test_strike_increments_count(self):
        self._apply('strike')
        self.assertEqual(self.game.strikes, 1)

    def test_strikeout_on_three_strikes(self):
        self.game.strikes = 2
        self._apply('strike')
        self.assertEqual(self.game.outs, 1)
        self.assertEqual(self.game.strikes, 0)
        self.assertEqual(self.game.balls, 0)

    def test_foul_with_two_strikes_does_not_increase(self):
        self.game.strikes = 2
        self._apply('foul')
        self.assertEqual(self.game.strikes, 2)

    def test_foul_with_one_strike_increases(self):
        self.game.strikes = 1
        self._apply('foul')
        self.assertEqual(self.game.strikes, 2)

    def test_bunt_foul_with_two_strikes_is_strikeout(self):
        self.game.strikes = 2
        self._apply('bunt_foul')
        self.assertEqual(self.game.outs, 1)

    # === HITS ===
    def test_single_places_batter_on_first(self):
        self._set_runners()
        self._apply('single')
        self.assertIsNotNone(self._get_runners().get('first'))
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)

    def test_double_places_batter_on_second(self):
        self._set_runners()
        self._apply('double')
        self.assertIsNotNone(self._get_runners().get('second'))
        self.assertEqual(self._get_runners()['second']['player_id'], self.batter.id)

    def test_triple_places_batter_on_third(self):
        self._set_runners()
        self._apply('triple')
        self.assertIsNotNone(self._get_runners().get('third'))
        self.assertEqual(self._get_runners()['third']['player_id'], self.batter.id)

    def test_homerun_scores(self):
        self._set_runners()
        self._apply('homerun')
        # Top of 1st — away team is batting
        self.assertEqual(self.game.away_score, 1)

    def test_homerun_with_runners_scores_all(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('homerun')
        # Top of 1st — away team is batting; 3 runs (batter + 2 runners)
        self.assertEqual(self.game.away_score, 3)

    def test_single_advances_runner(self):
        self._set_runners(first=self.runner1)
        self._apply('single')
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)

    def test_double_advances_runner_to_third(self):
        self._set_runners(first=self.runner1)
        self._apply('double')
        # Runner from first goes to third, batter to second
        self.assertEqual(self._get_runners()['second']['player_id'], self.batter.id)
        self.assertEqual(self._get_runners()['third']['player_id'], self.runner1.id)
        self.assertEqual(self.game.away_score, 0)

    # === OUT VARIANTS ===
    def test_ground_out_increases_outs(self):
        self._apply('out_ground')
        self.assertEqual(self.game.outs, 1)

    def test_fly_out_increases_outs(self):
        self._apply('out_fly')
        self.assertEqual(self.game.outs, 1)

    def test_line_out_increases_outs(self):
        self._apply('out_line')
        self.assertEqual(self.game.outs, 1)

    def test_pop_out_increases_outs(self):
        self._apply('out_pop')
        self.assertEqual(self.game.outs, 1)

    def test_three_outs_retires_side(self):
        self.game.outs = 2
        self._apply('out_ground')
        self.assertEqual(self.game.outs, 0)
        # Inning should advance
        self.assertFalse(self.game.is_top_inning)

    # === DOUBLE PLAY ===
    def test_double_play_default(self):
        self._set_runners(first=self.runner1)
        self._apply('double_play')
        self.assertEqual(self.game.outs, 2)
        self.assertIsNone(self._get_runners().get('first'))

    def test_double_play_with_two_runners(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('double_play')
        self.assertEqual(self.game.outs, 2)

    def test_double_play_clears_side_on_third_out(self):
        self.game.outs = 1
        self._set_runners(first=self.runner1)
        self._apply('double_play')
        # After 3 outs inning resets to 0
        self.assertEqual(self.game.outs, 0)
        self.assertFalse(self.game.is_top_inning)
        self.assertIsNone(self._get_runners().get('first'))
        self.assertIsNone(self._get_runners().get('second'))
        self.assertIsNone(self._get_runners().get('third'))

    # === TRIPLE PLAY ===
    def test_triple_play_retires_side(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('triple_play')
        # 3 outs → inning resets
        self.assertEqual(self.game.outs, 0)
        self.assertFalse(self.game.is_top_inning)

    # === PICK OFF ===
    def test_pickoff_default_picks_lead_runner(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('pickoff')
        self.assertEqual(self.game.outs, 1)
        # Lead runner (furthest from home, i.e. second base) should be out
        self.assertIsNone(self._get_runners().get('second'))

    def test_pickoff_with_runner_base_extra(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('pickoff', extra={'runner_base': 'first'})
        self.assertEqual(self.game.outs, 1)
        self.assertIsNone(self._get_runners().get('first'))
        self.assertIsNotNone(self._get_runners().get('second'))

    # === STEAL ===
    def test_steal_successful(self):
        self._set_runners(first=self.runner1)
        self._apply('steal', extra={'runner_base': 'first'})
        self.assertIsNone(self._get_runners().get('first'))
        self.assertIsNotNone(self._get_runners().get('second'))
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)

    def test_steal_to_third(self):
        self._set_runners(second=self.runner1)
        self._apply('steal', extra={'runner_base': 'second'})
        self.assertIsNone(self._get_runners().get('second'))
        self.assertIsNotNone(self._get_runners().get('third'))
        self.assertEqual(self._get_runners()['third']['player_id'], self.runner1.id)

    def test_steal_home_scores(self):
        self._set_runners(third=self.runner1)
        self._apply('steal', extra={'runner_base': 'third'})
        self.assertEqual(self.game.away_score, 1)
        self.assertIsNone(self._get_runners().get('third'))

    def test_caught_stealing(self):
        self._set_runners(first=self.runner1)
        self._apply('caught_stealing', extra={'runner_base': 'first'})
        self.assertEqual(self.game.outs, 1)
        self.assertIsNone(self._get_runners().get('first'))

    # === HIT BY PITCH ===
    def test_hit_by_pitch(self):
        self._set_runners()
        self._apply('hit_by_pitch')
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self.game.balls, 0)
        self.assertEqual(self.game.strikes, 0)

    def test_hbp_forces_runners(self):
        self._set_runners(first=self.runner1)
        self._apply('hit_by_pitch')
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)

    def test_hbp_scores_with_bases_loaded(self):
        self._set_runners(first=self.runner1, second=self.runner2, third=self.runner3)
        self._apply('hit_by_pitch')
        self.assertEqual(self.game.away_score, 1)

    # === SACRIFICE ===
    def test_sac_bunt_batter_out(self):
        self._set_runners(first=self.runner1)
        self._apply('sac_bunt')
        self.assertEqual(self.game.outs, 1)

    def test_sac_bunt_advances_runner(self):
        self._set_runners(first=self.runner1)
        self._apply('sac_bunt')
        self.assertIsNotNone(self._get_runners().get('second'))
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)

    def test_sac_fly_scores_from_third(self):
        self._set_runners(third=self.runner1)
        self._apply('sac_fly')
        self.assertEqual(self.game.outs, 1)
        self.assertEqual(self.game.away_score, 1)
        self.assertIsNone(self._get_runners().get('third'))

    # === ERROR ===
    def test_error_batter_safe(self):
        self._set_runners()
        self._apply('error')
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self.game.outs, 0)

    def test_error_advances_runners(self):
        self._set_runners(first=self.runner1)
        self._apply('error')
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)

    # === FIELDER'S CHOICE ===
    def test_fielders_choice(self):
        self._set_runners(first=self.runner1)
        self._apply('fielders_choice')
        self.assertEqual(self.game.outs, 1)
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)

    # === WILD PITCH / PASSED BALL ===
    def test_wild_pitch_advances_runners(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('wild_pitch')
        self.assertIsNone(self._get_runners().get('first'))
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)
        self.assertEqual(self._get_runners()['third']['player_id'], self.runner2.id)

    def test_passed_ball_advances_runners(self):
        self._set_runners(third=self.runner1)
        self._apply('passed_ball')
        self.assertEqual(self.game.away_score, 1)
        self.assertIsNone(self._get_runners().get('third'))

    # === BALK ===
    def test_balk_advances_all_runners(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('balk')
        self.assertIsNone(self._get_runners().get('first'))
        self.assertEqual(self._get_runners()['second']['player_id'], self.runner1.id)
        self.assertEqual(self._get_runners()['third']['player_id'], self.runner2.id)

    def test_balk_scores_from_third(self):
        self._set_runners(third=self.runner1)
        self._apply('balk')
        self.assertEqual(self.game.away_score, 1)
        self.assertIsNone(self._get_runners().get('third'))

    # === DROPPED 3RD STRIKE ===
    def test_dropped_third_strike_batter_reaches(self):
        self.game.strikes = 2
        self._set_runners()
        self._apply('dropped_third_strike')
        # Batter should reach first safely
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self.game.outs, 0)

    def test_dropped_third_strike_with_runner_on_first(self):
        self.game.strikes = 2
        self._set_runners(first=self.runner1)
        self._apply('dropped_third_strike')
        # With runner on first, batter is out (unless 2 outs)
        self.assertEqual(self.game.outs, 1)

    def test_dropped_third_strike_with_two_outs(self):
        self.game.outs = 2
        self.game.strikes = 2
        self._set_runners(first=self.runner1)
        self._apply('dropped_third_strike')
        # With 2 outs, batter can run regardless
        self.assertEqual(self._get_runners()['first']['player_id'], self.batter.id)
        self.assertEqual(self.game.outs, 2)

    # === INFIELD FLY ===
    def test_infield_fly_automatic_out(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self.game.outs = 0
        self._apply('infield_fly')
        self.assertEqual(self.game.outs, 1)

    def test_infield_fly_runners_hold(self):
        self._set_runners(first=self.runner1, second=self.runner2)
        self._apply('infield_fly')
        self.assertIsNotNone(self._get_runners().get('first'))
        self.assertIsNotNone(self._get_runners().get('second'))

    # === INNING ADVANCEMENT ===
    def test_three_outs_advances_inning(self):
        self.game.outs = 2
        self._apply('out_ground')
        self.assertEqual(self.game.outs, 0)
        self.assertFalse(self.game.is_top_inning)

    def test_six_outs_returns_to_top(self):
        self.game.outs = 2
        self._apply('out_ground')  # 3 outs, now bottom of 1st
        self._apply('out_ground')  # 1 out bottom 1st
        self._apply('out_ground')  # 2 outs bottom 1st
        self._apply('out_ground')  # 3 outs bottom 1st
        self.assertTrue(self.game.is_top_inning)
        self.assertEqual(self.game.current_inning, 2)

    # === STAT COMPUTATION ===
    def test_compute_stats_batter_hits(self):
        from .api import compute_game_stats
        self._set_runners()
        self._apply('single')
        stats = compute_game_stats(self.game)
        batter_id = self.batter.id
        self.assertIn(batter_id, stats['batters'])

    def test_compute_stats_pitcher_counts(self):
        from .api import compute_game_stats
        self._apply('strike')
        stats = compute_game_stats(self.game)
        pitcher_id = self.runner2.id
        self.assertIn(pitcher_id, stats['pitchers'])
        self.assertEqual(stats['pitchers'][pitcher_id]['pitch_count'], 1)

    def test_compute_stats_inning_data(self):
        from .api import compute_game_stats
        self._set_runners(third=self.runner1)
        self._apply('homerun')
        stats = compute_game_stats(self.game)
        self.assertIn(1, stats['innings'])
        # Away team scored 2 (runner on 3rd + batter)
        self.assertEqual(stats['innings'][1]['away'], 2)


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
