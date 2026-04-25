"""
CELPIP Practice Studio — Video assembly pipeline.

Speed improvements vs. original:
  • BAR_STEPS = 10 fixed steps per shadowing pause (was bar_fps×pause_dur ≈ 50–75 unique frames)
  • SHADOW_SEC_PER_WORD halved to 0.5  → shorter pause durations
  • Single-pass FFmpeg encode: one big concat → one encode → one mux (was 19 subprocesses)
  • Pure-Python WAV concatenation (no FFmpeg for audio assembly)
  • Section-1 countdown: one frame per PREP_STEP seconds (was 1 frame/second)
"""

import os
import sys
import shutil
import subprocess
import threading
import wave as _wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    TEMP_DIR, VIDEO_FPS, VIDEO_WIDTH, VIDEO_HEIGHT, TASK_DEFAULTS
)
from modules import frame_renderer as fr, style_gen, kokoro_tts

_tts_init_lock = threading.Lock()

W, H = VIDEO_WIDTH, VIDEO_HEIGHT
FPS  = VIDEO_FPS

# ── Tuning constants ────────────────────────────────────────────────────────
# Seconds each viewer gets to repeat a shadow sentence (per word)
SHADOW_SEC_PER_WORD = 0.7        # sec per word for shadowing pause
# Repetitions per sentence in the shadowing section
SHADOW_REPS = 2
# Fixed number of animated bar frames per pause (regardless of pause length)
BAR_STEPS = 10                   # was bar_fps=5 → up to 75 frames; now always 10
# Transition slide duration (seconds)
TRANSITION_DUR = 2.5
# Pause between sentences in answer section
ANSWER_SENT_PAUSE = 0.4
# Seconds per prep-countdown frame (section 1)
PREP_STEP = 1                    # 1 frame per second — smooth countdown


# ── FFmpeg helpers ──────────────────────────────────────────────────────────

def _run_ffmpeg(args, label=''):
    cmd = ['ffmpeg', '-y'] + args
    r   = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f'FFmpeg failed [{label}]:\n'
            f'CMD: {" ".join(cmd)}\n'
            f'STDERR: {r.stderr[-3000:]}'
        )
    return r


def _write_concat(path, items):
    """Write FFmpeg image concat file. items: [(filepath, duration_sec), ...]"""
    with open(path, 'w', encoding='utf-8') as f:
        for fp, dur in items:
            f.write(f"file '{fp.replace(chr(92), '/')}'\n")
            f.write(f'duration {dur:.4f}\n')


def _save_png(img, path):
    img.save(path, 'PNG', compress_level=0)
    return path


def _split_sentences(text):
    import re
    text  = text.strip()
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if p.strip()] or [text]


def _strip_markers(text):
    """Remove {marker} braces from text, keeping the enclosed words."""
    import re
    return re.sub(r'[{}]', '', text)


def _word_count(text):
    return len((_strip_markers(text) or '').split())


# ── Audio helpers (pure Python — no FFmpeg subprocesses) ────────────────────

def _silence_wav(path, duration):
    """Generate a silent WAV (24 kHz mono PCM_16) — no ffmpeg needed."""
    sample_rate = 24000
    n_samples   = int(sample_rate * duration)
    with _wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b'\x00' * n_samples * 2)


def _concat_wavs_python(wav_list, out_path):
    """
    Concatenate WAV files in pure Python — zero FFmpeg subprocesses.
    All inputs must share the same format (24 kHz mono 16-bit), which they
    always do here: both Kokoro TTS output and our silence generator use that format.
    """
    if not wav_list:
        _silence_wav(out_path, 0.1)
        return
    if len(wav_list) == 1:
        shutil.copy(wav_list[0], out_path)
        return

    with _wave.open(wav_list[0], 'rb') as first:
        params = first.getparams()

    with _wave.open(out_path, 'wb') as out:
        out.setparams(params)
        for wav_path in wav_list:
            try:
                with _wave.open(wav_path, 'rb') as w:
                    out.writeframes(w.readframes(w.getnframes()))
            except Exception as e:
                print(f'[VideoBuilder] WAV concat skip ({wav_path}): {e}', file=sys.stderr)


# ── Parallel TTS pre-generation ─────────────────────────────────────────────

