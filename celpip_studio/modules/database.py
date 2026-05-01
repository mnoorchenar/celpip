import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'data', 'celpip_practice.db')


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Ensure all tables exist (no-op if already created)."""
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS template_answers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                band             TEXT    NOT NULL,
                part             INTEGER NOT NULL,
                category         TEXT    NOT NULL,
                title            TEXT    NOT NULL,
                question         TEXT    NOT NULL,
                answer           TEXT    NOT NULL DEFAULT "",
                vocabulary       TEXT    NOT NULL DEFAULT "[]",
                frequency_label  TEXT,
                freq_priority    INTEGER DEFAULT 99,
                template_id      TEXT,
                video_status     TEXT    NOT NULL DEFAULT "not_generated",
                video_path       TEXT,
                pdf_path         TEXT,
                youtube_status   TEXT    NOT NULL DEFAULT "not_posted",
                youtube_url      TEXT,
                youtube_video_id TEXT,
                updated_at       TEXT    NOT NULL,
                UNIQUE(part, category, title)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS vocab_sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT    NOT NULL DEFAULT 'text',
                source_url  TEXT,
                raw_text    TEXT    NOT NULL,
                title       TEXT,
                created_at  TEXT    NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS vocab_bank (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER REFERENCES vocab_sources(id) ON DELETE CASCADE,
                word        TEXT    NOT NULL,
                item_type   TEXT    NOT NULL DEFAULT 'word',
                word_type   TEXT    NOT NULL DEFAULT '',
                definition  TEXT    NOT NULL DEFAULT '',
                example     TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL
            )
        ''')
        c.commit()


# ── Vocab Bank ────────────────────────────────────────────────────────────────

def save_vocab_source(source_type, source_url, raw_text, title=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn() as c:
        cur = c.execute(
            'INSERT INTO vocab_sources (source_type, source_url, raw_text, title, created_at) VALUES (?,?,?,?,?)',
            (source_type, source_url, raw_text, title, now)
        )
        c.commit()
        return cur.lastrowid


def save_vocab_items(source_id, items):
    """items: list of {word, item_type, word_type, definition, example}"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn() as c:
        c.executemany(
            '''INSERT INTO vocab_bank
               (source_id, word, item_type, word_type, definition, example, created_at)
               VALUES (?,?,?,?,?,?,?)''',
            [(source_id,
              it['word'],
              it.get('item_type', 'word'),
              it.get('word_type', ''),
              it.get('definition', ''),
              it.get('example', ''),
              now) for it in items]
        )
        c.commit()


def get_vocab_bank(limit=500):
    with _conn() as c:
        rows = c.execute(
            '''SELECT vb.id, vb.word, vb.item_type, vb.word_type,
                      vb.definition, vb.example, vb.created_at,
                      vs.source_type, vs.title, vs.source_url
               FROM vocab_bank vb
               LEFT JOIN vocab_sources vs ON vs.id = vb.source_id
               ORDER BY vb.created_at DESC LIMIT ?''',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_vocab_item(item_id):
    with _conn() as c:
        c.execute('DELETE FROM vocab_bank WHERE id=?', (item_id,))
        c.commit()


# ── Template Answers — Write ───────────────────────────────────────────────────

def update_template_answer(record_id, answer, vocabulary=None):
    """Set the answer (and optionally vocabulary) for a template row."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn() as c:
        if vocabulary is not None:
            c.execute(
                'UPDATE template_answers SET answer=?, vocabulary=?, updated_at=? WHERE id=?',
                (answer, json.dumps(vocabulary), now, record_id)
            )
        else:
            c.execute(
                'UPDATE template_answers SET answer=?, updated_at=? WHERE id=?',
                (answer, now, record_id)
            )
        c.commit()


def update_template_video(record_id, video_path):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn() as c:
        c.execute(
            "UPDATE template_answers "
            "SET video_status='generated', video_path=?, updated_at=? WHERE id=?",
            (video_path, now, record_id)
        )
        c.commit()


def update_template_pdf(record_id, pdf_path):
    with _conn() as c:
        c.execute('UPDATE template_answers SET pdf_path=? WHERE id=?',
                  (pdf_path, record_id))
        c.commit()


def reset_template(record_id):
    with _conn() as c:
        c.execute(
            "UPDATE template_answers "
            "SET video_status='not_generated', video_path=NULL, pdf_path=NULL "
            "WHERE id=?",
            (record_id,)
        )
        c.commit()


# ── Template Answers — Read ────────────────────────────────────────────────────

def get_templates(category=None, frequency_label=None,
                  video_status=None, search=None):
    conds, params = [], []
    if category:
        conds.append('category=?');        params.append(category)
    if frequency_label:
        conds.append('frequency_label=?'); params.append(frequency_label)
    if video_status:
        conds.append('video_status=?');    params.append(video_status)
    if search:
        conds.append('(title LIKE ? OR question LIKE ?)')
        params += [f'%{search}%', f'%{search}%']

    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    with _conn() as c:
        rows = c.execute(
            f'SELECT * FROM template_answers {where} '
            f'ORDER BY freq_priority ASC, id ASC',
            params
        ).fetchall()
    return [dict(r) for r in rows]


def get_template_by_id(record_id):
    with _conn() as c:
        row = c.execute('SELECT * FROM template_answers WHERE id=?',
                        (record_id,)).fetchone()
    return dict(row) if row else None


def get_template_stats():
    with _conn() as c:
        total     = c.execute('SELECT COUNT(*) FROM template_answers').fetchone()[0]
        generated = c.execute(
            "SELECT COUNT(*) FROM template_answers WHERE video_status='generated'"
        ).fetchone()[0]
        cats      = c.execute(
            'SELECT COUNT(DISTINCT category) FROM template_answers'
        ).fetchone()[0]
        with_answers = c.execute(
            "SELECT COUNT(*) FROM template_answers WHERE answer != ''"
        ).fetchone()[0]
    return {
        'total':         total,
        'with_answers':  with_answers,
        'generated':     generated,
        'not_generated': total - generated,
        'categories':    cats,
    }


def get_template_filter_options():
    with _conn() as c:
        cats  = [r[0] for r in c.execute(
            'SELECT DISTINCT category FROM template_answers ORDER BY category'
        ).fetchall()]
        freqs = [r[0] for r in c.execute(
            'SELECT DISTINCT frequency_label FROM template_answers ORDER BY freq_priority'
        ).fetchall()]
    return {'categories': cats, 'frequency_labels': freqs}


def get_next_ungenerated(count):
    """Return up to `count` ungenerated templates ordered by priority."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM template_answers "
            "WHERE video_status='not_generated' AND answer != '' "
            "ORDER BY freq_priority ASC, id ASC LIMIT ?",
            (count,)
        ).fetchall()
    return [dict(r) for r in rows]
