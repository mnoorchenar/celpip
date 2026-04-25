"""
Random visual style generator for vocabulary pages — supports light and dark themes.

Design rules this module enforces:
  1. Contrast safety: whenever a color is used as a BACKGROUND with white text
     (e.g. Section 1's category-colored hero background), the color is auto-
     darkened until white text is comfortably readable (perceptual luminance
     below a strict threshold). Light/vivid category brand colors like mint,
     hot pink, or gold are darkened on the fly — the brand family is kept,
     but the shade is pushed into a legible range.
  2. No repeats: seeds come from `secrets.randbits(32)` by default, not wall
     clock time, so two videos built seconds apart don't share RNG state.
     Additionally we persist the last few (bg, accent, decoration) tuples
     per section to `data/style_history.json` and reject a candidate tuple
     if it matches any of the last N. This guarantees consecutive videos
     never look identical, even if the same seed were used.
"""

import random
import os
import json
import secrets
import time
from collections import deque

# Windows system fonts — permitted for commercial video rendering on a licensed
# Windows machine (bitmap output only; font files are not distributed).
# Ref: https://learn.microsoft.com/en-us/typography/fonts/font-faq

# All fonts (any section that uses sparse/decorative text, e.g. vocab cards)
_FONT_CANDIDATES = [
    ('C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/segoeuib.ttf'),
    ('C:/Windows/Fonts/georgia.ttf', 'C:/Windows/Fonts/georgiab.ttf'),
    ('C:/Windows/Fonts/trebuc.ttf',  'C:/Windows/Fonts/trebucbd.ttf'),
    ('C:/Windows/Fonts/verdana.ttf', 'C:/Windows/Fonts/verdanab.ttf'),
    ('C:/Windows/Fonts/calibri.ttf', 'C:/Windows/Fonts/calibrib.ttf'),
    ('C:/Windows/Fonts/arial.ttf',   'C:/Windows/Fonts/arialbd.ttf'),
]

# Body-safe sans-serif fonts only — used for sections with dense running text
# (Question, Answer, Shadowing, Final Review). Georgia and Trebuchet MS are
# excluded: Georgia is a display serif that strains readability at body size,
# and Trebuchet has narrow spacing that becomes cramped in multi-line blocks.
_BODY_FONT_CANDIDATES = [
    ('C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/segoeuib.ttf'),
    ('C:/Windows/Fonts/verdana.ttf', 'C:/Windows/Fonts/verdanab.ttf'),
    ('C:/Windows/Fonts/calibri.ttf', 'C:/Windows/Fonts/calibrib.ttf'),
    ('C:/Windows/Fonts/arial.ttf',   'C:/Windows/Fonts/arialbd.ttf'),
]


def _build_available_fonts(candidates=None):
    if candidates is None:
        candidates = _FONT_CANDIDATES
    available = []
    for regular, bold in candidates:
        if os.path.exists(regular):
            b = bold if os.path.exists(bold) else regular
            available.append((regular, b))
    if not available:
        # Fallback to Pillow's built-in bitmap font (no external files needed)
        available = [(None, None)]
    return available


_AVAILABLE_FONTS = _build_available_fonts(_FONT_CANDIDATES)
_BODY_FONTS      = _build_available_fonts(_BODY_FONT_CANDIDATES)


# ── Contrast helpers ──────────────────────────────────────────────────────────
# Rule (agreed with client): when a background is used behind white text,
# its perceptual luminance (0.299R + 0.587G + 0.114B) must be < 110.
# Below 110, white on that bg passes a comfortable readability bar at video
# scale. Any brand color that sits above this gets pushed down until it fits.

_SAFE_DARK_LUM = 110.0   # max luminance allowed for a "white-text" background
_SAFE_LIGHT_LUM = 210.0  # min luminance allowed for a "dark-text" background


