import json
import os

from modules.phrase_matcher import safe_similarity, normalize

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'categories.json')


def _load():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_all():
    """Return the full categories dict."""
    return _load()


def get_categories(section, part):
    """Return list of user-added categories for that section/part."""
    data = _load()
    section = section.lower()
    part = part.lower()
    try:
        return data[section][part]['categories']
    except KeyError:
        return []


def add_category(section, part, name):
    """Add category if not already exists, save, return updated list."""
    data = _load()
    section = section.lower()
    part = part.lower()
    name = name.strip()
    if not name:
        return get_categories(section, part)
    if section not in data:
        data[section] = {}
    if part not in data[section]:
        data[section][part] = {'name': '', 'categories': []}
    cats = data[section][part]['categories']
    if name not in cats:
        cats.append(name)
        _save(data)
    return cats


def search_categories(section, part, query, threshold=0.35):
    """
    Filter categories by query using multi-layer phrase matching.
    Falls back to substring match so short/exact queries still work.
    Results are sorted by score descending.
    """
    cats = get_categories(section, part)
    query = query.strip()
    if not query:
        return cats

    query_norm = normalize(query)
    scored = []
    for c in cats:
        # Exact / substring fast-path (handles short 1-2 word queries well)
        if query_norm in normalize(c):
            scored.append((c, 1.0))
            continue
        score = safe_similarity(query, c)
        if score >= threshold:
            scored.append((c, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]
