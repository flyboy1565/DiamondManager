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

## Not in Scope This Session
- `clone_divisions` missing `preset_type` in defaults (leagues/api.py:115)
- `access_code=''` opponent Team creation (profiles/views.py:463)
- Game/TeamEvent duality
- Missing tests in competition/
- Duplicate migrations
- Android client — data contract alignment (see Android section)

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

### Phase 5+ on Deck
- Live scoring (`PATCH live-update`)
- Clean up `Player.team_id` field
- `clone_divisions` missing `preset_type` in defaults (leagues/api.py:115)
- `access_code=''` opponent Team creation (profiles/views.py:463)
- Game/TeamEvent duality
- Missing tests in competition/
- Duplicate migrations

## Commands
```bash
python manage.py test profiles.tests leagues.tests
python manage.py seed_data
python manage.py migrate
```
