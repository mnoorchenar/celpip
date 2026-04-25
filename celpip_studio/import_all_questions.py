"""
Import ALL part1 question .md files into template_answers.

- For categories already in the DB (e.g. Career & Work with answers): SKIPS existing rows.
- For categories with no answer yet: inserts questions with answer=''.
- Safe to re-run — skips any row where (part, category, title) already exists.

Run:  python import_all_questions.py
"""

import os
import re
import glob
import sqlite3
import json
from datetime import datetime

DB_PATH       = r"D:\YouTube\celpip_studio\data\celpip_practice.db"
QUESTIONS_DIR = r"D:\YouTube\celpip_studio\data\questions\part1"

# ── Slug → 2-letter code (for template_id) ────────────────────────────────────
CATEGORY_CODES = {
    'career_work':                 'CW',
    'health_lifestyle':            'HL',
    'family_relationships':        'FR',
    'education_learning':          'EL',
    'finance_money':               'FM',
    'housing_home':                'HH',
    'travel_vacation':             'TV',
    'technology_digital':          'TD',
    'social_friendships':          'SF',
    'parenting_children':          'PC',
    'stress_wellbeing':            'SW',
    'transportation':              'TR',
    'shopping_consumer':           'SC',
    'environment_community':       'EC',
    'cultural_adaptation':         'CA',
    'food_nutrition':              'FN',
    'sports_recreation':           'SR',
    'personal_development':        'PD',
    'communication_conflict':      'CC',
    'volunteer_community_service': 'VC',
}

# ── Slug → category accent color (from style_gen.py CATEGORY_ACCENT) ─────────
CATEGORY_COLOR = {
    'career_work':                 '#1e40af',
    'health_lifestyle':            '#0f766e',
    'family_relationships':        '#be185d',
    'education_learning':          '#5b21b6',
    'finance_money':               '#b45309',
    'housing_home':                '#9a3412',
    'travel_vacation':             '#0284c7',
    'technology_digital':          '#155e75',
    'social_friendships':          '#a21caf',
    'parenting_children':          '#15803d',
    'stress_wellbeing':            '#6d28d9',
    'transportation':              '#0c4a6e',
    'shopping_consumer':           '#c2410c',
    'environment_community':       '#166534',
    'cultural_adaptation':         '#d97706',
    'food_nutrition':              '#dc2626',
    'sports_recreation':           '#3f6212',
    'personal_development':        '#7e22ce',
    'communication_conflict':      '#1e4d8c',
    'volunteer_community_service': '#065f46',
}

FREQ_PRIORITY = {
    'High Probability':        1,
    'Medium-High Probability': 2,
    'Medium Probability':      3,
    'Lower Probability':       4,
}


def slug_from_filename(filename):
    """part1_questions_career_work.md  →  career_work"""
    base = os.path.basename(filename)
    m = re.match(r'part1_questions_(.+)\.md$', base)
    return m.group(1) if m else ''


