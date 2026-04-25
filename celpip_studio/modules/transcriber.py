"""
Whisper-based audio transcription with sentence alignment.
Falls back to even distribution if Whisper is unavailable.
"""

import os
import sys

from modules.phrase_matcher import safe_similarity

try:
    import whisper as _whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# Cache loaded model
_model = None


def _get_model():
    global _model
    if _model is None:
        from config import WHISPER_MODEL
        _model = _whisper.load_model(WHISPER_MODEL)
    return _model


def transcribe(audio_path):
    """
    Transcribe audio file.
    Returns list of segment dicts: {text, start, end}
    """
    if not WHISPER_AVAILABLE:
        return []
    try:
        model = _get_model()
        result = model.transcribe(audio_path, word_timestamps=False)
        segments = []
        for seg in result.get('segments', []):
            segments.append({
                'text': seg['text'].strip(),
                'start': float(seg['start']),
                'end': float(seg['end']),
            })
        return segments
    except Exception as e:
        print(f"[Transcriber] Whisper error: {e}", file=sys.stderr)
        return []


def align_sentences(sentences, segments):
    """
    Match input sentences to transcription segments.
    Returns list of {text, start_time, end_time}.

    If segments is empty (Whisper not available), falls back to even distribution.
    The total duration is estimated from the last segment end.
    """
    if not sentences:
        return []

    if not segments:
        # Fallback: evenly distribute across a default response window
        # We'll use 60 seconds as a default; caller may adjust
        total = 60.0
        dur = total / len(sentences)
        result = []
        for i, s in enumerate(sentences):
            result.append({
                'text': s,
                'start_time': i * dur,
                'end_time': (i + 1) * dur,
            })
        return result

    # Build a flat word/sentence alignment by matching sentences to segments
    total_duration = segments[-1]['end']
    n = len(sentences)

    # Try to greedily assign segments to sentences in order
    result = []
    seg_idx = 0
    n_segs = len(segments)

    for i, sentence in enumerate(sentences):
        sentence_lower = sentence.lower().strip().rstrip('.!?')
        # Look for the segment whose text best matches this sentence
        best_seg = None
        best_score = -1

        search_start = seg_idx
        search_end = min(n_segs, seg_idx + max(3, n_segs // n + 2))

        for j in range(search_start, search_end):
            seg_text = segments[j]['text'].strip()
            overlap = safe_similarity(sentence, seg_text)
            if overlap > best_score:
                best_score = overlap
                best_seg = j

        if best_seg is not None and best_score > 0.25:
            # Extend to include adjacent segments if needed
            start_seg = best_seg
            end_seg = best_seg

            # Check if next segments belong to same sentence (for long sentences)
            remaining_words = set(sentence_lower.split())
            covered = set(segments[best_seg]['text'].lower().split())
            remaining_words -= covered

            while remaining_words and end_seg + 1 < n_segs:
                next_words = set(segments[end_seg + 1]['text'].lower().split())
                new_covered = remaining_words & next_words
                if new_covered:
                    end_seg += 1
                    remaining_words -= new_covered
                else:
                    break

            result.append({
                'text': sentence,
                'start_time': segments[start_seg]['start'],
                'end_time': segments[end_seg]['end'],
            })
            seg_idx = end_seg + 1
        else:
            # Fallback: interpolate based on position
            frac_start = i / n
            frac_end = (i + 1) / n
            result.append({
                'text': sentence,
                'start_time': frac_start * total_duration,
                'end_time': frac_end * total_duration,
            })

    # Ensure no overlaps and monotonically increasing
    for i in range(1, len(result)):
        if result[i]['start_time'] < result[i - 1]['end_time']:
            result[i]['start_time'] = result[i - 1]['end_time']
        if result[i]['end_time'] <= result[i]['start_time']:
            result[i]['end_time'] = result[i]['start_time'] + 2.0

    return result


def fallback_align(sentences, total_duration):
    """Evenly distribute sentences over total_duration seconds."""
    if not sentences:
        return []
    dur = total_duration / len(sentences)
    return [
        {
            'text': s,
            'start_time': i * dur,
            'end_time': (i + 1) * dur,
        }
        for i, s in enumerate(sentences)
    ]