def _generate_all_tts(tasks, max_workers=4):
    """
    Run all TTS tasks in parallel threads.
    tasks: dict of key -> (text, path, voice)
    Returns dict of key -> duration_seconds.
    """
    # Pre-warm Kokoro before spawning threads (avoids race on init)
    with _tts_init_lock:
        kokoro_tts._get_kokoro()

    results = {}

    def _synth(key, text, path, voice):
        dur = kokoro_tts.to_wav_file(text, path, voice)
        return key, dur

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_synth, key, text, path, voice): key
            for key, (text, path, voice) in tasks.items()
        }
        for future in as_completed(futures):
            key, dur = future.result()
            results[key] = dur

    return results


# ── Section frame builders ───────────────────────────────────────────────────
# Each returns (items, wavs):
#   items = [(png_path, duration_secs), ...]
#   wavs  = [wav_path, ...]         (same total length as items when concatenated)

def _build_section1(job_temp, question, task_name, prep_time, response_time,
                    sentences, style, progress_cb, tts_paths, tts_durs):
    """Section 1: Question display + prep countdown."""
    progress_cb('Rendering exam section...', 12)
    s1_dir = os.path.join(job_temp, 's1')
    os.makedirs(s1_dir, exist_ok=True)

    items, wavs = [], []

    # Transition slide
    tr_img  = fr.render_section_transition(1, style)
    tr_path = _save_png(tr_img, os.path.join(s1_dir, 'transition.png'))
    items.append((tr_path, TRANSITION_DUR))
    sil_tr = os.path.join(s1_dir, 'sil_tr.wav')
    _silence_wav(sil_tr, TRANSITION_DUR)
    wavs.append(sil_tr)

    # TTS reads the question — full question shown at once (matches real exam behaviour)
    q_wav      = tts_paths['question']
    q_dur      = tts_durs['question']
    prep_frame = fr.render_prep_frame(task_name, question, prep_time, prep_time, style=style)
    pf_path    = _save_png(prep_frame, os.path.join(s1_dir, 'prep_read.png'))
    items.append((pf_path, q_dur))
    wavs.append(q_wav)

    # Prep countdown — one frame per PREP_STEP seconds (not per second)
    remaining_prep = max(0, prep_time - int(q_dur))
    t = remaining_prep
    frame_idx = 0
    while t > 0:
        step = min(PREP_STEP, t)
        img = fr.render_prep_frame(task_name, question, t, prep_time, style=style)
        fp  = _save_png(img, os.path.join(s1_dir, f'prep_{frame_idx:04d}.png'))
        items.append((fp, float(step)))
        frame_idx += 1
        t -= step
    if remaining_prep > 0:
        sil_prep = os.path.join(s1_dir, 'sil_prep.wav')
        _silence_wav(sil_prep, remaining_prep)
        wavs.append(sil_prep)

    return items, wavs


