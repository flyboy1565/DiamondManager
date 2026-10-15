# DiamondManager — Agent Memory

## Project
Django 6.0 + django-ninja API backend for youth baseball/softball league management.
Three apps: `profiles`, `leagues`, `competition`.
Hierarchy: Organization → Season → Division → Team.

## Schema Notes
- **Season** has fields: `organization`(FK), `season`(CharField choices), `year`, `is_active`. NO `name` field. `name` is a `@property`.
- **Team** has fields: `division`(FK), `name`, `color`, `coaches`(M2M), `icon`, `access_code`(unique). NO `season` field. `season` is a `@property`.
- **Division** has fields: `season`(FK), `name`, `preset_type`, `notes`. Auto-increment int PK.
- **Profile** links User → Organization via FK on Profile, related_name=`members`.
- All FKs that are traversable in `select_related`/`prefetch_related`: `TeamMembership.team` → `Team.division` → `Division.season` → `Season.organization`.

## Known Broken Items (targeted June 28 2026 session)

### 1. profiles/tests.py — Model construction uses old schema
- Season created with `name=…` (should use `season=`, `year=`)
- Team created with `season=…` (should use `division=`)
- Missing Division creation before Team
- Fixed: ✅ (also fixed JWT auth for Ninja API calls, added division_name to roster tests, added send_mail to _process_coach_onboarding)

### 2. profiles/views.py:112 — select_related uses invalid path
- `team__season__organization` — `season` is a @property, not FK
- Fix: `team__division__season__organization` ✅

### 3. profiles/api.py:57,63,70 — Same select_related issue
- All three paths use `team__season` — fix to `team__division__season` ✅

### 4. profiles/services.py:9 — user.organization_set doesn't exist
- Dead code, but fix to use Profile query ✅

### 5. seed_data.py — Full rewrite needed (old schema)
- Broken Season/Team creation, missing Divisions, no access_code ✅

## Completed (July 12 2026 Session)
- `access_code=''` fix in `CreateGameView` (profiles/views.py:632) — now generates unique 6-char code ✅
- Player API cleanup: `PlayerCreateSchema.team_id` → Optional, `update_player` explicit field setting, `jersey_number` handled via `PlayerMembership`, `team.season` → `team.division.season` in all profiles files ✅
- Squashed duplicate migrations: `profiles/0003+0004` (UUID flip-flop), `leagues/0012+0014` (add/remove locations) ✅
- Live scoring endpoints: Start Game, End Game, enriched scoreboard (107 tests total, +15 new) ✅
- Game↔TeamEvent bridge: `game` FK on `TeamEvent`, auto-create Game during admin scheduling ✅
- **Scheduling API endpoints (PARTIAL):** 8 new endpoints implemented (TeamEvent CRUD, weekly status, schedule game, location conflicts, org settings). 14 of 15 tests passing. One test (`test_location_conflicts_detected`) fails — timezone/date comparison issue in the location conflicts endpoint's `ref_dt` construction.

### Phase 6: Audio Notifications & Android Polish (July 13 2026)
- Installed `edge-tts` Python package for TTS (voice: `en-GB-ThomasNeural`, pitch: `-15Hz`, rate: `-8%`)
- Switched smart-voice-notify to `"both"` mode — sound + TTS voice immediately on task completion
- Fixed Android `AdminScheduleScreen`:
  - `uiState.getWeekEnd()` → `viewModel.getWeekEnd()` (unresolved reference bug)
  - Added `@OptIn(ExperimentalMaterial3Api::class)` to `SeasonPicker`, `DivisionPicker`, `TeamDropdown`, `EventTypeSelector`
- Added Enter/Done key action on password field in `LoginScreen` to trigger login submit
- Committed live scoring APIs, scheduling API endpoints, schema fixes (14 files, +1231 lines, `da31c39`)

## Android Client (`/mnt/c/Users/flybo/AndroidStudioProjects/DiamondManager`)

**Stack:** Kotlin, Jetpack Compose, Retrofit + OkHttp + kotlinx.serialization, DataStore.

**Current state:** 5 of ~38 API endpoints are called (login, my-teams, roster, profile, team-schedule). GameDay/Lineup/Scoreboard/Rulebook screens now fetch real data. Profile screen shows full profile from API.

### Phase 1: Fix + Profile (Done ✅)
- `TeamLink.season` → `TeamLink.division` + added `DivisionLink` model
- `DashboardViewModel` mapping fixed to use `team.division.season.name`
- `TeamCard.kt` navigation fixed (Roster + GameDay use `Screen.*.createRoute()`)
- `Profile`, `UserProfile` models added + `GET /profiles/me` endpoint wired
- `ProfileViewModel` created, `ProfileScreen` shows name/email/role/phone from API