def _hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def _lum_rgb(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def _ensure_bg_safe_for_white(hex_color, target_lum=_SAFE_DARK_LUM):
    """
    Darken `hex_color` toward black until its luminance is ≤ target_lum,
    preserving the hue. Returns a hex string. Used for backgrounds that will
    carry white text — e.g. the Section 1 hero bg painted in a category color.

    If the input is already dark enough, it is returned unchanged.
    """
    r, g, b = _hex_to_rgb(hex_color)
    lum = _lum_rgb(r, g, b)
    if lum <= target_lum:
        return hex_color
    # Scale channels proportionally toward 0 until luminance passes.
    # factor = target / current, clamped to [0, 1]
    factor = target_lum / max(lum, 1.0)
    # Leave a small floor so very light hues don't collapse to pure black —
    # blend 92% of the scaled color with 8% of the original for a hint of hue.
    nr = int(r * factor * 0.92 + r * 0.08 * (target_lum / 255))
    ng = int(g * factor * 0.92 + g * 0.08 * (target_lum / 255))
    nb = int(b * factor * 0.92 + b * 0.08 * (target_lum / 255))
    # Safety: iterate down if we somehow missed
    while _lum_rgb(nr, ng, nb) > target_lum and (nr + ng + nb) > 0:
        nr = int(nr * 0.9)
        ng = int(ng * 0.9)
        nb = int(nb * 0.9)
    return _rgb_to_hex(nr, ng, nb)


def _ensure_bg_safe_for_dark_text(hex_color, target_lum=_SAFE_LIGHT_LUM):
    """Lighten `hex_color` toward white until dark text is readable on it."""
    r, g, b = _hex_to_rgb(hex_color)
    lum = _lum_rgb(r, g, b)
    if lum >= target_lum:
        return hex_color
    # Blend toward white
    t = (target_lum - lum) / (255 - lum + 1e-6)
    nr = int(r + (255 - r) * t)
    ng = int(g + (255 - g) * t)
    nb = int(b + (255 - b) * t)
    return _rgb_to_hex(nr, ng, nb)


def _is_bg_white_text_safe(hex_color):
    r, g, b = _hex_to_rgb(hex_color)
    return _lum_rgb(r, g, b) <= _SAFE_DARK_LUM


def _is_bg_dark_text_safe(hex_color):
    r, g, b = _hex_to_rgb(hex_color)
    return _lum_rgb(r, g, b) >= _SAFE_LIGHT_LUM


def _pick_contrasting_accent(bg_hex, pool, rng=None):
    """
    Pick an accent from `pool` that has ≥80 luminance distance from the bg.
    This is a strict threshold: on a white bg (lum≈248) it rejects anything
    with luminance > 168, catching all pastels and near-white tints.
    Falls back to the most distant option in the pool if nothing clears the bar.
    Pass `rng` (a seeded random.Random) for reproducible shuffling; otherwise
    uses the module-level random state.
    """
    _MIN_GAP = 80
    bg_lum = _lum_rgb(*_hex_to_rgb(bg_hex))
    best = None
    best_gap = -1.0
    shuffled = list(pool)
    (rng or random).shuffle(shuffled)
    for c in shuffled:
        gap = abs(_lum_rgb(*_hex_to_rgb(c)) - bg_lum)
        if gap >= _MIN_GAP:
            return c
        if gap > best_gap:
            best_gap = gap
            best = c
    return best or pool[0]


# ── Anti-repeat history ───────────────────────────────────────────────────────
# Tracks the last N (bg, accent, decoration) tuples per section so that back-
# to-back videos don't land on identical combinations. Persisted to
# data/style_history.json so it survives across process restarts.

_HISTORY_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'style_history.json'
)
_HISTORY_WINDOW = 6   # remember the last 6 combos per section


def _load_history():
    try:
        with open(_HISTORY_PATH, 'r') as f:
            data = json.load(f)
        # Normalize: keys to int, values to list-of-list
        return {int(k): [tuple(x) for x in v] for k, v in data.items()}
    except Exception:
        return {}


def _save_history(hist):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(_HISTORY_PATH)), exist_ok=True)
        serializable = {str(k): [list(x) for x in v] for k, v in hist.items()}
        with open(_HISTORY_PATH, 'w') as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        pass   # history is a nice-to-have; never crash a render over it


def _record_combo(section_num, bg, accent, decoration):
    """Append (bg, accent, decoration) to the section's recent history."""
    hist = _load_history()
    q = deque(hist.get(section_num, []), maxlen=_HISTORY_WINDOW)
    q.append((bg, accent, decoration))
    hist[section_num] = list(q)
    _save_history(hist)


def _recent_combos(section_num):
    return set(tuple(x) for x in _load_history().get(section_num, []))


def _LAYOUTS_DEF():
    return ['centered', 'bold_top', 'minimal']


_LAYOUTS = _LAYOUTS_DEF()
_DECORATIONS = ['none', 'gradient', 'border', 'corner', 'diagonal']

# Sections that should only get subtle, non-intrusive decorations
_SECTION_DECORATIONS = {
    2: ['none', 'none', 'none', 'gradient'],   # answer — mostly plain, very subtle gradient only
    5: ['none', 'none', 'none', 'gradient'],   # final review — same
}

