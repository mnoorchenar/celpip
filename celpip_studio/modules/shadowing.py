import asyncio
import os
import re
import sys

VOICES = {
    'en-US-GuyNeural':     'Guy (US, Male)',
    'en-US-JennyNeural':   'Jenny (US, Female)',
    'en-CA-LiamNeural':    'Liam (Canada, Male)',
    'en-CA-ClaraNeural':   'Clara (Canada, Female)',
    'en-GB-RyanNeural':    'Ryan (UK, Male)',
    'en-GB-SoniaNeural':   'Sonia (UK, Female)',
    'en-AU-WilliamNeural': 'William (AU, Male)',
    'en-AU-NatashaNeural': 'Natasha (AU, Female)',
}

DEFAULT_VOICE = 'af_heart'

EDGE_GROUPS = [
    {'label': 'Canada',         'voices': ['en-CA-LiamNeural', 'en-CA-ClaraNeural']},
    {'label': 'United States',  'voices': ['en-US-GuyNeural', 'en-US-JennyNeural']},
    {'label': 'United Kingdom', 'voices': ['en-GB-RyanNeural', 'en-GB-SoniaNeural']},
    {'label': 'Australia',      'voices': ['en-AU-WilliamNeural', 'en-AU-NatashaNeural']},
]

KOKORO_SUB_GROUPS = [
    {'label': 'US Female', 'prefix': 'af_'},
    {'label': 'US Male',   'prefix': 'am_'},
    {'label': 'UK Female', 'prefix': 'bf_'},
    {'label': 'UK Male',   'prefix': 'bm_'},
]


def is_kokoro_voice(voice_id):
    return voice_id.startswith(('af_', 'am_', 'bf_', 'bm_'))


def split_sentences(text):
    text = text.strip()
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if p.strip()] or [text]


async def _generate_one(text, path, voice):
    import edge_tts
    tts = edge_tts.Communicate(text, voice)
    await tts.save(path)


def generate_shadowing_audio(sentences, audio_dir, voice=DEFAULT_VOICE):
    """
    Generate one audio file per sentence.
    Edge TTS voices → .mp3, Kokoro voices → .wav
    """
    os.makedirs(audio_dir, exist_ok=True)

    use_kokoro = is_kokoro_voice(voice)

    if not use_kokoro and sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    successful = []
    for i, sentence in enumerate(sentences):
        ext      = 'wav' if use_kokoro else 'mp3'
        filename = f'sentence_{i:03d}.{ext}'
        path     = os.path.join(audio_dir, filename)

        if os.path.exists(path) and os.path.getsize(path) > 0:
            successful.append({'index': i, 'text': sentence, 'filename': filename})
            continue

        try:
            if use_kokoro:
                from modules import kokoro_tts
                wav_bytes = kokoro_tts.to_wav_bytes(sentence, voice)
                with open(path, 'wb') as f:
                    f.write(wav_bytes)
            else:
                asyncio.run(_generate_one(sentence, path, voice))

            if os.path.exists(path) and os.path.getsize(path) > 0:
                successful.append({'index': i, 'text': sentence, 'filename': filename})
            else:
                print(f'[Shadowing] Empty file for sentence {i}, skipping.', file=sys.stderr)
        except Exception as e:
            print(f'[Shadowing] Sentence {i} failed: {e}', file=sys.stderr)

    return successful
