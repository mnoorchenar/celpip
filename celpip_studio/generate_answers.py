#!/usr/bin/env python3
"""
CELPIP Band 9-10 Answer Generator
-----------------------------------
Reads all Part 1 question files, generates band 9-10 model answers via Claude API,
saves one JSON file per category. Runs fully automatically, batch by batch.

Usage:
    set ANTHROPIC_API_KEY=your-key-here
    python generate_answers.py

Resume: safe to re-run — already-completed categories are skipped automatically.
"""

import os
import re
import json
import time
import sys
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
QUESTIONS_DIR = r"D:\YouTube\celpip_studio\data\questions\part1"
OUTPUT_DIR    = QUESTIONS_DIR   # save alongside question files
BATCH_SIZE    = 10              # questions per API call (do NOT increase)
MODEL         = "claude-opus-4-6"
PART_NUM      = 1

# ── System prompt (mirrors CLAUDE.md rules) ───────────────────────────────────
SYSTEM_PROMPT = """You are an expert CELPIP speaking coach generating band 9-10 model answers for Part 1 (Giving Advice).

STRICT RULES — apply to every single answer without exception:

STRUCTURE (mandatory for every answer):
1. Acknowledge the situation naturally (1 sentence)
2. Give 2–3 concrete, specific pieces of advice (2–3 sentences)
3. Explain the reasoning behind your advice (1–2 sentences)
4. Close with encouragement (1 sentence)
Total: minimum 6 sentences. Never write short or thin responses.

QUALITY:
- Band 9-10 level: natural fluency, sophisticated vocabulary, zero grammar errors
- Every sentence must add value — no padding, no repetition
- Each answer must sound natural when spoken aloud for 60–90 seconds
- NO two answers may use the same opening sentence — vary openers across the batch
- NO standalone filler sentences like "I understand how you feel" or "That's a tough situation"
- Use Canadian context where relevant (Canadian workplace culture, systems, norms)

VOCABULARY:
- Include exactly 6 vocab items per answer
- Each word or phrase must actually appear in the answer
- Definitions must be clear and exam-relevant

OUTPUT FORMAT — return ONLY a valid JSON array, no markdown fences, no explanation:
[
  {
    "band": "9_10",
    "task_num": 1,
    "category": "<exact category name>",
    "title": "<question title>",
    "question": "<full question text exactly as given>",
    "answer": "<full band 9-10 model answer>",
    "vocab": [
      {"word": "phrase or word", "definition": "clear, concise definition", "type": "word"},
      {"word": "...", "definition": "...", "type": "word"},
      {"word": "...", "definition": "...", "type": "word"},
      {"word": "...", "definition": "...", "type": "word"},
      {"word": "...", "definition": "...", "type": "word"},
      {"word": "...", "definition": "...", "type": "word"}
    ]
  }
]"""