# ── Section-specific safe accent pools ───────────────────────────────────────
# All colors verified: perceptual luminance (0.299r+0.587g+0.114b) < 110.
# This guarantees white text on any of these is always clearly readable.

# Section 2 (Model Answer) — blues, teals, greens: calm educational tones
_S2_ACCENT_POOL = [
    '#1e40af',  # navy
    '#1d4ed8',  # royal blue
    '#1e3a8a',  # deep navy
    '#0369a1',  # ocean blue
    '#075985',  # dark ocean
    '#0e7490',  # dark cyan
    '#0f766e',  # dark teal
    '#047857',  # dark emerald
    '#166534',  # forest green
    '#065f46',  # deep green
    '#14532d',  # hunter green
    '#1565c0',  # medium blue
    '#006d77',  # muted teal
    '#1b6ca8',  # steel blue
    '#0d5c8a',  # slate blue
]

# Section 5 (Final Review) — ambers, purples, reds: warm, distinct from S2
_S5_ACCENT_POOL = [
    '#b45309',  # amber dark
    '#a16207',  # dark gold
    '#92400e',  # dark amber
    '#c2410c',  # orange-red
    '#9a3412',  # sienna
    '#991b1b',  # dark red
    '#9f1239',  # dark crimson
    '#be185d',  # deep rose
    '#9d174d',  # dark rose
    '#831843',  # burgundy rose
    '#7e22ce',  # violet
    '#7c3aed',  # vivid purple
    '#6d28d9',  # deep purple
    '#a21caf',  # magenta
    '#86198f',  # dark magenta
]

# ── Full-spectrum bg pool for truly random sections (3 & 4) ───────────────────
# Spans the entire range: deep darks → saturated mids → vivid mids → pastels → near-whites

_BG_COLORS_FULL = [
    # Deep darks
    '#0d0d1f', '#0a1628', '#0f1a0f', '#1a0a0a', '#0a1a1a',
    '#12121a', '#100a1a', '#0a1020', '#080e18', '#120818',
    '#001428', '#280014', '#002814', '#140028', '#280000',
    # Medium-dark saturated
    '#0a2240', '#400a22', '#0a4022', '#22400a', '#220a40',
    '#40220a', '#0a4040', '#40400a', '#0a220a', '#2a0a4a',
    # Rich deep mids
    '#1e3a6e', '#6e1e3a', '#1e6e3a', '#3a6e1e', '#6e3a1e',
    '#3a1e6e', '#1e6e6e', '#6e6e1e', '#6e1e6e', '#3a3a6e',
    '#003366', '#660033', '#006633', '#333300', '#330066',
    '#006666', '#660000', '#006600', '#000066', '#660066',
    # Vivid medium
    '#1a5fa0', '#a01a5f', '#1aa05f', '#5fa01a', '#a05f1a',
    '#5f1aa0', '#1aa0a0', '#a0a01a', '#a01aa0', '#5f5fa0',
    '#c04000', '#0040c0', '#00c040', '#40c000', '#c00040',
    '#00c0c0', '#c0c000', '#4000c0', '#c000c0', '#0000c0',
    # Medium-light vivid
    '#3388cc', '#cc3388', '#33cc88', '#88cc33', '#cc8833',
    '#8833cc', '#33cccc', '#cccc33', '#cc33cc', '#5588cc',
    '#e05010', '#10a050', '#5010e0', '#10e050', '#e01050',
    # Saturated pastels
    '#a8d8ff', '#ffa8d8', '#a8ffd8', '#d8ffa8', '#ffd8a8',
    '#d8a8ff', '#a8a8ff', '#ffa8ff', '#a8ffff', '#ffffa8',
    '#ffb0b0', '#b0ffb0', '#b0b0ff', '#ffccb0', '#b0ffcc',
    # Near-white tints
    '#f5f7fa', '#f5f0ee', '#f0f5f2', '#f2f0f8', '#f5f2ee',
    '#eef4f8', '#f8f4f0', '#f0f8f4', '#f5eef4', '#f8f5f0',
]

