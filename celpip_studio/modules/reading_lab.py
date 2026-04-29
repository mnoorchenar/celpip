"""
Reading Lab — vocabulary extraction and YouTube transcript support.
"""

import os
import re
import spacy
from spacy.matcher import Matcher

_nlp = None
_matcher = None

# Curated phrasal verbs — ordered longest-first so 3-part matches beat 2-part
PHRASAL_VERBS = [
    # 3-part
    "catch up on", "come down with", "come up against", "come up with",
    "come across as", "cut down on", "end up with", "face up to",
    "get along with", "get away with", "get back to", "get on with",
    "get out of", "get rid of", "get up to", "give up on",
    "go along with", "go back on", "keep up with", "keep track of",
    "let go of", "live up to", "look down on", "look forward to",
    "look out for", "look up to", "make do with", "make up for",
    "mess around with", "miss out on", "move on from", "opt out of",
    "pay attention to", "put up with", "run out of", "stand up for",
    "take care of", "take part in", "talk back to", "think back on",
    "watch out for", "zero in on",
    "check up on", "cut back on", "go back to", "go out of",
    "keep away from", "talk out of", "wait around for", "walk away from",
    # 2-part
    "back off", "back up", "blow up", "break down", "break off",
    "break out", "break up", "bring about", "bring in", "bring out",
    "bring up", "build up", "burn out", "call back", "call off",
    "call on", "call out", "call up", "calm down",
    "carry on", "catch on", "catch up", "check in", "check out",
    "cheer up", "clear up", "close down", "come across", "come along",
    "come back", "come down", "come out", "come up", "count on",
    "apply for", "ask about", "ask for", "ask out",
    "care about", "care for", "carry out",
    "cross out", "cut back", "cut down", "cut off", "deal with",
    "depend on", "die down", "die out", "drag on", "draw on", "drop off",
    "drop out", "end up", "fall apart", "fall back", "fall behind",
    "fall through", "figure out", "fill in", "fill out", "find out",
    "fit in", "get across", "get ahead", "get along", "get away",
    "get back", "get by", "get down", "get over", "get through",
    "give away", "give back", "give in", "give out", "give up",
    "go ahead", "go back", "go on", "go over", "go through",
    "focus on", "grow up", "hand in", "hand out", "hold back", "hold on",
    "hold out", "hold up", "insist on", "keep on", "keep up", "let down",
    "log in", "log out", "look after", "look ahead", "look back",
    "look for", "look into", "look out", "look up",
    "make out", "make up", "messed up", "mess up",
    "move on", "narrow down", "open up", "pass away", "pass on",
    "pay back", "pay for", "pay off", "pick out", "pick up", "point out",
    "rely on",
    "pull off", "pull out", "push through", "put aside", "put away",
    "put back", "put down", "put forward", "put off", "put out",
    "reach out", "rule out", "run away", "run into", "run out",
    "set aside", "set back", "set off", "set out", "set up",
    "settle down", "show off", "show up", "shut down", "sign in",
    "sign off", "sign out", "sign up", "sit back", "sit down",
    "sort out", "speak out", "speak up", "stand by", "stand out", "stand up",
    "step back", "step down", "step in", "step up", "stick out",
    "stick to", "sum up", "take back", "take off", "take on",
    "take over", "take up", "talk about", "talk through",
    "think about", "think over", "think through", "throw away",
    "try out", "turn around", "turn back", "turn down", "turn off",
    "turn on", "turn out", "turn up", "use up", "wake up",
    "walk away", "walk in", "walk into", "walk out", "walk through",
    "watch out", "wear out", "weigh up", "wind down", "wind up",
    "work on", "work out", "write down", "write off", "write up",
]

# Words spaCy doesn't mark as stop words but are too basic for vocab study
_EXTRA_BASIC = {
    'work', 'works', 'worked', 'working',
    'look', 'looks', 'looked', 'looking',
    'make', 'makes', 'made', 'making',
    'take', 'takes', 'took', 'taken', 'taking',
    'come', 'comes', 'came', 'coming',
    'give', 'gives', 'gave', 'given', 'giving',
    'know', 'knows', 'knew', 'known', 'knowing',
    'think', 'thinks', 'thought', 'thinking',
    'want', 'wants', 'wanted', 'wanting',
    'need', 'needs', 'needed', 'needing',
    'feel', 'feels', 'felt', 'feeling',
    'find', 'finds', 'found', 'finding',
    'tell', 'tells', 'told', 'telling',
    'start', 'starts', 'started', 'starting',
    'keep', 'keeps', 'kept', 'keeping',
    'help', 'helps', 'helped', 'helping',
    'show', 'shows', 'showed', 'shown', 'showing',
    'hear', 'hears', 'heard', 'hearing',
    'play', 'plays', 'played', 'playing',
    'move', 'moves', 'moved', 'moving',
    'live', 'lives', 'lived', 'living',
    'happen', 'happens', 'happened', 'happening',
    'talk', 'talks', 'talked', 'talking',
    'walk', 'walks', 'walked', 'walking',
    'read', 'reads', 'reading',
    'write', 'writes', 'wrote', 'written', 'writing',
    'become', 'becomes', 'became', 'becoming',
    'people', 'person', 'thing', 'things',
    'place', 'places', 'time', 'times',
    'year', 'years', 'day', 'days', 'week', 'weeks',
    'month', 'months', 'home', 'house', 'school',
    'family', 'friend', 'friends', 'money', 'life',
    'good', 'great', 'nice', 'best', 'better',
    'new', 'old', 'big', 'small', 'long', 'short',
    'high', 'low', 'first', 'last', 'next', 'same',
    'different', 'able', 'able', 'sure', 'right',
    'wrong', 'easy', 'hard', 'free',
    'well', 'back', 'still', 'even', 'just', 'also',
    'really', 'always', 'often', 'never', 'maybe',
    'little', 'much', 'many', 'most', 'more', 'less',
    'very', 'quite', 'able', 'both', 'each',
    'type', 'types', 'kind', 'kinds', 'lot', 'lots',
    'part', 'parts', 'point', 'points', 'fact', 'facts',
    'idea', 'ideas', 'word', 'words', 'question', 'questions',
    'answer', 'answers', 'example', 'examples',
    'information', 'number', 'numbers', 'issue', 'issues',
}


