import os
from typing import Dict, Any, Optional

from django.conf import settings

class YouTubeConfigError(Exception):
    pass


class YouTubeLiveService:
    def __init__(self):
        self._service = None
        self._cfg = None

    def _get_config(self, org):
        # Prefer org config if enabled and has minimal creds
        cfg = getattr(org, 'youtube_config', None)
        if cfg and cfg.is_enabled:
            return cfg
        # fallback
        return None

    def _get_credentials_from_cfg(self, cfg):
        # For POC plaintext; in prod should be encrypted
        if not cfg:
            return None
        client_id = cfg.youtube_client_id or getattr(settings, 'YOUTUBE_FALLBACK_CLIENT_ID', '')
        client_secret = cfg.youtube_client_secret or getattr(settings, 'YOUTUBE_FALLBACK_CLIENT_SECRET', '')
        refresh_token = cfg.youtube_refresh_token or getattr(settings, 'YOUTUBE_FALLBACK_REFRESH_TOKEN', '')
        if not (client_id and client_secret and refresh_token):
            raise YouTubeConfigError('YouTube credentials missing (org or fallback)')
        try:
            from google.oauth2.credentials import Credentials
        except Exception as e:
            raise YouTubeConfigError(f'google-auth libraries missing: {e}')
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=['https://www.googleapis.com/auth/youtube.force-ssl'],
        )
        return creds

    def _build_service(self, creds):
        try:
            from googleapiclient.discovery import build
        except Exception as e:
            raise YouTubeConfigError(f'google-api-python-client missing: {e}')
        return build('youtube', 'v3', credentials=creds, cache_discovery=False)

    def _get_service(self, org):
        if self._service and self._cfg is not None:
            return self._service, self._cfg
        cfg = self._get_config(org)
        if not cfg:
            # try to construct fallback cfg object-like via settings
            class F:
                pass
            cfg = F()
            cfg.youtube_client_id = getattr(settings, 'YOUTUBE_FALLBACK_CLIENT_ID', '')
            cfg.youtube_client_secret = getattr(settings, 'YOUTUBE_FALLBACK_CLIENT_SECRET', '')
            cfg.youtube_refresh_token = getattr(settings, 'YOUTUBE_FALLBACK_REFRESH_TOKEN', '')
            cfg.youtube_channel_id = getattr(settings, 'YOUTUBE_FALLBACK_CHANNEL_ID', '')
            cfg.streaming_server_srt_url = getattr(settings, 'STREAMING_SERVER_SRT_URL_DEFAULT', '')
            cfg.privacy_status = getattr(settings, 'YOUTUBE_FALLBACK_PRIVACY', 'unlisted')
            if not (cfg.youtube_client_id and cfg.youtube_client_secret and cfg.youtube_refresh_token):
                raise YouTubeConfigError('No YouTube config for org and no fallback configured')
        creds = self._get_credentials_from_cfg(cfg)
        self._service = self._build_service(creds)
        self._cfg = cfg
        return self._service, cfg

    def create_broadcast(self, org, title: str, description: str = '', scheduled_start_time: Optional[str] = None, privacy_status: Optional[str] = None) -> Dict[str, Any]:
        service, cfg = self._get_service(org)
        ps = privacy_status or cfg.privacy_status or 'unlisted'
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'scheduledStartTime': scheduled_start_time,
            } if scheduled_start_time else {
                'title': title,
                'description': description,
            },
            'status': {
                'privacyStatus': ps,
            },
            'contentDetails': {
                'enableAutoStart': False,
                'enableAutoStop': False,
            },
        }
        # remove scheduledStartTime if None? handled above
        if scheduled_start_time:
            body['snippet']['scheduledStartTime'] = scheduled_start_time
        try:
            resp = service.liveBroadcasts().insert(
                part='snippet,contentDetails,status',
                body=body
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to create broadcast: {e}')
        return {
            'youtube_broadcast_id': resp['id'],
            'youtube_video_id': resp['id'],  # for live broadcasts video id is same as broadcast id in many cases? embed uses video id; liveBroadcast has id; embed expects videoId - for live, videoId is the broadcast id
            'snippet': resp.get('snippet', {}),
        }

    def create_stream(self, org) -> Dict[str, Any]:
        service, cfg = self._get_service(org)
        body = {
            'snippet': {
                'title': f'Stream for {org.name}',
            },
            'cdn': {
                'format': '1080p',
                'ingestionType': 'rtmp',
                'frameRate': '30fps',
            }
        }
        try:
            resp = service.liveStreams().insert(
                part='snippet,cdn,status',
                body=body
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to create stream: {e}')
        cdn = resp.get('cdn', {})
        return {
            'youtube_stream_id': resp['id'],
            'stream_key': cdn.get('ingestionInfo', {}).get('streamName'),
            'ingestion_address': cdn.get('ingestionInfo', {}).get('ingestionAddress'),
        }

    def bind_broadcast(self, org, broadcast_id: str, stream_id: str):
        service, _ = self._get_service(org)
        try:
            service.liveBroadcasts().bind(
                part='id,contentDetails',
                id=broadcast_id,
                streamId=stream_id,
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to bind broadcast: {e}')
        return True

    def get_broadcast(self, org, broadcast_id: str) -> Dict[str, Any]:
        service, _ = self._get_service(org)
        try:
            resp = service.liveBroadcasts().list(
                part='id,snippet,status,contentDetails',
                id=broadcast_id,
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to fetch broadcast: {e}')
        items = resp.get('items') or []
        if not items:
            raise YouTubeConfigError(f'Broadcast {broadcast_id} not found')
        item = items[0]
        # For live broadcasts the broadcast id doubles as the video id.
        return {
            'youtube_broadcast_id': item.get('id') or broadcast_id,
            'youtube_video_id': item.get('id') or broadcast_id,
            'lifeCycle_status': (item.get('status') or {}).get('lifeCycleStatus'),
            'privacy_status': (item.get('status') or {}).get('privacyStatus'),
        }

    def transition_broadcast(self, org, broadcast_id: str, status: str):
        """Transition a broadcast to one of: testing, live, complete."""
        if status not in ('testing', 'live', 'complete'):
            raise YouTubeConfigError(f'Unsupported broadcast status: {status}')
        service, _ = self._get_service(org)
        try:
            service.liveBroadcasts().transition(
                part='id,status',
                broadcastStatus=status,
                id=broadcast_id,
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to transition broadcast to {status}: {e}')
        return True

    def complete_broadcast(self, org, broadcast_id: str):
        return self.transition_broadcast(org, broadcast_id, 'complete')

    def get_stream_health(self, org, stream_id: str) -> Optional[str]:
        """Return the YouTube stream status, e.g. 'active', 'ready', 'inactive'."""
        service, _ = self._get_service(org)
        try:
            resp = service.liveStreams().list(
                part='id,status',
                id=stream_id,
            ).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to fetch stream health: {e}')
        items = resp.get('items') or []
        if not items:
            return None
        return ((items[0].get('status') or {}).get('streamStatus'))

    def delete_broadcast(self, org, broadcast_id: str):
        service, _ = self._get_service(org)
        try:
            service.liveBroadcasts().delete(id=broadcast_id).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to delete broadcast: {e}')
        return True

    def delete_stream(self, org, stream_id: str):
        service, _ = self._get_service(org)
        try:
            service.liveStreams().delete(id=stream_id).execute()
        except Exception as e:
            raise YouTubeConfigError(f'Failed to delete stream: {e}')
        return True
