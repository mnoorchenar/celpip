"""
Unified session-directory management.

All outputs for one practice session (PDF, shadowing MP3s, video) share
a single folder:
  output/speaking/Part {N}/Band {X-Y}/{Category}/NNN. {title}/
"""

import os
import re
import unicodedata

from config import OUTPUT_DIR

_BAND_FOLDER = {
    '7_8':   'Band 7-8',
    '9_10':  'Band 9-10',
    '11_12': 'Band 11-12',
}


def _display_name(text):
    """Sanitize text for use as a folder name, keeping spaces."""
    text = re.sub(r'[<>:"/\\|?*]', '', str(text)).strip()
    return text[:60] or 'Practice'


def _next_counter(parent_dir):
    """Return the next NNN counter by scanning existing numbered sub-dirs."""
    if not os.path.isdir(parent_dir):
        return 1
    nums = []
    for name in os.listdir(parent_dir):
        m = re.match(r'^(\d+)\.', name)
        if m and os.path.isdir(os.path.join(parent_dir, name)):
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def _parent_dir(task_num, band, category):
    band_folder = _BAND_FOLDER.get(str(band), f'Band {band}')
    cat_folder  = _display_name(category)
    return os.path.join(OUTPUT_DIR, 'speaking',
                        f'Part {task_num}', band_folder, cat_folder)


def find_existing_session_dir(task_num, band, category, title):
    """Return existing session dir for this title if it exists, else None."""
    display = _display_name(title or category)
    parent  = _parent_dir(task_num, band, category)
    if not os.path.isdir(parent):
        return None
    for name in os.listdir(parent):
        # Match any NNN. <title> folder regardless of number
        if re.match(r'^\d+\.\s+', name) and \
           name.split('. ', 1)[-1].strip() == display and \
           os.path.isdir(os.path.join(parent, name)):
            return os.path.join(parent, name)
    return None


def create_session_dir(task_num, band, category, title=None):
    """
    Return existing session dir if one exists for this title,
    otherwise create a new numbered one.
    """
    existing = find_existing_session_dir(task_num, band, category, title or category)
    if existing:
        return existing

    display     = _display_name(title or category)
    parent      = _parent_dir(task_num, band, category)
    os.makedirs(parent, exist_ok=True)
    counter     = _next_counter(parent)
    session_dir = os.path.join(parent, f'{counter:03d}. {display}')
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def shadowing_dir(session_dir):
    d = os.path.join(session_dir, 'shadowing')
    os.makedirs(d, exist_ok=True)
    return d


# ── Template answer output paths ───────────────────────────────────────────────

_FREQ_FOLDER = {
    'High Probability':        '1_high',
    'Medium-High Probability': '2_medium_high',
    'Medium Probability':      '3_medium',
    'Lower Probability':       '4_lower',
}


def _cat_slug(category):
    slug = re.sub(r'[^a-z0-9]+', '_', category.lower()).strip('_')
    return slug


def _title_slug(title, max_len=40):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return slug[:max_len].rstrip('-')


def template_session_dir(template_id, category, frequency_label, title):
    """
    Return (and create) the session folder for a template answer video.

    Structure:
      output/templates/p1/career_work/1_high/P1-CW-001.quitting-a-job/
    """
    part_slug  = template_id.split('-')[0].lower()        # 'p1'
    cat_slug   = _cat_slug(category)
    freq_slug  = _FREQ_FOLDER.get(frequency_label, 'other')
    title_part = _title_slug(title)
    folder     = f'{template_id}.{title_part}'

    path = os.path.join(OUTPUT_DIR, 'templates',
                        part_slug, cat_slug, freq_slug, folder)
    os.makedirs(path, exist_ok=True)
    return path
