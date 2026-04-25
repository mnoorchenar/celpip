"""
YouTube upload module for CELPIP Practice Studio.

Setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "YouTube Data API v3"
  3. Go to APIs & Services → Credentials → Create OAuth 2.0 Client ID
     - Application type: Web application
     - Authorized redirect URIs: http://127.0.0.1:5009/youtube/callback
  4. Download the JSON → save as  data/client_secrets.json
"""

import os
import json
import threading
import functools

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_SECRETS  = os.path.join(_BASE, 'data', 'client_secrets.json')
TOKEN_FILE      = os.path.join(_BASE, 'data', 'youtube_token.json')
YT_CONFIG_FILE  = os.path.join(_BASE, 'data', 'youtube_config.json')


@functools.lru_cache(maxsize=1)
def _load_yt_config():
    """Load youtube_config.json once and cache it."""
    try:
        with open(YT_CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'[YouTube] Could not load youtube_config.json: {e}')
        return {}

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
]

# state -> (Flow, redirect_uri)  — kept in memory between /auth and /callback
_pending_flows = {}
_flows_lock    = threading.Lock()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def client_secrets_present():
    return os.path.exists(CLIENT_SECRETS)


def is_authenticated():
    """True if valid (or refreshable) credentials exist on disk."""
    if not client_secrets_present() or not os.path.exists(TOKEN_FILE):
        return False
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        with open(TOKEN_FILE) as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        if creds.valid:
            return True
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)
            return True
        return False
    except Exception:
        return False


def _save_token(creds):
    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())


def get_auth_url(redirect_uri):
    """Begin OAuth flow. Returns (state, auth_url)."""
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS, scopes=SCOPES,
                                          redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    with _flows_lock:
        _pending_flows[state] = (flow, redirect_uri)
    return state, auth_url


def handle_callback(state, code):
    """Exchange auth code for credentials and persist token."""
    with _flows_lock:
        entry = _pending_flows.pop(state, None)
    if not entry:
        raise ValueError('Unknown or expired OAuth state')
    flow, redirect_uri = entry
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)
    _save_token(flow.credentials)


# ── YouTube API helpers ────────────────────────────────────────────────────────

def get_service():
    """Return an authorized youtube Resource."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    with open(TOKEN_FILE) as f:
        creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
    return build('youtube', 'v3', credentials=creds)


def get_or_create_playlist(service, task_num, part_name):
    """Return playlist id, creating one if it doesn't exist yet."""
    playlist_title = f'CELPIP Speaking · Part {task_num:02d} · {part_name}'
    resp = service.playlists().list(part='snippet', mine=True, maxResults=50).execute()
    for item in resp.get('items', []):
        if item['snippet']['title'] == playlist_title:
            return item['id']
    result = service.playlists().insert(
        part='snippet,status',
        body={
            'snippet': {
                'title': playlist_title,
                'description': (
                    f'CELPIP Speaking practice — Task {task_num}: {part_name}. '
                    f'Model answers with vocabulary and shadowing practice.'
                ),
                'defaultLanguage': 'en',
            },
            'status': {'privacyStatus': 'public'},
        }
    ).execute()
    return result['id']


# ── Metadata builders ──────────────────────────────────────────────────────────

_BAND_LABELS = {'7_8': 'Band 7–8', '9_10': 'Band 9–10', '11_12': 'Band 11–12'}


def _make_title(task_num, part_name, band, category, title):
    cfg = _load_yt_config()
    bl      = _BAND_LABELS.get(band, band)
    display = title if (title and title != category) else category
    template = cfg.get('title_template',
                       'CELPIP Speaking Part {task_num:02d} · {band_label} | {topic}')
    try:
        result = template.format(task_num=task_num, band_label=bl, topic=display,
                                 part_name=part_name, category=category)
    except Exception:
        result = f'CELPIP Speaking Part {task_num:02d} · {bl} | {display}'
    return result[:100]


