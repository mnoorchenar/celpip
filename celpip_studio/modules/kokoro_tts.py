"""Kokoro-ONNX text-to-speech wrapper for CELPIP Practice Studio."""

import os
import io
import sys
import tempfile
import subprocess
import threading
import urllib.request

KOKORO_VOICES = {
    'af_heart':    'Heart (US, Female)',
    'af_bella':    'Bella (US, Female)',
    'af_sarah':    'Sarah (US, Female)',
    'af_nova':     'Nova (US, Female)',
    'af_sky':      'Sky (US, Female)',
    'af_river':    'River (US, Female)',
    'am_adam':     'Adam (US, Male)',
    'am_michael':  'Michael (US, Male)',
    'am_echo':     'Echo (US, Male)',
    'am_eric':     'Eric (US, Male)',
    'am_liam':     'Liam (US, Male)',
    'bf_emma':     'Emma (UK, Female)',
    'bf_isabella': 'Isabella (UK, Female)',
    'bm_george':   'George (UK, Male)',
    'bm_lewis':    'Lewis (UK, Male)',
}

DEFAULT_VOICE = 'af_heart'

# Voices excluded from random selection
_EXCLUDED_FROM_RANDOM = {'am_adam'}


def random_voice():
    """Pick a random voice, excluding blacklisted ones (e.g. am_adam)."""
    import random as _random
    pool = [v for v in KOKORO_VOICES if v not in _EXCLUDED_FROM_RANDOM]
    return _random.choice(pool)

# Cache dir for model files
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'data', 'kokoro_models')

_MODEL_URL  = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx'
_VOICES_URL = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin'

_MODEL_FILE  = 'kokoro-v1.0.onnx'
_VOICES_FILE = 'voices-v1.0.bin'

_kokoro = None
_tts_lock = threading.Lock()   # espeak phonemizer is not thread-safe


def _download_if_missing(url, dest_path, label):
    if os.path.exists(dest_path):
        return
    print(f'[Kokoro TTS] Downloading {label} (~130MB first run)…', file=sys.stderr)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp = dest_path + '.tmp'
    try:
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, dest_path)
        print(f'[Kokoro TTS] Downloaded {label}.', file=sys.stderr)
    except Exception as e:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise RuntimeError(f'Failed to download {label}: {e}')


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise RuntimeError(
                'kokoro-onnx not installed.\n'
                'Run: pip install kokoro-onnx soundfile'
            )
        model_path  = os.path.join(_CACHE_DIR, _MODEL_FILE)
        voices_path = os.path.join(_CACHE_DIR, _VOICES_FILE)
        _download_if_missing(_MODEL_URL,  model_path,  'Kokoro model')
        _download_if_missing(_VOICES_URL, voices_path, 'Kokoro voices')
        _kokoro = Kokoro(model_path, voices_path)
    return _kokoro


def is_available():
    try:
        import kokoro_onnx
        return True
    except ImportError:
        return False


def _normalize_text(text):
    """Replace Unicode punctuation that confuses the espeak phonemizer."""
    replacements = [
        ('\u2014', ' - '),   # em dash —
        ('\u2013', ' - '),   # en dash –
        ('\u2018', "'"),     # left single quote '
        ('\u2019', "'"),     # right single quote '
        ('\u201c', '"'),     # left double quote "
        ('\u201d', '"'),     # right double quote "
        ('\u2026', '...'),   # ellipsis …
        ('\u00a0', ' '),     # non-breaking space
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    return text


def synthesize(text, voice=DEFAULT_VOICE, speed=1.0):
    """Return (samples_ndarray, sample_rate)."""
    k = _get_kokoro()
    with _tts_lock:
        samples, sr = k.create(_normalize_text(text), voice=voice, speed=speed, lang='en-us')
    return samples, sr


KOKORO_SAMPLE_RATE = 24000   # Kokoro always outputs 24 kHz mono


def to_wav_bytes(text, voice=DEFAULT_VOICE, speed=1.0):
    """Return WAV bytes for browser playback (44100 Hz for max compatibility)."""
    import soundfile as sf
    samples, sr = synthesize(text, voice, speed)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    raw = buf.read()
    # Resample to 44100 Hz via ffmpeg for universal browser/player support
    try:
        result = subprocess.run(
            ['ffmpeg', '-y',
             '-f', 'wav', '-i', 'pipe:0',
             '-ar', '44100', '-ac', '1',
             '-f', 'wav', 'pipe:1'],
            input=raw, capture_output=True, check=True
        )
        return result.stdout
    except Exception:
        return raw   # fallback: return 24 kHz WAV if ffmpeg not available


def to_wav_file(text, path, voice=DEFAULT_VOICE, speed=1.0):
    """Save WAV at 24 kHz mono PCM_16. Returns duration in seconds."""
    import soundfile as sf
    samples, sr = synthesize(text, voice, speed)
    sf.write(path, samples, sr, subtype='PCM_16')
    return len(samples) / sr


def to_mp3_file(text, path, voice=DEFAULT_VOICE, speed=1.0):
    """Save MP3 file via ffmpeg. Returns actual duration in seconds."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        duration = to_wav_file(text, tmp_path, voice, speed)
        subprocess.run(
            ['ffmpeg', '-y', '-i', tmp_path,
             '-c:a', 'libmp3lame', '-q:a', '2', path],
            capture_output=True, check=True
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return duration


def estimate_duration(text, speed=1.0):
    """Rough estimate: ~150 words/min adjusted by speed."""
    words = len(text.split())
    return max(1.0, (words / 150.0) * 60.0 / speed)
