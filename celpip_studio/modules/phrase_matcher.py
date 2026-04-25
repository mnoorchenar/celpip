"""
Professional phrase matching with normalization, negation guard, and bigram scoring.
"""

import re

# ── Contraction map ─────────────────────────────────────────────────────────────

CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "won't": "will not", "wouldn't": "would not", "couldn't": "could not",
    "shouldn't": "should not", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not", "you're": "you are",
    "i'm": "i am", "he's": "he is", "she's": "she is", "it's": "it is",
    "we're": "we are", "they're": "they are", "i've": "i have",
    "you've": "you have", "we've": "we have", "they've": "they have",
    "i'd": "i would", "you'd": "you would", "he'd": "he would",
    "i'll": "i will", "you'll": "you will", "they'll": "they will",
    "can't": "cannot", "let's": "let us", "that's": "that is",
    "there's": "there is", "here's": "here is", "what's": "what is",
    "who's": "who is", "where's": "where is", "how's": "how is",
    "they'd": "they would", "she'd": "she would", "we'd": "we would",
    "you'd": "you would", "it'd": "it would", "that'd": "that would",
    "i'm": "i am", "y'all": "you all", "gonna": "going to",
    "wanna": "want to", "gotta": "got to", "kinda": "kind of",
    "sorta": "sort of", "hafta": "have to", "oughta": "ought to",
}

# Words that carry no semantic weight for matching
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "i", "you", "he", "she", "we", "they",
    "me", "him", "her", "us", "them", "my", "your", "his", "our", "their",
}

# Spoken filler words that add no meaning
FILLERS = {
    "um", "uh", "like", "you", "know", "mean", "basically", "literally",
    "actually", "just", "so", "well", "right", "okay", "ok", "then",
}

# Negation markers — used to detect meaning-flipping words
_NEG_PATTERN = re.compile(
    r"\b(not|no|never|nobody|nothing|nowhere|neither|nor|hardly|barely|"
    r"don't|doesn't|didn't|won't|can't|couldn't|shouldn't|wouldn't|"
    r"isn't|aren't|wasn't|weren't)\b",
    re.IGNORECASE,
)


# ── Normalization ───────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, expand contractions, strip punctuation, collapse spaces."""
    text = text.lower().strip()
    for contraction, expanded in CONTRACTIONS.items():
        text = re.sub(r'\b' + re.escape(contraction) + r'\b', expanded, text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def content_words(text: str) -> set:
    """Return meaningful words after normalization, minus stop words and fillers."""
    return {
        w for w in normalize(text).split()
        if w not in STOP_WORDS and w not in FILLERS
    }


def _bigrams(text: str) -> set:
    words = normalize(text).split()
    return set(zip(words, words[1:])) if len(words) > 1 else set()


def has_negation(text: str) -> bool:
    return bool(_NEG_PATTERN.search(text))


# ── Scoring ─────────────────────────────────────────────────────────────────────

def phrase_similarity(a: str, b: str) -> float:
    """
    Returns 0.0–1.0 similarity score using three weighted signals:
      - 50%  Jaccard on content words  (what words are shared)
      - 35%  Bigram overlap            (word-order awareness)
      - 15%  Length ratio              (penalises extreme size mismatch)
    """
    a_words = content_words(a)
    b_words = content_words(b)

    if not a_words or not b_words:
        return 0.0

    # Signal 1: content-word Jaccard
    jaccard = len(a_words & b_words) / len(a_words | b_words)

    # Signal 2: bigram overlap
    a_bi = _bigrams(a)
    b_bi = _bigrams(b)
    if a_bi or b_bi:
        bigram_score = len(a_bi & b_bi) / max(len(a_bi | b_bi), 1)
    else:
        bigram_score = jaccard  # single-word phrases fall back to Jaccard

    # Signal 3: length ratio
    len_ratio = min(len(a_words), len(b_words)) / max(len(a_words), len(b_words))

    return round(0.50 * jaccard + 0.35 * bigram_score + 0.15 * len_ratio, 4)


def safe_similarity(a: str, b: str) -> float:
    """
    phrase_similarity with a negation guard:
    if one phrase is negated and the other is not, score is forced to 0.
    Prevents 'It's a good idea' from matching 'It's not a good idea'.
    """
    if has_negation(a) != has_negation(b):
        return 0.0
    return phrase_similarity(a, b)