def _build_section2(job_temp, question, task_name, response_time,
                    sentences, style, progress_cb, tts_paths, tts_durs,
                    vocab_words=None):
    """Section 2: Model answer, sentence by sentence."""
    progress_cb('Rendering exam section...', 22)
    s2_dir = os.path.join(job_temp, 's2')
    os.makedirs(s2_dir, exist_ok=True)

    items, wavs = [], []
    png_path = None

    # Transition
    tr_img  = fr.render_section_transition(2, style)
    tr_path = _save_png(tr_img, os.path.join(s2_dir, 'transition.png'))
    items.append((tr_path, TRANSITION_DUR))
    sil_tr = os.path.join(s2_dir, 'sil_tr.wav')
    _silence_wav(sil_tr, TRANSITION_DUR)
    wavs.append(sil_tr)

    # Build fake timing for all sentences (for the response frame renderer)
    fake_sents = []
    t = 0.0
    for s in sentences:
        d = max(1.0, _word_count(s) / 2.5)
        fake_sents.append({'text': s, 'start_time': t, 'end_time': t + d})
        t += d

    # Detect overflow and split into pages
    pages       = fr.compute_page_split(fake_sents, style)
    total_pages = len(pages)

    # Map each global sentence index → (page_num, local_idx within that page)
    sent_page_map = {}
    for pg_idx, page_sents in enumerate(pages):
        for local_idx, s in enumerate(page_sents):
            # Match by text since fake_sents dicts are reused
            text = s['text'] if isinstance(s, dict) else s
            for gi, fs in enumerate(fake_sents):
                if fs['text'] == text and gi not in sent_page_map:
                    sent_page_map[gi] = (pg_idx + 1, local_idx, page_sents)
                    break

    for i, sent in enumerate(sentences):
        wav_path = tts_paths[f'sent_{i}']
        dur      = tts_durs[f'sent_{i}']

        pg_num, local_idx, page_sents = sent_page_map.get(i, (1, i, fake_sents))

        img = fr.render_response_frame(
            task_name, question, page_sents, local_idx,
            max(1, int(response_time - sum(
                _word_count(s) / 2.5 for s in sentences[:i]))),
            response_time, style=style, vocab_words=vocab_words,
            page_num=pg_num if total_pages > 1 else None,
            total_pages=total_pages if total_pages > 1 else None,
        )
        png_path = _save_png(img, os.path.join(s2_dir, f'sent_{i:03d}.png'))
        items.append((png_path, dur))
        wavs.append(wav_path)

        # Short pause between sentences
        if i < len(sentences) - 1:
            sil = os.path.join(s2_dir, f'pause_{i:03d}.wav')
            _silence_wav(sil, ANSWER_SENT_PAUSE)
            items.append((png_path, ANSWER_SENT_PAUSE))
            wavs.append(sil)

    # Hold last sentence frame
    if png_path:
        hold_sil = os.path.join(s2_dir, 'sil_end_hold.wav')
        _silence_wav(hold_sil, 3.0)
        items.append((png_path, 3.0))
        wavs.append(hold_sil)

    return items, wavs


def _build_section3(job_temp, task_name, vocab, style, progress_cb, tts_paths, tts_durs):
    """Section 3: Vocabulary building, one word at a time."""
    progress_cb('Rendering vocabulary pages...', 38)
    s3_dir = os.path.join(job_temp, 's3')
    os.makedirs(s3_dir, exist_ok=True)

    items, wavs = [], []

    # Transition
    tr_img  = fr.render_section_transition(3, style)
    tr_path = _save_png(tr_img, os.path.join(s3_dir, 'transition.png'))
    items.append((tr_path, TRANSITION_DUR))
    sil_tr = os.path.join(s3_dir, 'sil_tr.wav')
    _silence_wav(sil_tr, TRANSITION_DUR)
    wavs.append(sil_tr)

    total_vocab = sum(1 for v in vocab if v.get('word'))
    word_counter = 0
    for vi, v in enumerate(vocab):
        word = v.get('word', '')
        if not word:
            continue
        wav_path = tts_paths[f'vocab_{vi}']
        dur      = tts_durs[f'vocab_{vi}']

        img      = fr.render_vocab_page(
            word, v.get('type', 'word'), v.get('definition', ''), v.get('example', ''), style,
            word_idx=word_counter, total_words=total_vocab)
        word_counter += 1
        png_path = _save_png(img, os.path.join(s3_dir, f'vocab_{vi:03d}.png'))

        # TTS duration + short linger
        hold = dur + 1.5
        items.append((png_path, hold))
        wavs.append(wav_path)
        sil = os.path.join(s3_dir, f'linger_{vi:03d}.wav')
        _silence_wav(sil, 1.5)
        wavs.append(sil)

    return items, wavs


