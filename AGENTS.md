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
- `Game`/`TeamEvent` duality still unresolved (scheduling uses TeamEvent only).
- No API endpoints yet for the new scheduling features (Android client not updated).

## Commands
```bash
python manage.py test profiles.tests leagues.tests
python manage.py seed_data
python manage.py migrate
```


## Frontend Tech Stack
* **Framework:** React 19 + TypeScript 5
* **Build System:** Vite
* **Primary Styling:** Tailwind CSS v4 + Radix UI primitives

## CSS & Styling Style Guide

### Core Styling Rules
* **No Inline Styles:** Never use the `style={{}}` attribute for static styles.
* **No Arbitrary Values:** Avoid Tailwind arbitrary values like `top-[13px]` unless strictly necessary. Use design tokens instead.
* **Design Tokens Only:** All color choices must strictly use the design utility tokens defined in `src/styles/theme.css`.
* **Dark Mode Strategy:** Always append the `dark:` selector to utility classes. Verify background contrast ratios.
* **Vendor Prefixes:** Do not manually append vendor prefixes. Let PostCSS Autoprefixer handle it during the build process.

### React Component Styling Patterns
* **Conditional Layout Classes:** Always use the `clsx` or `tailwind-merge` utility library to merge dynamic class strings cleanly.
* **Component-Level Hierarchy:** Maintain standard component structures:
  * Structure: `src/components/Button/` containing `Button.tsx`, `Button.test.tsx`, and `index.ts`.
* **CSS Modules (If applicable):** Name files exactly as `[ComponentName].module.css` and import them as `styles` objects.

### Specific Styling Dos and Don'ts
* **DO:** Use Semantic HTML layouts (`<main>`, `<section>`, `<nav>`) instead of deeply nesting generic `<div>` blocks.
* **DO:** Rely on design token custom properties like `var(--color-primary-500)` rather than hardcoding static hex strings like `#3b82f6`.
* **DON'T:** Use custom element overrides or build raw HTML string tooltips if out-of-the-box system components already exist.
* **DON'T:** Mix styling paradigms. If a repository uses Tailwind CSS, do not randomly install or introduce `styled-components`.