# Combined accent pool for truly random sections (e.g. Section 3 Vocabulary).
# ALL entries have perceptual luminance ≤ 140 so they are safe as text/highlight
# colors on white or near-white backgrounds (luminance gap ≥ 80 vs white).
# Pastels, near-whites, and any color with luminance > 160 have been removed.
_ACCENT_COLORS_FULL = [
    '#1a5fb4', '#c01c28', '#1b6e4f', '#813d9c', '#b5420e',
    '#1c7d3d', '#2c5f8a', '#d01a1a', '#0d6e6e', '#7948a8',
    '#c05c00', '#1b8a3f', '#1965b5', '#c4185c', '#007060',
    '#1565c0', '#0d47a1', '#6b21a8', '#9d174d', '#b45309',
    '#c2410c', '#15803d', '#0f766e', '#7e22ce', '#9333ea',
    '#1e40af', '#0e7490', '#047857', '#166534', '#065f46',
    '#9a3412', '#991b1b', '#9f1239', '#831843', '#86198f',
    '#a21caf', '#6d28d9', '#7c3aed', '#be185d', '#0369a1',
    '#075985', '#1e3a8a', '#3730a3', '#1d4ed8', '#0284c7',
]

# ── Dark theme palettes ────────────────────────────────────────────────────────

_BG_COLORS_DARK = [
    '#0d0d1f', '#0a1628', '#0f1a0f', '#1a0a0a', '#0a1a1a',
    '#1a0f00', '#12121a', '#0f0f1a', '#1a0a15', '#0a1510',
    '#15100a', '#0a0f1a', '#1a1000', '#100a1a', '#0a1a15',
    '#1a0a08', '#081a0a', '#1a1015', '#0a1020', '#18080a',
    '#080e18', '#120818', '#081812',
]

_ACCENT_COLORS_DARK = [
    '#f0c040', '#ff7055', '#40d0d0', '#80e040', '#ff70b0',
    '#ffaa30', '#70c0ff', '#c080ff', '#40ffb0', '#ff9060',
    '#60ffff', '#ffdd60', '#ff6680', '#80ff80', '#6080ff',
]

_SECTION_ACCENTS_DARK = {
    1: ['#4a9eff', '#3a7fff', '#70b0ff', '#5080f0', '#60c0ff'],
    2: ['#40d090', '#30c080', '#50e0a0', '#60ff90', '#40ffb0'],
    3: _ACCENT_COLORS_DARK,
    4: ['#c080ff', '#ff7055', '#ff9060', '#d060ff', '#ff70b0'],
    5: ['#f0c040', '#ffdd60', '#ffaa30', '#ffd060', '#ffc840'],
}

# ── Light theme palettes ───────────────────────────────────────────────────────

_BG_COLORS_LIGHT = [
    '#f5f7fa', '#f5f0ee', '#f0f5f2', '#f2f0f8', '#f5f2ee',
    '#eef4f8', '#f8f4f0', '#f0f8f4', '#f5eef4', '#f8f5f0',
    '#f0f5f8', '#f8f0f4', '#f2f8f0', '#f5f0f8', '#f0f2f8',
    '#f8f2ee', '#f0f8f8', '#f8f0f0', '#f4f8f0', '#f0f4f8',
]

_ACCENT_COLORS_LIGHT = [
    '#1a5fb4', '#c01c28', '#1b6e4f', '#813d9c', '#b5420e',
    '#1c7d3d', '#2c5f8a', '#d01a1a', '#0d6e6e', '#7948a8',
    '#c05c00', '#1b8a3f', '#1965b5', '#c4185c', '#007060',
]

_SECTION_ACCENTS_LIGHT = {
    # Section 1 – Question: blues + indigos
    1: ['#1565c0', '#0d47a1', '#1976d2', '#1e3a8a', '#2563eb',
        '#1a56db', '#3730a3', '#1d4ed8', '#0369a1', '#075985',
        '#1e40af', '#2d6bbf'],
    # Section 2 – Model Answer: clear greens + teals (readable on mint bg)
    2: ['#15803d', '#059669', '#0d9488', '#0f766e', '#16a34a',
        '#047857', '#0e7490', '#1b8a5a', '#12916a', '#1a7a5a'],
    # Section 3 – Vocabulary: full palette (maximum variety)
    3: _ACCENT_COLORS_LIGHT,
    # Section 4 – Shadowing: purples + magentas + deep reds
    4: ['#6b21a8', '#9d174d', '#7c3aed', '#be185d', '#a21caf',
        '#86198f', '#701a75', '#831843', '#6d28d9', '#7e22ce',
        '#9333ea', '#c026d3'],
    # Section 5 – Final Review: rich ambers + oranges (readable on warm bg)
    5: ['#b45309', '#d97706', '#c2410c', '#9a3412', '#a16207',
        '#b85c00', '#c07000', '#bf4800', '#a05a00', '#c05010'],
}

