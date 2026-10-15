# Deployment & Ops

Operational guide for deploying the DiamondManager backend and, in particular,
the **self-hosted live-streaming pipeline**. For the conceptual design, see
[Youth Baseball Streaming Architecture](../streaming/youth-baseball-streaming-architecture.md).

## Components

| Component | Role | Where |
| --- | --- | --- |
| Django backend | API, orchestration, YouTube API calls, reconciler | App server |
| SRS (`ossrs/srs:5`) | Accepts SRT from field devices; serves RTMP internally | Relay host (Docker) |
| relay-agent | FastAPI + ffmpeg; per-game bridge `SRS → YouTube RTMP` | Relay host (Docker) |
| YouTube Live API | Broadcast/stream creation, health, transitions | Google Cloud |

Data path:

```
Larix (SRT) --> SRS :10080/udp --> [relay-agent: ffmpeg] --> YouTube RTMP ingest
```

SRT URL handed to field devices: `srt://<relay-host>:10080?streamid=live/game-<game_id>`.

The reference ops files live in [`ops/streaming/`](../../ops/streaming/) and its
[README](../../ops/streaming/README.md).

## Environment variables

All are read from the environment in `config/settings.py` (defaults shown).
Set them in the app server's environment / process manager.

### Core YouTube fallback channel

Used when an organization has no `OrganizationYouTubeConfig` (or it is disabled).

| Variable | Default | Purpose |
| --- | --- | --- |
| `STREAMING_SERVER_SRT_URL_DEFAULT` | `''` | Default SRT base URL returned to clients |
| `YOUTUBE_FALLBACK_CHANNEL_ID` | `''` | Fallback channel |
| `YOUTUBE_FALLBACK_CLIENT_ID` | `''` | OAuth client id |
| `YOUTUBE_FALLBACK_CLIENT_SECRET` | `''` | OAuth client secret |
| `YOUTUBE_FALLBACK_REFRESH_TOKEN` | `''` | Long-lived refresh token |
| `YOUTUBE_FALLBACK_PRIVACY` | `unlisted` | `public` / `unlisted` / `private` |

### Relay control agent (Django → agent)

| Variable | Default | Purpose |
| --- | --- | --- |
| `STREAMING_RELAY_ENABLED` | `False` | Master switch; must be truthy to call the agent |
| `STREAMING_RELAY_AGENT_URL` | `http://127.0.0.1:8088` | Agent base URL |
| `STREAMING_RELAY_AGENT_TOKEN` | `''` | Shared secret (sent as `X-Relay-Token`) |
| `STREAMING_RELAY_TIMEOUT` | `10` | HTTP timeout (seconds) |

> The agent container reads the same secret as **`RELAY_TOKEN`**. Set
> `STREAMING_RELAY_AGENT_TOKEN` on Django and `RELAY_TOKEN` on the agent to the
> **same value**.

### Reconciler

| Variable | Default | Purpose |
| --- | --- | --- |
| `STREAM_RECONCILE_TIMEOUT` | `180` | Seconds a game may stay `preparing` before it's marked `error` |

### Per-org OAuth onboarding

| Variable | Default | Purpose |
| --- | --- | --- |
| `YOUTUBE_OAUTH_CLIENT_ID` | `''` | Google OAuth 2.0 (Web) client id |
| `YOUTUBE_OAUTH_CLIENT_SECRET` | `''` | Google OAuth client secret |
| `YOUTUBE_OAUTH_REDIRECT_URI` | `''` | Must match Google Console, e.g. `https://<backend>/api/competition/youtube/oauth/callback` |
| `YOUTUBE_OAUTH_SUCCESS_REDIRECT` | `''` | Browser redirect after success (e.g. the app deep link) |
| `YOUTUBE_OAUTH_ERROR_REDIRECT` | `''` | Browser redirect on failure |

### Secret encryption

| Variable | Default | Purpose |
| --- | --- | --- |
| `STREAMING_ENCRYPTION_KEY` | `''` (falls back to `SECRET_KEY`) | Fernet key material for `youtube_client_secret` / `youtube_refresh_token` at rest |

