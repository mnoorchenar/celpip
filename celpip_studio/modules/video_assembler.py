"""
FFmpeg-based video assembly pipeline for CELPIP Practice Studio.
"""

import os
import sys
import shutil
import random
import subprocess
import re

from config import (
    OUTPUT_DIR, TEMP_DIR, VIDEO_FPS, VIDEO_WIDTH, VIDEO_HEIGHT,
    TASK_DEFAULTS, MIN_PAGE_DURATION, WORDS_PER_SECOND_SLOW
)
from PIL import Image
from modules import transcriber, style_gen, music_gen, frame_renderer


def _safe_filename(name):
    """Convert name to filesystem-safe string."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s]+', '_', name).strip('_')
    return name[:50]


def _run_ffmpeg(args, step_desc=''):
    """Run an ffmpeg command, raise on error."""
    cmd = ['ffmpeg', '-y'] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f'FFmpeg failed at [{step_desc}]:\n'
            f'CMD: {" ".join(cmd)}\n'
            f'STDERR: {result.stderr[-3000:]}'
        )
    return result


def _write_concat_file(path, items):
    """
    Write FFmpeg concat demuxer file.
    items: list of (file_path, duration_sec)
    """
    with open(path, 'w', encoding='utf-8') as f:
        for file_path, duration in items:
            # FFmpeg concat requires forward slashes
            fp = file_path.replace('\\', '/')
            f.write(f"file '{fp}'\n")
            f.write(f'duration {duration:.4f}\n')


def _encode_concat(concat_file, out_mp4, fps=VIDEO_FPS):
    """Encode image sequence from concat file to MP4 (no audio)."""
    _run_ffmpeg([
        '-f', 'concat', '-safe', '0',
        '-i', concat_file,
        '-vf', f'fps={fps},scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}',
        '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
        out_mp4
    ], step_desc=f'encode_concat:{os.path.basename(out_mp4)}')


def _get_output_path(task_num, band, category):
    """Compute output path with auto-incrementing counter."""
    safe_cat = _safe_filename(category) if category else 'uncategorized'
    out_dir = os.path.join(OUTPUT_DIR, 'speaking', f'part{task_num}', f'band_{band}')
    os.makedirs(out_dir, exist_ok=True)
    existing = [f for f in os.listdir(out_dir) if f.endswith('.mp4')]
    counter = len(existing) + 1
    return os.path.join(out_dir, f'{safe_cat}_{counter:03d}.mp4')


def assemble_video(job_data, progress_callback):
    """
    Main pipeline: transcribe → render frames → generate music → ffmpeg → output MP4.

    job_data keys:
        question, answer, audio_path, vocab (list of {word, type, definition, example}),
        task_num (int), band (str e.g. '7_8'), category (str), job_id
    Returns output_path string.
    """
    job_id = job_data['job_id']
    question = job_data['question']
    answer = job_data['answer']
    audio_path = job_data['audio_path']
    vocab = job_data.get('vocab', [])
    task_num = int(job_data.get('task_num', 1))
    band = job_data.get('band', '7_8')
    category = job_data.get('category', 'General')

    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    task_name = task_info['name']
    prep_time = task_info['prep']
    response_time = task_info['response']

    # Per-job temp dir
    job_temp = os.path.join(TEMP_DIR, job_id)
    os.makedirs(job_temp, exist_ok=True)

    # ── Step 1: Transcribe ─────────────────────────────────────────────────
    progress_callback('Transcribing audio...', 5)
    sentences_raw = frame_renderer.split_sentences(answer)

    try:
        segments = transcriber.transcribe(audio_path)
        aligned = transcriber.align_sentences(sentences_raw, segments)
    except Exception as e:
        print(f'[Assembler] Transcription error: {e}', file=sys.stderr)
        aligned = transcriber.fallback_align(sentences_raw, response_time)

    # Ensure we have timing for all sentences
    if not aligned:
        aligned = transcriber.fallback_align(sentences_raw, response_time)

    # Build sentence dicts
    sentences = []
    for item in aligned:
        sentences.append({
            'text': item['text'],
            'start_time': float(item.get('start_time', 0)),
            'end_time': float(item.get('end_time', response_time / max(1, len(aligned)))),
        })

    # ── Step 2: Render exam frames ─────────────────────────────────────────
    progress_callback('Rendering exam section...', 15)
    exam_frames_dir = os.path.join(job_temp, 'frames_exam')
    os.makedirs(exam_frames_dir, exist_ok=True)

    exam_items = []

    # Prep phase: 1 PNG per second
    for sec in range(prep_time):
        time_remaining = prep_time - sec
        img = frame_renderer.render_prep_frame(task_name, question,
                                               time_remaining, prep_time)
        fname = os.path.join(exam_frames_dir, f'prep_{sec:05d}.png')
        img.save(fname, 'PNG')
        exam_items.append((fname, 1.0))

    # Response phase: 1 PNG per second
    for sec in range(response_time):
        time_remaining = response_time - sec
        # Find active sentence index
        current_time = float(sec)
        active_idx = 0
        for idx, s in enumerate(sentences):
            if s['start_time'] <= current_time < s['end_time']:
                active_idx = idx
                break
            elif current_time >= s['end_time']:
                active_idx = min(idx + 1, len(sentences) - 1)

        img = frame_renderer.render_response_frame(
            task_name, question, sentences, active_idx,
            time_remaining, response_time
        )
        fname = os.path.join(exam_frames_dir, f'resp_{sec:05d}.png')
        img.save(fname, 'PNG')
        exam_items.append((fname, 1.0))

    # Time's up frame (2 seconds)
    timesup_img = frame_renderer.render_timesup_frame(task_name, sentences)
    timesup_path = os.path.join(exam_frames_dir, 'timesup.png')
    timesup_img.save(timesup_path, 'PNG')
    exam_items.append((timesup_path, 2.0))

    concat_exam_path = os.path.join(job_temp, 'concat_exam.txt')
    _write_concat_file(concat_exam_path, exam_items)

    # ── Step 3: Render vocabulary pages ───────────────────────────────────
    progress_callback('Rendering vocabulary pages...', 40)
    vocab_frames_dir = os.path.join(job_temp, 'frames_vocab')
    os.makedirs(vocab_frames_dir, exist_ok=True)

    # Intro slide
    intro_img = frame_renderer.render_vocab_intro_frame(task_name)
    intro_path = os.path.join(vocab_frames_dir, 'vocab_intro.png')
    intro_img.save(intro_path, 'PNG')
    vocab_items = [(intro_path, 4.0)]

    for v_idx, v in enumerate(vocab):
        seed = hash(f'{job_id}_{v_idx}') % (2 ** 31)
        vstyle = style_gen.generate_style(seed=seed)

        word = v.get('word', '')
        word_type = v.get('type', 'word')
        definition = v.get('definition', '')
        example = v.get('example', '')

        img = frame_renderer.render_vocab_page(word, word_type, definition, example, vstyle)
        fname = os.path.join(vocab_frames_dir, f'vocab_{v_idx:03d}.png')
        img.save(fname, 'PNG')

        # Duration: doubled — gives viewers enough time to read twice
        word_count = len(example.split()) if example else 10
        duration = max(MIN_PAGE_DURATION, word_count / WORDS_PER_SECOND_SLOW) * 2
        vocab_items.append((fname, duration))

    # If no vocab, add a placeholder
    if not vocab_items:
        placeholder = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT),
                                 color=frame_renderer._parse_color(frame_renderer.BG))
        ph_path = os.path.join(vocab_frames_dir, 'placeholder.png')
        placeholder.save(ph_path, 'PNG')
        vocab_items.append((ph_path, 2.0))

    concat_vocab_path = os.path.join(job_temp, 'concat_vocab.txt')
    _write_concat_file(concat_vocab_path, vocab_items)

    vocab_total_duration = sum(dur for _, dur in vocab_items)

    # ── Step 4: Render review frames ──────────────────────────────────────
    progress_callback('Rendering review section...', 55)
    review_frames_dir = os.path.join(job_temp, 'frames_review')
    os.makedirs(review_frames_dir, exist_ok=True)

    vocab_words = [{'word': v.get('word',''), 'definition': v.get('definition','')}
                   for v in vocab if v.get('word')]
    review_items = []

    for sec in range(response_time):
        time_remaining = response_time - sec
        current_time = float(sec)
        active_idx = 0
        for idx, s in enumerate(sentences):
            if s['start_time'] <= current_time < s['end_time']:
                active_idx = idx
                break
            elif current_time >= s['end_time']:
                active_idx = min(idx + 1, len(sentences) - 1)

        img = frame_renderer.render_review_frame(
            task_name, answer, sentences, active_idx,
            vocab_words, time_remaining, response_time
        )
        fname = os.path.join(review_frames_dir, f'rev_{sec:05d}.png')
        img.save(fname, 'PNG')
        review_items.append((fname, 1.0))

    concat_review_path = os.path.join(job_temp, 'concat_review.txt')
    _write_concat_file(concat_review_path, review_items)

    # ── Step 5: Render disclaimer ──────────────────────────────────────────
    progress_callback('Rendering disclaimer...', 65)
    disc_img = frame_renderer.render_disclaimer_frame()
    disc_path = os.path.join(job_temp, 'disclaimer.png')
    disc_img.save(disc_path, 'PNG')

    concat_disc_path = os.path.join(job_temp, 'concat_disclaimer.txt')
    _write_concat_file(concat_disc_path, [(disc_path, 5.0)])

    # ── Step 6: Generate background music ─────────────────────────────────
    progress_callback('Generating background music...', 70)
    music_seed = random.randint(0, 9999)
    music_path = music_gen.generate_ambient_music(
        vocab_total_duration,
        seed=music_seed,
        job_temp_dir=job_temp
    )

    # ── Step 7: Encode video segments ─────────────────────────────────────
    progress_callback('Encoding video...', 75)

    exam_mp4 = os.path.join(job_temp, 'exam.mp4')
    vocab_mp4 = os.path.join(job_temp, 'vocab_video.mp4')
    review_mp4 = os.path.join(job_temp, 'review.mp4')
    disc_mp4 = os.path.join(job_temp, 'disclaimer.mp4')

    _encode_concat(concat_exam_path, exam_mp4)
    _encode_concat(concat_vocab_path, vocab_mp4)
    _encode_concat(concat_review_path, review_mp4)
    _encode_concat(concat_disc_path, disc_mp4)

    # ── Step 8: Add audio ─────────────────────────────────────────────────
    progress_callback('Mixing audio...', 85)

    silence_path = os.path.join(job_temp, 'silence.wav')
    exam_audio_path = os.path.join(job_temp, 'exam_audio.wav')
    exam_with_audio = os.path.join(job_temp, 'exam_with_audio.mp4')
    vocab_with_music = os.path.join(job_temp, 'vocab_with_music.mp4')
    review_with_audio = os.path.join(job_temp, 'review_with_audio.mp4')
    disc_silent = os.path.join(job_temp, 'disclaimer_with_audio.mp4')

    # Generate prep silence
    _run_ffmpeg([
        '-f', 'lavfi',
        '-i', f'anullsrc=r=44100:cl=stereo',
        '-t', str(prep_time),
        silence_path
    ], 'gen_silence')

    # Concat silence + user audio for exam
    _run_ffmpeg([
        '-i', silence_path,
        '-i', audio_path,
        '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1[outa]',
        '-map', '[outa]',
        exam_audio_path
    ], 'concat_exam_audio')

    # Add audio to exam video (-shortest to avoid length mismatch)
    _run_ffmpeg([
        '-i', exam_mp4,
        '-i', exam_audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        exam_with_audio
    ], 'exam_with_audio')

    # Mix music into vocab video
    _run_ffmpeg([
        '-i', vocab_mp4,
        '-i', music_path,
        '-filter_complex',
        f'[1:a]volume={0.15}[music];[music]apad[apad];[apad]atrim=duration={vocab_total_duration:.2f}[atrimmed]',
        '-map', '0:v',
        '-map', '[atrimmed]',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        vocab_with_music
    ], 'vocab_with_music')

    # Add user audio to review (no silence prefix — starts from second 0)
    _run_ffmpeg([
        '-i', review_mp4,
        '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        review_with_audio
    ], 'review_with_audio')

    # Disclaimer: add silence track
    disc_dur = 5.0
    _run_ffmpeg([
        '-i', disc_mp4,
        '-f', 'lavfi',
        '-i', f'anullsrc=r=44100:cl=stereo',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-shortest',
        disc_silent
    ], 'disclaimer_silent')

    # ── Step 9: Concatenate all sections ──────────────────────────────────
    progress_callback('Finalizing video...', 95)

    output_path = job_data.get('video_output_path') or _get_output_path(task_num, band, category)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    _run_ffmpeg([
        '-i', exam_with_audio,
        '-i', vocab_with_music,
        '-i', review_with_audio,
        '-i', disc_silent,
        '-filter_complex',
        '[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a]concat=n=4:v=1:a=1[outv][outa]',
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        output_path
    ], 'final_concat')

    # ── Step 10: Cleanup temp ──────────────────────────────────────────────
    progress_callback('Done!', 100)
    try:
        shutil.rmtree(job_temp)
    except Exception as e:
        print(f'[Assembler] Cleanup warning: {e}', file=sys.stderr)

    return output_path