def _load_nlp():
    global _nlp, _matcher
    if _nlp is not None:
        return
    _nlp = spacy.load('en_core_web_sm')
    _matcher = Matcher(_nlp.vocab)
    patterns = []
    for pv in PHRASAL_VERBS:
        words = pv.split()
        # Use LEMMA for the verb (first token) so inflected forms match;
        # particles/prepositions are fixed, so LOWER is fine for the rest.
        pat = [{'LEMMA': words[0]}] + [{'LOWER': w} for w in words[1:]]
        patterns.append(pat)
    _matcher.add('PHRASAL_VERB', patterns)


def extract_items(text):
    """
    Returns list of {text, start, end, type} sorted by position.
    Types: phrasal_verb | noun_chunk | word
    """
    _load_nlp()
    doc = _nlp(text)
    covered = set()
    items = []

    # 1. Phrasal verbs — highest priority
    matches = _matcher(doc)
    # Sort by length descending so longer matches win over shorter ones
    matches = sorted(matches, key=lambda m: m[2] - m[1], reverse=True)
    for _, start_tok, end_tok in matches:
        span = doc[start_tok:end_tok]
        s, e = span.start_char, span.end_char
        if not any(i in covered for i in range(s, e)):
            items.append({'text': span.text, 'start': s, 'end': e, 'type': 'phrasal_verb'})
            covered.update(range(s, e))

    # 2. Multi-word noun chunks (strip leading determiners)
    for chunk in doc.noun_chunks:
        start_tok = chunk.start
        while start_tok < chunk.end and doc[start_tok].pos_ == 'DET':
            start_tok += 1
        if chunk.end - start_tok < 2:
            continue
        span = doc[start_tok:chunk.end]
        s, e = span.start_char, span.end_char
        if not any(i in covered for i in range(s, e)):
            items.append({'text': span.text, 'start': s, 'end': e, 'type': 'noun_chunk'})
            covered.update(range(s, e))

    # 3. Individual content words — tagged with actual POS
    _pos_map = {'NOUN': 'noun', 'VERB': 'verb', 'ADJ': 'adjective', 'ADV': 'adverb'}
    for token in doc:
        if token.pos_ not in _pos_map:
            continue
        if token.is_stop or token.is_punct or not token.is_alpha:
            continue
        if len(token.text) < 4:
            continue
        if token.lower_ in _EXTRA_BASIC:
            continue
        s, e = token.idx, token.idx + len(token.text)
        if not any(i in covered for i in range(s, e)):
            items.append({'text': token.text, 'start': s, 'end': e, 'type': _pos_map[token.pos_]})
            covered.update(range(s, e))

    return sorted(items, key=lambda x: x['start'])


def build_segments(text, items):
    """Split text into plain/tagged segments for frontend rendering."""
    segments = []
    pos = 0
    for item in sorted(items, key=lambda x: x['start']):
        if item['start'] > pos:
            segments.append({'text': text[pos:item['start']], 'type': 'plain'})
        segments.append(item)
        pos = item['end']
    if pos < len(text):
        segments.append({'text': text[pos:], 'type': 'plain'})
    return segments


def get_youtube_transcript(url):
    """
    Extract transcript text from a YouTube URL.
    Returns (text, video_id).
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    patterns = [
        r'(?:v=)([A-Za-z0-9_-]{11})',
        r'(?:youtu\.be/)([A-Za-z0-9_-]{11})',
        r'(?:embed/)([A-Za-z0-9_-]{11})',
    ]
    video_id = None
    for p in patterns:
        m = re.search(p, url)
        if m:
            video_id = m.group(1)
            break

    if not video_id:
        raise ValueError('Could not extract video ID from URL')

    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    raw = ' '.join(snippet.text for snippet in transcript)
    # Remove [Music], [Applause] etc.
    raw = re.sub(r'\[.*?\]', '', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()

    return raw, video_id