### Phase 2: Game Day (Done ✅)
- Backend: `GET /api/competition/team/{team_id}/schedule` added
- Android: `GameData`, `LineupEntry`, `Rule` models added
- Android: `GameDayViewModel`, `LineupViewModel`, `ScoreboardViewModel`, `RulebookViewModel` created
- Android: `GameDayScreen` fetches schedule, `LineupScreen`/`ScoreboardScreen` use `gameId`
- Android: `RulebookScreen` fetches rules from API
- `Screen.Lineup`/`Scoreboard` routes changed from `{teamId}` to `{gameId}`

### Phase 3: Invitations (Done ✅)
- `JoinTeamRequest`, `VerifyInvitationResponse`, `AcceptInvitationRequest`, `SimpleResponse` models added
- `GET /profiles/invitations/verify/{token}`, `POST /profiles/invitations/accept`, `POST /profiles/teams/join-as-follower` endpoints wired
- `Screen.JoinByCode` route + `JoinByCodeScreen`: user enters access code to join team as follower
- `Screen.AcceptInvitation` route + `InvitationAcceptScreen`: verifies token, shows details, handles new/existing user flow with registration
- `JoinByCodeViewModel`, `InvitationAcceptViewModel` created
- "Join Team" key icon added to Dashboard top bar

### Phase 4: Team Management (Done ✅)
- `PlayerCreateRequest`, `PlayerUpdateRequest` models added
- `POST /profiles/players`, `PUT /profiles/players/{id}`, `DELETE /profiles/players/{id}`, `GET /profiles/my-kids` endpoints wired
- `Screen.AddPlayer` route + `AddPlayerScreen`: form to add player to team (name + jersey)
- `Screen.PlayerDetail` route + `PlayerDetailScreen`: view/edit/delete player, with delete confirmation dialog
- `Screen.MyKids` route + `MyKidsScreen`: list of players where user is guardian
- FAB on RosterScreen navigates to AddPlayer; PlayerCard taps navigate to PlayerDetail
- ProfileScreen has "My Kids" button linking to the kids list
- `AddPlayerViewModel`, `PlayerDetailViewModel`, `MyKidsViewModel` created

### Phase 5+: Live Scoring APIs (July 12 2026 — Done ✅)
- `POST /games/{game_id}/start` — initializes scoring_data, sets is_live=True (TDD: 3 tests)
- `POST /games/{game_id}/end` — sets is_completed=True, accepts optional final scores (TDD: 4 tests)
- `GET /games/{game_id}/scoreboard` — enriched to return `GameScoreDetailSchema` with scoring_data (runners, pitchers, play-by-play)
- **Game↔TeamEvent bridge**: added nullable `game` FK on `TeamEvent` model. `AdminScheduleView.form_valid` now creates a `Game` alongside paired TeamEvents for GAME/SCRIMMAGE/TOURNAMENT/PLAYOFF event types.
- `competition/migrations/0011_teamevent_game.py` — new migration for the bridge FK

### Phase 5++: Scheduling API Endpoints (July 12 2026 — Done ✅)
8 new endpoints implemented in `competition/api.py`:
- `GET /teams/{team_id}/events` — list team events (all types, not just Games)
- `POST /teams/{team_id}/events` — create team event with weekly limit enforcement
- `PUT /events/{event_id}` — update event (admin or creator)
- `DELETE /events/{event_id}` — delete event (admin or creator)
- `GET /divisions/{division_id}/weekly-status?year=&month=&day=` — per-team event counts
- `POST /admin/schedule-game` — paired TeamEvent creation with limit + game creation
- `GET /location-conflicts?location=&date=&division_id=` — conflict detection
- `GET/PUT /organizations/{org_id}/settings` — org max_events_per_team_per_week

### Phase 5+++: Android Client — Scheduling Parity (Done ✅)
- `AdminScheduleViewModel.kt` — rewritten with full scheduling support (weekly status, schedule game, location conflicts, week navigation, org settings)
- `AdminScheduleScreen.kt` — 9 composable sections (season/division pickers, week nav, team counts with progress bars, schedule game form, location conflicts, org settings editor)

## YouTube Streaming (Backend + Android)

Self-hosted SRT→YouTube live pipeline. Branch `feature/youtube-streaming`.

**Data path:** Larix (SRT) → SRS :10080/udp → [relay-agent: ffmpeg] → YouTube RTMP ingest.
SRT URL: `srt://<relay-host>:10080?streamid=live/game-<game_id>`.

