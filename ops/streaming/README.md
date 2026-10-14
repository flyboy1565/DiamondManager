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

## YouTube Config Per Org
Create `OrganizationYouTubeConfig` in Django admin or via API later. If missing/disabled, fallback channel is used if configured.

## Notes
- POC stores secrets as plaintext in DB (marked). Encrypt in production.
- Manual Go Live only for v1.
