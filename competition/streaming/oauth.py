"""YouTube OAuth 2.0 onboarding helpers.

Lets an org admin connect their own YouTube channel. The platform OAuth app
(settings.YOUTUBE_OAUTH_*) is used for the consent flow; the resulting refresh
token + channel id are stored on the org's OrganizationYouTubeConfig.

Uses the stdlib for HTTP so it has no hard dependency on google-auth at import
time (tests mock the network calls).
"""
import json
import secrets as _secrets
import urllib.error
import urllib.request
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.core.cache import cache

AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
CHANNELS_ENDPOINT = 'https://www.googleapis.com/youtube/v3/channels'
SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'

STATE_SALT = 'youtube-oauth'
STATE_TTL = 600  # seconds


class OAuthError(Exception):
    pass


def _client_config():
    client_id = getattr(settings, 'YOUTUBE_OAUTH_CLIENT_ID', '')
    client_secret = getattr(settings, 'YOUTUBE_OAUTH_CLIENT_SECRET', '')
    redirect_uri = getattr(settings, 'YOUTUBE_OAUTH_REDIRECT_URI', '')
    if not (client_id and client_secret and redirect_uri):
        raise OAuthError('YouTube OAuth app is not configured (YOUTUBE_OAUTH_*)')
    return client_id, client_secret, redirect_uri


def _http_post_form(url, data, timeout=10):
    body = urlencode(data).encode('utf-8')
    req = urllib.request.Request(
        url, data=body, method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _http_get_json(url, access_token, timeout=10):
    req = urllib.request.Request(
        url, headers={'Authorization': f'Bearer {access_token}'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def create_state(org_id, user_id):
    nonce = _secrets.token_urlsafe(16)
    token = signing.dumps(
        {'org_id': str(org_id), 'user_id': user_id, 'nonce': nonce},
        salt=STATE_SALT,
    )
    cache.set(f'youtube-oauth-state:{nonce}', True, STATE_TTL)
    return token


def consume_state(token):
    if not token:
        raise OAuthError('Missing state')
    try:
        payload = signing.loads(token, salt=STATE_SALT, max_age=STATE_TTL)
    except signing.SignatureExpired:
        raise OAuthError('State expired')
    except signing.BadSignature:
        raise OAuthError('Invalid state')
    nonce = payload.get('nonce')
    if not nonce or not cache.get(f'youtube-oauth-state:{nonce}'):
        raise OAuthError('State already used or expired')
    cache.delete(f'youtube-oauth-state:{nonce}')
    return payload


def get_redirect_uri():
    return _client_config()[2]


def build_authorization_url(org_id, user_id):
    client_id, _, redirect_uri = _client_config()
    state = create_state(org_id, user_id)
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    return f'{AUTH_ENDPOINT}?{urlencode(params)}'


def fetch_channel_id(access_token):
    data = _http_get_json(
        f'{CHANNELS_ENDPOINT}?part=id&mine=true', access_token,
    )
    items = data.get('items') or []
    if not items:
        raise OAuthError('No YouTube channel found for this Google account')
    return items[0].get('id', '')


def exchange_code(code):
    client_id, client_secret, redirect_uri = _client_config()
    if not code:
        raise OAuthError('Missing authorization code')
    try:
        payload = _http_post_form(TOKEN_ENDPOINT, {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        })
    except urllib.error.HTTPError as e:
        raise OAuthError(f'Token exchange failed (HTTP {e.code})')
    except urllib.error.URLError as e:
        raise OAuthError(f'Token exchange failed: {e.reason}')

    access_token = payload.get('access_token')
    refresh_token = payload.get('refresh_token')
    if not access_token:
        raise OAuthError('Token exchange returned no access token')
    if not refresh_token:
        raise OAuthError('No refresh token returned (re-consent required)')

    return {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'channel_id': fetch_channel_id(access_token),
    }
