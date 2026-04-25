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

DEFAULT_VOICE = 'en-US-GuyNeural'


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
    Generate one MP3 per sentence sequentially.
    Skips failed sentences and returns only successful ones.
    """
    os.makedirs(audio_dir, exist_ok=True)

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    successful = []
    for i, sentence in enumerate(sentences):
        filename = f'sentence_{i:03d}.mp3'
        path     = os.path.join(audio_dir, filename)

        # Skip if already generated
        if os.path.exists(path) and os.path.getsize(path) > 0:
            successful.append({'index': i, 'text': sentence, 'filename': filename})
            continue

        try:
            asyncio.run(_generate_one(sentence, path, voice))
            if os.path.exists(path) and os.path.getsize(path) > 0:
                successful.append({'index': i, 'text': sentence, 'filename': filename})
            else:
                print(f'[Shadowing] Empty file for sentence {i}, skipping.', file=sys.stderr)
        except Exception as e:
            print(f'[Shadowing] Sentence {i} failed: {e}', file=sys.stderr)

    return successful
