"""
Adds 'frequency' and 'frequency_label' fields to all existing
part1_answers_9_10_*.json files based on question position.

Frequency mapping (matches all Part 1 question files):
  Q1  – Q10  → ★★★  High Probability
  Q11 – Q20  → ★★☆  Medium-High Probability
  Q21 – Q30  → ★★☆  Medium Probability
  Q31 – Q35  → ★☆☆  Lower Probability

Run:  python add_frequency_labels.py
"""

import os, json, glob

QUESTIONS_DIR = r"D:\YouTube\celpip_studio\data\questions\part1"

def frequency_for(index):
    """Return (stars, label) for a 0-based question index."""
    if index < 10:
        return "★★★", "High Probability"
    elif index < 20:
        return "★★☆", "Medium-High Probability"
    elif index < 30:
        return "★★☆", "Medium Probability"
    else:
        return "★☆☆", "Lower Probability"

files = glob.glob(os.path.join(QUESTIONS_DIR, "part1_answers_9_10_*.json"))

if not files:
    print("No answer JSON files found.")
else:
    for path in sorted(files):
        with open(path, "r", encoding="utf-8") as f:
            answers = json.load(f)

        changed = 0
        for i, ans in enumerate(answers):
            stars, label = frequency_for(i)
            if ans.get("frequency") != stars or ans.get("frequency_label") != label:
                ans["frequency"]       = stars
                ans["frequency_label"] = label
                changed += 1

        with open(path, "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)

        print(f"  {os.path.basename(path):50s}  {len(answers):2d} entries  ({changed} updated)")

print("\nDone.")