### Backend
- `competition/models.py:Game` — stream fields: `stream_status` (`idle|preparing|live|ended|error`), `youtube_video_id`, `youtube_broadcast_id`, `youtube_stream_id`, `srt_stream_id`, `stream_started_at`, `stream_ended_at`, `is_streaming_enabled`, `stream_error`.
- `leagues/models.py:OrganizationYouTubeConfig` — per-org channel + OAuth creds; `youtube_client_secret`/`youtube_refresh_token` use `EncryptedTextField` (`leagues/fields.py`, Fernet; key = `STREAMING_ENCRYPTION_KEY` or `SECRET_KEY`).
- `competition/streaming/youtube.py:YouTubeLiveService` — `create_broadcast`/`create_stream`/`bind_broadcast`/`transition_broadcast`/`get_stream_health`/`complete_broadcast`/`delete_*`; falls back to `YOUTUBE_FALLBACK_*` settings when org has no config.
- `competition/streaming/relay.py` — stdlib client for the relay agent (`start_relay`/`stop_relay`/`relay_status`/`agent_health`).
- `competition/streaming/oauth.py` — per-org channel onboarding (signed single-use state via cache, code exchange, channel fetch).
- `competition/management/commands/reconcile_streams.py` — polls `preparing` games, promotes to `live` when YouTube health is `active`, else `error` after `STREAM_RECONCILE_TIMEOUT` (default 180s). Run via cron/systemd-timer (documented in `ops/streaming/README.md`).
- **Endpoints** (`competition/api.py`): `POST /games/{id}/stream/start` (idempotent while `preparing`/`live`), `POST /games/{id}/stream/stop`, `GET /games/{id}/stream/status`; `GET/PUT /organizations/{id}/youtube-config` (admin-only; secrets masked as `********`, PUT body auto-encrypts via the model field); `GET /organizations/{id}/youtube/oauth/start`, public `GET /youtube/oauth/callback`.
- Admin: stream fields/filters/actions on `GameAdmin`; `OrganizationYouTubeConfigAdmin`.
- Tests: `competition/tests.py` — ScoringEngine, RelayClient, YouTubeService, StreamLifecycle, ReconcileStreamsCommand, YouTubeOAuthClient/API, StreamingSecretEncryption, YouTubeConfigAPI.

### Android
- API: `startStream`/`stopStream`/`getStreamStatus`, `getYoutubeConfig`, `getYoutubeOAuthStart`.
- Deep link `diamondmanager://youtube` (MainActivity `singleTask` + VIEW/BROWSABLE intent-filter); `data/OAuthDeepLink.kt` parses the OAuth callback redirect.
- `ui/screens/admin/AdminStreamingScreen.kt` + `AdminStreamingViewModel.kt` — connect/reconnect a YouTube channel; opened from `AdminDashboardScreen`.
- `GameDayScreen`/`GameDayViewModel` surface `stream_error` and stream status.