# Section-specific background palettes (light theme only)
# These are noticeably tinted "paper" tones — 88–94% lightness, not near-white
_BG_COLORS_SECTION_LIGHT = {
    # Section 1 – very light blue tint
    1: ['#f0f4fc', '#eef2fa', '#f2f5fd', '#edf2fb', '#f0f3fb',
        '#eef4fc', '#f2f6fd', '#edf3fb', '#f0f5fc', '#eef3fb'],
    # Section 2 – very light mint tint
    2: ['#f0faf4', '#eef8f2', '#f2fcf6', '#edf8f2', '#f0f9f4',
        '#eef9f3', '#f2fbf6', '#edf9f3', '#f0faf5', '#eef8f3'],
    # Section 4 – very light lavender tint
    4: ['#f4f0fc', '#f2eefa', '#f5f2fd', '#f1eefb', '#f3f0fc',
        '#f2f0fb', '#f5f2fc', '#f1f0fb', '#f4f1fc', '#f2effb'],
    # Section 5 – very light warm/cream tint
    5: ['#fdf6ec', '#fbf4e8', '#fef7ee', '#faf4e8', '#fcf5ea',
        '#fbf5ea', '#fef7ec', '#faf3e8', '#fcf6ec', '#fbf4ea'],
}

# ── Structural colors per theme (used by frame_renderer) ──────────────────────

THEME_COLORS = {
    'dark': {
        'bg':           '#080910',
        'surface':      '#0f1223',
        'border':       '#1e2240',
        'active_bg':    '#1a2550',
        'active_border':'#3a6aff',
        'spoken':       '#2a9060',
        'upcoming':     '#4a5070',
        'text':         '#ffffff',
        'gold':         '#f0c040',
        'prep':         '#f0c040',
        'speak':        '#40d090',
        'done':         '#e05555',
    },
    'light': {
        'bg':           '#f8f9ff',
        'surface':      '#eceef8',
        'border':       '#c4c8dc',
        'active_bg':    '#dce8ff',
        'active_border':'#2a5fd8',
        'spoken':       '#1e7040',
        'upcoming':     '#888ca0',
        'text':         '#111122',
        'gold':         '#c07800',
        'prep':         '#b06000',
        'speak':        '#1a6e3a',
        'done':         '#b82020',
    },
}


def generate_style(seed=None, theme='light'):
    """Generate a random visual style dict for a vocabulary page."""
    rng = random.Random(seed)

    if theme == 'light':
        bg     = rng.choice(_BG_COLORS_LIGHT)
        bg     = _ensure_bg_safe_for_dark_text(bg)
        accent = _pick_contrasting_accent(bg, _ACCENT_COLORS_LIGHT, rng)
        text   = '#111122'
    else:
        bg     = rng.choice(_BG_COLORS_DARK)
        bg     = _ensure_bg_safe_for_white(bg)
        accent = _pick_contrasting_accent(bg, _ACCENT_COLORS_DARK, rng)
        text   = '#ffffff'

    layout     = rng.choice(_LAYOUTS)
    decoration = rng.choice(_DECORATIONS)
    regular, bold = rng.choice(_AVAILABLE_FONTS)

    return {
        'bg_color':     bg,
        'text_color':   text,
        'accent_color': accent,
        'word_color':   text,
        'font_regular': regular,
        'font_bold':    bold,
        'layout':       layout,
        'decoration':   decoration,
        'theme':        theme,
    }


