"""
Migration: upgrade template_answers table with all new columns.
Assigns template_id, category_color, and default statuses.

Safe to re-run — skips columns/values that already exist.

Run:  python migrate_template_answers.py
"""

import sqlite3
import colorsys
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'data', 'celpip_practice.db')

# 2-letter code for each known category
CATEGORY_CODES = {
    'Career & Work':                     'CW',
    'Health & Lifestyle':                'HL',
    'Family & Relationships':            'FR',
    'Education & Learning':              'EL',
    'Finance & Money':                   'FM',
    'Housing & Home':                    'HH',
    'Travel & Vacation':                 'TV',
    'Technology & Digital Life':         'TD',
    'Social Life & Friendships':         'SF',
    'Parenting & Children':              'PC',
    'Stress & Mental Wellbeing':         'SW',
    'Transportation & Commuting':        'TC',
    'Shopping & Consumer Decisions':     'SC',
    'Environment & Community':           'EC',
    'Cultural & Social Adaptation':      'CA',
    'Food & Nutrition':                  'FN',
    'Sports & Recreation':               'SR',
    'Personal Development':              'PD',
    'Communication & Conflict Resolution': 'CR',
    'Volunteer & Community Service':     'VC',
}

# Priority order for frequency labels (used when sorting batch generation)
FREQ_PRIORITY = {
    'High Probability':        1,
    'Medium-High Probability': 2,
    'Medium Probability':      3,
    'Lower Probability':       4,
}


def golden_angle_color(index):
    """Generate a maximally distinct color via golden angle hue rotation."""
    hue = (index * 137.5077) % 360
    r, g, b = colorsys.hls_to_rgb(hue / 360, 0.42, 0.68)
    return '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b * 255))


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Add new columns (safe — each silently ignored if it already exists) ──
    new_columns = [
        ('template_id',      'TEXT'),
        ('video_status',     "TEXT NOT NULL DEFAULT 'not_generated'"),
        ('video_path',       'TEXT'),
        ('pdf_path',         'TEXT'),
        ('youtube_status',   "TEXT NOT NULL DEFAULT 'not_posted'"),
        ('youtube_url',      'TEXT'),
        ('youtube_video_id', 'TEXT'),
        ('category_color',   'TEXT'),
        ('session_dir',      'TEXT'),
        ('freq_priority',    'INTEGER DEFAULT 99'),
    ]

    for col, typ in new_columns:
        try:
            conn.execute(f'ALTER TABLE template_answers ADD COLUMN {col} {typ}')
            print(f'  + Added column: {col}')
        except Exception:
            print(f'    Column already exists: {col}')
    conn.commit()

    # ── Assign category colors (golden angle, by order of first appearance) ──
    categories = [r[0] for r in conn.execute(
        'SELECT DISTINCT category FROM template_answers ORDER BY id'
    ).fetchall()]

    cat_color = {cat: golden_angle_color(i) for i, cat in enumerate(categories)}

    # ── Assign template_id + color + freq_priority per record ──
    total = 0
    for cat in categories:
        rows = conn.execute(
            'SELECT id, frequency_label FROM template_answers '
            'WHERE category=? ORDER BY id',
            (cat,)
        ).fetchall()

        code  = CATEGORY_CODES.get(cat, cat.replace(' ', '')[:2].upper())
        color = cat_color[cat]
        part  = 1  # extend for part2+ later

        for seq, row in enumerate(rows, 1):
            tid      = f'P{part}-{code}-{seq:03d}'
            priority = FREQ_PRIORITY.get(row['frequency_label'], 99)
            conn.execute(
                '''UPDATE template_answers
                   SET template_id    = ?,
                       category_color = ?,
                       freq_priority  = ?,
                       video_status   = COALESCE(NULLIF(video_status,''), 'not_generated'),
                       youtube_status = COALESCE(NULLIF(youtube_status,''), 'not_posted')
                   WHERE id = ?''',
                (tid, color, priority, row['id'])
            )
            total += 1

        print(f'  {cat:42s} {len(rows):3d} records  {color}  code={code}')

    conn.commit()
    conn.close()
    print(f'\n  Total records updated: {total}')
    print('Migration complete.')


if __name__ == '__main__':
    run()
