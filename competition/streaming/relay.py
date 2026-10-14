"""Client for the relay control agent.

The agent owns the per-game FFmpeg process that bridges the local SRS relay to
the YouTube RTMP ingest endpoint. Django calls this module to start/stop the
relay and to query its status.

Uses the standard library only (urllib) so no extra runtime dependency is
required in the Django process.
"""
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from django.conf import settings


class RelayError(Exception):
    """Raised when the relay agent cannot be reached or returns an error."""


def _agent_url(path: str) -> str:
    base = getattr(settings, 'STREAMING_RELAY_AGENT_URL', 'http://127.0.0.1:8088').rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    return base + path


def _headers() -> Dict[str, str]:
    return {
        'Content-Type': 'application/json',
        'X-Relay-Token': getattr(settings, 'STREAMING_RELAY_AGENT_TOKEN', ''),
    }


def relay_enabled() -> bool:
    return bool(getattr(settings, 'STREAMING_RELAY_ENABLED', False))


def _request(path: str, method: str = 'GET', payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(_agent_url(path), data=data, headers=_headers(), method=method)
    timeout = getattr(settings, 'STREAMING_RELAY_TIMEOUT', 10)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RelayError(f'Relay agent returned {exc.code}: {detail}') from exc
    except urllib.error.URLError as exc:
        raise RelayError(f'Relay agent unreachable: {exc.reason}') from exc


def start_relay(stream_id: str, ingest_url: str, stream_key: str, source_url: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        'stream_id': stream_id,
        'ingest_url': ingest_url,
        'stream_key': stream_key,
    }
    if source_url:
        payload['source_url'] = source_url
    return _request('/relay/start', method='POST', payload=payload)


def stop_relay(stream_id: str) -> Dict[str, Any]:
    return _request('/relay/stop', method='POST', payload={'stream_id': stream_id})


def relay_status(stream_id: str) -> Dict[str, Any]:
    return _request(f'/relay/{stream_id}', method='GET')


def agent_health() -> Dict[str, Any]:
    return _request('/health', method='GET')