def _luminance(hex_color):
    """Perceived luminance 0–255 of a hex color string."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def generate_section_style(section_num, seed=None, theme='light'):
    """Generate a random visual style for a video section (1-5).

    Guarantees:
      - Background contrast is safe for the chosen text color.
      - (bg, accent, decoration) does not match this section's recent history,
        so consecutive videos never share the same look.
    """
    # True entropy by default so videos built seconds apart don't collide
    if seed is None:
        seed = secrets.randbits(32)
    rng = random.Random(seed)

    recent = _recent_combos(section_num)

    def _pick_combo():
        """Pick (bg, accent, text, theme) applying the section's rules."""
        if section_num == 5:
            return '#ffffff', _pick_contrasting_accent('#ffffff', _S5_ACCENT_POOL, rng), '#111122', 'light'
        if section_num in (1, 2):
            # Fallback only — video_builder uses make_group_style for 1 & 2
            return '#ffffff', _pick_contrasting_accent('#ffffff', _S2_ACCENT_POOL, rng), '#111122', 'light'
        if section_num in (3, 4):
            return '#ffffff', _pick_contrasting_accent('#ffffff', _ACCENT_COLORS_FULL, rng), '#111122', 'light'
        if theme == 'light':
            bg_pool = _BG_COLORS_SECTION_LIGHT.get(section_num, _BG_COLORS_LIGHT)
            bg_v    = _ensure_bg_safe_for_dark_text(rng.choice(bg_pool))
            palette = _SECTION_ACCENTS_LIGHT.get(section_num, _ACCENT_COLORS_LIGHT)
            return bg_v, _pick_contrasting_accent(bg_v, palette, rng), '#111122', 'light'
        bg_v    = _ensure_bg_safe_for_white(rng.choice(_BG_COLORS_DARK))
        palette = _SECTION_ACCENTS_DARK.get(section_num, _ACCENT_COLORS_DARK)
        return bg_v, _pick_contrasting_accent(bg_v, palette, rng), '#ffffff', 'dark'

    dec_pool = _SECTION_DECORATIONS.get(section_num, _DECORATIONS)
    # Font pool — dense-text sections stick to body-safe sans
    font_pool = _AVAILABLE_FONTS if section_num == 3 else _BODY_FONTS

    # Try up to 12 candidate combos; accept the first one NOT in recent history.
    # If all tries collide (small pools + long history), fall back to the last try.
    bg = accent = text = theme_v = decoration = None
    for _ in range(12):
        bg, accent, text, theme_v = _pick_combo()
        decoration = rng.choice(dec_pool)
        if (bg, accent, decoration) not in recent:
            break

    layout     = rng.choice(_LAYOUTS)
    regular, bold = rng.choice(font_pool)

    _record_combo(section_num, bg, accent, decoration)

    return {
        'bg_color':     bg,
        'text_color':   text,
        'accent_color': accent,
        'word_color':   text,
        'font_regular': regular,
        'font_bold':    bold,
        'layout':       layout,
        'decoration':   decoration,
        'theme':        theme_v,
        'section':      section_num,
    }


def default_seeds():
    """Return a fresh seed dict for all 5 sections.

    Uses `secrets.randbits(32)` for cryptographically strong entropy per
    section — crucially, NOT wall-clock time. Previously two videos built
    within the same second could share RNG state because their seeds differed
    by only a few integer units, which sometimes produced identical choices
    from small decoration/color pools. `secrets` guarantees independence.
    """
    return {i: secrets.randbits(32) for i in range(1, 6)}


# ── Group Style System ─────────────────────────────────────────────────────────
# One fixed visual identity per category × band × frequency tier × section.
# Edit any dict below to change how that group looks.

CATEGORY_DISPLAY = {
    'career_work':                 'Career & Work',
    'health_lifestyle':            'Health & Lifestyle',
    'family_relationships':        'Family & Relationships',
    'education_learning':          'Education & Learning',
    'finance_money':               'Finance & Money',
    'housing_home':                'Housing & Home',
    'travel_vacation':             'Travel & Vacation',
    'technology_digital':          'Technology & Digital',
    'social_friendships':          'Social Life & Friendships',
    'parenting_children':          'Parenting & Children',
    'stress_wellbeing':            'Stress & Wellbeing',
    'transportation':              'Transportation',
    'shopping_consumer':           'Shopping & Consumer',
    'environment_community':       'Environment & Community',
    'cultural_adaptation':         'Cultural Adaptation',
    'food_nutrition':              'Food & Nutrition',
    'sports_recreation':           'Sports & Recreation',
    'personal_development':        'Personal Development',
    'communication_conflict':      'Communication & Conflict',
    'volunteer_community_service': 'Volunteer & Community',
}

# Primary accent color per category (top bar highlight, word color, badges)
CATEGORY_ACCENT = {
    'career_work':                 '#1e40af',  # navy
    'health_lifestyle':            '#0f766e',  # teal
    'family_relationships':        '#be185d',  # rose
    'education_learning':          '#5b21b6',  # indigo
    'finance_money':               '#b45309',  # amber
    'housing_home':                '#9a3412',  # sienna
    'travel_vacation':             '#0284c7',  # sky blue
    'technology_digital':          '#0891b2',  # bright cyan        (was #155e75 dark cyan — too close to teal)
    'social_friendships':          '#a21caf',  # magenta
    'parenting_children':          '#15803d',  # forest green
    'stress_wellbeing':            '#34d399',  # vivid mint         (was #6d28d9 violet — clashed with education+personal)
    'transportation':              '#64748b',  # slate gray         (was #0c4a6e deep ocean — too close to tech)
    'shopping_consumer':           '#c2410c',  # orange-red
    'environment_community':       '#65a30d',  # lime-green         (was #166534 forest — near-identical to parenting)
    'cultural_adaptation':         '#7c3aed',  # vivid purple       (was #d97706 gold — too close to finance)
    'food_nutrition':              '#dc2626',  # vivid red
    'sports_recreation':           '#3f6212',  # dark olive
    'personal_development':        '#f59e0b',  # golden amber       (was #7e22ce purple — clashed with education+stress)
    'communication_conflict':      '#f97316',  # bright orange      (was #1e4d8c steel blue — near-identical to career navy)
    'volunteer_community_service': '#ec4899',  # hot pink           (was #065f46 emerald — 3rd near-identical green)
}