def _build_section4(job_temp, task_name, sentences, vocab_words,
                    style, progress_cb, tts_paths, tts_durs):
    """
    Section 4: Shadowing.
    Uses BAR_STEPS fixed frames per pause — constant regardless of pause length.
    This eliminates the old bar_fps×pause_dur frame explosion.
    """
    progress_cb('Rendering vocabulary pages...', 55)
    s4_dir = os.path.join(job_temp, 's4')
    os.makedirs(s4_dir, exist_ok=True)

    items, wavs = [], []

    # Transition (reused as instruction slide too — saves one render)
    tr_img  = fr.render_section_transition(4, style)
    tr_path = _save_png(tr_img, os.path.join(s4_dir, 'transition.png'))
    items.append((tr_path, TRANSITION_DUR))
    sil_tr = os.path.join(s4_dir, 'sil_tr.wav')
    _silence_wav(sil_tr, TRANSITION_DUR)
    wavs.append(sil_tr)

    # 3-second instruction hold (reuse same PNG — no extra render)
    items.append((tr_path, 3.0))
    sil_inst = os.path.join(s4_dir, 'sil_inst.wav')
    _silence_wav(sil_inst, 3.0)
    wavs.append(sil_inst)

    sent_dicts = [{'text': s} for s in sentences]

    for si, sent in enumerate(sentences):
        wc        = _word_count(sent)
        pause_dur = max(2.0, wc * SHADOW_SEC_PER_WORD)

        base_tts_wav = tts_paths[f'sent_{si}']
        base_tts_dur = tts_durs[f'sent_{si}']

        for rep in range(1, SHADOW_REPS + 1):
            prefix = f's{si:03d}_r{rep}'

            # ── TTS phase: one static frame for the full TTS duration ──────
            tts_img = fr.render_shadow_frame(
                sent, sent_dicts, si, vocab_words,
                rep, SHADOW_REPS, 'tts', 1.0, style)
            tts_png = _save_png(tts_img, os.path.join(s4_dir, f'{prefix}_tts.png'))
            items.append((tts_png, base_tts_dur))
            wavs.append(base_tts_wav)

            # ── Pause phase: BAR_STEPS frames (constant count) ────────────
            frame_dur = pause_dur / BAR_STEPS
            sil_step  = os.path.join(s4_dir, f'{prefix}_sil_step.wav')
            _silence_wav(sil_step, frame_dur)   # one silence file reused for all steps

            for fi in range(BAR_STEPS):
                ratio   = 1.0 - (fi / BAR_STEPS)
                bar_img = fr.render_shadow_frame(
                    sent, sent_dicts, si, vocab_words,
                    rep, SHADOW_REPS, 'pause', ratio, style)
                bar_png = _save_png(bar_img,
                                    os.path.join(s4_dir, f'{prefix}_bar_{fi:02d}.png'))
                items.append((bar_png, frame_dur))
                wavs.append(sil_step)   # same silence file referenced multiple times — OK

    return items, wavs


def _build_section5(job_temp, task_name, sentences, vocab_words,
                    style, progress_cb, tts_paths, tts_durs):
    """Section 5: Final answer review with vocab highlights."""
    progress_cb('Rendering review section...', 72)
    s5_dir = os.path.join(job_temp, 's5')
    os.makedirs(s5_dir, exist_ok=True)

    items, wavs = [], []

    # Transition
    tr_img  = fr.render_section_transition(5, style)
    tr_path = _save_png(tr_img, os.path.join(s5_dir, 'transition.png'))
    items.append((tr_path, TRANSITION_DUR))
    sil_tr = os.path.join(s5_dir, 'sil_tr.wav')
    _silence_wav(sil_tr, TRANSITION_DUR)
    wavs.append(sil_tr)

    sent_dicts = [{'text': s} for s in sentences]
    png_path   = None

    # Detect overflow and split into pages so all sentences are visible at once
    pages       = fr.compute_page_split(sent_dicts, style)
    total_pages = len(pages)

    # Map each global sentence index → (page_num, local_idx, page_sents)
    sent_page_map = {}
    for pg_idx, page_sents in enumerate(pages):
        for local_idx, s in enumerate(page_sents):
            text = s['text'] if isinstance(s, dict) else s
            for gi, sd in enumerate(sent_dicts):
                if sd['text'] == text and gi not in sent_page_map:
                    sent_page_map[gi] = (pg_idx + 1, local_idx, page_sents)
                    break

    for si, sent in enumerate(sentences):
        wav_path = tts_paths[f'sent_{si}']
        dur      = tts_durs[f'sent_{si}']

        pg_num, local_idx, page_sents = sent_page_map.get(si, (1, si, sent_dicts))

        img = fr.render_final_answer_frame(
            task_name, page_sents, local_idx, vocab_words, style,
            page_num=pg_num if total_pages > 1 else None,
            total_pages=total_pages if total_pages > 1 else None,
        )
        png_path = _save_png(img, os.path.join(s5_dir, f'sent_{si:03d}.png'))
        items.append((png_path, dur))
        wavs.append(wav_path)

        if si < len(sentences) - 1:
            sil = os.path.join(s5_dir, f'pause_{si:03d}.wav')
            _silence_wav(sil, ANSWER_SENT_PAUSE)
            items.append((png_path, ANSWER_SENT_PAUSE))
            wavs.append(sil)

    return items, wavs