> **Keep `STREAMING_ENCRYPTION_KEY` stable and secret.** Changing it makes
> existing ciphertext unreadable (per-org YouTube credentials would need to be
> re-entered). Set this in production rather than relying on `SECRET_KEY`.

## Deploying the relay host

`ops/streaming/docker-compose.yml` runs SRS and the relay-agent.

```bash
cd ops/streaming
cp .env.example .env          # set RELAY_TOKEN, SRS_RTMP_BASE, YouTube keys
cp srs.conf.template srs.conf # already provided as srs.conf in-repo
docker compose up -d
```

Ports:

| Port | Proto | Purpose |
| --- | --- | --- |
| `10080` | udp | SRT ingest (open to field devices) |
| `1935` | tcp | RTMP (internal SRS ⇄ agent) |
| `8080` | tcp | SRS HTTP API / dashboard |
| `8088` | tcp | Relay control API (reachable from Django) |

Then point the backend at the agent:

```
STREAMING_RELAY_ENABLED=True
STREAMING_RELAY_AGENT_URL=http://<relay-host>:8088
STREAMING_RELAY_AGENT_TOKEN=<same as RELAY_TOKEN>
```

Relay agent API (all require `X-Relay-Token`): `GET /health`,
`POST /relay/start`, `POST /relay/stop`, `GET /relay/{stream_id}`.

## Reconciler scheduling

`stream/start` sets a game to `preparing`. A scheduled `reconcile_streams` run
polls YouTube health and, when the stream is `active`, transitions the broadcast
to `live` and flips the game to `live`; games with no signal within
`STREAM_RECONCILE_TIMEOUT` become `error`.

**cron (every 30s):**

```cron
* * * * * for i in 0 30; do python manage.py reconcile_streams; sleep 30; done
```

**systemd timer** (`reconcile-streams.service`):

```ini
[Unit]
Description=Reconcile DiamondManager YouTube streams

[Service]
Type=oneshot
WorkingDirectory=/srv/diamondmanager
ExecStart=/srv/diamondmanager/.venv/bin/python manage.py reconcile_streams
```

`reconcile-streams.timer`:

```ini
[Unit]
Description=Run stream reconciler every 30s

[Timer]
OnBootSec=30
OnUnitActiveSec=30
AccuracySec=1

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now reconcile-streams.timer
```

## Stream lifecycle

1. `POST /api/competition/games/{id}/stream/start` — creates the YouTube
   broadcast + stream, binds them, starts the relay agent, sets `preparing`.
   Idempotent while `preparing`/`live`.
2. Reconciler promotes `preparing → live` (or `error` on timeout).
3. `POST /api/competition/games/{id}/stream/stop` — stops the agent, completes
   the broadcast, sets `ended`.
4. `GET /api/competition/games/{id}/stream/status` — current state/health.

Organizations can connect their own channel via OAuth
(`/organizations/{id}/youtube/oauth/start`) — see the ops README for the flow.

## Django production checklist

The repo ships dev defaults (`DEBUG=True`, a hardcoded `SECRET_KEY`, SQLite).
Before a real deployment:

- Set `DEBUG=False` and a strong, secret `SECRET_KEY` (env var, not the repo).
- Set `ALLOWED_HOSTS` to your real hostnames.
- Use a production database (Postgres) instead of SQLite.
- Run behind a real web server (`gunicorn`/`uvicorn` + reverse proxy); serve
  static files properly (`STATIC_ROOT` is not set in dev).
- Terminate TLS; the OAuth redirect URI must be HTTPS and match Google Console.
- Set `STREAMING_ENCRYPTION_KEY` and keep it stable.
- Run `reconcile_streams` on a timer (above).

## Known caveats (POC)

- **Single relay, manual Go Live** for v1 — no multi-relay autoscaling.
- **No overlay/scorebug** is burned in yet (architecture doc describes the
  target design).
- The Docker compose/agent has **not been validated in WSL** (no Docker CLI);
  verify on the relay host.
- The Android client's live scoreboard SSE endpoint
  (`GET /api/competition/games/{id}/stream`) is **not implemented**; the
  scoreboard falls back to its initial snapshot.