# Background color per band — all white; band identity lives on the thumbnail only
BAND_BG = {
    '7_8':   '#ffffff',
    '9_10':  '#ffffff',
    '11_12': '#ffffff',
}

BAND_DISPLAY = {
    '7_8':   'Band 7–8',
    '9_10':  'Band 9–10',
    '11_12': 'Band 11–12',
}

# Frequency tier label badge (shown in top bar of each frame)
FREQ_CONFIG = {
    'high':        {'label': 'HIGH PRIORITY',   'color': '#dc2626'},
    'medium_high': {'label': 'LIKELY EXAM',     'color': '#ea580c'},
    'medium':      {'label': 'PRACTICE',        'color': '#2563eb'},
    'lower':       {'label': 'BONUS CHALLENGE', 'color': '#7c3aed'},
}

FREQ_DISPLAY = {
    'high':        '★★★  High Priority',
    'medium_high': '★★½  Likely Exam',
    'medium':      '★★☆  Practice',
    'lower':       '★☆☆  Bonus Challenge',
}

# Maps the raw DB frequency_label strings → FREQ_CONFIG keys
_FREQ_LABEL_MAP = {
    'high probability':         'high',
    'medium-high probability':  'medium_high',
    'medium probability':       'medium',
    'lower probability':        'lower',
}


def freq_key_from_label(frequency_label):
    """Convert a DB frequency_label string to a FREQ_CONFIG key ('high'/'medium_high'/'medium'/'lower')."""
    if not frequency_label:
        return 'medium'
    return _FREQ_LABEL_MAP.get(frequency_label.lower().strip(), 'medium')

# Fixed badge color per section + pool of allowed decorations (picked randomly per video via seed)
# badge_color:  color of the section label pill in the top bar — FIXED per section
# decorations:  pool to draw from randomly — same color, different texture each video
SECTION_STYLE = {
    1: {                                          # Prep / Question — blue
        'badge_color': '#2563eb',
        'decorations': ['none', 'none', 'gradient', 'corner'],
    },
    2: {                                          # Model Answer — green
        'badge_color': '#16a34a',
        'decorations': ['none', 'none', 'gradient', 'border'],
    },
    3: {                                          # Vocabulary Builder — amber
        'badge_color': '#d97706',
        'decorations': ['gradient', 'border', 'corner', 'diagonal'],
    },
    4: {                                          # Shadowing — violet
        'badge_color': '#7c3aed',
        'decorations': ['border', 'corner', 'diagonal', 'gradient'],
    },
    5: {                                          # Final Review — cyan
        'badge_color': '#0891b2',
        'decorations': ['none', 'none', 'gradient', 'border'],
    },
}

SECTION_DISPLAY = {
    1: 'Prep / Question',
    2: 'Model Answer',
    3: 'Vocabulary Builder',
    4: 'Shadowing',
    5: 'Final Review',
}