def _build_intro(job_temp, task_num, task_name, band, category, title,
                  thumb_seed, thumb_color, thumb_font=None, thumb_font_scale=1.0,
                  freq_label=None, freq_color=None, category_slug=None, speaker_label=None):
    """4-second thumbnail intro frame at 1920×1080 (opens every video)."""
    intro_dir = os.path.join(job_temp, 'intro')
    os.makedirs(intro_dir, exist_ok=True)
    img      = fr.render_intro_frame(task_num, task_name, band, category, title,
                                      seed=thumb_seed, color_theme=thumb_color,
                                      thumb_font=thumb_font, font_scale=thumb_font_scale,
                                      freq_label=freq_label, freq_color=freq_color,
                                      category_slug=category_slug,
                                      speaker_label=speaker_label)
    png_path = _save_png(img, os.path.join(intro_dir, 'intro.png'))
    sil_path = os.path.join(intro_dir, 'sil_intro.wav')
    _silence_wav(sil_path, 4.0)
    return [(png_path, 4.0)], [sil_path]


def _build_outro(job_temp, style=None):
    """CTA slide shown after Section 5 and before the engage slide (5 seconds)."""
    outro_img  = fr.render_outro_frame(style=style)
    outro_path = os.path.join(job_temp, 'outro.png')
    _save_png(outro_img, outro_path)
    sil_path = os.path.join(job_temp, 'sil_outro.wav')
    _silence_wav(sil_path, 5.0)
    return [(outro_path, 5.0)], [sil_path]


def _build_engage(job_temp, seed=None):
    """Like/subscribe + gift-draw slide, shown just before the disclaimer (5 seconds)."""
    eng_img  = fr.render_engage_frame(seed=seed)
    eng_path = os.path.join(job_temp, 'engage.png')
    _save_png(eng_img, eng_path)
    sil_path = os.path.join(job_temp, 'sil_engage.wav')
    _silence_wav(sil_path, 5.0)
    return [(eng_path, 5.0)], [sil_path]


def _build_disclaimer(job_temp, progress_cb, style=None):
    """Disclaimer slide, 5 seconds."""
    progress_cb('Rendering disclaimer...', 88)
    disc_img  = fr.render_disclaimer_frame(style=style)
    disc_path = os.path.join(job_temp, 'disclaimer.png')
    _save_png(disc_img, disc_path)
    sil_path  = os.path.join(job_temp, 'sil_disc.wav')
    _silence_wav(sil_path, 5.0)
    return [(disc_path, 5.0)], [sil_path]


# ── Main entry point ─────────────────────────────────────────────────────────

