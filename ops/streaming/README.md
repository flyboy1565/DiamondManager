# Streaming Relay (POC)

## Overview
For POC we use a single SRS relay ingesting SRT from field devices (Larix). Backend creates YouTube broadcast/stream per game (manual Go Live) and returns SRT config. A small **relay control agent** (FFmpeg) bridges SRS -> YouTube RTMP per game.

Data path:
```
Larix (SRT) --> SRS :10080/udp --> [relay-agent: ffmpeg] --> YouTube RTMP ingest
```

## Components
- `srs` — SRS 5 media server. SRT ingest on `10080/udp`, RTMP on `1935`, dashboard `8080`.
- `relay-agent` — FastAPI + ffmpeg. Django calls it to start/stop a per-game bridge
  that pulls `rtmp://srs:1935/live/game-<id>` and pushes to the YouTube ingest URL/key.

## Quick Start
1. Copy `.env.example` to `.env` and fill values (set `RELAY_TOKEN`).
2. Copy `srs.conf.template` to `srs.conf`.
3. `docker compose up -d`
4. Open UDP `10080` on firewall/router for SRT; ensure server has public IP/domain if remote.
5. Point Django at the agent: set `STREAMING_RELAY_ENABLED=True`,
   `STREAMING_RELAY_AGENT_URL=http://<host>:8088`, `STREAMING_RELAY_AGENT_TOKEN=<RELAY_TOKEN>`.

## Relay Agent API
All endpoints require header `X-Relay-Token: <RELAY_TOKEN>`.
- `GET /health`
- `POST /relay/start` `{stream_id, ingest_url, stream_key, source_url?}`
- `POST /relay/stop` `{stream_id}`
- `GET /relay/{stream_id:path}`

## Larix Config
Full SRT URL: `srt://<relay-host>:10080?streamid=live/game-<game_id>`

## Stream Lifecycle
1. `POST /api/competition/games/{id}/stream/start` — creates YouTube broadcast + stream,
   binds them, starts the relay agent, and sets the game to `preparing`.
2. A cron/loop runs `python manage.py reconcile_streams` — polls YouTube stream health;
   once `active` it transitions the broadcast to `live` and flips the game to `live`.
   Games that never produce a signal within `STREAM_RECONCILE_TIMEOUT` seconds are
   marked `error`.
3. `POST /api/competition/games/{id}/stream/stop` — stops the relay agent, completes the
   broadcast, and sets the game to `ended`.

Run the reconciler on a schedule, e.g. every 30s:
```
* * * * * for i in 0 30; do python manage.py reconcile_streams; sleep 30; done
```

## YouTube Config Per Org
Create `OrganizationYouTubeConfig` in Django admin or via API later. If missing/disabled, fallback channel is used if configured.

### Connecting a channel via OAuth
1. Configure the platform OAuth app (`YOUTUBE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI`).
   Register the redirect URI in Google Cloud Console.
2. An org admin calls `GET /api/competition/organizations/{org_id}/youtube/oauth/start`
   and opens the returned `authorize_url` in a browser.
3. Google redirects to `GET /api/competition/youtube/oauth/callback` (public, no JWT).
   The backend exchanges the code, reads the user's channel id, and stores the
   refresh token + channel id on the org's config, enabling it.
4. If `YOUTUBE_OAUTH_SUCCESS_REDIRECT` is set, the browser is sent there with
   `?organization_id=...&youtube_channel_id=...`; otherwise JSON is returned.

`state` is a signed, single-use, 10-minute token (replay-protected via cache).

## Notes
- Per-org YouTube secrets (`youtube_client_secret`, `youtube_refresh_token`) are
  encrypted at rest with Fernet (`leagues.fields.EncryptedTextField`). Key material
  comes from `STREAMING_ENCRYPTION_KEY` (falls back to Django `SECRET_KEY`); keep it
  stable, since changing it makes existing ciphertext unreadable. The `youtube-config`
  API masks secrets as `********` on read and ignores a masked/blank value on write.
- `stream/start` is idempotent: calling it while a game is already `preparing` or
  `live` returns the existing session instead of creating another broadcast.
- Manual Go Live only for v1.
- Admin: Django admin exposes stream status on Games and per-org YouTube config. The reconciler (`reconcile_streams`) automates `preparing → live` on signal.

## Reconciler scheduling
Run `python manage.py reconcile_streams` on a short interval so `preparing` games
flip to `live` shortly after the field signal appears (and time out to `error`
after `STREAM_RECONCILE_TIMEOUT`). Examples:

cron (every 30s):
```
* * * * * for i in 0 30; do python manage.py reconcile_streams; sleep 30; done
```

systemd timer (every 30s), `reconcile-streams.service`:
```
[Unit]
Description=Reconcile DiamondManager YouTube streams

[Service]
Type=oneshot
WorkingDirectory=/srv/diamondmanager
ExecStart=/srv/diamondmanager/.venv/bin/python manage.py reconcile_streams
```
`reconcile-streams.timer`:
```
[Unit]
Description=Run stream reconciler every 30s

[Timer]
OnBootSec=30
OnUnitActiveSec=30
AccuracySec=1

[Install]
WantedBy=timers.target
```

