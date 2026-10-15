# Development Accounts

Reference for the accounts available in the **local development database**
(`db.sqlite3`). Use these to log into the web portal, the Django admin, the API,
and the Android client while developing.

> These are development credentials only. Never reuse them in production, and do
> not commit real secrets.

## Where you can log in

| Surface | URL | Notes |
| --- | --- | --- |
| Web portal | `http://localhost:8321/profiles/portal/login/` | Session login for coaches/org owners |
| Django admin | `http://localhost:8321/admin/` | Requires `is_staff` (superuser) |
| API (JWT) | `POST http://localhost:8321/api/token/pair` | Body `{"username": "...", "password": "..."}` → `access` / `refresh` |
| Android client | Login screen | Uses the API above via `BASE_URL` (emulator: `http://10.0.2.2:8321/api/`) |

Start the backend on port **8321** so the Android client can reach it:

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8321
```

## Hand-created accounts

These were created manually for local testing and are the most useful logins
because they are linked to a real organization.

| Username | Password | Role | Organization | Email | Name |
| --- | --- | --- | --- | --- | --- |
| `flyboy1565` | _not documented_ | superuser (`is_staff`, `is_superuser`) | — | — | — |
| `jholstine` | _not documented_ | `ORG_OWNER` | Catus Wren Little League | flyboy1565@gmail.com | John Holstine |
| `owner` | `password123` | `ORG_OWNER` | Canyon Creek Little League | owner@example.com | — |
| `coach_mike` | `password123` | `COACH` | Canyon Creek Little League | mike.j@email.com | Mike Johnson |
| `scorer` | `password123` | `SCORER` | Canyon Creek Little League | scorer@test.com | Official Scorer |
| `debug` | `password123` | `FOLLOWER` | — | — | — |

`owner`, `coach_mike`, `scorer`, and `debug` use the shared dev password
`password123`. The passwords for `flyboy1565` (Django admin) and `jholstine`
are managed separately and intentionally not documented here. To set or reset
any of them:

```bash
# interactive
python manage.py changepassword owner

# or non-interactive, for a single account
python manage.py shell -c "from django.contrib.auth.models import User; u=User.objects.get(username='owner'); u.set_password('password123'); u.save()"
```

Use `flyboy1565` for the Django admin (reset it the same way if needed).

## Seeded accounts

`python manage.py seed_data` generates a batch of sample users (password
`password123`) plus orgs, seasons, divisions, teams, players, games, and lineups.

- **Password:** `password123` (all seeded users)
- **Usernames are deterministic** — `seed_data` uses `Faker.seed(42)` / `random.seed(42)`, so the same list is produced on every fresh seed.
- **Not linked to an organization:** seeded users have `profile.organization = None`; their access is via **TeamMembership** (coach/parent on specific teams).
- **Do not re-run blindly:** re-running `seed_data` against an already-seeded DB fails on the users' `UNIQUE` username constraint. Drop/recreate the DB or skip the command.

| Username | Role |
| --- | --- |
| `zlawrence_0` | `ORG_OWNER` |
| `maria95_1` | `COACH` |
| `lynchgeorge_2` | `COACH` |
| `donald88_3` | `ORG_OWNER` |
| `dcarlson_4` | `PARENT` |
| `kathryn88_5` | `COACH` |
| `ibrandt_6` | `COACH` |
| `carlosjohnson_7` | `COACH` |
| `nuneztracey_8` | `ORG_OWNER` |
| `gabrieltucker_9` | `COACH` |
| `williamsthomas_10` | `ORG_OWNER` |
| `sarah35_11` | `ORG_OWNER` |
| `justin78_12` | `ORG_OWNER` |
| `rebecca01_13` | `COACH` |
| `tanderson_14` | `ORG_OWNER` |
| `erik16_15` | `PARENT` |
| `sheila14_16` | `COACH` |
| `qjones_17` | `COACH` |
| `jason99_18` | `COACH` |
| `traceycarr_19` | `COACH` |

## Team access codes (Join-by-Code)

Used by the *Join Team by Code* flow (follower) and roster onboarding. Codes
belong to **Canyon Creek Little League** (Fall 2026 season) in the current dev DB.

| Team | Division | Access code |
| --- | --- | --- |
| Canyon Creek Eagles | Majors | `LWIBMX` |
| Canyon Creek Thunder | Majors | `S8P0MF` |
| Canyon Creek Mustangs | Majors | `5XGMJQ` |
| DevBot | Tee Ball | `7b5a151a2046` |
| LittlePine | Tee Ball | `d26a0f7f35be` |

> `seed_data` generates **random** access codes (`uuid4().hex[:8].upper()`); the
> codes above are for the hand-created Canyon Creek teams and stay stable unless
> the rows are recreated.

## Role reference

`Profile.role` values (`profiles/models.py`):

| Role | Meaning |
| --- | --- |
| `ADMIN` | Global admin |
| `ORG_OWNER` | Organization owner |
| `ORG_ADMIN` | Organization admin |
| `MANAGER` | Team manager |
| `COACH` | Team coach |
| `SCORER` | Official scorer |
| `PARENT` | Player parent |
| `FOLLOWER` | Player follower (default) |

Scoring and lineup endpoints require a scoring-capable role
(`ADMIN`, `ORG_OWNER`, `ORG_ADMIN`, `SCORER`, `COACH`, `MANAGER`).

## Creating a new development account

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User

u = User.objects.create_user(username="dev_coach", password="password123",
                             email="dev_coach@example.com")
u.profile.role = "COACH"
u.save()
# Optionally link to an organization:
from leagues.models import Organization
u.profile.organization = Organization.objects.get(name="Canyon Creek Little League")
u.profile.save()
```

A `Profile` is created automatically for every new `User` via a `post_save`
signal (`profiles/models.py`).

## Resetting the database

To start from a clean state and reseed:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py seed_data
```