def build_video(job_data, section_seeds, voice, output_path, progress_cb=None):
    """
    Build the full YouTube video from job_data using Kokoro TTS.

    Optimised pipeline:
      Phase 1 — Parallel TTS (all sentences + vocab in one ThreadPoolExecutor batch)
      Phase 2 — Render all section frames (Pillow)
      Phase 3 — Single FFmpeg encode (one process for entire video)
      Phase 4 — Python WAV concat (no FFmpeg subprocess for audio)
      Phase 5 — Single FFmpeg mux (video + audio)
    """
    if progress_cb is None:
        progress_cb = lambda s, p: None

    task_num  = int(job_data.get('task_num', 1))
    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    task_name = task_info['name']
    prep_time = task_info['prep']
    resp_time = task_info['response']

    question  = job_data['question']
    answer    = job_data['answer']
    vocab     = job_data.get('vocab', [])

    sentences   = _split_sentences(answer)
    vocab_words = [{'word': v.get('word', ''), 'definition': v.get('definition', '')}
                   for v in vocab if v.get('word')]

    _raw_scales = job_data.get('font_scales', {})
    _scale_defaults = {1: 1.4, 2: 1.1, 3: 1.0, 4: 1.0, 5: 1.1}
    font_scales = {i: float(_raw_scales.get(str(i), _raw_scales.get(i, _scale_defaults[i])))
                   for i in range(1, 6)}

    # Resolve category slug for group style (sections 1 & 2 use category brand color)
    import re as _re
    cat_slug = job_data.get('category_slug') or _re.sub(
        r'[^a-z0-9]+', '_', job_data.get('category', '').lower()).strip('_')
    band_key = job_data.get('band', '9_10')
    freq_key = job_data.get('freq', 'medium')

    # Format band key for display (e.g. "9_10" → "Band 9-10")
    _band_display = 'Band ' + band_key.replace('_', '-')

    styles = {}
    for s in range(1, 6):
        if s in (1, 2):
            # Category-branded sections: fixed accent + section badge, random decoration
            st = style_gen.make_group_style(
                category_slug=cat_slug, band=band_key, freq=freq_key,
                section=s, seed=section_seeds.get(s)
            )
        else:
            # Vocab / Shadowing / Final Review: fully random for visual variety
            st = style_gen.generate_section_style(s, seed=section_seeds.get(s))
        st['font_scale'] = font_scales.get(s, 1.0)
        st['section_num'] = s          # progress indicator ("2/5" in top bar)
        if s in (2, 5):
            st['band_label'] = _band_display   # "Band 9-10" badge in answer/review sections
        styles[s] = st

    # Freq label for thumbnail
    _freq_cfg   = style_gen.FREQ_CONFIG.get(freq_key, style_gen.FREQ_CONFIG['medium'])
    _freq_label = _freq_cfg['label']
    _freq_color = _freq_cfg['color']


    import uuid
    job_temp = os.path.join(TEMP_DIR, f'build_{uuid.uuid4().hex}')
    os.makedirs(job_temp, exist_ok=True)

    try:
        # ── Phase 1: Generate all TTS in parallel ────────────────────────
        progress_cb('Transcribing audio...', 5)
        tts_tasks = {}
        tts_tasks['question'] = (question,
                                  os.path.join(job_temp, 'tts_question.wav'), voice)
        for i, sent in enumerate(sentences):
            tts_tasks[f'sent_{i}'] = (_strip_markers(sent),
                                       os.path.join(job_temp, f'tts_sent_{i:03d}.wav'), voice)
        for vi, v in enumerate(vocab):
            if v.get('word'):
                tts_text = f"{v['word']}. {v.get('definition', '')}."
                if v.get('example'):
                    tts_text += f" Example: {v['example']}."
                tts_tasks[f'vocab_{vi}'] = (tts_text,
                                             os.path.join(job_temp, f'tts_vocab_{vi:03d}.wav'),
                                             voice)

        tts_durs  = _generate_all_tts(tts_tasks)
        tts_paths = {key: path for key, (_, path, _) in tts_tasks.items()}

        # ── Phase 2: Build all section frames ────────────────────────────
        thumb_color = job_data.get('thumb_color')

        # Intro (thumbnail at 1920×1080) — always first
        intro_items, intro_wavs = _build_intro(
            job_temp, task_num, task_name,
            band_key,
            job_data.get('category', ''),
            job_data.get('title', ''),
            job_data.get('thumb_seed'),
            thumb_color,
            thumb_font=job_data.get('thumb_font'),
            thumb_font_scale=float(job_data.get('thumb_font_scale', 1.0)),
            freq_label=_freq_label,
            freq_color=_freq_color,
            category_slug=cat_slug,
            speaker_label=job_data.get('voice_label'),
        )
        all_items: list = list(intro_items)
        all_wavs:  list = list(intro_wavs)

        for sec_fn, args in [
            (_build_section1, (job_temp, question, task_name, prep_time, resp_time,
                               sentences, styles[1], progress_cb, tts_paths, tts_durs)),
            (_build_section2, (job_temp, question, task_name, resp_time,
                               sentences, styles[2], progress_cb, tts_paths, tts_durs,
                               vocab_words)),
            (_build_section3, (job_temp, task_name, vocab, styles[3],
                               progress_cb, tts_paths, tts_durs)),
            (_build_section4, (job_temp, task_name, sentences, vocab_words,
                               styles[4], progress_cb, tts_paths, tts_durs)),
            (_build_section5, (job_temp, task_name, sentences, vocab_words,
                               styles[5], progress_cb, tts_paths, tts_durs)),
        ]:
            items, wavs = sec_fn(*args)
            all_items.extend(items)
            all_wavs.extend(wavs)

        # Outro CTA slide (Practice Complete + subscribe prompt)
        outro_items, outro_wavs = _build_outro(job_temp, style=styles[5])
        all_items.extend(outro_items)
        all_wavs.extend(outro_wavs)

        # Engage slide — seed=None makes Python's Random use system entropy,
        # so each build gets a truly different message and emoji.
        eng_items, eng_wavs = _build_engage(job_temp, seed=None)
        all_items.extend(eng_items)
        all_wavs.extend(eng_wavs)

        disc_items, disc_wavs = _build_disclaimer(job_temp, progress_cb, style=styles[1])
        all_items.extend(disc_items)
        all_wavs.extend(disc_wavs)

        # ── Phase 3: Prepare concat file + audio WAV ─────────────────────
        progress_cb('Encoding video...', 90)

        concat_txt   = os.path.join(job_temp, 'all_frames.txt')
        raw_video    = os.path.join(job_temp, 'raw_video.mp4')
        combined_wav = os.path.join(job_temp, 'combined_audio.wav')
        encoded_aac  = os.path.join(job_temp, 'audio.m4a')

        _write_concat(concat_txt, all_items)

        # Python WAV concat + 1 s tail-padding so audio is never shorter than video
        tail_sil = os.path.join(job_temp, 'sil_tail.wav')
        _silence_wav(tail_sil, 1.0)
        _concat_wavs_python(all_wavs + [tail_sil], combined_wav)

        # ── Phase 4: Encode video AND audio in parallel ───────────────────
        # Both run simultaneously; combined they take as long as the slower one.
        # The final mux then just stream-copies two pre-encoded streams → near-instant.
        encode_error = [None]

        def _encode_video():
            try:
                _run_ffmpeg([
                    '-f', 'concat', '-safe', '0',
                    '-i', concat_txt,
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-r', str(FPS),
                    raw_video,
                ], label='encode_video')
            except Exception as e:
                encode_error[0] = e

        def _encode_audio():
            try:
                _run_ffmpeg([
                    '-i', combined_wav,
                    '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-b:a', '128k',
                    encoded_aac,
                ], label='encode_audio')
            except Exception as e:
                encode_error[0] = e

        with ThreadPoolExecutor(max_workers=2) as pool:
            vid_fut = pool.submit(_encode_video)
            aud_fut = pool.submit(_encode_audio)
            vid_fut.result()
            aud_fut.result()

        if encode_error[0]:
            raise encode_error[0]

        # ── Phase 5: Stream-copy mux (near-instant — no encoding) ─────────
        # Both streams are pre-encoded; this step just copies bytes into the MP4
        # container. -shortest stops at end of video (audio has 1s tail padding
        # so it always outlasts the video, preventing any audio cutoff).
        progress_cb('Finalizing video...', 97)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        _run_ffmpeg([
            '-i', raw_video,
            '-i', encoded_aac,
            '-c', 'copy',
            '-shortest',
            output_path,
        ], label='mux')

        # ── Thumbnail ────────────────────────────────────────────────────
        try:
            thumb_path = os.path.join(os.path.dirname(output_path), 'thumbnail.jpg')
            fr.save_thumbnail(
                task_num, task_name,
                job_data.get('band', '7_8'),
                job_data.get('category', ''),
                job_data.get('title', ''),
                thumb_path,
                seed=job_data.get('thumb_seed'),
                color_theme=thumb_color,
                thumb_font=job_data.get('thumb_font'),
                font_scale=float(job_data.get('thumb_font_scale', 1.0)),
                category_slug=cat_slug,
            )
        except Exception as e:
            print(f'[VideoBuilder] Thumbnail warning: {e}', file=sys.stderr)

        progress_cb('Done!', 100)
        return output_path

    finally:
        try:
            shutil.rmtree(job_temp)
        except Exception as e:
            print(f'[VideoBuilder] Cleanup warning: {e}', file=sys.stderr)
