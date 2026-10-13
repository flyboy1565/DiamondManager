# Youth Baseball Streaming System (Self-Hosted Architecture)

An automated, low-cost, self-hosted streaming architecture designed to scale 6–8 concurrent youth baseball field streams to YouTube using a personal server, SRT ingestion, dynamic scorebug overlays, and the YouTube Live API.

## System Architecture Overview

```text
[Field Devices 1–8] ──(SRT Protocol / Larix App)──> [Personal Server (SRS / Docker)]
                                                              │
                                                  ┌───────────┴───────────┐
                                          (Optional Overlay)           (Relay)
                                                  │                       │
                                                  ▼                       ▼
                                       [FFmpeg + HTML Scorebug] ──> [YouTube Ingest RTMP]
```

## Key Components

1. **Field Hardware / App**: Mobile devices (iOS/Android) using Larix Broadcaster or a custom mobile wrapper to stream video over cellular networks using SRT (Secure Reliable Transport) for high packet-loss resilience.

2. **Personal Server (Ingest & Relay)**: A self-hosted Linux server running SRS (Simple Real-time Server) or Restreamer inside Docker, accepting incoming SRT feeds from the fields.

3. **Overlay & Transcoding Engine**: An automated FFmpeg/Docker worker that injects a real-time web-based scorebug overlay onto the video stream.

4. **Orchestration Backend**: A Node.js/Python service that interfaces with the YouTube Data API v3 to auto-create broadcasts, manage stream keys, and link streams to your mobile app.

## Server Prerequisites

- **OS**: Linux (Ubuntu 22.04 LTS recommended)
- **Hardware**: Multi-core CPU with an NVIDIA GPU or Intel CPU supporting QuickSync (required if burning overlays on 8 simultaneous streams)
- **Network**: Minimum 50+ Mbps symmetrical upload/download bandwidth on your home/personal server network
- **Software**: Docker & Docker Compose installed

## Configuration & Setup

### 1. SRS (Simple Real-time Server) Docker Setup

Create a file named `docker-compose.yml` on your server to handle SRT ingestion and RTMP relay.

```yaml
version: '3.8'

services:
  srs:
    image: ossrs/srs:5-snapshot
    container_name: baseball-srs-relay
    restart: always
    ports:
      - "1935:1935"       # RTMP ingest/out
      - "8080:8080"       # HTTP API / Web dashboard
      - "10080:10080/udp" # SRT ingest port
    volumes:
      - ./srs.conf:/usr/local/srs/conf/srs.conf
```

### 2. SRS Configuration (srs.conf)

Configure SRS to accept incoming SRT streams and relay them to YouTube destinations.

```conf
# srs.conf snippet
listen          1935;
max_connections 1000;
daemon          off;
srs_log_tank    console;

srt_server {
    enabled     on;
    listen      10080;
}

vhost __defaultVhost__ {
    # Ingest SRT and convert/relay to YouTube RTMP destination
    forward {
        enabled on;
        dest    rtmp://a.rtmp.youtube.com/live2/YOUR_YOUTUBE_STREAM_KEY;
    }
}
```

## Field Setup (For Volunteers)

To keep field setup foolproof for non-technical volunteers:

1. Download **Larix Broadcaster** on an iOS or Android device.
2. Configure a new connection destination pointing to your server:
   - **URL**: `srt://your-server-ip:10080?streamid=live/field1`
3. Recommended settings:
   - **Resolution**: 720p or 1080p @ 30fps
   - **Bitrate**: 3000–4500 Kbps (optimized for field LTE/5G upload caps)
4. Mount the device behind the backstop netting using an appropriate sunshade and external battery pack.

## YouTube API Automation Workflow

To manage 6–8 concurrent streams without manual YouTube dashboard configuration:

1. **Auth**: Authenticate your application using Google OAuth 2.0 with YouTube Data API v3 scopes (`youtube.force-ssl`).
2. **Broadcast Creation**: Use the `liveBroadcasts.insert` endpoint to programmatically create upcoming game events before game time.
3. **Stream Association**: Use `liveStreams.insert` to generate distinct stream keys and bind them to your broadcasts via `liveBroadcasts.bind`.
4. **App Integration**: Fetch the resulting YouTube embed URLs (`https://www.youtube.com/embed/VIDEO_ID`) and populate them directly into your game schedule UI inside the app.

## Reliability & Fail-Safes

- **Connection Drop Handling**: Because field devices use SRT, brief cellular drops will automatically reconnect without breaking the destination stream pipe to YouTube.
- **Fallback Stream Card**: If a field phone loses connection completely, your server can fallback to a looping "Game Paused / Reconnecting..." graphic using FFmpeg, preventing YouTube from terminating the live event.

## Integration Notes (DiamondManager Context)

This streaming architecture complements our existing Django/Android ecosystem. Key integration points to consider:

- **Game ↔ Stream Linking**: Associate a `Game` model (from `competition`) with a YouTube `video_id` and/or stream configuration. Could add fields like `stream_status`, `youtube_video_id`, `stream_key`, or `srt_stream_id` to the Game model.
- **API Endpoints**: Add Ninja endpoints to manage stream creation/assignment for games (authz: org admins/scorekeepers).
- **Android Client**: Extend the app to display embedded YouTube streams in GameDay/Scoreboard views when a game is live.
- **Automation**: Backend service (Django management command, Celery task, or separate microservice) to orchestrate YouTube Live API based on game schedule (start times, fields).