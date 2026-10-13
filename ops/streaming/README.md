# Streaming Relay (POC)

## Overview
For POC we use a single SRS relay ingesting SRT from field devices (Larix). Backend creates YouTube broadcast/stream per game (manual Go Live) and returns SRT config. In v1 SRS has no global forward; orchestration of per-stream FFmpeg to YouTube RTMP can be added later.

## Quick Start
1. Copy `.env.example` to `.env` and fill values.
2. Copy `srs.conf.template` to `srs.conf`.
3. `docker compose up -d`
4. Open UDP `10080` on firewall/router for SRT; ensure server has public IP/domain if remote.

## Larix Config
Full SRT URL: `srt://<relay-host>:10080?streamid=live/game-<game_id>`

## YouTube Config Per Org
Create `OrganizationYouTubeConfig` in Django admin or via API later. If missing/disabled, fallback channel is used if configured.

## Notes
- POC stores secrets as plaintext in DB (marked). Encrypt in production.
- Manual Go Live only for v1.
