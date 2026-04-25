"""
Pillow-based 1920x1080 frame renderer for CELPIP Practice Studio.
"""

import re
import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Color Scheme (dark defaults kept for backward compat) ─────────────────────
BG            = '#080910'
SURFACE       = '#0f1223'
BORDER        = '#1e2240'
PREP_COLOR    = '#f0c040'
SPEAK_COLOR   = '#40d090'
DONE_COLOR    = '#e05555'
ACTIVE_BG     = '#1a2550'
ACTIVE_BORDER = '#3a6aff'
SPOKEN_TEXT   = '#2a9060'
UPCOMING_TEXT = '#4a5070'
WHITE         = '#ffffff'
GOLD          = '#f0c040'

from modules.style_gen import THEME_COLORS as _THEME_COLORS


def _tc(style):
    """Return the structural color dict for the style's theme, with per-style overrides."""
    theme = (style or {}).get('theme', 'light')
    base  = dict(_THEME_COLORS.get(theme, _THEME_COLORS['light']))
    # Allow the style dict to override individual structural colour keys
    _overridable = {'bg', 'surface', 'border', 'active_bg', 'active_border',
                    'spoken', 'upcoming', 'text', 'gold', 'prep', 'speak', 'done'}
    for k in _overridable:
        if style and k in style:
            base[k] = style[k]
    return base

W, H = 1920, 1080

# ── Margin config ──────────────────────────────────────────────────────────────
import json as _json

_MARGINS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'margin_config.json')

_MARGIN_DEFAULTS = {
    'side':          100,   # left = right content margin (px)
    'top':           100,   # top content margin below the section bar (px)
    'bottom':        100,   # bottom content margin (px)
    'hl_right_mult': 2.0,   # highlight box: right_inner = hl_right_mult × left_inner
    'sentence_gap':  16,    # vertical gap BETWEEN sentence blocks in sections 2 & 5 (px)
    'line_gap':      0,     # extra line height WITHIN a sentence (multi-line spacing, px)
}

def _load_saved_margins():
    try:
        with open(_MARGINS_PATH) as _f:
            _d = _json.load(_f)
        return {k: type(_MARGIN_DEFAULTS[k])(_d[k]) for k in _MARGIN_DEFAULTS if k in _d}
    except Exception:
        return {}

_SAVED_MARGINS = {**_MARGIN_DEFAULTS, **_load_saved_margins()}


def reload_margin_config():
    """Reload saved margins from disk (call after saving new config)."""
    global _SAVED_MARGINS
    _SAVED_MARGINS = {**_MARGIN_DEFAULTS, **_load_saved_margins()}


def save_margin_config(margins):
    """Persist margin config to disk and reload into memory."""
    os.makedirs(os.path.dirname(os.path.abspath(_MARGINS_PATH)), exist_ok=True)
    with open(_MARGINS_PATH, 'w') as _f:
        _json.dump(margins, _f, indent=2)
    reload_margin_config()


def _get_margins(style=None):
    """Return effective margins — style['_margins'] overrides saved config (live preview)."""
    base = dict(_SAVED_MARGINS)
    m = (style or {}).get('_margins')
    if m:
        for k in _MARGIN_DEFAULTS:
            if k in m:
                base[k] = type(_MARGIN_DEFAULTS[k])(m[k])
    return base


# Font cache
_font_cache = {}


def _load_font(path, size):
    key = (path, size)
    if key in _font_cache:
        return _font_cache[key]
    try:
        if path and os.path.exists(path):
            font = ImageFont.truetype(path, size)
        else:
            raise IOError("not found")
    except Exception:
        try:
            font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
        except Exception:
            font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _default_font(size):
    return _load_font('C:/Windows/Fonts/segoeui.ttf', size)


def _bold_font(size):
    return _load_font('C:/Windows/Fonts/segoeuib.ttf', size)


def _emoji_font(size):
    return _load_font('C:/Windows/Fonts/seguiemj.ttf', size)


def _mono_font(size):
    return _load_font('C:/Windows/Fonts/courbd.ttf', size)


def _strip_emoji(text):
    """Remove emoji/symbol codepoints that regular text fonts cannot render."""
    return re.sub(
        r'[\U0001F000-\U0001FFFF'   # misc symbols & pictographs, emoticons, etc.
        r'\U00002600-\U000027FF'     # miscellaneous symbols, dingbats
        r'\U00002300-\U000023FF'     # misc technical
        r'\uFE0F]',                  # variation selector-16 (emoji style)
        '', text
    ).strip()


def _sfont(size, style, bold=False):
    """Return a font scaled by style['font_scale'] (default 1.0)."""
    scale = (style or {}).get('font_scale', 1.0)
    scaled = max(10, int(size * scale))
    return _bold_font(scaled) if bold else _default_font(scaled)


def _hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _parse_color(color):
    """Accept hex string or tuple."""
    if isinstance(color, str):
        return _hex_to_rgb(color)
    return color


def _luminance(color):
    """Perceived luminance 0–255 of a color."""
    r, g, b = _parse_color(color) if isinstance(color, str) else color
    return 0.299 * r + 0.587 * g + 0.114 * b


def _contrast_on(bg):
    """High-contrast primary text color for any background."""
    return (10, 12, 24) if _luminance(bg) > 140 else (240, 243, 255)


def _muted_on(bg):
    """Readable but clearly secondary text color for any background."""
    return (80, 86, 108) if _luminance(bg) > 140 else (158, 163, 190)


def _vocab_hl_color(accent_color):
    """
    Distinct vocab-word highlight (box background) for use inside an active
    sentence block whose background is `accent_color`.

    Rule: warm accent (red/amber dominant) → cool cyan highlight so it pops;
          cool/neutral accent (blue/teal/purple/green) → warm gold highlight.
    This guarantees the vocab box is always visually different from the
    sentence block background.
    """
    ac = _parse_color(accent_color) if isinstance(accent_color, str) else accent_color
    warmth = ac[0] - ac[2]   # positive → warm, negative → cool
    if warmth > 50:
        return (40, 220, 200)   # cool teal-cyan on warm/red/amber bg
    return (255, 210, 40)       # warm gold on cool/blue/green/purple bg


def _spoken_on(bg, accent):
    """Color for already-spoken/done text on any background."""
    ac = _parse_color(accent) if isinstance(accent, str) else accent
    if _luminance(bg) > 140:
        return tuple(max(0, int(c * 0.48)) for c in ac)
    return tuple(min(255, int(c * 0.58 + 28)) for c in ac)


# Irregular verb/word forms. Key = base/infinitive form; value = all surface
# forms that should also be highlighted when the key word is a vocab word.
# Entries are bidirectional: any of the listed forms triggers matching of all.
_IRREGULAR_FORMS = {
    'be':      ['is', 'am', 'are', 'was', 'were', 'been', 'being'],
    'have':    ['has', 'had', 'having'],
    'do':      ['does', 'did', 'done', 'doing'],
    'go':      ['goes', 'went', 'gone', 'going'],
    'get':     ['gets', 'got', 'gotten', 'getting'],
    'make':    ['makes', 'made', 'making'],
    'take':    ['takes', 'took', 'taken', 'taking'],
    'come':    ['comes', 'came', 'coming'],
    'see':     ['sees', 'saw', 'seen', 'seeing'],
    'know':    ['knows', 'knew', 'known', 'knowing'],
    'think':   ['thinks', 'thought', 'thinking'],
    'say':     ['says', 'said', 'saying'],
    'tell':    ['tells', 'told', 'telling'],
    'give':    ['gives', 'gave', 'given', 'giving'],
    'find':    ['finds', 'found', 'finding'],
    'feel':    ['feels', 'felt', 'feeling'],
    'keep':    ['keeps', 'kept', 'keeping'],
    'leave':   ['leaves', 'left', 'leaving'],
    'meet':    ['meets', 'met', 'meeting'],
    'put':     ['puts', 'putting'],
    'run':     ['runs', 'ran', 'running'],
    'set':     ['sets', 'setting'],
    'sit':     ['sits', 'sat', 'sitting'],
    'stand':   ['stands', 'stood', 'standing'],
    'bring':   ['brings', 'brought', 'bringing'],
    'buy':     ['buys', 'bought', 'buying'],
    'build':   ['builds', 'built', 'building'],
    'hold':    ['holds', 'held', 'holding'],
    'lead':    ['leads', 'led', 'leading'],
    'read':    ['reads', 'reading'],   # read/read (same spelling, diff pronunciation)
    'write':   ['writes', 'wrote', 'written', 'writing'],
    'speak':   ['speaks', 'spoke', 'spoken', 'speaking'],
    'show':    ['shows', 'showed', 'shown', 'showing'],
    'spend':   ['spends', 'spent', 'spending'],
    'lose':    ['loses', 'lost', 'losing'],
    'win':     ['wins', 'won', 'winning'],
    'begin':   ['begins', 'began', 'begun', 'beginning'],
    'break':   ['breaks', 'broke', 'broken', 'breaking'],
    'choose':  ['chooses', 'chose', 'chosen', 'choosing'],
    'drive':   ['drives', 'drove', 'driven', 'driving'],
    'eat':     ['eats', 'ate', 'eaten', 'eating'],
    'fall':    ['falls', 'fell', 'fallen', 'falling'],
    'fly':     ['flies', 'flew', 'flown', 'flying'],
    'forget':  ['forgets', 'forgot', 'forgotten', 'forgetting'],
    'grow':    ['grows', 'grew', 'grown', 'growing'],
    'hang':    ['hangs', 'hung', 'hanging'],
    'hear':    ['hears', 'heard', 'hearing'],
    'hit':     ['hits', 'hitting'],
    'hurt':    ['hurts', 'hurting'],
    'let':     ['lets', 'letting'],
    'lie':     ['lies', 'lay', 'lain', 'lying'],
    'pay':     ['pays', 'paid', 'paying'],
    'rise':    ['rises', 'rose', 'risen', 'rising'],
    'send':    ['sends', 'sent', 'sending'],
    'shoot':   ['shoots', 'shot', 'shooting'],
    'sing':    ['sings', 'sang', 'sung', 'singing'],
    'sleep':   ['sleeps', 'slept', 'sleeping'],
    'slide':   ['slides', 'slid', 'sliding'],
    'swim':    ['swims', 'swam', 'swum', 'swimming'],
    'swing':   ['swings', 'swung', 'swinging'],
    'teach':   ['teaches', 'taught', 'teaching'],
    'throw':   ['throws', 'threw', 'thrown', 'throwing'],
    'understand': ['understands', 'understood', 'understanding'],
    'wake':    ['wakes', 'woke', 'woken', 'waking'],
    'wear':    ['wears', 'wore', 'worn', 'wearing'],
    'wish':    ['wishes', 'wished', 'wishing'],
}

# Build a reverse index: surface form → canonical key
_IRREGULAR_REVERSE: dict[str, str] = {}
for _base, _forms in _IRREGULAR_FORMS.items():
    _IRREGULAR_REVERSE[_base] = _base
    for _f in _forms:
        _IRREGULAR_REVERSE[_f] = _base


def _word_variants_pattern(word):
    """
    Return a case-insensitive regex pattern that matches the given word and its
    common English inflected/derived forms.

    Rules handled:
      - irregular verbs       : be → is/am/are/was/were/been/being (lookup table)
      - words ending in 'e'   : love → love, loves, loved, loving, lover, lovers
      - words ending in C+y   : try → try, tries, tried, trying
      - CVC pattern           : run → run, runs, running, runner (consonant doubled)
      - general               : bother → bother, bothers, bothered, bothering, …
      - multi-word phrases    : exact boundary match only
    """
    word = word.strip().lower()
    if not word:
        return r'(?!)'   # match nothing

    if ' ' in word:
        # Phrase: match exactly at word boundaries
        return r'\b' + re.escape(word) + r'\b'

    # ── Irregular verb lookup ────────────────────────────────────────────────
    canonical = _IRREGULAR_REVERSE.get(word)
    if canonical is not None:
        all_forms = [canonical] + _IRREGULAR_FORMS.get(canonical, [])
        alts = '|'.join(re.escape(f) for f in all_forms)
        return rf'\b(?:{alts})\b'

    base = re.escape(word)
    vowels = 'aeiou'

    # Words ending in silent 'e': use → uses, used, using, user, users
    if word.endswith('e') and len(word) > 2:
        stem = re.escape(word[:-1])
        return (rf'\b(?:{base}[sd]?'
                rf'|{stem}(?:ing|ed|er|ers|ation|ations))\b')

    # Words ending in consonant + y: try → tries, tried, trying
    if (word.endswith('y') and len(word) > 2
            and word[-2] not in vowels):
        stem = re.escape(word[:-1])
        return rf'\b(?:{base}(?:ing|s)?|{stem}(?:ies|ied))\b'

    # CVC pattern → double final consonant: run → running, runner
    if (len(word) >= 3
            and word[-1] not in vowels + 'wy'
            and word[-2] in vowels
            and word[-3] not in vowels
            and word[-1] != 'x'):
        doubled = re.escape(word + word[-1])
        return (rf'\b(?:{base}(?:s|es|ed|ing|er|ers|est|ly|'
                rf'ment|ments|ness|ful|less|able|ible)?'
                rf'|{doubled}(?:ing|ed|er|ers))\b')

    # General: just try common suffixes
    return (rf'\b{base}(?:s|es|ed|ing|er|ers|est|ly|'
            rf'ment|ments|tion|tions|ness|ful|less|able|ible)?\b')


def wrap_text(draw, text, font, max_width, bold_font=None):
    """Split text into lines that fit within max_width pixels.

    Supports {marker} syntax for vocab highlights — markers are preserved in
    output lines but stripped for width measurement.  A {multi word phrase} is
    kept as a single token so it is never split across lines.

    bold_font: when provided, width is measured using the bolder font.
    Vocab words render in bold, which is wider than regular — measuring with
    bold_font guarantees the rendered line never overflows max_width.
    """
    # Measure with bold font when given — bold renders wider than regular.
    measure_font = bold_font if bold_font is not None else font

    # Tokenise: {marker} blocks are atomic; everything else splits on spaces.
    tokens = []
    for chunk in re.split(r'(\{[^}]+\})', text):
        if chunk.startswith('{'):
            tokens.append(chunk)
        else:
            tokens.extend(w for w in chunk.split() if w)

    lines = []
    current = []
    for token in tokens:
        test = ' '.join(current + [token])
        clean = re.sub(r'[{}]', '', test)
        bbox = draw.textbbox((0, 0), clean, font=measure_font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(token)
        else:
            if current:
                lines.append(' '.join(current))
            current = [token]
    if current:
        lines.append(' '.join(current))
    return lines if lines else ['']


def split_sentences(text):
    """Split text on sentence boundaries."""
    text = text.strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def compute_page_split(sentences, style, area_w=None, area_h=None):
    """
    Measure total block height of all sentences and split into pages if they
    don't all fit within area_h.

    Returns a list of pages; each page is a list of sentence dicts.
    If everything fits, returns a single-element list [[...all sentences...]].

    area_w / area_h default to the values used by render_final_answer_frame.
    """
    _m = _get_margins(style)
    pad = int(_m['side'])
    if area_w is None:
        area_w = W - pad * 2 - 3      # matches render_final_answer_frame
    if area_h is None:
        # S5 now mirrors S2: bar_bottom=90, panel_y_start = 90 + top_margin
        area_h = H - (90 + int(_m['top'])) - int(_m['bottom'])

    _fscale = (style or {}).get('font_scale', 1.0)
    font_s      = _sfont(36, style)
    font_s_bold = _sfont(36, style, bold=True)
    line_h   = int(48 * _fscale)
    block_gap = 14
    block_pad = 16

    tmp  = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(tmp)

    pages        = []
    current_page = []
    current_h    = 0

    for s in sentences:
        text  = s['text'] if isinstance(s, dict) else s
        lines = wrap_text(draw, text, font_s, area_w, bold_font=font_s_bold)
        h     = len(lines) * line_h + 2 * block_pad

        if current_page and current_h + block_gap + h > area_h:
            pages.append(current_page)
            current_page = [s if isinstance(s, dict) else {'text': s}]
            current_h    = h
        else:
            current_page.append(s if isinstance(s, dict) else {'text': s})
            current_h += (block_gap if current_page else 0) + h

    if current_page:
        pages.append(current_page)

    return pages


def _draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    if fill:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)
    elif outline:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=None, outline=outline, width=width)


