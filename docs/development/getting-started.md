# Getting Started (Local Development)

How to run the DiamondManager backend and the Android client on your machine and
connect them.

## Prerequisites

| Tool | Version used | Notes |
| --- | --- | --- |
| Python | 3.12 | Backend runtime (`.venv` in this repo is 3.12.3) |
| Git | any recent | |
| Android Studio | recent | Kotlin + Jetpack Compose client; brings its own JDK |
| JDK | via Android Studio | No JDK is installed in WSL, so Android builds happen in Android Studio |

The backend uses SQLite (`db.sqlite3`) in development — no database server needed.

## 1. Backend setup

```bash
# from the repo root
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver 0.0.0.0:8321
```

Run on **port 8321**: the Android client's `BASE_URL` points at it (see below).
Binding `0.0.0.0` makes it reachable from the emulator/device.

> **Dev-only dependencies are not pinned in `requirements.txt`.** `seed_data`
> needs `faker`, and tests need `pytest` / `pytest-django`. If a command below
> fails with a missing module, install them:
>
> ```bash
> pip install faker pytest pytest-django
> ```

### URLs once running

| What | URL |
| --- | --- |
| API docs (Swagger UI) | `http://localhost:8321/api/docs` |
| OpenAPI schema | `http://localhost:8321/api/openapi.json` |
| Web portal login | `http://localhost:8321/profiles/portal/login/` |
| Django admin | `http://localhost:8321/admin/` |
| Landing portal | `http://localhost:8321/` |

Log in with the accounts in [Development Accounts](accounts.md). For a fresh DB,
create your own admin with `python manage.py createsuperuser`.

### Optional: sample data

```bash
python manage.py seed_data
```

Generates sample orgs, seasons, divisions, teams, players, games, and lineups
(all seeded users share the password `password123`). **Do not run it twice** —
it collides on the users' unique username constraint. See
[Development Accounts](accounts.md) for the full list.

## 2. Android client

The Android project lives in a separate directory (e.g.
`/mnt/c/Users/flybo/AndroidStudioProjects/DiamondManager`).

1. Open the project in **Android Studio** and let Gradle sync.
2. Configure the backend URL in
   `app/src/main/java/com/example/diamondmanager/data/api/DiamondManagerAPIService.kt`:
   ```kotlin
   const val BASE_URL = "http://10.0.2.2:8321/api/"
   ```
3. Run on an emulator. `10.0.2.2` is the emulator's alias for the **host
   machine**, so the emulator reaches the backend on the host's `:8321`.

### Networking notes

- **Emulator:** `10.0.2.2:8321` works out of the box (already in Django's
  `ALLOWED_HOSTS`).
- **Physical device:** use the host machine's LAN IP (e.g.
  `http://192.168.1.50:8321/api/`), add that IP to `ALLOWED_HOSTS` in
  `config/settings.py`, and make sure the phone and host are on the same network.
- **Cleartext HTTP:** allowed via `android:usesCleartextTraffic="true"` in the
  manifest; the app expects `http://`, not `https://`, in dev.

## 3. Common commands

```bash
# Run the backend
python manage.py runserver 0.0.0.0:8321

# Apply/serve migrations
python manage.py makemigrations
python manage.py migrate

# Tests (all three apps)
python manage.py test profiles.tests leagues.tests competition.tests

# Tests (pytest — configured via pytest.ini; runs everything)
pytest -q

# Tests (a single class or file)
pytest competition/tests.py::ScheduleLineupAPITestCase -q

# Django admin user
python manage.py createsuperuser
```

## 4. What works locally vs. what needs extra setup

**Works with just the backend running:**

- Login, dashboard / my-teams, roster, profile
- Team & season schedule, GameDay, lineup
- Invitations / join-by-code, admin screens (teams, players, schedule,
  positions, volunteers)
- Live scoring: start / end game, scoreboard snapshot

**Needs additional setup:**

- **Live streaming** (`/games/{id}/stream/*`) requires the self-hosted SRS relay
  and YouTube credentials — see `ops/streaming/` and the
  [streaming architecture doc](../streaming/youth-baseball-streaming-architecture.md).
  It will not work against a plain local backend.
- **Real-time scoreboard push:** the Android client subscribes to an SSE
  endpoint (`GET /api/competition/games/{id}/stream`) that the backend does not
  implement yet. The scoreboard still loads its initial snapshot; it just won't
  live-refresh.

## 5. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| App shows network errors on emulator | Backend not running, or not bound to `0.0.0.0:8321` |
| `ModuleNotFoundError: faker` (or pytest) | Install dev deps: `pip install faker pytest pytest-django` |
| `seed_data` fails with UNIQUE constraint | DB already seeded — reset it (see [accounts](accounts.md#resetting-the-database)) |
| Django "Invalid HTTP_HOST header" | Add the device's host/IP to `ALLOWED_HOSTS` in `config/settings.py` |
| Android won't build in WSL | Build in Android Studio (no JDK in WSL) |
