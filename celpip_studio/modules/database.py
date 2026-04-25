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
    """Ensure the template_answers table exists (no-op if already created)."""
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


def mark_template_posted(record_id, youtube_url=None, youtube_video_id=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _conn() as c:
        c.execute(
            "UPDATE template_answers "
            "SET youtube_status='posted', youtube_url=?, youtube_video_id=?, updated_at=? WHERE id=?",
            (youtube_url, youtube_video_id, now, record_id)
        )
        c.commit()


def unmark_template_posted(record_id):
    with _conn() as c:
        c.execute(
            "UPDATE template_answers "
            "SET youtube_status='not_posted', youtube_url=NULL, youtube_video_id=NULL "
            "WHERE id=?",
            (record_id,)
        )
        c.commit()


def reset_template(record_id):
    """Clear video + YouTube data so the template can be regenerated."""
    with _conn() as c:
        c.execute(
            "UPDATE template_answers "
            "SET video_status='not_generated', video_path=NULL, "
            "    pdf_path=NULL, youtube_status='not_posted', "
            "    youtube_url=NULL, youtube_video_id=NULL "
            "WHERE id=?",
            (record_id,)
        )
        c.commit()


# ── Template Answers — Read ────────────────────────────────────────────────────

def get_templates(category=None, frequency_label=None,
                  video_status=None, youtube_status=None, search=None):
    conds, params = [], []
    if category:
        conds.append('category=?');        params.append(category)
    if frequency_label:
        conds.append('frequency_label=?'); params.append(frequency_label)
    if video_status:
        conds.append('video_status=?');    params.append(video_status)
    if youtube_status:
        conds.append('youtube_status=?');  params.append(youtube_status)
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
        posted    = c.execute(
            "SELECT COUNT(*) FROM template_answers WHERE youtube_status='posted'"
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
        'posted':        posted,
        'not_posted':    total - posted,
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