### Ops
- `ops/streaming/` — `docker-compose.yml` (SRS + relay-agent), `srs.conf*`, `relay-agent/` (FastAPI+ffmpeg), `.env.example`, `README.md`.
- Caveats: Docker CLI not available in this WSL distro (can't validate compose); no JDK in WSL (Android builds verified in Android Studio only).

### Note
- `GET /api/competition/team|season/{id}/schedule`, `GET /api/competition/games/{id}`, `GET/POST/PUT/DELETE /api/competition/games/{id}/lineup[/entries|/clone]`, and `GET /api/leagues/organizations/{id}/facilities` were removed in commit `6321fce`; they have been **restored** on `feature/youtube-streaming` (tests: `ScheduleLineupAPITestCase`). `facilities` also still exists as a Django view (`profiles/views.py:FacilityManageView`).
- Pre-existing gap (not introduced by the restore): `PUT/DELETE /games/{id}/lineup/entries/{entry_id}` have no `_can_score` check (matches the pre-`6321fce` original).
- `GET /api/competition/games/{id}/stream` (SSE push) that Android `GameEventService` calls does **not** exist yet; scoreboard falls back to its snapshot (SSE error is swallowed).

### On Deck (not yet started)
- `clone_divisions` missing `preset_type` in defaults — **Fixed ✅**
- Live scoring future work:
  - WebSocket/SSE for real-time spectator push (see `config/asgi.py`)
  - Android `ScoreboardScreen` — expand from 4 pitch types to 30+ (Ball/Strike/Foul/Hit → singles, doubles, HR, steals, errors, etc.)
  - Android `RecordPitchRequest` — add `extra` field for complex plays
  - `PlayerGameStat` model — wire up post-game population from `compute_game_stats()`
  - `GameSchema` enrichment — expose `scoring_data` fields on all game endpoints, not just scoreboard
  - Explicit "start first batter" on Start Game (currently initializes scoring_data but doesn't set first batter)

## Theming System (CSS Variables — July 3 2026 Session)
- Replaced old class-override theme system (`.bg-slate-900`, `.text-white` per-theme overrides) with CSS custom properties design tokens.
- Defined `--slate-50` through `--slate-950` and `--white` on `:root` (default Slate dark).
- Each theme (Light/Forest/Ocean) redefines variables rather than overriding classes.
- Templates now use Tailwind arbitrary values: `bg-[var(--slate-900)]`, `text-[var(--white)]`, `border-[var(--slate-700)]`, `divide-[var(--slate-700)]`, `from-[var(--slate-800)]`, `to-[var(--slate-950)]`, `placeholder-[var(--slate-500)]`.
- Opacity variants: `--slate-700-30`, `--slate-700-50`, `--slate-800-80` for `bg-slate-700/30`, `hover:bg-slate-700/30`, `bg-slate-700/50`, `border-slate-800/80`.
- `<select>` option styling uses `var(--slate-800)`/`var(--slate-100)`.
- JS injection scripts in create_season/create_team/create_org/roster_onboarding updated to add CSS variable classes.
- All 30 tests pass (10 profiles + 20 competition).
- `base.html:8-72` — CSS definitions; `base.html:201-215` — theme picker JS (unchanged).

## Weekly Scheduling System (July 4 2026 Session)

### New Fields
- **Organization**: `max_events_per_team_per_week` (PositiveIntegerField, default=10) — max countable events per team in a Mon-Sun week.
- **TeamEvent**: `counts_against_limit` (BooleanField, default=True) — if unchecked, event doesn't count toward weekly limit. Default: True for team events, False for division/org events.

### Scheduling Logic (`competition/scheduling.py`)
- `get_week_range(reference_date=None)` → `(monday_start, sunday_end)` — Mon-Sun week window.
- `team_event_count(team, week_start, week_end)` → int — counts TeamEvents where team is primary or opponent, `counts_against_limit=True`, status != CANCELLED.
- `team_can_add_events(team, count=1, week_start, week_end)` → `(allowed, current_count, max_allowed)`.

### Admin Schedule View
- **URL**: `GET/POST /competition/admin/schedule/<int:division_id>/` (name: `admin_schedule`)
- **View**: `competition/views.py:AdminScheduleView` — FormView with `ScheduleGameForm`.
- **Template**: `competition/templates/competition/admin/schedule.html`
- Shows: week navigation, team event counts with color-coded progress bars, scheduling form (home/away team, type, date/time, location, counts_against_limit checkbox), existing week events list.
- On submit: validates limits for both teams (blocks with error if either would exceed), creates two TeamEvent objects (one per team) linked via `opponent_team`.

### Limit Guards
- `CreateTeamEventView.form_valid` — blocks + error if team at limit (for countable events).
- `CreateDivisionEventView.form_valid` — warns but allows if teams at limit.
- `CreateOrganizationEventView.form_valid` — warns but allows if teams at limit.

### Form Changes
- `ScheduleGameForm` — new form for admin scheduling (non-ModelForm).
- `TeamEventForm` — added `counts_against_limit` field.
- `DivisionEventForm` — added `counts_against_limit` field (initial=False).
- `OrganizationEventForm` — added `counts_against_limit` field (initial=False).

### Admin Links
- `season_detail.html` — "Schedule Games" button per division (admin only).
- `schedule_event.html` — "Schedule Games" button per division.

### Organization Settings Page
- **URL**: `/profiles/admin/settings/` (name: `org_settings`)
- **View**: `DivisionPositionsView` in `profiles/views.py` — handles both org settings + division positions.
- **Template**: `profiles/admin/division_positions.html`
- Sections:
  - **League Settings**: `max_events_per_team_per_week` number input.
  - **Division Positions**: per-division checkbox grids (same as before), now with `action=update_positions` hidden field.
- Permissions: `ORG_OWNER` / `ORG_ADMIN` only for all POST actions.
- Old URL `/admin/positions/` redirects permanently to `/admin/settings/`.

### Django Admin
- `OrganizationAdmin` in `leagues/admin.py` — custom fieldset with "Scheduling Limits" section.

### Known Issues
- `seed_data` fails on re-run (UNIQUE constraint on username) — pre-existing, not from this session.
- `Game`/`TeamEvent` duality partially resolved (bridge FK added, but TeamEvent still has its own scoring fields that duplicate Game's).

## Commands
```bash
python manage.py test profiles.tests leagues.tests competition.tests
python manage.py seed_data
python manage.py migrate
```

