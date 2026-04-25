# CELPIP Practice Studio — Project Rules

## Question Files

- All CELPIP practice questions are saved as `.md` files
- Save location: `D:\YouTube\celpip_studio\data\questions\part{N}\`
  - Example: `data\questions\part1\part1_questions_career_work.md`
- Each part gets its own subfolder (`part1`, `part2`, etc.)
- Each category gets its own file named `part{N}_questions_{category_slug}.md`
- A `part{N}_categories.md` index file lives alongside the question files in each part folder

## Question File Format

- Always provide **40 questions per category** (10 per probability tier: High, Medium-High, Medium, Lower)
- Sort questions by exam likelihood: ★★★ High → ★★☆ Medium-High → ★★☆ Medium → ★☆☆ Lower
- Every question must be written as a **full CELPIP-style scenario** — a person speaking in first person describing their situation, ending with "What advice would you give me?" or equivalent
- Include a one-line *Why high/relevant* note under each ★★★ question explaining the exam rationale
- End every file with a **Quick Reference ranked table** listing all 40 questions with their probability tier
- **Never sacrifice question quality to hit the number 40** — all 40 must be genuinely realistic, exam-worthy, and distinct from each other

## Quality Standards

- Questions must have **no single correct answer** — they should allow multiple valid advice directions
- Prefer scenarios that are **emotionally loaded** and require **balanced, nuanced advice**
- Prioritize topics relevant to **Canadian context** and **immigrant/multicultural experiences**
- Do not repeat the same core dilemma with minor wording changes

---

## Band 9-10 Template Answer Rules

> **DEFAULT BAND: 9-10.** All answers in the database are generated at CLB 9-10 (Band 9-10) level unless explicitly told otherwise. Do not change this default without a direct instruction.

### Output Format (JSON)
Each answer is saved as `part1_answers_9_10_{category_slug}.json` in the same folder as the question files.
Each file is a JSON array of objects:
```json
[
  {
    "band": "9_10",
    "task_num": 1,
    "category": "Career & Work",
    "title": "Short descriptive title of the scenario",
    "question": "Full question text exactly as written in the .md file",
    "answer": "Full band 9-10 model response",
    "vocab": [
      {
        "word": "word or phrase",
        "definition": "clear, exam-relevant definition",
        "example": "A natural example sentence showing the word used in context",
        "type": "noun"
      }
    ]
  }
]
```

### Answer Quality Rules (NON-NEGOTIABLE)
- **Every answer must be band 9-10 level** — clear structure, natural fluency, sophisticated vocabulary, no grammar errors
- **Minimum 6 sentences per answer** — never write short or thin responses; every sentence must add value
- **Structure every answer**: acknowledge the situation → give 2–3 concrete pieces of advice → explain the reasoning → close with encouragement
- **No two answers may use the same opening sentence** — vary openers across all 40 questions
- **No filler phrases** — never use "That's a great question", "I understand how you feel" as standalone filler
- **Each answer must feel complete and self-contained** — someone memorizing it should sound natural speaking it aloud
- **Use Canadian context** where relevant (references to Canadian systems, norms, or language)

### Vocabulary Level Rules (NON-NEGOTIABLE)
- **Target range: upper B1 through B2 (CLB 9-10)** — this is the sweet spot for exam preparation
- **Do NOT include A1/A2 basics** — words like "hobby", "friend", "colleague", "confirm" that any elementary learner knows
- **Do NOT reach into C1/CLB 11+ territory** — avoid rare academic or literary words that go beyond what the exam tests
- The goal is vocabulary a strong intermediate learner (B1+) genuinely needs to study and can realistically use on the exam
- **No artificial restrictions on vocab selection** — select any upper B1–B2 word, phrase, idiom, or collocation that appears in the answer and is worth studying; do not limit choices based on word class, topic area, or perceived difficulty within the B1–B2 range
- **All parts of speech are valid**: nouns, adjectives, adverbs, verb phrases, idioms, collocations — not limited to verbs
- **The `type` field must reflect the actual part of speech** — use: `"noun"`, `"adjective"`, `"adverb"`, `"verb"`, `"verb phrase"`, `"idiom"`, `"collocation"`, `"noun phrase"`. Never use `"word"` as a type.
- **Every vocab item must have three fields**:
  - `definition` — clear, plain-English meaning written for an intermediate learner
  - `example` — one natural sentence showing the word used in a realistic context (workplace or advice situations preferred)
- **Words must appear in the answer verbatim** — the exact word or phrase (or its base form) must be findable as a substring in the answer text; do not list vocab that only appears in the question or that was paraphrased away
- **Morphological forms**: if the answer uses "commuting", the vocab entry word must be "commuting" (not "commute / commuting"); keep the word field to exactly the form used in the answer

### Continuing the Database (remaining 665 questions)
When asked to continue generating answers for the database:
1. Query the DB to find the next batch of unanswered records (`WHERE answer = '' ORDER BY id LIMIT 10`)
2. Generate answers and vocab following ALL rules above
3. Insert using the existing `update_template_answer(record_id, answer, vocabulary)` function in `modules/database.py`
4. Confirm how many remain after each batch

### Batch Size Rule
- **Maximum 10 questions per generation request** — never attempt all 40 in one request
- Process in batches of 10: fetch → generate → save → confirm → next batch
- This rule exists to guarantee consistent quality across every single answer
- Quality must be identical from question 1 to question 40 — never rush or shorten later answers