def _format_time(seconds):
    """Format seconds as M:SS."""
    seconds = max(0, int(seconds))
    m = seconds // 60
    s = seconds % 60
    return f'{m}:{s:02d}'


def _new_frame(style=None):
    """Create a new 1920x1080 image using the section's bg_color when available."""
    tc = _tc(style)
    # Use the section's random bg_color so all slides in a section share the same background
    if style and style.get('bg_color'):
        bg = _parse_color(style['bg_color'])
    else:
        bg = _parse_color(tc['bg'])
    img = Image.new('RGB', (W, H), color=bg)
    return img


def _draw_top_bar(draw, left_text, center_text, center_color, right_text, right_color,
                  show_rec=False, style=None):
    """Draw the 80px top bar."""
    tc    = _tc(style)
    # section_badge_color overrides center_color for the pill when group styles are active
    badge_color = (style or {}).get('section_badge_color', center_color)
    bar_h = 80
    draw.rectangle([0, 0, W, bar_h], fill=_parse_color(tc['surface']))
    draw.rectangle([0, bar_h - 2, W, bar_h], fill=_parse_color(tc['border']))

    # Section progress indicator appended to left text (subtle "§ 2/5" suffix)
    section_num = (style or {}).get('section_num')
    if section_num:
        left_text = f'{left_text}  ·  {section_num}/5'

    font_left = _default_font(22)
    draw.text((30, bar_h // 2), left_text, font=font_left, fill=_parse_color(tc['text']),
              anchor='lm')

    font_badge = _bold_font(20)
    badge_bbox = draw.textbbox((0, 0), center_text, font=font_badge)
    bw = badge_bbox[2] - badge_bbox[0] + 32
    bh = 36
    bx = (W - bw) // 2
    by = (bar_h - bh) // 2
    _draw_rounded_rect(draw, [bx, by, bx + bw, by + bh], radius=6,
                       fill=_parse_color(badge_color), outline=None)
    # Badge text: dark on light badge, light on dark badge
    badge_lum = sum(_parse_color(badge_color)) / 3
    badge_txt = (20, 20, 30) if badge_lum > 140 else (240, 240, 240)
    draw.text((W // 2, bar_h // 2), center_text, font=font_badge,
              fill=badge_txt, anchor='mm')

    if show_rec:
        rec_x = W // 2 + bw // 2 + 50
        rec_y = bar_h // 2
        draw.ellipse([rec_x - 8, rec_y - 8, rec_x + 8, rec_y + 8],
                     fill=_parse_color(tc['done']))

    # Band score badge (e.g. "Band 9-10") — shown when style['band_label'] is set
    band_label = (style or {}).get('band_label')
    if band_label:
        font_band = _bold_font(18)
        bb_bbox   = draw.textbbox((0, 0), band_label, font=font_band)
        bb_w      = bb_bbox[2] - bb_bbox[0] + 20
        bb_h      = 28
        bb_x      = W - 250 - bb_w
        bb_y      = (bar_h - bb_h) // 2
        _draw_rounded_rect(draw, [bb_x, bb_y, bb_x + bb_w, bb_y + bb_h],
                           radius=6, fill=(60, 120, 60), outline=None)
        draw.text((bb_x + bb_w // 2, bar_h // 2), band_label,
                  font=font_band, fill=(200, 255, 200), anchor='mm')

    font_timer = _mono_font(48)
    draw.text((W - 30, bar_h // 2), right_text, font=font_timer,
              fill=_parse_color(right_color), anchor='rm')


def _draw_progress_bar(draw, ratio, y_start=80, height=8,
                       fill_color=None, bg_color=None, style=None):
    """Draw a horizontal progress bar."""
    tc = _tc(style)
    fill_color = fill_color or tc['prep']
    bg_color   = bg_color   or tc['border']
    draw.rectangle([0, y_start, W, y_start + height], fill=_parse_color(bg_color))
    fill_w = int(W * max(0.0, min(1.0, ratio)))
    if fill_w > 0:
        draw.rectangle([0, y_start, fill_w, y_start + height], fill=_parse_color(fill_color))


def render_prep_frame(task_name, question, time_remaining, total_prep_time, style=None):
    """
    Render a preparation phase frame.
    Returns PIL Image.
    """
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    # Use section's accent color so prep slides match the section's visual theme
    accent_color = style.get('accent_color', tc['prep']) if style else tc['prep']
    _draw_decoration(draw, style or {})

    left_label = f'CELPIP Speaking · {task_name}'
    timer_str = _format_time(time_remaining)
    _draw_top_bar(draw, left_label, 'PREPARATION TIME', accent_color, timer_str, accent_color, style=style)

    # Progress bar (fills 100% → 0%)
    ratio = time_remaining / max(1, total_prep_time)
    _draw_progress_bar(draw, ratio, y_start=80, fill_color=accent_color, style=style)

    # Question text centered in main area
    main_top = 100
    main_h = H - main_top - 80  # leave 80 for watermark area

    font_q = _sfont(36, style)

    lines = wrap_text(draw, question, font_q, 1200)
    line_h = int(36 * (style or {}).get('font_scale', 1.0)) + 12
    total_text_h = len(lines) * line_h
    start_y = main_top + (main_h - total_text_h) // 2

    for i, line in enumerate(lines):
        y = start_y + i * line_h
        draw.text((W // 2, y), line, font=font_q, fill=_parse_color(tc['text']), anchor='mt')

    # Freq label badge — bottom-left, just above watermark area
    freq_label = (style or {}).get('freq_label')
    if freq_label:
        freq_color = (style or {}).get('freq_color', accent_color)
        font_freq  = _bold_font(20)
        fl_bbox    = draw.textbbox((0, 0), freq_label, font=font_freq)
        bw         = fl_bbox[2] - fl_bbox[0] + 24
        bh         = 32
        bx, by2    = 30, H - 70
        _draw_rounded_rect(draw, [bx, by2, bx + bw, by2 + bh], radius=6,
                           fill=_parse_color(freq_color))
        ftxt = (255, 255, 255) if _luminance(_parse_color(freq_color)) < 140 else (20, 20, 30)
        draw.text((bx + bw // 2, by2 + bh // 2), freq_label,
                  font=font_freq, fill=ftxt, anchor='mm')

    # Watermark
    font_wm = _sfont(24, style)
    draw.text((W // 2, H - 40), 'PREPARATION TIME', font=font_wm,
              fill=_parse_color(tc['upcoming']), anchor='mm')

    _draw_watermark(img)
    return img


def _s2_active_bg(accent_color):
    """Very light tint of the accent for the active-sentence highlight box."""
    ac = _parse_color(accent_color)
    # Blend accent 12% into white
    return tuple(int(255 * 0.88 + ac[i] * 0.12) for i in range(3))


def _s2_spoken_color(accent_color):
    """Darker, desaturated version of accent for already-spoken sentences."""
    ac = _parse_color(accent_color)
    # Darken by 35% and shift toward gray
    return tuple(max(0, int(ac[i] * 0.55 + 30)) for i in range(3))


def render_response_frame(task_name, question, sentences, active_idx, time_remaining,
                           total_response_time, style=None, vocab_words=None,
                           page_num=None, total_pages=None):
    """
    Render a speaking/response phase frame.
    Returns PIL Image.
    """
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    # Use section's accent color for top bar and progress bar
    accent_color = style.get('accent_color', tc['speak']) if style else tc['speak']
    _draw_decoration(draw, style or {})

    left_label = f'CELPIP Speaking · {task_name}'
    timer_str = _format_time(time_remaining)
    _draw_top_bar(draw, left_label, 'SPEAKING TIME', accent_color, timer_str, accent_color,
                  show_rec=True, style=style)

    # Progress bar
    ratio = time_remaining / max(1, total_response_time)
    _draw_progress_bar(draw, ratio, y_start=80, fill_color=accent_color, style=style)

    bar_bottom = 90  # top bar + progress bar

    # ── Full-width sentences panel ─────────────────────────────────────────
    _m = _get_margins(style)
    lpad = int(_m['side'])
    rpad = int(_m['side'])
    _fscale = (style or {}).get('font_scale', 1.0)
    panel_y_start = bar_bottom + int(_m['top'])
    panel_y_end = H - int(_m['bottom'])
    panel_content_h = panel_y_end - panel_y_start

    # Sentence counter — top right, small
    total_s = len(sentences)
    current_s = min(active_idx + 1, total_s)
    font_counter = _default_font(18)
    draw.text((W - rpad, panel_y_start + 5), f'{current_s} / {total_s}',
              font=font_counter, fill=_parse_color(tc['upcoming']), anchor='rt')

    font_s      = _sfont(36, style)
    font_s_bold = _sfont(36, style, bold=True)
    line_h      = int(48 * _fscale) + int(_m['line_gap'])   # inner line spacing within a sentence
    block_pad   = 16
    sent_gap    = int(_m['sentence_gap'])                    # gap between sentence blocks

    # Calculate block heights first.
    # Measure with bold font — vocab words render bold (wider than regular),
    # so bold measurement guarantees no overflow regardless of which words are highlighted.
    # Active text starts at bx1+18; ensure it stays within right content margin (W-rpad)
    _wrap_w = W - lpad - rpad - 26    # 26 = 18 (active indent) + 8 (clearance)
    blocks = []
    for i, s in enumerate(sentences):
        lines = wrap_text(draw, s['text'], font_s, _wrap_w, bold_font=font_s_bold)
        h = len(lines) * line_h + 2 * block_pad
        blocks.append({'lines': lines, 'height': h, 'idx': i})

    # Determine scroll offset so active block is visible
    # Layout top-down, find cumulative y positions
    cumulative = []
    cy = 0
    for b in blocks:
        cumulative.append(cy)
        cy += b['height'] + sent_gap
    total_h = cy

    # Scroll so active is roughly centered in panel
    if active_idx < len(cumulative):
        active_top = cumulative[active_idx]
        active_bot = active_top + blocks[active_idx]['height']
        # Center the active block
        desired_top = (panel_content_h - blocks[active_idx]['height']) // 2
        scroll = active_top - desired_top
        scroll = max(0, min(scroll, max(0, total_h - panel_content_h)))
    else:
        scroll = 0

    # Draw visible blocks
    for i, b in enumerate(blocks):
        block_y = cumulative[i] - scroll + panel_y_start

        # Skip if fully out of view
        if block_y + b['height'] < panel_y_start:
            continue
        if block_y > panel_y_end:
            break

        bx1 = lpad
        bx2 = W - rpad          # symmetric: same right margin as lpad region
        by1 = block_y
        by2 = block_y + b['height']

        bg_color = style.get('bg_color', '#080910') if style else '#080910'
        active_fill   = _parse_color(accent_color)
        active_text   = _contrast_on(accent_color)
        upcoming_text = _muted_on(bg_color)
        spoken_text   = _spoken_on(bg_color, accent_color)
        bar_color     = _contrast_on(accent_color)  # left border inside active block
        vocab_hl      = _vocab_hl_color(accent_color)  # distinct vocab highlight on active bg
        if i < active_idx:
            # Spoken — clearly done, auto-contrast against bg
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 10, ly, line, vocab_words,
                        font_s, font_s_bold, spoken_text, _parse_color(accent_color))
        elif i == active_idx:
            # Active — solid vivid accent block for max attention
            clip_y1 = max(by1, panel_y_start)
            clip_y2 = min(by2, panel_y_end)
            if clip_y1 < clip_y2:
                # Dynamic box right: text_x + max_line_px + 2 × left_inner
                _box_left  = bx1 - 12
                _text_x    = bx1 + 18
                _left_in   = _text_x - _box_left          # 30px
                _max_lw    = max(
                    (draw.textbbox((0, 0), re.sub(r'[{}]', '', ln), font=font_s_bold)[2]
                     for ln in b['lines']),
                    default=0
                )
                _box_right = min(_text_x + _max_lw + _m['hl_right_mult'] * _left_in, W - 20)
                draw.rounded_rectangle([_box_left, clip_y1, _box_right, clip_y2],
                                       radius=8, fill=active_fill)
                draw.rectangle([_box_left, clip_y1, bx1 - 4, clip_y2], fill=bar_color)
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    # Use vocab_hl (gold or cyan) so vocab boxes stay clearly
                    # visible even when the full sentence block is accent-coloured
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 18, ly, line, vocab_words,
                        font_s, font_s_bold, active_text, vocab_hl)
        else:
            # Upcoming — clearly readable, auto-contrast
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 10, ly, line, vocab_words,
                        font_s, font_s_bold, upcoming_text, _parse_color(accent_color))

    # Page number — centered bottom, visible
    if page_num is not None and total_pages is not None and total_pages > 1:
        font_pg = _default_font(28)
        draw.text((W // 2, H - 28), f'Page {page_num} / {total_pages}',
                  font=font_pg, fill=_parse_color(accent_color), anchor='mm')

    _draw_watermark(img)
    return img


def render_timesup_frame(task_name, sentences, style=None):
    """Render the 'Time is Up' frame."""
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    accent_color = style.get('accent_color', tc['done']) if style else tc['done']
    _draw_decoration(draw, style or {})

    # "TIME IS UP" centered
    font_big = _sfont(72, style, bold=True)
    draw.text((W // 2, H // 3), 'TIME IS UP', font=font_big,
              fill=_parse_color(accent_color), anchor='mm')

    # All sentences below
    font_s = _sfont(28, style)
    _fscale = (style or {}).get('font_scale', 1.0)
    y = H // 3 + 120
    for s in sentences:
        lines = wrap_text(draw, s['text'] if isinstance(s, dict) else s, font_s, 1400)
        for line in lines:
            if y < H - 40:
                draw.text((W // 2, y), line, font=font_s,
                          fill=_parse_color(tc['spoken']), anchor='mt')
                y += int(40 * _fscale)

    _draw_watermark(img)
    return img


_WATERMARK_TEXT = 'youtube.com/@CELPIPSpeaking'


def _draw_watermark(img, corner='bottom-right'):
    """
    Burn a clean italic watermark onto the frame.
    No box — just elegant text with a soft shadow.
    """
    from PIL import Image as _Img, ImageDraw as _ID

    font    = _default_font(20)
    overlay = _Img.new('RGBA', img.size, (0, 0, 0, 0))
    od      = _ID.Draw(overlay)

    bb = od.textbbox((0, 0), _WATERMARK_TEXT, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]

    margin = 24
    if corner == 'bottom-right':
        tx = img.width  - tw - margin
        ty = img.height - th - margin
    else:
        tx = margin
        ty = img.height - th - margin

    # Soft drop shadow (offset 2px, very low opacity)
    for dx, dy in [(1, 1), (2, 2)]:
        od.text((tx + dx, ty + dy), _WATERMARK_TEXT,
                font=font, fill=(0, 0, 0, 55))

    # Main text — white at ~45% opacity, clean and unobtrusive
    od.text((tx, ty), _WATERMARK_TEXT, font=font, fill=(255, 255, 255, 115))

    base = img.convert('RGBA')
    base.alpha_composite(overlay)
    img.paste(base.convert('RGB'))


def _draw_decoration(draw, style, w=W, h=H, img=None):
    """Draw background decoration based on style dict."""
    dec = style.get('decoration', 'none')
    accent = _parse_color(style.get('accent_color', '#f0c040'))
    bg = _parse_color(style.get('bg_color', '#0d0d1f'))

    if dec == 'none':
        pass

    elif dec == 'gradient':
        # Subtle horizontal gradient overlay
        for x in range(0, w, 4):
            ratio = x / w
            alpha = int(15 * math.sin(math.pi * ratio))
            r = min(255, bg[0] + alpha)
            g = min(255, bg[1] + alpha)
            b = min(255, bg[2] + alpha)
            draw.line([(x, 0), (x, h)], fill=(r, g, b))

    elif dec == 'border':
        draw.rectangle([20, 20, w - 20, h - 20], outline=accent, width=4)

    elif dec == 'corner':
        sz = 60
        lw = 4
        # Top-left
        draw.line([(20, 20), (20 + sz, 20)], fill=accent, width=lw)
        draw.line([(20, 20), (20, 20 + sz)], fill=accent, width=lw)
        # Top-right
        draw.line([(w - 20 - sz, 20), (w - 20, 20)], fill=accent, width=lw)
        draw.line([(w - 20, 20), (w - 20, 20 + sz)], fill=accent, width=lw)
        # Bottom-left
        draw.line([(20, h - 20 - sz), (20, h - 20)], fill=accent, width=lw)
        draw.line([(20, h - 20), (20 + sz, h - 20)], fill=accent, width=lw)
        # Bottom-right
        draw.line([(w - 20, h - 20 - sz), (w - 20, h - 20)], fill=accent, width=lw)
        draw.line([(w - 20 - sz, h - 20), (w - 20, h - 20)], fill=accent, width=lw)

    elif dec == 'stripe':
        # Subtle diagonal stripes
        for i in range(-h, w + h, 80):
            draw.line([(i, 0), (i + h, h)], fill=(*accent, 30) if len(accent) == 3
                      else accent, width=2)

    elif dec == 'dots':
        import random
        rng = random.Random(str(style.get('bg_color', '')))
        for _ in range(40):
            x = rng.randint(0, w)
            y = rng.randint(0, h)
            r = rng.randint(2, 8)
            a_color = (*accent[:3],)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=a_color)

    elif dec == 'diagonal':
        # Single diagonal band
        pts = [(0, h // 2), (w // 3, 0), (w // 3 + 20, 0), (20, h // 2)]
        # Subtle fill
        r2 = tuple(min(255, c + 15) for c in _parse_color(style.get('bg_color', BG)))
        draw.polygon(pts, fill=r2)



def render_vocab_intro_frame(task_name, style=None):
    """Intro slide shown before vocabulary pages: 'Vocabulary Builder'."""
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    accent_color = style.get('accent_color', tc['gold']) if style else tc['gold']
    _draw_decoration(draw, style or {})

    # Subtle horizontal accent strip at top
    draw.rectangle([0, 0, W, 6], fill=_parse_color(accent_color))

    # Main label
    font_main = _sfont(88, style, bold=True)
    draw.text((W // 2, H // 2 - 40), 'Vocabulary Builder',
              font=font_main, fill=_parse_color(tc['text']), anchor='mm')

    # Sub-label
    font_sub = _sfont(34, style)
    draw.text((W // 2, H // 2 + 60),
              f'Key words & phrases — {task_name}',
              font=font_sub, fill=_parse_color(tc['upcoming']), anchor='mm')

    # Bottom accent strip
    draw.rectangle([0, H - 6, W, H], fill=_parse_color(accent_color))

    _draw_watermark(img)
    return img


# Vivid part-of-speech label colors (readable on dark backgrounds).
# Cycled by word_idx so each card gets a distinct colour.
_POS_COLORS = [
    (255, 100, 130),   # coral-pink
    (80,  210, 200),   # teal-cyan
    (180, 120, 255),   # violet-purple
    (255, 170,  50),   # amber-orange
    (80,  220, 110),   # lime-green
    (100, 170, 255),   # sky-blue
    (255, 220,  80),   # gold-yellow
    (255, 130,  80),   # warm-orange
]


def render_vocab_page(word, word_type, definition, example, style,
                      word_idx=0, total_words=1):
    """
    Render a vocabulary page.
    Returns PIL Image.

    Args:
        word: the vocabulary word/phrase
        word_type: e.g. "noun", "verb", "phrase"
        definition: definition string
        example: example sentence (word must appear in it)
        style: style dict from style_gen.generate_style()
        word_idx: 0-based index of this word
        total_words: total number of vocab words
    """
    tc = _tc(style)
    bg_color = _parse_color(style.get('bg_color', '#0d0d1f'))
    text_color = _parse_color(style.get('text_color', '#ffffff'))
    accent_color = _parse_color(style.get('accent_color', '#f0c040'))
    word_color = _parse_color(style.get('word_color', '#ffffff'))
    font_regular = style.get('font_regular')
    font_bold_path = style.get('font_bold')
    layout = style.get('layout', 'centered')

    img = Image.new('RGB', (W, H), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Draw decoration
    _draw_decoration(draw, style)

    # ── Top bar ────────────────────────────────────────────────────────────
    bar_h = 70
    draw.rectangle([0, 0, W, bar_h], fill=_parse_color(tc['surface']))
    draw.rectangle([0, bar_h - 2, W, bar_h], fill=accent_color)

    font_top = _load_font(font_bold_path, 20)
    vocab_left_text = 'VOCABULARY BUILDER'
    _sec_num = style.get('section_num') if style else None
    if _sec_num:
        vocab_left_text = f'{vocab_left_text}  ·  {_sec_num}/5'
    draw.text((30, bar_h // 2), vocab_left_text,
              font=font_top, fill=accent_color, anchor='lm')

    # Countdown bullets (top-right): same style as shadowing sentence dots.
    # Starts with total_words dots; each finished word removes one from the right.
    remaining  = total_words - word_idx   # includes current word
    dot_r      = 10
    dot_gap    = 32
    dots_total = remaining * dot_gap - (dot_gap - dot_r * 2)
    dot_start  = W - 30 - dots_total
    dot_y      = bar_h // 2
    for di in range(remaining):
        dx    = dot_start + di * dot_gap + dot_r
        color = accent_color if di == 0 else _parse_color(tc['border'])
        draw.ellipse([dx - dot_r, dot_y - dot_r, dx + dot_r, dot_y + dot_r], fill=color)

    pad = 80
    content_w = W - 2 * pad
    available_h = H - bar_h - 20 - pad  # top bar + gap + bottom padding

    # Auto-scale: start large, reduce until everything fits vertically.
    # Also apply user font_scale multiplier on top.
    _user_scale = style.get('font_scale', 1.0)
    _tmp = ImageDraw.Draw(Image.new('RGB', (W, H)))
    word_size = def_size = ex_size = type_size = 0
    for scale in [1.0, 0.88, 0.76, 0.66, 0.56, 0.48]:
        ws = max(28, int(96 * scale * _user_scale))
        ds = max(18, int(46 * scale * _user_scale))
        es = max(18, int(48 * scale * _user_scale))
        ts = max(16, int(32 * scale * _user_scale))

        fw = _load_font(font_bold_path, ws)
        fd = _load_font(font_regular,   ds)
        fe = _load_font(font_regular,   es)

        wl = wrap_text(_tmp, word,                              fw, content_w)
        dl = wrap_text(_tmp, definition,                        fd, content_w)
        el = wrap_text(_tmp, re.sub(r'[{}]', '', example),     fe, content_w)

        total_h = (
            len(wl) * (ws + 10) +
            ts + 20 +
            len(dl) * (ds + 8) + 16 +
            44 +
            len(el) * (es + 12) + 16 +
            60
        )
        if total_h <= available_h:
            word_size, def_size, ex_size, type_size = ws, ds, es, ts
            break

    if not word_size:
        word_size, def_size, ex_size, type_size = 28, 18, 18, 16

    font_word    = _load_font(font_bold_path, word_size)
    font_type    = _load_font(font_regular,   type_size)
    font_def     = _load_font(font_regular,   def_size)
    font_ex      = _load_font(font_regular,   ex_size)
    font_bold_ex = _load_font(font_bold_path, ex_size)

    # Pick a vivid POS colour that varies per card.
    # Darken on light backgrounds so the colour stays readable (vivid neons
    # like gold-yellow or lime are near-invisible on white without adjustment).
    _raw_pos = _POS_COLORS[word_idx % len(_POS_COLORS)]
    bg_lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    pos_color = tuple(max(0, int(c * 0.52)) for c in _raw_pos) if bg_lum > 170 else _raw_pos

    if layout == 'centered':
        _render_vocab_centered(draw, img, word, word_type, definition, example,
                               font_word, font_type, font_def, font_ex, font_bold_ex,
                               text_color, accent_color, word_color, pad, content_w, tc=tc,
                               pos_color=pos_color)
    elif layout == 'left_heavy':
        _render_vocab_left_heavy(draw, img, word, word_type, definition, example,
                                  font_word, font_type, font_def, font_ex, font_bold_ex,
                                  text_color, accent_color, word_color, pad, content_w,
                                  pos_color=pos_color)
    elif layout == 'bold_top':
        _render_vocab_bold_top(draw, img, word, word_type, definition, example,
                                font_word, font_type, font_def, font_ex, font_bold_ex,
                                text_color, accent_color, word_color, pad, content_w, tc=tc,
                                pos_color=pos_color)
    elif layout == 'minimal':
        _render_vocab_minimal(draw, img, word, word_type, definition, example,
                               font_word, font_type, font_def, font_ex, font_bold_ex,
                               text_color, accent_color, word_color, pad, content_w,
                               pos_color=pos_color)
    elif layout == 'split':
        _render_vocab_split(draw, img, word, word_type, definition, example,
                             font_word, font_type, font_def, font_ex, font_bold_ex,
                             text_color, accent_color, word_color, pad, content_w, tc=tc,
                             pos_color=pos_color)
    else:
        _render_vocab_centered(draw, img, word, word_type, definition, example,
                               font_word, font_type, font_def, font_ex, font_bold_ex,
                               text_color, accent_color, word_color, pad, content_w, tc=tc,
                               pos_color=pos_color)
    _draw_watermark(img)
    return img


def _highlight_word_in_example(draw, x, y, example, word, font_ex, font_bold_ex,
                                text_color, accent_color, max_w):
    """
    Draw example sentence with the vocabulary word highlighted.
    Supports two modes:
      • Marker mode  — if example contains {…} spans, parse them directly.
      • Regex mode   — fallback; matches word and its inflected forms via pattern.
    Returns the final y position.
    """
    # ── Marker mode ─────────────────────────────────────────────────────────
    if '{' in example and '}' in example:
        spans = []
        pos = 0
        for m in re.finditer(r'\{([^}]+)\}', example):
            if m.start() > pos:
                spans.append((example[pos:m.start()], False))
            spans.append((m.group(1), True))
            pos = m.end()
        if pos < len(example):
            spans.append((example[pos:], False))
        if not spans:
            spans = [(re.sub(r'[{}]', '', example), False)]
    else:
        # ── Regex mode (legacy — no markers in example) ──────────────────
        pattern = re.compile(_word_variants_pattern(word), re.IGNORECASE)
        spans = []
        last = 0
        for m in pattern.finditer(example):
            if m.start() > last:
                spans.append((example[last:m.start()], False))
            spans.append((example[m.start():m.end()], True))
            last = m.end()
        if last < len(example):
            spans.append((example[last:], False))

    if not spans:
        spans = [(example, False)]

    # Render word by word across multiple lines
    # First, tokenize spans into words preserving highlight flag
    word_tokens = []  # list of (text, is_highlight, has_space_after)
    for text, is_hl in spans:
        words_in_span = re.split(r'(\s+)', text)
        for w in words_in_span:
            if w.strip():
                word_tokens.append((w, is_hl))
            elif w and word_tokens:
                # Attach space to previous token
                prev = word_tokens[-1]
                word_tokens[-1] = (prev[0] + ' ', prev[1])

    # Now lay out lines manually
    cur_x = x
    cur_y = y
    line_h = font_ex.size + 10 if hasattr(font_ex, 'size') else 46

    dummy_draw = draw  # reuse same draw

    def text_width(t, fnt):
        bb = dummy_draw.textbbox((0, 0), t, font=fnt)
        return bb[2] - bb[0]

    # Pre-compute consistent highlight box bounds from reference glyphs.
    # textbbox returns tight glyph bounds that vary per word (descenders on g/y/p
    # make the box taller). Using 'Ay' captures max ascender+descender so all
    # highlight boxes share the same height regardless of the word content.
    _ref_bb = dummy_draw.textbbox((0, 0), 'Ay', font=font_bold_ex)
    _hl_top_off = _ref_bb[1]   # ascender offset from y
    _hl_bot_off = _ref_bb[3]   # descender bottom offset from y
    pad_box = 4
    ac = accent_color if isinstance(accent_color, tuple) else _parse_color(accent_color)
    hl_txt = (20, 20, 30) if sum(ac) / 3 > 140 else (240, 240, 240)

    for tok, is_hl in word_tokens:
        fnt = font_bold_ex if is_hl else font_ex
        tw = text_width(tok, fnt)

        if cur_x + tw > x + max_w and cur_x > x:
            cur_x = x
            cur_y += line_h

        if is_hl:
            # Strip trailing space — highlight only the word, not the gap after it
            draw_tok = tok.rstrip()
            bb = dummy_draw.textbbox((cur_x, cur_y), draw_tok, font=fnt)
            dummy_draw.rectangle(
                [bb[0] - pad_box,
                 cur_y + _hl_top_off - pad_box,
                 bb[2] + pad_box,
                 cur_y + _hl_bot_off + pad_box],
                fill=accent_color
            )
            dummy_draw.text((cur_x, cur_y), draw_tok, font=fnt, fill=hl_txt)
        else:
            dummy_draw.text((cur_x, cur_y), tok, font=fnt, fill=text_color)

        cur_x += tw

    return cur_y + line_h


def _render_vocab_centered(draw, img, word, word_type, definition, example,
                            font_word, font_type, font_def, font_ex, font_bold_ex,
                            text_color, accent_color, word_color, pad, content_w, tc=None,
                            pos_color=None):
    """Centered layout for vocab page."""
    cx = W // 2
    y = 160

    # Word
    draw.text((cx, y), word, font=font_word, fill=word_color, anchor='mt')
    word_bbox = draw.textbbox((cx, y), word, font=font_word, anchor='mt')
    y = word_bbox[3] + 20

    # Type
    type_col = pos_color if pos_color is not None else accent_color
    draw.text((cx, y), f'({word_type})', font=font_type,
              fill=type_col, anchor='mt')
    y += 40

    # Separator
    draw.rectangle([cx - 200, y, cx + 200, y + 3], fill=accent_color)
    y += 30

    # Definition
    font_def_size = font_def
    def_lines = wrap_text(draw, definition, font_def_size, content_w)
    for line in def_lines:
        draw.text((cx, y), line, font=font_def_size, fill=text_color, anchor='mt')
        y += 44

    y += 40
    # Separator 2
    border_color = tc['border'] if tc else BORDER
    draw.rectangle([pad, y, W - pad, y + 2], fill=_parse_color(border_color))
    y += 30

    # Example label
    font_label = font_type
    draw.text((pad, y), 'Example:', font=font_label, fill=accent_color)
    y += 38

    # Example sentence with highlighting
    _highlight_word_in_example(draw, pad, y, example, word, font_ex, font_bold_ex,
                               text_color, accent_color, content_w)


def _render_vocab_left_heavy(draw, img, word, word_type, definition, example,
                              font_word, font_type, font_def, font_ex, font_bold_ex,
                              text_color, accent_color, word_color, pad, content_w,
                              pos_color=None):
    """Left-heavy layout."""
    left_w = W // 2 - pad
    right_x = W // 2 + pad // 2
    right_w = W - right_x - pad

    y = 200
    # Word on left, large
    draw.text((pad, y), word, font=font_word, fill=word_color)
    wb = draw.textbbox((pad, y), word, font=font_word)
    y = wb[3] + 10

    type_col = pos_color if pos_color is not None else accent_color
    draw.text((pad, y), f'({word_type})', font=font_type, fill=type_col)
    y += 40

    draw.rectangle([pad, y, pad + left_w, y + 3], fill=accent_color)
    y += 20

    def_lines = wrap_text(draw, definition, font_def, left_w)
    for line in def_lines:
        draw.text((pad, y), line, font=font_def, fill=text_color)
        y += 44

    # Right side: example
    ry = 200
    draw.text((right_x, ry), 'Example:', font=font_type, fill=accent_color)
    ry += 38
    _highlight_word_in_example(draw, right_x, ry, example, word, font_ex, font_bold_ex,
                               text_color, accent_color, right_w)


def _render_vocab_bold_top(draw, img, word, word_type, definition, example,
                            font_word, font_type, font_def, font_ex, font_bold_ex,
                            text_color, accent_color, word_color, pad, content_w, tc=None,
                            pos_color=None):
    """Bold top layout: word dominates top third."""
    import random as _rnd
    ac = accent_color if isinstance(accent_color, tuple) else _parse_color(accent_color)
    ac_lum = 0.299 * ac[0] + 0.587 * ac[1] + 0.114 * ac[2]

    # Angled banner — tapers from left to right for a dynamic ribbon look
    _BL, _BR = 228, 192          # left and right banner heights
    draw.polygon([(0, 0), (W, 0), (W, _BR), (0, _BL)], fill=ac)

    # Subtle dot texture within the banner — adds visual pattern, not boring flat colour
    _dot_rng = _rnd.Random(hash(ac))
    dot_col = tuple(min(255, int(c + (255 - c) * 0.28)) for c in ac)
    for _ in range(14):
        dx = _dot_rng.randint(40, W - 40)
        dy = _dot_rng.randint(14, _BL - 28)
        dr = _dot_rng.randint(4, 10)
        draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=dot_col)

    # Word text: white on dark banner, near-black on light banner (contrast-safe)
    banner_text = (255, 255, 255) if ac_lum < 145 else (20, 20, 30)
    draw.text((W // 2, (_BL + _BR) // 4 + 10), word, font=font_word, fill=banner_text, anchor='mm')

    y = _BL + 44
    cx = W // 2
    type_col = pos_color if pos_color is not None else accent_color
    type_col_c = type_col if isinstance(type_col, tuple) else _parse_color(type_col)
    tc_lum = 0.299 * type_col_c[0] + 0.587 * type_col_c[1] + 0.114 * type_col_c[2]
    pill_text_col = (255, 255, 255) if tc_lum < 145 else (20, 20, 30)
    # POS label as a pill badge
    type_bb = draw.textbbox((0, 0), word_type, font=font_type)
    _tw = type_bb[2] - type_bb[0]
    _th = type_bb[3] - type_bb[1]
    _pp = 14       # horizontal padding inside pill
    pill_l = cx - _tw // 2 - _pp
    pill_rx = cx + _tw // 2 + _pp
    pill_t = y
    pill_b = y + _th + 12
    pill_rad = (pill_b - pill_t) // 2
    draw.rounded_rectangle([pill_l, pill_t, pill_rx, pill_b], radius=pill_rad, fill=type_col_c)
    draw.text((cx, pill_t + (pill_b - pill_t) // 2), word_type, font=font_type,
              fill=pill_text_col, anchor='mm')
    y = pill_b + 28

    def_lines = wrap_text(draw, definition, font_def, content_w)
    for line in def_lines:
        draw.text((cx, y), line, font=font_def, fill=text_color, anchor='mt')
        y += 44

    y += 30
    border_color = tc['border'] if tc else BORDER
    draw.rectangle([pad, y, W - pad, y + 2], fill=_parse_color(border_color))
    y += 24

    draw.text((pad, y), 'Example:', font=font_type, fill=accent_color)
    y += 38
    _highlight_word_in_example(draw, pad, y, example, word, font_ex, font_bold_ex,
                               text_color, accent_color, content_w)


def _render_vocab_minimal(draw, img, word, word_type, definition, example,
                           font_word, font_type, font_def, font_ex, font_bold_ex,
                           text_color, accent_color, word_color, pad, content_w,
                           pos_color=None):
    """Minimal clean layout."""
    y = H // 4
    # Word left-aligned large
    draw.text((pad, y), word, font=font_word, fill=accent_color)
    wb = draw.textbbox((pad, y), word, font=font_word)
    y = wb[3] + 8

    type_col = pos_color if pos_color is not None else text_color
    draw.text((pad + 4, y), f'— {word_type}', font=font_type, fill=type_col)
    y += 44

    def_lines = wrap_text(draw, definition, font_def, content_w)
    for line in def_lines:
        draw.text((pad, y), line, font=font_def, fill=text_color)
        y += 44

    y += 30
    draw.text((pad, y), '"', font=font_word, fill=accent_color)
    y_ex = y
    _highlight_word_in_example(draw, pad + 40, y_ex, example, word, font_ex, font_bold_ex,
                               text_color, accent_color, content_w - 40)


def _render_vocab_split(draw, img, word, word_type, definition, example,
                         font_word, font_type, font_def, font_ex, font_bold_ex,
                         text_color, accent_color, word_color, pad, content_w, tc=None,
                         pos_color=None):
    """Split: left panel word+def, right panel example."""
    mid = W // 2

    # Left panel background
    surface_color = tc['surface'] if tc else SURFACE
    draw.rectangle([0, 0, mid, H],
                   fill=tuple(min(255, c + 10) for c in _parse_color(surface_color)))

    # Word
    y = 200
    draw.text((pad, y), word, font=font_word, fill=word_color)
    wb = draw.textbbox((pad, y), word, font=font_word)
    y = wb[3] + 10

    type_col = pos_color if pos_color is not None else accent_color
    draw.text((pad, y), f'({word_type})', font=font_type, fill=type_col)
    y += 40

    draw.rectangle([pad, y, mid - pad, y + 3], fill=accent_color)
    y += 24

    def_lines = wrap_text(draw, definition, font_def, mid - 2 * pad)
    for line in def_lines:
        draw.text((pad, y), line, font=font_def, fill=text_color)
        y += 44

    # Right panel
    rx = mid + pad
    ry = 200
    draw.text((rx, ry), 'Example Sentence', font=font_type, fill=accent_color)
    ry += 38
    draw.rectangle([rx, ry, W - pad, ry + 3], fill=accent_color)
    ry += 24
    _highlight_word_in_example(draw, rx, ry, example, word, font_ex, font_bold_ex,
                               text_color, accent_color, W - rx - pad)


def render_review_frame(task_name, answer, sentences, active_idx, vocab_words,
                        time_remaining, total_time, style=None):
    """
    Render a review section frame.
    Left panel: vocabulary table (word | definition).
    Right panel: answer sentences with active highlighting + vocab word highlight.
    vocab_words: list of dicts {word, definition} or plain strings.
    Returns PIL Image.
    """
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    accent_color = style.get('accent_color', tc['gold']) if style else tc['gold']
    _draw_decoration(draw, style or {})

    left_label = f'CELPIP Speaking · {task_name} · Review'
    timer_str = _format_time(time_remaining)
    _draw_top_bar(draw, left_label, 'REVIEW', accent_color, timer_str, accent_color,
                  show_rec=True, style=style)

    ratio = time_remaining / max(1, total_time)
    _draw_progress_bar(draw, ratio, y_start=80, fill_color=accent_color, style=style)

    bar_bottom = 90
    left_panel_w = 672
    right_panel_x = left_panel_w + 4
    right_panel_w = W - right_panel_x

    # ── Left panel: vocabulary table ──────────────────────────────────────
    lpad = 30
    y = bar_bottom + 24

    _fscale = (style or {}).get('font_scale', 1.0)
    font_header = _sfont(22, style, bold=True)
    draw.text((lpad, y), 'Vocabulary', font=font_header, fill=_parse_color(accent_color))
    y += int(34 * _fscale)
    draw.rectangle([lpad, y, left_panel_w - lpad, y + 2], fill=_parse_color(tc['border']))
    y += 14

    font_word = _sfont(20, style, bold=True)
    font_def  = _sfont(18, style)
    _row_step = int(22 * _fscale)
    def_width = left_panel_w - lpad * 2 - 8

    for item in vocab_words:
        if isinstance(item, dict):
            w_text = item.get('word', '')
            d_text = item.get('definition', '')
        else:
            w_text = str(item)
            d_text = ''

        if y > H - 80:
            break

        # Word on its own line (full panel width — no truncation on long phrases)
        draw.text((lpad, y), w_text, font=font_word, fill=_parse_color(accent_color))
        y += _row_step + 2

        # Definition wrapped below, slightly indented
        if d_text:
            def_lines = wrap_text(draw, d_text, font_def, def_width)
            for dl in def_lines[:3]:
                if y > H - 60:
                    break
                draw.text((lpad + 14, y), dl, font=font_def,
                          fill=_parse_color(tc['text']))
                y += _row_step

        # subtle separator
        draw.rectangle([lpad, y + 4, left_panel_w - lpad, y + 5],
                       fill=_parse_color(tc['border']))
        y += 14

    # Divider
    draw.rectangle([left_panel_w, bar_bottom, left_panel_w + 3, H],
                   fill=_parse_color(tc['border']))

    # Right: sentences with active highlighting + vocab word coloring
    rpad = 30
    panel_y_start = bar_bottom + 10
    panel_y_end = H - 60           # 60px bottom breathing room
    panel_content_h = panel_y_end - panel_y_start

    font_s = _sfont(28, style)
    font_s_bold = _sfont(28, style, bold=True)
    line_h = int(38 * _fscale)
    block_pad = 12

    # Build blocks
    blocks = []
    for i, s in enumerate(sentences):
        text = s['text'] if isinstance(s, dict) else s
        lines = wrap_text(draw, text, font_s, right_panel_w - 2 * rpad - 10)
        h = len(lines) * line_h + 2 * block_pad
        blocks.append({'text': text, 'lines': lines, 'height': h, 'idx': i})

    cumulative = []
    cy = 0
    for b in blocks:
        cumulative.append(cy)
        cy += b['height'] + 8

    scroll = 0
    if active_idx < len(cumulative):
        active_top = cumulative[active_idx]
        desired_top = (panel_content_h - blocks[active_idx]['height']) // 2
        scroll = max(0, min(active_top - desired_top,
                            max(0, cy - panel_content_h)))

    bg_color_s3    = style.get('bg_color', '#080910') if style else '#080910'
    s3_active_fill = _parse_color(accent_color)
    s3_active_text = _contrast_on(accent_color)
    s3_spoken_col  = _spoken_on(bg_color_s3, accent_color)
    s3_upcoming    = _muted_on(bg_color_s3)
    s3_bar_col     = _contrast_on(accent_color)
    s3_vocab_hl    = _vocab_hl_color(accent_color)  # gold or cyan — distinct from active fill

    for i, b in enumerate(blocks):
        block_y = cumulative[i] - scroll + panel_y_start
        if block_y + b['height'] < panel_y_start:
            continue
        if block_y > panel_y_end:
            break

        bx1 = right_panel_x + rpad // 2
        bx2 = W - rpad // 2

        if i < active_idx:
            txt_color = s3_spoken_col
        elif i == active_idx:
            clip_y1 = max(block_y, panel_y_start)
            clip_y2 = min(block_y + b['height'], panel_y_end)
            if clip_y1 < clip_y2:
                draw.rounded_rectangle([bx1, clip_y1, bx2, clip_y2],
                                       radius=6, fill=s3_active_fill)
                draw.rectangle([bx1, clip_y1, bx1 + 8, clip_y2], fill=s3_bar_col)
            txt_color = s3_active_text
        else:
            txt_color = s3_upcoming

        # Draw lines with vocab highlighting
        for j, line in enumerate(b['lines']):
            ly = block_y + block_pad + j * line_h
            if ly < panel_y_start or ly > panel_y_end:
                continue
            lx = bx1 + (18 if i == active_idx else 10)
            # Active sentence bg IS the accent color — use gold/cyan so vocab boxes
            # are clearly distinct. Non-active sentences sit on white — accent is fine.
            vocab_hl_color = s3_vocab_hl if i == active_idx else _parse_color(accent_color)
            _draw_line_with_vocab_highlights(draw, lx, ly, line, vocab_words,
                                             font_s, font_s_bold,
                                             txt_color,
                                             vocab_hl_color)

    _draw_watermark(img)
    return img


def _draw_line_with_vocab_highlights(draw, x, y, line, vocab_words,
                                      font_normal, font_bold,
                                      text_color, highlight_color):
    """Draw a text line, highlighting vocab words.

    Two modes:
      • Marker mode  — if *line* contains ``{...}`` spans, parse them directly.
        The braces are stripped; the enclosed text is rendered highlighted.
      • Regex mode   — legacy fallback; scans *line* for entries in vocab_words
        using morphological pattern matching.
    """
    # ── Marker mode ─────────────────────────────────────────────────────────
    if '{' in line and '}' in line:
        spans = []
        pos = 0
        for m in re.finditer(r'\{([^}]+)\}', line):
            if m.start() > pos:
                spans.append((line[pos:m.start()], False))
            spans.append((m.group(1), True))
            pos = m.end()
        if pos < len(line):
            spans.append((line[pos:], False))
        if not spans:
            spans = [(re.sub(r'[{}]', '', line), False)]
    else:
        # ── Regex mode (legacy — no markers in text) ─────────────────────
        if not vocab_words:
            draw.text((x, y), line, font=font_normal, fill=text_color)
            return

        word_strings = []
        for vw in vocab_words:
            w = vw.get('word', '') if isinstance(vw, dict) else str(vw)
            w = w.strip()
            if w:
                word_strings.append(w)

        if not word_strings:
            draw.text((x, y), line, font=font_normal, fill=text_color)
            return

        all_matches = []
        for vw in word_strings:
            pat = _word_variants_pattern(vw)
            for m in re.finditer(pat, line, re.IGNORECASE):
                all_matches.append((m.start(), m.end()))

        all_matches.sort()
        merged = []
        for start, end in all_matches:
            if merged and start < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append([start, end])

        spans = []
        pos = 0
        for start, end in merged:
            if start > pos:
                spans.append((line[pos:start], False))
            spans.append((line[start:end], True))
            pos = end
        if pos < len(line):
            spans.append((line[pos:], False))

        if not spans:
            spans = [(line, False)]

    # Pre-compute consistent highlight box bounds so all highlighted spans
    # share the same height (tight glyph bounds vary per word due to descenders).
    _ref_bb_normal = draw.textbbox((0, 0), 'Ay', font=font_normal)
    _ref_bb_bold   = draw.textbbox((0, 0), 'Ay', font=font_bold)
    _hl_top = _ref_bb_bold[1]
    _hl_bot = _ref_bb_bold[3]
    # Bold and regular fonts can have different ascender offsets at the same point
    # size. Compensate so bold text aligns to the same visual baseline as regular.
    _bold_y_offset = _ref_bb_normal[1] - _ref_bb_bold[1]
    hc = highlight_color if isinstance(highlight_color, tuple) else _parse_color(highlight_color)
    _hl_lum = 0.299 * hc[0] + 0.587 * hc[1] + 0.114 * hc[2]
    hl_txt = (20, 20, 20) if _hl_lum > 128 else (240, 240, 240)

    cur_x = x
    for text, is_hl in spans:
        fnt = font_bold if is_hl else font_normal
        if is_hl:
            bb = draw.textbbox((cur_x, y), text, font=fnt)
            draw.rectangle([bb[0] - 2, y + _hl_top - 2, bb[2] + 2, y + _hl_bot + 2],
                           fill=highlight_color)
            draw.text((cur_x, y + _bold_y_offset), text, font=fnt, fill=hl_txt)
        else:
            draw.text((cur_x, y), text, font=fnt, fill=text_color)
        tw = draw.textbbox((cur_x, y), text, font=fnt)[2] - cur_x
        cur_x += tw


_SECTION_LABELS = {
    1: ('01', 'Question',            '📋'),
    2: ('02', 'Model Answer',        '📢'),
    3: ('03', 'Vocabulary Building', '📚'),
    4: ('04', 'Shadowing Practice',  '🎯'),
    5: ('05', 'Final Review',        '🔁'),
}


def render_section_transition(section_num, style):
    """
    2-3s transition slide shown between sections.
    Section number above the label in gray, label in main text color.
    """
    bg      = _parse_color(style.get('bg_color', BG))
    accent  = _parse_color(style.get('accent_color', GOLD))
    regular = style.get('font_regular')
    bold_p  = style.get('font_bold')
    tc      = _tc(style)

    img  = Image.new('RGB', (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    _draw_decoration(draw, style)

    num_str, label, emoji = _SECTION_LABELS.get(section_num, ('0', 'Section', ''))

    cx = W // 2
    cy = H // 2

    # Section number — clearly visible in gray ABOVE the label
    _fscale = style.get('font_scale', 1.0)
    gray = _parse_color(tc['upcoming'])
    font_num = _load_font(bold_p, max(10, int(80 * _fscale)))
    draw.text((cx, cy - 120), num_str, font=font_num, fill=gray, anchor='mm')

    # Top accent line
    draw.rectangle([cx - 260, cy - 72, cx + 260, cy - 69], fill=accent)

    # Section label — large, main text color
    font_label = _load_font(bold_p, max(10, int(80 * _fscale)))
    draw.text((cx, cy - 20), label, font=font_label, fill=_parse_color(tc['text']), anchor='mm')

    # Progress dots
    font_dot = _sfont(28, style)
    dot_row = '  ·  '.join(['●' if i + 1 == section_num else '○' for i in range(5)])
    draw.text((cx, cy + 60), dot_row, font=font_dot, fill=accent, anchor='mm')

    # Bottom accent line
    draw.rectangle([cx - 260, cy + 96, cx + 260, cy + 99], fill=accent)

    # ── Channel signature ────────────────────────────────────────────────
    sig_y = cy + 155

    # Small "Watch more on" label in muted color
    font_pre = _load_font(regular, 22)
    draw.text((cx, sig_y), 'Watch more on', font=font_pre,
              fill=_parse_color(tc['upcoming']), anchor='mm')

    # Channel handle in Georgia bold — elegant serif look
    georgia_bold = 'C:/Windows/Fonts/georgiab.ttf'
    font_handle  = _load_font(georgia_bold, 40)
    handle_text  = '@CELPIPSpeaking'
    handle_w     = int(draw.textlength(handle_text, font=font_handle))

    # YouTube-style play button (drawn manually — red rounded rect + white triangle)
    btn_h  = 34
    btn_w  = 50
    gap    = 14
    total_w = btn_w + gap + handle_w
    sx     = cx - total_w // 2
    btn_y  = sig_y + 32

    # Red pill
    draw.rounded_rectangle([sx, btn_y, sx + btn_w, btn_y + btn_h],
                            radius=8, fill=(255, 40, 40))
    # White triangle inside
    tx = sx + btn_w // 2 - 1
    ty = btn_y + btn_h // 2
    tri = [(tx - 8, ty - 9), (tx - 8, ty + 9), (tx + 10, ty)]
    draw.polygon(tri, fill=(255, 255, 255))

    # Handle text
    handle_x = sx + btn_w + gap
    handle_y = btn_y + btn_h // 2
    draw.text((handle_x, handle_y), handle_text,
              font=font_handle, fill=_parse_color(tc['text']), anchor='lm')

    # Thin decorative rule under handle
    rule_w = total_w + 20
    draw.rectangle([cx - rule_w // 2, btn_y + btn_h + 14,
                    cx + rule_w // 2, btn_y + btn_h + 16],
                   fill=accent)

    _draw_watermark(img)
    return img


def render_shadow_frame(sentence_text, sentences, sent_idx, vocab_words,
                         rep, total_reps, phase, bar_ratio, style):
    """
    Render a shadowing practice frame.

    phase: 'tts'   — TTS is playing (speaker icon)
           'pause' — user repeats (depleting bar)
    bar_ratio: 0.0 (empty) → 1.0 (full) — only used in 'pause' phase
    """
    bg      = _parse_color(style.get('bg_color', BG))
    accent  = _parse_color(style.get('accent_color', GOLD))
    regular = style.get('font_regular')
    bold_p  = style.get('font_bold')

    tc   = _tc(style)
    img  = Image.new('RGB', (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    _draw_decoration(draw, style)

    cx = W // 2

    # ── Top bar ─────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 70], fill=_parse_color(tc['surface']))
    draw.rectangle([0, 68, W, 70], fill=accent)

    # Left: SHADOWING PRACTICE label (with section progress suffix)
    font_top = _load_font(bold_p, 20)
    _shad_left = 'SHADOWING PRACTICE'
    _shad_sec  = style.get('section_num') if style else None
    if _shad_sec:
        _shad_left = f'{_shad_left}  ·  {_shad_sec}/5'
    draw.text((30, 35), _shad_left, font=font_top, fill=accent, anchor='lm')

    # Right: shadowing tip (phase-aware instruction)
    tip_text  = 'Listen carefully…' if phase == 'tts' else 'Now repeat aloud!'
    font_ctr  = _load_font(bold_p, 22)
    ctr_bbox  = draw.textbbox((0, 0), tip_text, font=font_ctr)
    ctr_w     = ctr_bbox[2] - ctr_bbox[0] + 28
    ctr_h     = 34
    ctr_x     = W - 30 - ctr_w
    ctr_y     = (70 - ctr_h) // 2
    _draw_rounded_rect(draw, [ctr_x, ctr_y, ctr_x + ctr_w, ctr_y + ctr_h],
                       radius=8, fill=_parse_color(tc['surface']), outline=accent)
    draw.text((W - 30 - ctr_w // 2, 35), tip_text,
              font=font_ctr, fill=accent, anchor='mm')

    # ── Rep indicator (dots) ──────────────────────────────────────────────
    dot_y = 120
    dot_r = 16
    dot_gap = 50
    start_x = cx - ((total_reps - 1) * dot_gap) // 2
    for i in range(total_reps):
        dx = start_x + i * dot_gap
        filled = i < rep
        color = accent if filled else _parse_color(tc['border'])
        draw.ellipse([dx - dot_r, dot_y - dot_r, dx + dot_r, dot_y + dot_r],
                     fill=color)

    font_rep = _load_font(bold_p, 22)
    draw.text((cx, dot_y + dot_r + 16),
              f'Rep {rep} / {total_reps}',
              font=font_rep, fill=accent, anchor='mt')

    # ── Sentence text (center, large) ────────────────────────────────────
    sent_y_center = H // 2 - 20
    _fscale = style.get('font_scale', 1.0)
    font_sent = _load_font(bold_p, max(10, int(58 * _fscale)))
    max_w = W - 200

    # Get vocab word list for highlighting
    vocab_list = []
    for v in (vocab_words or []):
        if isinstance(v, dict):
            vocab_list.append(v.get('word', ''))
        else:
            vocab_list.append(str(v))
    vocab_list = [w for w in vocab_list if w]

    lines = wrap_text(draw, sentence_text, font_sent, max_w)
    # Line height must scale with font to prevent overlap on wrapped sentences
    _sent_bb = draw.textbbox((0, 0), 'Ag', font=font_sent)
    line_h_sent = int((_sent_bb[3] - _sent_bb[1]) * 1.45)
    total_sent_h = len(lines) * line_h_sent
    sent_start_y = sent_y_center - total_sent_h // 2

    for li, line in enumerate(lines):
        ly = sent_start_y + li * line_h_sent
        if vocab_list:
            _draw_line_with_vocab_highlights(
                draw, (W - draw.textbbox((0, 0), line, font=font_sent)[2]) // 2,
                ly, line, vocab_list, font_sent,
                _load_font(bold_p, max(10, int(58 * _fscale))),
                _parse_color(tc['text']), accent
            )
        else:
            draw.text((cx, ly), line, font=font_sent,
                      fill=_parse_color(tc['text']), anchor='mt')

    # ── Phase indicator ───────────────────────────────────────────────────
    bottom_y = H - 180

    if phase == 'tts':
        # Speaker waves
        font_phase = _load_font(bold_p, 30)
        draw.text((cx, bottom_y), 'Listening…', font=font_phase,
                  fill=accent, anchor='mm')

    else:  # pause phase — depleting bar
        font_phase = _load_font(bold_p, 36)
        draw.text((cx, bottom_y - 30), 'Your Turn!', font=font_phase,
                  fill=_parse_color(tc['text']), anchor='mm')

        # Depleting bar
        bar_x1 = cx - 400
        bar_x2 = cx + 400
        bar_top = bottom_y + 10
        bar_bot = bottom_y + 44
        bar_r   = 17

        # Background track
        draw.rounded_rectangle([bar_x1, bar_top, bar_x2, bar_bot],
                               radius=bar_r, fill=_parse_color(tc['border']))

        # Fill (depletes left to right as bar_ratio goes 1 → 0)
        fill_w = int((bar_x2 - bar_x1) * max(0.0, bar_ratio))
        if fill_w > bar_r * 2:
            fill_color = accent
            draw.rounded_rectangle(
                [bar_x1, bar_top, bar_x1 + fill_w, bar_bot],
                radius=bar_r, fill=fill_color
            )

    # ── Bottom: sentence progress dots + remaining label ─────────────────
    n_sents   = len(sentences)
    remaining = n_sents - sent_idx - 1

    dot_r2   = 10
    dot_gap2 = 32
    dots_total_w = n_sents * dot_gap2 - (dot_gap2 - dot_r2 * 2)
    dot_start = cx - dots_total_w // 2
    dots_y    = H - 70

    for di in range(n_sents):
        dx = dot_start + di * dot_gap2 + dot_r2
        if di < sent_idx:
            color = _parse_color(tc['done']) if 'done' in tc else _parse_color(tc['border'])
        elif di == sent_idx:
            color = accent
        else:
            color = _parse_color(tc['border'])
        draw.ellipse([dx - dot_r2, dots_y - dot_r2, dx + dot_r2, dots_y + dot_r2], fill=color)

    font_remain = _load_font(bold_p, 20)
    if remaining > 0:
        remain_text = f'{remaining} sentence{"s" if remaining > 1 else ""} remaining'
        remain_color = _parse_color(tc['upcoming'])
    else:
        remain_text = 'Last sentence!'
        remain_color = accent
    draw.text((cx, H - 30), remain_text, font=font_remain,
              fill=remain_color, anchor='mm')

    _draw_watermark(img)
    return img


def render_final_answer_frame(task_name, sentences, active_idx, vocab_words, style,
                              page_num=None, total_pages=None):
    """
    Section 5: Final answer review — identical visual layout to Section 2.

    sentences   – page subset (already split by compute_page_split)
    active_idx  – index within `sentences` (local, not global)
    page_num    – 1-based page number; None = no indicator
    total_pages – total pages; None = no indicator
    """
    tc = _tc(style)
    img = _new_frame(style)
    draw = ImageDraw.Draw(img)

    accent_color = style.get('accent_color', tc['speak']) if style else tc['speak']
    _draw_decoration(draw, style or {})

    left_label = f'CELPIP Speaking · {task_name}'
    total_s    = len(sentences)
    current_s  = min(active_idx + 1, total_s)

    # Top bar — same 80 px bar + badge as Section 2
    _draw_top_bar(draw, left_label, 'FINAL REVIEW', accent_color,
                  f'{current_s} / {total_s}', accent_color, style=style)

    # Progress bar — position through sentences on this page
    ratio = (active_idx + 1) / max(1, total_s)
    _draw_progress_bar(draw, ratio, y_start=80, fill_color=accent_color, style=style)

    bar_bottom = 90  # same as Section 2

    # ── Sentences panel — exact copy of Section 2 layout ──────────────────────
    _m = _get_margins(style)
    lpad = int(_m['side'])
    rpad = int(_m['side'])
    _fscale = (style or {}).get('font_scale', 1.0)
    panel_y_start = bar_bottom + int(_m['top'])
    panel_y_end   = H - int(_m['bottom'])
    panel_content_h = panel_y_end - panel_y_start

    font_s      = _sfont(36, style)
    font_s_bold = _sfont(36, style, bold=True)
    line_h    = int(48 * _fscale) + int(_m['line_gap'])   # inner line spacing within a sentence
    block_pad = 16
    sent_gap  = int(_m['sentence_gap'])                    # gap between sentence blocks

    _wrap_w = W - lpad - rpad - 26

    blocks = []
    for i, s in enumerate(sentences):
        text  = s['text'] if isinstance(s, dict) else s
        lines = wrap_text(draw, text, font_s, _wrap_w, bold_font=font_s_bold)
        h     = len(lines) * line_h + 2 * block_pad
        blocks.append({'lines': lines, 'height': h, 'idx': i})

    # Scroll so active block is centered — identical to Section 2
    cumulative = []
    cy = 0
    for b in blocks:
        cumulative.append(cy)
        cy += b['height'] + sent_gap
    total_h = cy

    if active_idx < len(cumulative):
        active_top  = cumulative[active_idx]
        desired_top = (panel_content_h - blocks[active_idx]['height']) // 2
        scroll = active_top - desired_top
        scroll = max(0, min(scroll, max(0, total_h - panel_content_h)))
    else:
        scroll = 0

    bg_color      = style.get('bg_color', '#080910') if style else '#080910'
    active_fill   = _parse_color(accent_color)
    active_text   = _contrast_on(accent_color)
    upcoming_text = _muted_on(bg_color)
    spoken_text   = _spoken_on(bg_color, accent_color)
    bar_color     = _contrast_on(accent_color)
    vocab_hl      = _vocab_hl_color(accent_color)

    for i, b in enumerate(blocks):
        block_y = cumulative[i] - scroll + panel_y_start

        if block_y + b['height'] < panel_y_start:
            continue
        if block_y > panel_y_end:
            break

        bx1 = lpad
        bx2 = W - rpad
        by1 = block_y
        by2 = block_y + b['height']

        if i < active_idx:
            # Spoken — same as Section 2
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 10, ly, line, vocab_words,
                        font_s, font_s_bold, spoken_text, _parse_color(accent_color))
        elif i == active_idx:
            # Active — identical highlight to Section 2
            clip_y1 = max(by1, panel_y_start)
            clip_y2 = min(by2, panel_y_end)
            if clip_y1 < clip_y2:
                _box_left = bx1 - 12
                _text_x   = bx1 + 18
                _left_in  = _text_x - _box_left          # 30px
                _max_lw   = max(
                    (draw.textbbox((0, 0), re.sub(r'[{}]', '', ln), font=font_s_bold)[2]
                     for ln in b['lines']),
                    default=0
                )
                _box_right = min(_text_x + _max_lw + _m['hl_right_mult'] * _left_in, W - 20)
                draw.rounded_rectangle([_box_left, clip_y1, _box_right, clip_y2],
                                       radius=8, fill=active_fill)
                draw.rectangle([_box_left, clip_y1, bx1 - 4, clip_y2], fill=bar_color)
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 18, ly, line, vocab_words,
                        font_s, font_s_bold, active_text, vocab_hl)
        else:
            # Upcoming — same as Section 2
            for j, line in enumerate(b['lines']):
                ly = by1 + block_pad + j * line_h
                if panel_y_start <= ly <= panel_y_end:
                    _draw_line_with_vocab_highlights(
                        draw, bx1 + 10, ly, line, vocab_words,
                        font_s, font_s_bold, upcoming_text, _parse_color(accent_color))

    if page_num is not None and total_pages is not None and total_pages > 1:
        font_pg = _default_font(28)
        draw.text((W // 2, H - 28), f'Page {page_num} / {total_pages}',
                  font=font_pg, fill=_parse_color(accent_color), anchor='mm')

    _draw_watermark(img)
    return img


# ── Engage frame helpers ──────────────────────────────────────────────────────

_EMOJI_DIR       = os.path.join(os.path.dirname(__file__), '..', 'data', 'emojis')
_END_MESSAGE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'EndMessage.md')

# Pre-compiled regex to strip emoji / non-BMP characters from message text
_EMOJI_STRIP_RE = re.compile(
    r'[\U0001F000-\U0001FFFF'   # Supplemental symbols, emoticons, transport, etc.
    r'\U00002600-\U000027FF'    # Misc symbols
    r'\U00002B00-\U00002BFF'    # Misc symbols and arrows
    r'\U0000FE00-\U0000FE0F'    # Variation selectors
    r'\U0001FA00-\U0001FAFF'    # Symbols and pictographs extended-A
    r']+',
    flags=re.UNICODE,
)


def _load_end_messages():
    """Return list of clean (emoji-stripped) messages from EndMessage.md."""
    try:
        with open(_END_MESSAGE_PATH, encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]
        cleaned = [_EMOJI_STRIP_RE.sub('', l).strip() for l in lines]
        return [m for m in cleaned if m]
    except Exception:
        return ['Great work! Keep going!']


def _load_emoji_pngs():
    """Return list of paths to available Noto Emoji PNG files."""
    if not os.path.isdir(_EMOJI_DIR):
        return []
    return [
        os.path.join(_EMOJI_DIR, f)
        for f in os.listdir(_EMOJI_DIR)
        if f.endswith('.png')
    ]


# Cached at first use
_CACHED_MESSAGES: list = []
_CACHED_EMOJI_PATHS: list = []

# ── Legacy list kept for reference (no longer used) ───────────────────────────
# _ENGAGE_MESSAGES was a list of (label, setup, punchline) tuples used before
# the emoji-based engage frame was introduced.

_DUMMY_ENGAGE_MESSAGES = [
    ("CELPIP FACT",
     "Band 10 answer to\n'What will you do after the exam?'",
     "Watch this channel again. Obviously."),
    ("PRO TIP",
     "If you talk to yourself\nwhile studying...",
     "Congratulations. That counts as Speaking practice."),
    ("EXAM STRATEGY",
     "Step 1: Study.\nStep 2: Panic.\nStep 3: Study again.",
     "Step 4: Pass. (Step 3 is doing the heavy lifting.)"),
    ("WRITING TASK",
     "Describe your emotions\nafter a 3-hour study session.",
     "Word limit: 150-200. Tears: unlimited."),
    ("LISTENING TASK",
     "You heard 'in conclusion'\nand stopped listening.",
     "The answer was in the next sentence. Classic."),
    ("SPEAKING TASK",
     "You prepared the perfect answer.",
     "The timer beeped before 'Hello.' Great chat."),
    ("VOCABULARY TIP",
     "'Exhausted' is a Band 5 word.",
     "'Utterly drained by the relentless pursuit of fluency'\nis a Band 9 word. Same feeling."),
    ("READING TIP",
     "You re-read the same paragraph\nfour times.",
     "You understood it on the fifth. Progress."),
    # --- self-aware / meta ---
    ("TRUE STORY",
     "We wrote 100 funny messages\nfor this slide.",
     "You got this one. It was handpicked.\n(It was random. But still.)"),
    ("CONFESSION",
     "This slide exists because\nwe ran out of vocab words.",
     "No we didn't. We just wanted to make you smile."),
    ("BEHIND THE SCENES",
     "Our editor spent 6 hours\non this video.",
     "She asked us to mention that.\nShe asked us three times."),
    ("META MOMENT",
     "You are currently watching\na slide about watching slides.",
     "Inception. But for CELPIP."),
    # --- absurd / comedy ---
    ("BREAKING NEWS",
     "Local student stares at\nvocabulary list for 40 minutes.",
     "Absorbs zero words. Somehow still passes. Film at 11."),
    ("SCIENCE",
     "Studies show that students\nwho laugh while studying...",
     "Made that up. But it sounds right. Keep laughing."),
    ("ANCIENT WISDOM",
     "'The journey of a thousand words\nbegins with a single vocab card.'",
     "-- Someone who passed CELPIP. Probably."),
    ("FUN FACT",
     "A goldfish has a 9-second memory.",
     "Still longer than the time\nyou spent on that Reading passage."),
    ("PHILOSOPHY",
     "If you study in the forest\nand no one hears you...",
     "Your Speaking score still counts. Get a study partner."),
    ("LOGIC",
     "You stayed up until 2am studying.",
     "The exam was at 9am.\nThis is a tragedy in two parts."),
    ("HISTORY",
     "In 1847, no one had to take CELPIP.",
     "Those people also had no electricity.\nSwings and roundabouts."),
    ("ECONOMICS",
     "Time spent studying: priceless.\nTime spent worrying about studying:",
     "Also priceless. But significantly less useful."),
    # --- encouragement jokes ---
    ("MOTIVATIONAL",
     "You can do this.",
     "We genuinely mean that.\nThe joke is that it's not a joke."),
    ("COACH SAYS",
     "'Believe in yourself'\nis not just a poster slogan.",
     "It is also a Band 9 speaking strategy.\nUse it."),
    ("HONEST ADVICE",
     "Fluency is not the absence\nof mistakes.",
     "It is the confident continuation\ndespite them. Quote us."),
    ("REMINDER",
     "Your accent is not\nyour band score.",
     "Clarity, structure, and vocabulary are.\nYou have all three. Use them."),
    # --- exam day jokes ---
    ("EXAM DAY TIP",
     "Eat breakfast\nbefore your CELPIP exam.",
     "Your brain runs on glucose,\nnot anxiety. Although anxiety is free."),
    ("LAST-MINUTE ADVICE",
     "Do not cram new vocabulary\nthe night before the exam.",
     "Use words you own.\nNot words you met yesterday."),
    ("TIMING TIP",
     "You have 60 seconds to answer.",
     "That is longer than it sounds\nuntil you are in the room."),
    ("OBSERVATION",
     "You practised your answer\n47 times at home.",
     "The examiner will ask\nquestion number 48. Stay loose."),
    # --- study life ---
    ("STUDY LIFE",
     "Your phone is not\na study tool.",
     "It is a distraction dressed\nas a dictionary. We both know this."),
    ("REAL TALK",
     "You have watched this video\nat 1.5x speed.",
     "Respect. Your time is valuable.\nYour band score will be too."),
    ("NIGHT OWL",
     "3am: 'Just one more practice question.'",
     "7am: 'Just one more hour of sleep.'\nThe cycle is real. We see you."),
    ("PRODUCTIVITY",
     "You made a colour-coded study schedule.",
     "You followed it for exactly one day.\nThe colours were beautiful though."),
]


def render_outro_frame(style=None):
    """
    Section 5 outro / CTA slide shown after Final Review, before the engage slide.
    Encourages viewers to try the next question and subscribe.
    Duration: 5 seconds.
    """
    tc     = _tc(style)
    bg     = _parse_color(style.get('bg_color', '#080910')) if style else _parse_color('#080910')
    accent = _parse_color(style.get('accent_color', GOLD)) if style else _parse_color(GOLD)

    img  = Image.new('RGB', (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    _draw_decoration(draw, style or {})

    cx = W // 2
    cy = H // 2

    # ── Top & bottom accent bars ───────────────────────────────────────────────
    draw.rectangle([0, 0, W, 6], fill=accent)
    draw.rectangle([0, H - 6, W, H], fill=accent)

    # ── Checkmark badge ────────────────────────────────────────────────────────
    badge_r = 60
    badge_y = cy - 200
    draw.ellipse([cx - badge_r, badge_y - badge_r, cx + badge_r, badge_y + badge_r],
                 fill=accent)
    # Draw a checkmark inside the circle
    check_pts = [
        (cx - 30, badge_y),
        (cx - 10, badge_y + 24),
        (cx + 32, badge_y - 26),
    ]
    bg_lum  = sum(bg) / 3
    chk_col = (20, 20, 30) if sum(accent) / 3 > 140 else (240, 240, 240)
    draw.line(check_pts, fill=chk_col, width=7)

    # ── "Practice Complete!" heading ───────────────────────────────────────────
    bold_p    = (style or {}).get('font_bold')
    regular   = (style or {}).get('font_regular')
    text_col  = _parse_color(tc['text'])
    muted_col = _parse_color(tc['upcoming'])

    font_h1 = _load_font(bold_p, 72)
    draw.text((cx, badge_y + badge_r + 50), 'Practice Complete!',
              font=font_h1, fill=text_col, anchor='mt')

    # ── Sub-line ───────────────────────────────────────────────────────────────
    font_sub = _load_font(regular or bold_p, 38)
    draw.text((cx, badge_y + badge_r + 145), 'Great work on all 5 sections.',
              font=font_sub, fill=muted_col, anchor='mt')

    # ── Divider ────────────────────────────────────────────────────────────────
    div_y = badge_y + badge_r + 215
    draw.rectangle([cx - 300, div_y, cx + 300, div_y + 3], fill=accent)

    # ── CTA row: "Try the next question  ·  Subscribe for daily practice" ─────
    font_cta = _load_font(bold_p, 34)
    cta_y    = div_y + 36

    cta1 = 'Try the next question'
    cta2 = 'Subscribe for daily practice'
    dot  = '  ·  '

    full_cta  = cta1 + dot + cta2
    full_w    = draw.textlength(full_cta, font=font_cta)
    cta_start = cx - int(full_w) // 2

    # Draw cta1 in accent, dot in muted, cta2 in accent
    x = cta_start
    for part, col in [(cta1, accent), (dot, muted_col), (cta2, accent)]:
        draw.text((x, cta_y), part, font=font_cta, fill=col, anchor='lt')
        x += int(draw.textlength(part, font=font_cta))

    # ── Channel handle row ─────────────────────────────────────────────────────
    georgia_bold = 'C:/Windows/Fonts/georgiab.ttf'
    font_handle  = _load_font(georgia_bold, 36)
    draw.text((cx, cta_y + 70), '@CELPIPSpeaking',
              font=font_handle, fill=muted_col, anchor='mt')

    _draw_watermark(img)
    return img


def render_engage_frame(seed=None):
    """
    Celebratory slide shown just before the disclaimer.
    Layout: one large Noto Emoji PNG (centered) + a random message from EndMessage.md.
    Emoji PNGs are Apache 2.0 (Google Noto Emoji) — free for commercial use.
    Run download_emojis.py once to populate data/emojis/.
    """
    global _CACHED_MESSAGES, _CACHED_EMOJI_PATHS

    import random as _rng
    rng = _rng.Random(seed)

    # Load messages and emoji paths (cached after first call)
    if not _CACHED_MESSAGES:
        _CACHED_MESSAGES = _load_end_messages()
    if not _CACHED_EMOJI_PATHS:
        _CACHED_EMOJI_PATHS = _load_emoji_pngs()

    message   = rng.choice(_CACHED_MESSAGES)
    emoji_png = rng.choice(_CACHED_EMOJI_PATHS) if _CACHED_EMOJI_PATHS else None

    img  = Image.new('RGB', (W, H), '#0a0a0a')
    draw = ImageDraw.Draw(img)

    cx   = W // 2
    GOLD  = '#f0c040'
    WHITE = '#ffffff'

    # ── Top & bottom accent bars ──────────────────────────────────────────────
    draw.rectangle([0, 0, W, 6],       fill=GOLD)
    draw.rectangle([0, H - 6, W, H],   fill=GOLD)

    EMOJI_SIZE = 380   # px — large and punchy
    font_msg   = _bold_font(60)
    line_h     = font_msg.size + 14

    # ── Wrap message text ─────────────────────────────────────────────────────
    MAX_CHARS = 48
    if len(message) > MAX_CHARS:
        mid      = len(message) // 2
        break_at = message.rfind(' ', 0, mid + 10)
        if break_at == -1:
            break_at = message.find(' ', mid)
        msg_lines = ([message[:break_at].strip(), message[break_at:].strip()]
                     if break_at != -1 else [message])
    else:
        msg_lines = [message]

    # ── Calculate total block height and centre vertically ────────────────────
    GAP       = 40   # px between emoji and text
    text_h    = len(msg_lines) * line_h
    if emoji_png:
        block_h = EMOJI_SIZE + GAP + text_h
    else:
        block_h = text_h

    block_y = (H - block_h) // 2 - 80   # slightly above centre

    if emoji_png:
        # ── Large emoji image, centred horizontally ───────────────────────────
        try:
            emo   = Image.open(emoji_png).convert('RGBA')
            emo   = emo.resize((EMOJI_SIZE, EMOJI_SIZE), Image.LANCZOS)
            emo_x = (W - EMOJI_SIZE) // 2
            img.paste(emo, (emo_x, block_y), emo)
        except Exception:
            pass
        text_y = block_y + EMOJI_SIZE + GAP
    else:
        text_y = block_y

    # ── Message text (bold, white, centred) ───────────────────────────────────
    for line in msg_lines:
        draw.text((cx, text_y), line, font=font_msg,
                  fill=_parse_color(WHITE), anchor='mt')
        text_y += line_h

    _draw_watermark(img)
    return img


def render_disclaimer_frame(style=None):
    """Render the disclaimer frame — black background, red text, all centered."""
    from config import DISCLAIMER_TEXT

    # Always black background regardless of theme
    img  = Image.new('RGB', (W, H), '#000000')
    draw = ImageDraw.Draw(img)

    RED        = '#cc2222'
    RED_BRIGHT = '#ff4444'

    cx = W // 2
    cy = H // 2

    font_header = _bold_font(58)
    font_disc   = _default_font(38)

    line_h = 62
    gap    = 36

    total_h = (
        font_header.size + 8 + 3 +
        gap +
        len(DISCLAIMER_TEXT) * line_h
    )

    y = cy - total_h // 2

    # Header
    draw.text((cx, y), 'EDUCATIONAL DISCLAIMER', font=font_header,
              fill=_parse_color(RED_BRIGHT), anchor='mt')
    y += font_header.size + 8

    # Separator line
    draw.rectangle([cx - 420, y, cx + 420, y + 3], fill=_parse_color(RED))
    y += 3 + gap

    # Disclaimer lines
    for line in DISCLAIMER_TEXT:
        draw.text((cx, y), line, font=font_disc,
                  fill=_parse_color(RED), anchor='mt')
        y += line_h

    _draw_watermark(img)
    return img


# ── YouTube Thumbnail ──────────────────────────────────────────────────────────

_THUMB_W, _THUMB_H = 1280, 720

# Multiple bg variants per band — seed picks one
_THUMB_PALETTES = {
    '7_8': [
        {'bg': '#0d1b2a', 'accent': '#f0c040', 'badge_bg': '#1e3a5a', 'sub': '#a8c4e0'},
        {'bg': '#0a1520', 'accent': '#ffd060', 'badge_bg': '#162840', 'sub': '#90b8d8'},
        {'bg': '#12100a', 'accent': '#f0a830', 'badge_bg': '#2a2010', 'sub': '#c0a870'},
        {'bg': '#1a1200', 'accent': '#ffcc40', 'badge_bg': '#302000', 'sub': '#c0a840'},
        {'bg': '#080d18', 'accent': '#e8b830', 'badge_bg': '#101e38', 'sub': '#8090b8'},
    ],
    '9_10': [
        {'bg': '#0f1e14', 'accent': '#38d48a', 'badge_bg': '#163324', 'sub': '#88c4a0'},
        {'bg': '#081a10', 'accent': '#40e890', 'badge_bg': '#0e2818', 'sub': '#70c090'},
        {'bg': '#0a1a18', 'accent': '#30d0a0', 'badge_bg': '#102820', 'sub': '#80c0a8'},
        {'bg': '#0d1e1a', 'accent': '#50e0a0', 'badge_bg': '#183028', 'sub': '#90ceb8'},
        {'bg': '#081410', 'accent': '#28c880', 'badge_bg': '#0c2018', 'sub': '#68b890'},
    ],
    '11_12': [
        {'bg': '#1a0d2e', 'accent': '#c084fc', 'badge_bg': '#2a1450', 'sub': '#b090d8'},
        {'bg': '#120830', 'accent': '#d090ff', 'badge_bg': '#200c50', 'sub': '#c0a0e8'},
        {'bg': '#1e0a28', 'accent': '#b870f0', 'badge_bg': '#300e40', 'sub': '#a878d0'},
        {'bg': '#16082a', 'accent': '#cc80ff', 'badge_bg': '#241048', 'sub': '#b890e0'},
        {'bg': '#0e0820', 'accent': '#a060e8', 'badge_bg': '#180c38', 'sub': '#9878c8'},
    ],
}
_THUMB_PALETTES_DEFAULT = [
    {'bg': '#0d1220', 'accent': '#f0c040', 'badge_bg': '#1e2a50', 'sub': '#8090b0'},
]

# Background patterns applied before text — seed selects one
# Named color themes — user picks one; pattern stays random via seed.
# Each theme: bg (dark bg), accent (vivid highlight), badge_bg, sub (secondary text).
_THUMB_COLOR_THEMES = {
    'gold':   {'bg': '#0d1b2a', 'accent': '#f0c040', 'badge_bg': '#1e3a5a', 'sub': '#a8c4e0'},
    'green':  {'bg': '#0f1e14', 'accent': '#38d48a', 'badge_bg': '#163324', 'sub': '#88c4a0'},
    'purple': {'bg': '#1a0d2e', 'accent': '#c084fc', 'badge_bg': '#2a1450', 'sub': '#b090d8'},
    'blue':   {'bg': '#080f2a', 'accent': '#4488ff', 'badge_bg': '#102050', 'sub': '#90b4f0'},
    'red':    {'bg': '#1e0808', 'accent': '#ff4444', 'badge_bg': '#3a1010', 'sub': '#e09090'},
    'orange': {'bg': '#1e1008', 'accent': '#ff8c00', 'badge_bg': '#3a2010', 'sub': '#e0b880'},
    'teal':   {'bg': '#081a1e', 'accent': '#00d4d4', 'badge_bg': '#0c3038', 'sub': '#80d4d8'},
    'pink':   {'bg': '#1e0814', 'accent': '#ff60b0', 'badge_bg': '#3a1028', 'sub': '#e090c0'},
    'dark':   {'bg': '#080808', 'accent': '#e0e0e0', 'badge_bg': '#181818', 'sub': '#909090'},
    'navy':   {'bg': '#06091e', 'accent': '#60a8ff', 'badge_bg': '#0c1540', 'sub': '#8090c0'},
}

# Thumbnail font options — (bold_path, regular_path)
_THUMB_FONTS = {
    'segoe':     ('C:/Windows/Fonts/segoeuib.ttf',  'C:/Windows/Fonts/segoeui.ttf'),
    'arial':     ('C:/Windows/Fonts/arialbd.ttf',   'C:/Windows/Fonts/arial.ttf'),
    'impact':    ('C:/Windows/Fonts/impact.ttf',    'C:/Windows/Fonts/impact.ttf'),
    'trebuchet': ('C:/Windows/Fonts/trebucbd.ttf',  'C:/Windows/Fonts/trebuc.ttf'),
    'calibri':   ('C:/Windows/Fonts/calibrib.ttf',  'C:/Windows/Fonts/calibri.ttf'),
    'verdana':   ('C:/Windows/Fonts/verdanab.ttf',  'C:/Windows/Fonts/verdana.ttf'),
    'georgia':   ('C:/Windows/Fonts/georgiab.ttf',  'C:/Windows/Fonts/georgia.ttf'),
}


_THUMB_PATTERNS = [
    'diagonal_bands',   # 2-3 angled bright bands crossing the bg
    'split_diagonal',   # bg split on a diagonal into two tones
    'corner_triangle',  # large filled triangle from a corner
    'horizontal_sweep', # horizontal gradient from left
    'dot_grid',         # regular grid of faint dots
    'chevrons',         # repeating chevron / arrow shapes
    'radial_lines',     # lines radiating from bottom-left
    'cross_hatching',   # subtle cross-hatch lines
    'large_circles',    # overlapping faint circles
    'vertical_bands',   # 3 vertical colour bands
]

_BAND_SHORT = {
    '7_8':   ('Band 7–8', 'Good'),
    '9_10':  ('Band 9–10', 'Strong'),
    '11_12': ('Band 11–12', 'Expert'),
}


def _draw_thumb_pattern(draw, img, pattern, bg, accent, rng, TW, TH):
    """Draw the chosen background pattern onto img/draw."""
    import random as _r
    a = accent  # vivid accent colour tuple

    # Helper: accent with reduced brightness for bg patterns
    def _dim(c, factor=0.18):
        return tuple(int(x * factor) for x in c)

    def _mid(c, factor=0.10):
        return tuple(min(255, bg[i] + int((c[i] - bg[i]) * factor)) for i in range(3))

    if pattern == 'diagonal_bands':
        # 2-4 bold diagonal stripes
        n = rng.randint(2, 4)
        for i in range(n):
            offset = rng.randint(-TH, TW)
            thickness = rng.randint(60, 140)
            pts = [
                (offset, 0), (offset + thickness, 0),
                (offset + thickness + TH, TH), (offset + TH, TH)
            ]
            draw.polygon(pts, fill=_mid(a, 0.14))

    elif pattern == 'split_diagonal':
        # Bg split on a diagonal — right half slightly lighter
        cx = rng.randint(TW // 3, 2 * TW // 3)
        pts = [(cx, 0), (TW, 0), (TW, TH), (cx - TH // 2, TH)]
        lighter = tuple(min(255, bg[i] + 20) for i in range(3))
        draw.polygon(pts, fill=lighter)

    elif pattern == 'corner_triangle':
        # Large filled triangle from a corner
        corner = rng.choice(['tl', 'tr', 'bl', 'br'])
        size_x = rng.randint(TW // 2, int(TW * 0.75))
        size_y = rng.randint(TH // 2, int(TH * 0.75))
        if corner == 'tl':
            pts = [(0, 0), (size_x, 0), (0, size_y)]
        elif corner == 'tr':
            pts = [(TW, 0), (TW - size_x, 0), (TW, size_y)]
        elif corner == 'bl':
            pts = [(0, TH), (size_x, TH), (0, TH - size_y)]
        else:
            pts = [(TW, TH), (TW - size_x, TH), (TW, TH - size_y)]
        draw.polygon(pts, fill=_mid(a, 0.16))

    elif pattern == 'horizontal_sweep':
        # Gradient bands sweeping from left
        steps = 80
        for i in range(steps):
            x = int(TW * i / steps)
            factor = 0.12 * (1 - i / steps)
            c = tuple(min(255, bg[j] + int((a[j] - bg[j]) * factor)) for j in range(3))
            draw.rectangle([x, 0, x + TW // steps + 1, TH], fill=c)

    elif pattern == 'dot_grid':
        spacing = rng.randint(55, 90)
        r = rng.randint(4, 9)
        c = _mid(a, 0.22)
        for gx in range(0, TW + spacing, spacing):
            for gy in range(0, TH + spacing, spacing):
                draw.ellipse([gx - r, gy - r, gx + r, gy + r], fill=c)

    elif pattern == 'chevrons':
        gap   = rng.randint(70, 110)
        thick = rng.randint(3, 7)
        c     = _mid(a, 0.20)
        for ox in range(-TH, TW + TH, gap):
            for y in range(0, TH, 2):
                x1 = ox + y // 2
                x2 = ox + gap // 2 - y // 2
                if 0 <= x1 < TW:
                    draw.line([(x1, y), (x1 + thick, y)], fill=c, width=thick)
                if 0 <= x2 < TW:
                    draw.line([(x2, y), (x2 + thick, y)], fill=c, width=thick)

    elif pattern == 'radial_lines':
        ox = rng.randint(0, TW // 3)
        oy = rng.randint(2 * TH // 3, TH)
        c  = _mid(a, 0.18)
        for angle_deg in range(0, 90, rng.randint(6, 12)):
            angle = math.radians(angle_deg)
            ex = ox + int(math.cos(angle) * TW * 1.5)
            ey = oy - int(math.sin(angle) * TH * 1.5)
            draw.line([(ox, oy), (ex, ey)], fill=c, width=rng.randint(2, 5))

    elif pattern == 'cross_hatching':
        gap   = rng.randint(50, 80)
        c     = _mid(a, 0.14)
        for i in range(-TH, TW + TH, gap):
            draw.line([(i, 0), (i + TH, TH)], fill=c, width=2)
            draw.line([(i + TH, 0), (i, TH)], fill=c, width=2)

    elif pattern == 'large_circles':
        n = rng.randint(3, 6)
        c = _mid(a, 0.15)
        for _ in range(n):
            cx2 = rng.randint(0, TW)
            cy2 = rng.randint(0, TH)
            r2  = rng.randint(120, 280)
            draw.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2],
                         outline=c, width=rng.randint(3, 8))

    elif pattern == 'vertical_bands':
        n = rng.randint(3, 5)
        bw = TW // n
        for i in range(n):
            if i % 2 == 1:
                c = tuple(min(255, bg[j] + 18) for j in range(3))
                draw.rectangle([i * bw, 0, (i + 1) * bw, TH], fill=c)


def _category_thumb_palette(category_slug):
    """
    Build a thumbnail colour palette from a category's brand accent colour.

    Generates a DARK-BG + VIVID-ACCENT palette in the category's hue family,
    matching the professional look of the band palettes (_THUMB_PALETTES).

    Instead of using the raw category color as a solid background (which looks
    flat and garish), we:
      • bg     = very dark, slightly desaturated version of the hue (~10% L)
      • accent = bright, vivid version of the hue (~68% L) — used for score,
                 title text, quality pill — always white-text-safe on dark bg
      • badge  = medium-dark tint (~17% L) for bottom bar, pill fills
      • sub    = lighter muted tint (~72% L) for secondary labels

    All 20 categories produce clearly distinct hue families from one another.
    All use dark bgs so white text is always safe — no contrast issues.
    """
    from modules.style_gen import CATEGORY_ACCENT

    # ── HSL ↔ RGB helpers (inline to avoid external deps) ────────────────
    def _rgb_to_hsl(r, g, b):
        r, g, b = r / 255, g / 255, b / 255
        mx, mn = max(r, g, b), min(r, g, b)
        ll = (mx + mn) / 2
        if mx == mn:
            return (0.0, 0.0, ll)
        d = mx - mn
        ss = d / (2 - mx - mn) if ll > 0.5 else d / (mx + mn)
        if mx == r:   hh = (g - b) / d + (6 if g < b else 0)
        elif mx == g: hh = (b - r) / d + 2
        else:         hh = (r - g) / d + 4
        return (hh * 60, ss, ll)

    def _hsl_to_rgb(hh, ss, ll):
        if ss == 0:
            v = int(ll * 255)
            return (v, v, v)
        def _hue(p, q, t):
            if t < 0: t += 1
            if t > 1: t -= 1
            if t < 1/6: return p + (q - p) * 6 * t
            if t < 1/2: return q
            if t < 2/3: return p + (q - p) * (2/3 - t) * 6
            return p
        q = ll * (1 + ss) if ll < 0.5 else ll + ss - ll * ss
        p = 2 * ll - q
        return (
            int(_hue(p, q, hh/360 + 1/3) * 255),
            int(_hue(p, q, hh/360)       * 255),
            int(_hue(p, q, hh/360 - 1/3) * 255),
        )

    def _t(rgb):
        return '#{:02x}{:02x}{:02x}'.format(
            max(0, min(255, rgb[0])),
            max(0, min(255, rgb[1])),
            max(0, min(255, rgb[2])),
        )

    hex_brand = CATEGORY_ACCENT.get(category_slug, '#1e40af')
    r, g, b   = _parse_color(hex_brand)
    hh, ss, _ = _rgb_to_hsl(r, g, b)

    # bg — very dark, keeps hue identity without being fully black
    bg_rgb     = _hsl_to_rgb(hh, min(ss, 0.65), 0.10)
    # accent — vivid, bright, clearly readable on dark bg
    accent_rgb = _hsl_to_rgb(hh, min(1.0, ss * 1.15), 0.68)
    # badge — slightly lighter than bg (pill fills, bottom bar)
    badge_rgb  = _hsl_to_rgb(hh, min(ss, 0.50), 0.18)
    # sub — light muted tint for secondary labels ("BAND", part line)
    sub_rgb    = _hsl_to_rgb(hh, min(ss * 0.55, 0.45), 0.72)

    return {
        'bg':       _t(bg_rgb),
        'accent':   _t(accent_rgb),
        'badge_bg': _t(badge_rgb),
        'sub':      _t(sub_rgb),
    }


def render_thumbnail(task_num, task_name, band, category, title, seed=None, color_theme=None, thumb_font=None, font_scale=1.0, freq_label=None, freq_color=None, category_slug=None, speaker_label=None):
    """
    Render a 1280×720 YouTube thumbnail.
    Split layout — LEFT: band score hero, RIGHT: title + part badge.
    color_theme: key from _THUMB_COLOR_THEMES; pattern stays random via seed.
    thumb_font: key from _THUMB_FONTS (e.g. 'arial', 'impact'); None = segoe default.
    """
    import random as _r
    rng = _r.Random(seed)  # seed=None → truly random each call

    palettes      = _THUMB_PALETTES.get(band, _THUMB_PALETTES_DEFAULT)
    pal_from_band = rng.choice(palettes)
    if category_slug:
        # Category slug takes priority: thumbnail bg = category brand colour
        pal = _category_thumb_palette(category_slug)
    elif color_theme:
        pal = _THUMB_COLOR_THEMES.get(color_theme, pal_from_band)
    else:
        pal = pal_from_band

    bg     = _parse_color(pal['bg'])
    accent = _parse_color(pal['accent'])
    badge  = _parse_color(pal['badge_bg'])
    sub    = _parse_color(pal['sub'])
    white  = (255, 255, 255)

    # Font resolver for right-side text (applies font_scale)
    _tf = _THUMB_FONTS.get(thumb_font) if thumb_font else None
    def _tf_bold(sz):
        return _load_font(_tf[0], int(sz * font_scale)) if _tf else _bold_font(int(sz * font_scale))
    def _tf_reg(sz):
        return _load_font(_tf[1], int(sz * font_scale)) if _tf else _default_font(int(sz * font_scale))
    def _fs(sz):
        return max(8, int(sz * font_scale))

    pattern = rng.choice(_THUMB_PATTERNS)

    TW, TH = _THUMB_W, _THUMB_H
    img  = Image.new('RGB', (TW, TH), color=bg)
    draw = ImageDraw.Draw(img)

    _draw_thumb_pattern(draw, img, pattern, bg, accent, rng, TW, TH)

    # ── Left accent bar ──────────────────────────────────────────────────
    draw.rectangle([0, 0, 14, TH], fill=accent)

    # Zone geometry — band zone 30%, title zone 70%
    mid  = int(TW * 0.30)   # ≈384 — split point
    lpad = 52               # left content start x
    lcx  = (lpad + mid - 20) // 2   # center of left zone
    lmax = mid - 20 - lpad  # max width for score ≈ 312
    rx   = mid + 28         # right content start x
    rw   = TW - 40 - rx     # right content width ≈ 828

    # Subtle vertical separator line
    sep_col = tuple(min(255, c + 22) for c in bg)
    draw.rectangle([mid - 1, 80, mid + 1, TH - 64], fill=sep_col)

    # ── Top-left: CELPIP SPEAKING label ─────────────────────────────────
    font_label = _bold_font(_fs(30))
    draw.text((lpad, 46), 'CELPIP  SPEAKING', font=font_label, fill=sub, anchor='lm')
    lw = int(draw.textlength('CELPIP  SPEAKING', font=font_label))
    draw.rectangle([lpad, 60, lpad + lw, 64], fill=accent)

    # ── LEFT HERO: Band score ─────────────────────────────────────────────
    band_line, band_tag = _BAND_SHORT.get(band, ('Band', ''))
    score_str = band_line.replace('Band ', '')   # "7–8" / "9–10" / "11–12"

    # Auto-scale to fit left zone width
    score_font = _bold_font(_fs(140))
    for sz in [280, 240, 210, 180, 155, 140]:
        f = _bold_font(_fs(sz))
        if draw.textlength(score_str, font=f) <= lmax:
            score_font = f
            break

    font_band_lbl = _bold_font(_fs(46))
    font_quality  = _bold_font(_fs(32))
    lbl_h  = 54
    qual_h = 50

    score_bb = draw.textbbox((0, 0), score_str, font=score_font)
    score_h  = score_bb[3] - score_bb[1]

    main_top = 84
    main_bot = TH - 64
    main_cy  = (main_top + main_bot) // 2
    total_hero_h = lbl_h + 10 + score_h + 18 + qual_h
    hero_top = main_cy - total_hero_h // 2

    # "BAND" label
    lbl_y = hero_top + lbl_h // 2
    draw.text((lcx, lbl_y), 'BAND', font=font_band_lbl, fill=sub, anchor='mm')

    # Score number
    score_y = lbl_y + lbl_h // 2 + 10
    draw.text((lcx, score_y), score_str, font=score_font, fill=accent, anchor='mt')

    # Quality pill ("Good" / "Strong" / "Expert")
    score_b = draw.textbbox((lcx, score_y), score_str, font=score_font, anchor='mt')
    qual_y  = score_b[3] + 18
    qw = int(draw.textlength(band_tag, font=font_quality)) + 48
    qx1 = lcx - qw // 2
    qx2 = lcx + qw // 2
    draw.rounded_rectangle([qx1, qual_y, qx2, qual_y + qual_h], radius=10, fill=badge)
    draw.rounded_rectangle([qx1, qual_y, qx2, qual_y + qual_h], radius=10, outline=accent, width=2)
    draw.text((lcx, qual_y + qual_h // 2), band_tag, font=font_quality, fill=accent, anchor='mm')

    # ── RIGHT: Title → Category → Part · Task name (vertical stack) ─────────
    display_title = title if title else (task_name if task_name else category)

    # Title — largest, most prominent
    font_title = _tf_bold(80)
    title_lines = _thumb_wrap(draw, display_title.upper(), font_title, rw)
    if len(title_lines) > 2:
        font_title = _tf_bold(66)
        title_lines = _thumb_wrap(draw, display_title.upper(), font_title, rw)
    if len(title_lines) > 3:
        font_title = _tf_bold(54)
        title_lines = _thumb_wrap(draw, display_title.upper(), font_title, rw)

    title_line_h  = int(font_title.size * 1.25)
    title_total_h = len(title_lines) * title_line_h

    # Category chip — white pill with dark text for distinct contrast
    font_cat = _tf_bold(36)
    cat_text  = category if category else ''
    cat_pad_x, cat_pad_y, cat_r = 22, 11, 9
    cat_tw    = int(draw.textlength(cat_text, font=font_cat)) if cat_text else 0
    cat_chip_h = int(font_cat.size) + cat_pad_y * 2

    # Part · Task name line
    part_label = f'Part {task_num:02d}'
    if task_name and task_name.upper() != display_title.upper():
        part_line = f'{part_label}  ·  {task_name}'
    else:
        part_line = part_label
    font_part = _tf_bold(38)  # _tf_bold already applies font_scale
    part_line_h = int(font_part.size * 1.4)

    gap = 20
    block_h = title_total_h + gap + cat_chip_h + gap + part_line_h
    block_y  = main_cy - block_h // 2

    # Draw title lines — always white on the dark category bg
    for k, line in enumerate(title_lines[:3]):
        draw.text((rx, block_y + k * title_line_h), line,
                  font=font_title, fill=white, anchor='lm')

    # Draw category chip + optional freq chip on same row
    cat_y = block_y + title_total_h + gap
    chip_x = rx
    if cat_text:
        cx1 = chip_x
        cx2 = chip_x + cat_tw + cat_pad_x * 2
        cy1 = cat_y
        cy2 = cat_y + cat_chip_h
        # Always white pill with bg-tinted text — works on all dark bgs
        draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=cat_r, fill=white)
        draw.text((chip_x + cat_pad_x, cy1 + cat_chip_h // 2), cat_text,
                  font=font_cat, fill=bg, anchor='lm')
        chip_x = cx2 + 14  # advance past category chip

    # freq_label chip intentionally not drawn on thumbnail

    # Draw part · task name line
    part_y = cat_y + cat_chip_h + gap
    draw.text((rx, part_y), part_line, font=font_part, fill=sub, anchor='lm')

    # ── Bottom bar ───────────────────────────────────────────────────────
    bar_h = 60
    draw.rectangle([14, TH - bar_h, TW, TH], fill=badge)

    # Top accent line of bottom bar: priority colour if available, else theme accent
    if freq_label and freq_color:
        bar_accent = _parse_color(freq_color)
    else:
        bar_accent = accent
    draw.rectangle([14, TH - bar_h, TW, TH - bar_h + 4], fill=bar_accent)

    font_bottom = _bold_font(_fs(26))

    if freq_label:
        # Left: priority label in priority colour
        fc = _parse_color(freq_color) if freq_color else accent
        draw.text((30, TH - bar_h // 2), freq_label,
                  font=font_bottom, fill=fc, anchor='lm')
        # Right: studio name
        draw.text((TW - 20, TH - bar_h // 2),
                  'CELPIP Practice Studio  ·  Speaking Test Preparation',
                  font=font_bottom, fill=sub, anchor='rm')
    else:
        draw.text((TW // 2, TH - bar_h // 2),
                  'CELPIP Practice Studio  ·  Speaking Test Preparation',
                  font=font_bottom, fill=sub, anchor='mm')

    # ── Speaker box (bottom-right, above bottom bar) ─────────────────────
    if speaker_label:
        import re as _re
        # Parse "Heart (US, Female)" → name="Heart", accent="US · Female"
        _m = _re.match(r'^(.+?)\s*\(([^)]+)\)$', speaker_label)
        if _m:
            _spk_name   = _m.group(1).strip()
            _spk_accent = _m.group(2).strip().replace(', ', ' · ')
        else:
            _spk_name   = speaker_label
            _spk_accent = ''

        _font_spk_name   = _bold_font(_fs(28))
        _font_spk_accent = _tf_reg(_fs(22)) if _tf else _default_font(_fs(22))

        _spk_lbl1 = f'Speaker: {_spk_name}'
        _spk_lbl2 = _spk_accent

        _tw1 = int(draw.textlength(_spk_lbl1, font=_font_spk_name))
        _tw2 = int(draw.textlength(_spk_lbl2, font=_font_spk_accent)) if _spk_lbl2 else 0
        _box_w = max(_tw1, _tw2) + 28
        _line_h1 = int(_font_spk_name.size * 1.3)
        _line_h2 = int(_font_spk_accent.size * 1.3) if _spk_lbl2 else 0
        _box_h   = _line_h1 + (_line_h2 + 4 if _spk_lbl2 else 0) + 16
        _box_pad = 14   # margin from right edge / bottom bar

        _bx2 = TW - _box_pad
        _bx1 = _bx2 - _box_w
        _by2 = TH - bar_h - _box_pad   # sit just above the bottom bar
        _by1 = _by2 - _box_h

        # Semi-transparent dark pill background
        _spk_bg = Image.new('RGBA', (_box_w, _box_h), (0, 0, 0, 0))
        _spk_dr = ImageDraw.Draw(_spk_bg)
        _spk_dr.rounded_rectangle([0, 0, _box_w - 1, _box_h - 1], radius=10,
                                   fill=(0, 0, 0, 170))
        _spk_dr.rounded_rectangle([0, 0, _box_w - 1, _box_h - 1], radius=10,
                                   outline=accent + (200,), width=2)
        img.paste(_spk_bg, (_bx1, _by1), _spk_bg)

        # Text
        _tx = _bx1 + 14
        _ty1 = _by1 + 8
        draw.text((_tx, _ty1), _spk_lbl1, font=_font_spk_name, fill=(255, 255, 255))
        if _spk_lbl2:
            _ty2 = _ty1 + _line_h1 + 2
            draw.text((_tx, _ty2), _spk_lbl2, font=_font_spk_accent, fill=sub)

    return img


def _thumb_wrap(draw, text, font, max_w):
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_intro_frame(task_num, task_name, band, category, title,
                        seed=None, color_theme=None, thumb_font=None, font_scale=1.0,
                        freq_label=None, freq_color=None, category_slug=None, speaker_label=None):
    """
    Render the thumbnail scaled to 1920×1080 for use as the video intro frame.
    Both thumbnail (1280×720) and video (1920×1080) are 16:9, so it's a clean 1.5× upscale.
    """
    from PIL import Image as _Image
    thumb = render_thumbnail(task_num, task_name, band, category, title,
                              seed=seed, color_theme=color_theme, thumb_font=thumb_font,
                              font_scale=font_scale, freq_label=freq_label, freq_color=freq_color,
                              category_slug=category_slug, speaker_label=speaker_label)
    return thumb.resize((W, H), _Image.LANCZOS)


def save_thumbnail(task_num, task_name, band, category, title, out_path,
                   seed=None, color_theme=None, thumb_font=None, font_scale=1.0,
                   category_slug=None):
    """Render and save the YouTube thumbnail as a JPEG."""
    img = render_thumbnail(task_num, task_name, band, category, title,
                           seed=seed, color_theme=color_theme, thumb_font=thumb_font,
                           font_scale=font_scale, category_slug=category_slug)
    img.save(out_path, 'JPEG', quality=95)
    return out_path