# ── Question file parser ───────────────────────────────────────────────────────
def parse_questions(filepath):
    """Parse a Part 1 question .md file. Returns list of {title, question} dicts."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    questions = []
    # Split on each question header
    blocks = re.split(r'\n(?=\*\*Q\d+\.)', content)

    for block in blocks:
        title_match = re.match(r'\*\*Q\d+\.\s+(.+?)\*\*', block)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        # Collect all blockquote lines (> ...) and join them
        quote_lines = re.findall(r'^>\s*(.+)', block, re.MULTILINE)
        if not quote_lines:
            continue
        question_text = ' '.join(line.strip() for line in quote_lines).strip()

        questions.append({'title': title, 'question': question_text})

    return questions


def slug_to_category(slug):
    """Convert file slug like 'career_work' to 'Career & Work'."""
    mapping = {
        'career_work':              'Career & Work',
        'communication_conflict':   'Communication & Conflict Resolution',
        'cultural_adaptation':      'Cultural & Social Adaptation',
        'education_learning':       'Education & Learning',
        'environment_community':    'Environment & Community',
        'family_relationships':     'Family & Relationships',
        'finance_money':            'Finance & Money',
        'food_nutrition':           'Food & Nutrition',
        'health_lifestyle':         'Health & Lifestyle',
        'housing_home':             'Housing & Home',
        'parenting_children':       'Parenting & Children',
        'personal_development':     'Personal Development',
        'shopping_consumer':        'Shopping & Consumer Decisions',
        'social_friendships':       'Social Life & Friendships',
        'sports_recreation':        'Sports & Recreation',
        'stress_wellbeing':         'Stress & Mental Wellbeing',
        'technology_digital':       'Technology & Digital Life',
        'transportation':           'Transportation & Commuting',
        'travel_vacation':          'Travel & Vacation',
        'volunteer_community_service': 'Volunteer & Community Service',
    }
    return mapping.get(slug, slug.replace('_', ' ').title())


# ── API call ──────────────────────────────────────────────────────────────────
def generate_batch(client, batch, category, batch_label):
    """Call Claude API for one batch of questions. Returns list of answer dicts."""
    questions_text = "\n\n".join(
        f"Q{i+1}. Title: {q['title']}\nQuestion: {q['question']}"
        for i, q in enumerate(batch)
    )

    user_message = (
        f"Generate band 9-10 CELPIP Part 1 model answers for the following "
        f"{len(batch)} questions.\nCategory: {category}\n\n"
        f"{questions_text}\n\n"
        f"Return a JSON array with exactly {len(batch)} objects.\n"
        f'Set "category" to "{category}" and "task_num" to {PART_NUM} for all objects.'
    )

    print(f"    Calling API ({batch_label}, {len(batch)} questions)...", flush=True)

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    ) as stream:
        response = stream.get_final_message()

    # Extract text block
    text = next((b.text for b in response.content if b.type == "text"), "")

    # Strip markdown fences if model wraps in ```json ... ```
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text.strip())

    answers = json.loads(text)

    # Inject the correct question text (in case model truncated it)
    for i, ans in enumerate(answers):
        if i < len(batch):
            ans['question'] = batch[i]['question']
            ans['title']    = batch[i]['title']
            ans['category'] = category
            ans['band']     = '9_10'
            ans['task_num'] = PART_NUM

    return answers


# ── Category processor ────────────────────────────────────────────────────────
def process_category(client, filepath, slug):
    """Process one category: parse → batch → generate → save. Resumes if partial."""
    category    = slug_to_category(slug)
    output_path = os.path.join(OUTPUT_DIR, f"part1_answers_9_10_{slug}.json")

    print(f"\n{'─'*60}")
    print(f"  Category : {category}")
    print(f"  Output   : part1_answers_9_10_{slug}.json")

    # Resume support
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            all_answers = json.load(f)
        if len(all_answers) >= 35:
            print(f"  Status   : COMPLETE ({len(all_answers)} answers) — skipping")
            return
        print(f"  Status   : Resuming from answer #{len(all_answers)+1}")
    else:
        all_answers = []

    # Parse questions
    questions = parse_questions(filepath)
    print(f"  Questions: {len(questions)} parsed")

    start_idx = len(all_answers)
    if start_idx >= len(questions):
        print("  Status   : Already answered all questions.")
        return

    remaining = questions[start_idx:]
    batches   = [remaining[i:i+BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total_batches = len(batches)

    for b_idx, batch in enumerate(batches, 1):
        q_start = start_idx + (b_idx - 1) * BATCH_SIZE + 1
        q_end   = q_start + len(batch) - 1
        label   = f"batch {b_idx}/{total_batches}, Q{q_start}–Q{q_end}"

        success = False
        for attempt in range(1, 4):  # up to 3 retries per batch
            try:
                answers = generate_batch(client, batch, category, label)
                all_answers.extend(answers)
                # Save after every batch
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_answers, f, ensure_ascii=False, indent=2)
                print(f"    Saved  : {len(all_answers)} answers total", flush=True)
                success = True
                break
            except json.JSONDecodeError as e:
                print(f"    JSON parse error (attempt {attempt}/3): {e}")
                time.sleep(5)
            except anthropic.RateLimitError:
                wait = 30 * attempt
                print(f"    Rate limited — waiting {wait}s (attempt {attempt}/3)")
                time.sleep(wait)
            except Exception as e:
                print(f"    Error (attempt {attempt}/3): {e}")
                time.sleep(10)

        if not success:
            print(f"    FAILED after 3 attempts — saving progress and stopping this category.")
            if all_answers:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_answers, f, ensure_ascii=False, indent=2)
            return

        # Small pause between batches (avoid bursting the API)
        if b_idx < total_batches:
            time.sleep(3)

    print(f"  DONE     : {len(all_answers)} answers saved.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        print("Run:  set ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("=" * 60)
    print("  CELPIP Band 9-10 Answer Generator")
    print(f"  Model      : {MODEL}")
    print(f"  Batch size : {BATCH_SIZE} questions per API call")
    print(f"  Output dir : {OUTPUT_DIR}")
    print("=" * 60)

    # Discover all Part 1 question files
    files = sorted([
        f for f in os.listdir(QUESTIONS_DIR)
        if re.match(r'part1_questions_.+\.md', f)
    ])

    if not files:
        print("No question files found.")
        sys.exit(1)

    print(f"\nFound {len(files)} categories to process.\n")

    for i, filename in enumerate(files, 1):
        filepath = os.path.join(QUESTIONS_DIR, filename)
        slug_match = re.match(r'part1_questions_(.+)\.md', filename)
        slug = slug_match.group(1) if slug_match else filename

        print(f"[{i:02d}/{len(files)}] {filename}")

        try:
            process_category(client, filepath, slug)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Progress has been saved.")
            sys.exit(0)
        except Exception as e:
            print(f"  UNEXPECTED ERROR: {e}")
            print("  Continuing to next category in 10s...")
            time.sleep(10)

    print("\n" + "=" * 60)
    print("  ALL CATEGORIES COMPLETE!")
    print(f"  JSON files saved in: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