def parse_questions(filepath):
    """
    Parse a part1 question .md file and return a list of dicts:
      { question_num, title, question_text, frequency, frequency_label, freq_priority }
    """
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()

    # ── Extract category display name ──────────────────────────────────────────
    category_name = ''
    for line in lines:
        m = re.match(r'^##\s+Category\s+\d+:\s+(.+?)\s+[—-]', line)
        if m:
            category_name = m.group(1).strip()
            break

    # ── State machine parse ────────────────────────────────────────────────────
    questions      = []
    current_freq   = ''
    current_stars  = ''
    current_prio   = 99
    current_q      = None
    collecting_text = False
    q_text_lines   = []

    FREQ_HEADERS = [
        (r'★★★.*High Probability',        '★★★', 'High Probability',        1),
        (r'★★☆.*Medium-High Probability',  '★★☆', 'Medium-High Probability', 2),
        (r'★★☆.*Medium Probability',       '★★☆', 'Medium Probability',      3),
        (r'★☆☆.*Lower Probability',        '★☆☆', 'Lower Probability',       4),
    ]

    def flush_question():
        if current_q is not None:
            text = ' '.join(q_text_lines).strip()
            current_q['question_text'] = text
            questions.append(current_q)

    for line in lines:
        stripped = line.strip()

        # Stop at Quick Reference table
        if stripped.startswith('## Quick Reference'):
            flush_question()
            current_q = None
            break

        # Detect frequency section headers
        matched_freq = False
        for pattern, stars, label, prio in FREQ_HEADERS:
            if re.search(pattern, stripped):
                flush_question()
                current_q = None
                q_text_lines = []
                collecting_text = False
                current_freq  = label
                current_stars = stars
                current_prio  = prio
                matched_freq = True
                break
        if matched_freq:
            continue

        # Detect question title: **Q12. Some Title**
        m = re.match(r'^\*\*Q(\d+)\.\s+(.+?)\*\*\s*$', stripped)
        if m:
            flush_question()
            q_text_lines = []
            collecting_text = False
            current_q = {
                'question_num':    int(m.group(1)),
                'title':           m.group(2).strip(),
                'frequency':       current_stars,
                'frequency_label': current_freq,
                'freq_priority':   current_prio,
                'question_text':   '',
                'category':        category_name,
            }
            continue

        # Detect blockquote lines (question text)
        if stripped.startswith('>') and current_q is not None:
            text_part = stripped[1:].strip()
            q_text_lines.append(text_part)
            collecting_text = True
            continue

        # A blank line or --- ends blockquote collection
        if collecting_text and (not stripped or stripped == '---'):
            collecting_text = False

    # Flush last question
    flush_question()

    return category_name, questions


def import_file(conn, filepath, dry_run=False):
    slug = slug_from_filename(filepath)
    if not slug:
        print(f'  SKIP (unrecognised filename): {os.path.basename(filepath)}')
        return 0, 0

    category_name, questions = parse_questions(filepath)
    if not category_name:
        print(f'  WARN: could not extract category name from {os.path.basename(filepath)}')

    code  = CATEGORY_CODES.get(slug, slug[:2].upper())
    color = CATEGORY_COLOR.get(slug, '#888888')
    now   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    inserted = skipped = 0

    for q in questions:
        # Check if this (part, category, title) already exists
        existing = conn.execute(
            'SELECT id FROM template_answers WHERE part=? AND category=? AND title=?',
            (1, q['category'], q['title'])
        ).fetchone()

        if existing:
            skipped += 1
            continue

        tid = f'P1-{code}-{q["question_num"]:03d}'

        if not dry_run:
            conn.execute("""
                INSERT INTO template_answers
                    (band, part, category, title, question, answer,
                     vocabulary, frequency, frequency_label, freq_priority,
                     template_id, category_color,
                     video_status, youtube_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?,
                        'not_generated', 'not_posted', ?)
            """, (
                '9_10', 1, q['category'], q['title'], q['question_text'], '',
                '[]', q['frequency'], q['frequency_label'], q['freq_priority'],
                tid, color,
                now,
            ))
        inserted += 1

    if not dry_run:
        conn.commit()

    return inserted, skipped


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    files = sorted(
        f for f in glob.glob(os.path.join(QUESTIONS_DIR, 'part1_questions_*.md'))
        if os.path.basename(f) != 'part1_categories.md'
    )

    if not files:
        print('No question .md files found.')
        return

    print(f'Found {len(files)} question files.\n')

    total_inserted = total_skipped = 0

    for filepath in files:
        slug = slug_from_filename(filepath)
        ins, skp = import_file(conn, filepath)
        total_inserted += ins
        total_skipped  += skp
        status = f'+{ins:2d} inserted  ~{skp:2d} skipped'
        print(f'  {os.path.basename(filepath):55s}  {status}')

    total = conn.execute('SELECT COUNT(*) FROM template_answers').fetchone()[0]
    conn.close()

    print(f'\n  DB total: {total} records')
    print(f'  This run: +{total_inserted} new  ~{total_skipped} already existed')
    print('\nDone.')


if __name__ == '__main__':
    main()
