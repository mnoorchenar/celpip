import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOADS_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

WHISPER_MODEL = 'base'

DEFAULT_BAND = '7_8'   # fallback when JSON or request omits band

BAND_LABELS = {
    '7_8': 'Band 7–8 · Good',
    '9_10': 'Band 9–10 · Strong',
    '11_12': 'Band 11–12 · Expert',
}

TASK_DEFAULTS = {
    1: {'name': 'Giving Advice', 'prep': 30, 'response': 90},
    2: {'name': 'Talking About a Personal Experience', 'prep': 30, 'response': 60},
    3: {'name': 'Describing a Scene', 'prep': 30, 'response': 60},
    4: {'name': 'Making Predictions', 'prep': 30, 'response': 60},
    5: {'name': 'Comparing and Persuading', 'prep': 60, 'response': 60},
    6: {'name': 'Dealing With a Difficult Situation', 'prep': 60, 'response': 60},
    7: {'name': 'Expressing Opinions', 'prep': 30, 'response': 90},
    8: {'name': 'Describing an Unusual Situation', 'prep': 30, 'response': 60},
}

DISCLAIMER_TEXT = [
    "This video is created for educational and practice purposes only.",
    "We are not affiliated with, endorsed by, or connected to CELPIP\u00ae",
    "or Paragon Testing Enterprises in any way.",
    "Sample answers and scores shown are not guaranteed to be accurate.",
    "Individual exam results may vary.",
    "This content does not constitute professional language instruction.",
]

MUSIC_VOLUME = 0.015
MIN_PAGE_DURATION = 4.0
WORDS_PER_SECOND_SLOW = 100 / 60  # ~1.67 words/sec