def _make_description(task_num, part_name, band, category, title,
                       question, answer, vocab):
    cfg = _load_yt_config()
    bl  = _BAND_LABELS.get(band, band)
    d   = cfg.get('description', {})

    lines = []

    # Intro lines
    for line in d.get('intro', []):
        lines.append(line.format(band_label=bl, task_num=task_num, part_name=part_name))
    lines.append('')

    # Task + band header
    lines += [
        f'CELPIP Speaking Task {task_num} – {part_name}',
        f'Band Score: {bl}',
        f'Category: {category}',
        '',
    ]

    # Sections list
    sec_header = d.get('sections_header', "WHAT'S IN THIS VIDEO")
    lines.append(f'━━ {sec_header} ━━')
    for i, sec in enumerate(d.get('sections', []), 1):
        lines.append(f'  {i}. {sec.format(band_label=bl)}')
    lines.append('')

    # Question + Answer
    lines += ['━━ QUESTION ━━', question, '', '━━ MODEL ANSWER ━━', answer]

    # Vocabulary
    if vocab:
        lines += ['', '━━ VOCABULARY ━━']
        for v in vocab:
            w = v.get('word', '')
            d_def = v.get('definition', '')
            if w:
                lines.append(f'• {w}: {d_def}')

    lines.append('')

    # Tips
    tips = d.get('tips', [])
    if tips:
        lines.append('━━ TIPS ━━')
        for tip in tips:
            lines.append(f'  ✔ {tip}')
        lines.append('')

    # Call to action
    cta = d.get('call_to_action', '')
    if cta:
        lines += [cta, '']

    # Tutoring link
    tutoring = d.get('tutoring', [])
    if tutoring:
        lines.append('')
        for t_line in tutoring:
            lines.append(t_line)
        lines.append('')

    # Website
    lines += ['🌐 tutordice.com', '']

    # Disclaimer
    lines.append('─' * 50)
    for disc_line in d.get('disclaimer', [
        'This video is for educational and practice purposes only.',
        'Not affiliated with CELPIP® or Paragon Testing Enterprises.',
    ]):
        lines.append(disc_line)
    lines.append('─' * 50)
    lines.append('')

    # Hashtags
    lines.append(' '.join(d.get('hashtags', ['#CELPIP', '#CELPIPSpeaking'])))

    return '\n'.join(lines)[:5000]


def _make_tags(task_num, band):
    cfg  = _load_yt_config()
    tags_cfg = cfg.get('tags', {})
    tags = list(tags_cfg.get('base', []))
    tags += tags_cfg.get('per_band', {}).get(band, [])
    tags += tags_cfg.get('per_task', {}).get(str(task_num), [])
    return tags[:30]  # YouTube limit


# ── Main upload function ───────────────────────────────────────────────────────

def upload_video(video_path, thumbnail_path,
                 task_num, part_name, band, category, title,
                 question, answer, vocab,
                 progress_cb=None):
    """
    Upload video to YouTube and return the video_id.
    progress_cb(pct: int) is called with values 0–100.
    """
    from googleapiclient.http import MediaFileUpload

    service = get_service()

    cfg  = _load_yt_config()
    ch   = cfg.get('channel', {})

    yt_title = _make_title(task_num, part_name, band, category, title)
    yt_desc  = _make_description(task_num, part_name, band, category,
                                  title, question, answer, vocab)
    tags     = _make_tags(task_num, band)

    body = {
        'snippet': {
            'title':                yt_title,
            'description':          yt_desc,
            'tags':                 tags,
            'categoryId':           str(ch.get('category_id', '27')),
            'defaultLanguage':      ch.get('default_language', 'en'),
            'defaultAudioLanguage': ch.get('default_audio_language', 'en'),
        },
        'status': {
            'privacyStatus': ch.get('privacy_status', 'public'),
            'license':       ch.get('license', 'youtube'),
            'embeddable':    ch.get('embeddable', True),
            'madeForKids':   ch.get('made_for_kids', False),
        },
    }

    media = MediaFileUpload(video_path, mimetype='video/mp4',
                             resumable=True, chunksize=4 * 1024 * 1024)
    req = service.videos().insert(part='snippet,status', body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status and progress_cb:
            progress_cb(int(status.progress() * 80))   # 0 → 80 %

    video_id = response['id']
    if progress_cb:
        progress_cb(85)

    # Add to section playlist
    try:
        pl_id = get_or_create_playlist(service, task_num, part_name)
        service.playlistItems().insert(
            part='snippet',
            body={'snippet': {
                'playlistId': pl_id,
                'resourceId': {'kind': 'youtube#video', 'videoId': video_id},
            }}
        ).execute()
    except Exception as e:
        print(f'[YouTube] Playlist error: {e}')

    if progress_cb:
        progress_cb(93)

    # Set custom thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype='image/jpeg'),
            ).execute()
        except Exception as e:
            print(f'[YouTube] Thumbnail set error: {e}')

    if progress_cb:
        progress_cb(100)

    return video_id