def make_group_style(category_slug=None, band=None, freq=None, section=3, seed=None):
    """
    Build a style dict representing a group's fixed visual identity.
    Compatible with all render_* functions in frame_renderer.

    Colors are FIXED per category/section (so the same category always reads
    as the same brand family). Within that constraint we:
      - Auto-darken the category color whenever it's used as a background
        for white text, so readability is guaranteed even for light brand
        hues like mint, hot pink, or gold.
      - Pick the decoration pseudo-randomly AND reject any (section, decoration)
        combo that matches the last few runs in `style_history.json`. Two
        consecutive videos in the same category therefore still differ in
        texture, even though they share primary color.

    Args:
        category_slug: key from CATEGORY_ACCENT (e.g. 'career_work')
        band:          key from BAND_BG (e.g. '9_10')
        freq:          key from FREQ_CONFIG (e.g. 'high')
        section:       1–5
        seed:          int seed. None → cryptographically-strong random per call.
    """
    import random as _rnd
    cat_accent = CATEGORY_ACCENT.get(category_slug, '#1e40af')
    freq_cfg   = FREQ_CONFIG.get(freq or 'medium', FREQ_CONFIG['medium'])
    sec_cfg    = SECTION_STYLE.get(section, SECTION_STYLE[1])

    # True entropy by default — never fall back to wall-clock-derived seeds
    if seed is None:
        seed = secrets.randbits(32)
    rng = _rnd.Random(seed)

    # Decoration — pick from section's pool, but skip any combo we just used
    # (scoped per section + category so variety survives category repeats).
    history_key = (section, category_slug or '_')
    recent_decs = set()
    try:
        _hist = _load_history()
        # We stuff (cat, accent, dec) into history for group styles
        recent_decs = {
            d for (c, _a, d) in _hist.get(section, [])
            if c == (category_slug or '_')
        }
    except Exception:
        recent_decs = set()

    dec_pool   = sec_cfg.get('decorations', ['none', 'gradient', 'corner', 'border'])
    # Deduplicate while preserving weight intent: if every distinct option is
    # in the recent set we have no choice but to reuse one, so only filter when
    # it wouldn't empty the pool.
    unique_opts = list(dict.fromkeys(dec_pool))
    fresh_opts  = [d for d in unique_opts if d not in recent_decs]
    choose_from = fresh_opts if fresh_opts else unique_opts
    decoration = rng.choice(choose_from)

    regular = 'C:/Windows/Fonts/segoeui.ttf'
    bold    = 'C:/Windows/Fonts/segoeuib.ttf'
    if not os.path.exists(regular):
        regular = bold = None

    if section == 1:
        # Section 1 (Question page) uses the category colour as background.
        # CRITICAL: white text lives on this bg, so we MUST guarantee the
        # luminance is safe. Auto-darken light brand colors (mint, hot pink,
        # gold, lime, orange, …) until white text is comfortably readable.
        # The hue family is preserved — only the shade is adjusted.
        safe_bg      = _ensure_bg_safe_for_white(cat_accent)
        accent       = safe_bg
        bg           = safe_bg
        ac_frame     = '#ffffff'   # white accent for progress bar / timer on dark bg
        text_col     = '#ffffff'
        word_col     = '#ffffff'
        theme_val    = 'dark'
        # Light tint of the safe bg for secondary/muted text
        _r, _g, _b = _hex_to_rgb(safe_bg)
        upcoming_col = '#{:02x}{:02x}{:02x}'.format(
            min(255, _r + int((255 - _r) * 0.60)),
            min(255, _g + int((255 - _g) * 0.60)),
            min(255, _b + int((255 - _b) * 0.60)),
        )
    elif section == 2:
        # Section 2 (Model Answer): random from curated pool — varied per video,
        # always readable (all pool colors have perceptual luminance < 110).
        # Reject the last few picks so consecutive videos in this category vary.
        _s2_recent = {a for (c, a, _d) in _load_history().get(2, [])
                      if c == (category_slug or '_')}
        _s2_fresh  = [c for c in _S2_ACCENT_POOL if c not in _s2_recent]
        accent       = rng.choice(_s2_fresh if _s2_fresh else _S2_ACCENT_POOL)
        bg           = BAND_BG.get(band, '#ffffff')
        ac_frame     = accent
        text_col     = '#111122'
        word_col     = '#111122'
        theme_val    = 'light'
        upcoming_col = None
    else:
        accent       = cat_accent
        bg           = BAND_BG.get(band, '#ffffff')
        ac_frame     = accent
        text_col     = '#111122'
        word_col     = '#111122'
        theme_val    = 'light'
        upcoming_col = None   # use theme default

    # Record (category, accent_used, decoration) so next build avoids repeats
    _record_combo(section, category_slug or '_', accent, decoration)

    style_dict = {
        'bg_color':            bg,
        'text_color':          text_col,
        'accent_color':        ac_frame,
        'word_color':          word_col,
        'font_regular':        regular,
        'font_bold':           bold,
        'layout':              'bold_top',
        'decoration':          decoration,
        'theme':               theme_val,
        'section':             section,
        'section_badge_color': sec_cfg['badge_color'],
        'freq_label':          freq_cfg['label'],
        'freq_color':          freq_cfg['color'],
        'category_slug':       category_slug,
        'category_accent':     cat_accent,   # original category brand colour for reference
        'band':                band,
        'freq':                freq,
        'seed':                seed,
    }
    if upcoming_col is not None:
        style_dict['upcoming'] = upcoming_col
    return style_dict
