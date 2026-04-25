"""
Creates the `template_answers` table in celpip_practice.db
and imports all part1_answers_9_10_*.json files into it.

Safe to re-run — uses INSERT OR REPLACE so duplicates are updated, not doubled.

Run:  python import_answers_to_db.py
"""

import os
import json
import glob
import sqlite3

DB_PATH       = r"D:\YouTube\celpip_studio\data\celpip_practice.db"
QUESTIONS_DIR = r"D:\YouTube\celpip_studio\data\questions\part1"


# ── Create table ──────────────────────────────────────────────────────────────
def init_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS template_answers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            band            TEXT    NOT NULL,
            part            INTEGER NOT NULL,
            category        TEXT    NOT NULL,
            title           TEXT    NOT NULL,
            question        TEXT    NOT NULL,
            answer          TEXT    NOT NULL,
            vocabulary      TEXT    NOT NULL DEFAULT '[]',
            frequency       TEXT,
            frequency_label TEXT,
            created_at      TEXT    NOT NULL,
            UNIQUE(part, category, title)
        )
    """)
    conn.commit()


# ── Import one JSON file ───────────────────────────────────────────────────────
def import_file(conn, filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        answers = json.load(f)

    inserted = 0
    updated  = 0

    for ans in answers:
        # Check if row already exists
        existing = conn.execute(
            "SELECT id FROM template_answers WHERE part=? AND category=? AND title=?",
            (ans.get("task_num", 1), ans.get("category", ""), ans.get("title", ""))
        ).fetchone()

        vocab_json = json.dumps(ans.get("vocab", []), ensure_ascii=False)

        if existing:
            conn.execute("""
                UPDATE template_answers
                SET band=?, answer=?, vocabulary=?, frequency=?, frequency_label=?
                WHERE id=?
            """, (
                ans.get("band", "9_10"),
                ans.get("answer", ""),
                vocab_json,
                ans.get("frequency", ""),
                ans.get("frequency_label", ""),
                existing["id"]
            ))
            updated += 1
        else:
            from datetime import datetime
            conn.execute("""
                INSERT INTO template_answers
                    (band, part, category, title, question, answer,
                     vocabulary, frequency, frequency_label, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ans.get("band", "9_10"),
                ans.get("task_num", 1),
                ans.get("category", ""),
                ans.get("title", ""),
                ans.get("question", ""),
                ans.get("answer", ""),
                vocab_json,
                ans.get("frequency", ""),
                ans.get("frequency_label", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            inserted += 1

    conn.commit()
    return inserted, updated


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_table(conn)

    files = sorted(glob.glob(os.path.join(QUESTIONS_DIR, "part1_answers_9_10_*.json")))

    if not files:
        print("No answer JSON files found.")
        return

    total_inserted = total_updated = 0

    for filepath in files:
        name = os.path.basename(filepath)
        ins, upd = import_file(conn, filepath)
        total_inserted += ins
        total_updated  += upd
        print(f"  {name:50s}  +{ins:2d} inserted  ~{upd:2d} updated")

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM template_answers").fetchone()[0]
    print(f"\n  DB total: {total} template answers")
    print(f"  This run: +{total_inserted} new  ~{total_updated} updated")
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
