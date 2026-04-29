"""
CELPIP Practice Studio - Flask Web Application
"""

import asyncio
import os
import sys
import uuid
import json
import threading
import traceback
import queue as _queue
import time as _time

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, Response
)
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    OUTPUT_DIR, DATA_DIR, UPLOADS_DIR, TEMP_DIR,
    TASK_DEFAULTS, BAND_LABELS, DEFAULT_BAND
)
from modules import categories as cats_module
from modules import pdf_gen
from modules import shadowing as shadow_mod
from modules import output_dirs
from modules import database as db
from modules import kokoro_tts, style_gen, video_builder
from modules import frame_renderer as fr
from modules import youtube_upload as yt_mod

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ── Startup ────────────────────────────────────────────────────────────────────
for d in [OUTPUT_DIR, DATA_DIR, UPLOADS_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)
db.init_db()

# ── Global stores ──────────────────────────────────────────────────────────────
jobs            = {}        # job_id -> job state dict
shadow_sessions = {}        # sess_id -> {audio_dir, session_dir}

_JOB_TTL = 24 * 3600  # seconds to keep completed/errored jobs in memory


def _cleanup_old_jobs():
    """Remove done/errored jobs older than _JOB_TTL to prevent unbounded growth."""
    cutoff = _time.time() - _JOB_TTL
    stale = [jid for jid, j in list(jobs.items())
             if j.get('done') and j.get('created_at', 0) < cutoff]
    for jid in stale:
        jobs.pop(jid, None)


def _int(val, default=1):
    """Safe int cast — returns default on None/bad input instead of raising."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

# ── Video generation queue ──────────────────────────────────────────────────────
_job_queue    = _queue.Queue()   # FIFO queue of job_ids
_queue_order  = []               # ordered list for display (includes all non-done jobs)
_queue_lock   = threading.Lock()


def _queue_worker():
    """Single background thread that processes video jobs one at a time."""
    while True:
        job_id = _job_queue.get()
        try:
            j = jobs.get(job_id)
            if not j or j.get('cancelled'):
                continue
            j['status'] = 'running'
            j['step']   = 'Starting…'

            job_data           = j['_job_data']
            section_seeds      = j['_section_seeds']
            voice              = j['_voice']
            session_dir        = job_data['session_dir']
            template_record_id = job_data.get('template_record_id')

            def cb(step, pct):
                j.update(step=step, progress=pct)

            try:
                out_path = os.path.join(session_dir, 'video.mp4')
                video_builder.build_video(job_data, section_seeds, voice, out_path, cb)
                # Update DB before marking done — so the UI refresh sees the new status
                if template_record_id:
                    try:
                        pdf_path = None
                        try:
                            pdf_path = pdf_gen.generate_pdf(job_data, session_dir)
                            db.update_template_pdf(template_record_id, pdf_path)
                        except Exception as e:
                            print(f'[Queue] Template PDF error: {e}', file=sys.stderr)
                        db.update_template_video(template_record_id, out_path)
                    except Exception as e:
                        print(f'[Queue] Template DB update failed: {e}', file=sys.stderr)
                j.update(output_path=out_path, done=True, step='Done!', progress=100,
                         status='done')
            except Exception as e:
                print(f'[Queue job {job_id}] Error:\n{traceback.format_exc()}',
                      file=sys.stderr)
                j.update(error=str(e), done=True, step='Error', status='error')
        finally:
            with _queue_lock:
                if job_id in _queue_order:
                    _queue_order.remove(job_id)
            _cleanup_old_jobs()
            _job_queue.task_done()


_worker = threading.Thread(target=_queue_worker, daemon=True, name='VideoQueueWorker')
_worker.start()


def _allowed_audio(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'mp3', 'wav', 'm4a', 'ogg', 'flac'}


# ── Error handlers (always return JSON for /api routes) ────────────────────────
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': f'Route not found: {request.path}'}), 404
    return str(e), 404

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': f'Server error: {e}'}), 500
    return str(e), 500


# ── Main studio ────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('dashboard.html')


# ── Kokoro TTS ─────────────────────────────────────────────────────────────────
@app.route('/api/kokoro/voices')
def kokoro_voices():
    return jsonify({
        'voices':        kokoro_tts.KOKORO_VOICES,
        'default_voice': kokoro_tts.DEFAULT_VOICE,
        'available':     kokoro_tts.is_available(),
    })


@app.route('/api/kokoro/preview', methods=['POST'])
def kokoro_preview():
    data  = request.get_json() or {}
    text  = data.get('text', 'Hello! This is a sample of my voice for CELPIP practice.').strip()
    voice = data.get('voice', kokoro_tts.DEFAULT_VOICE)
    if voice not in kokoro_tts.KOKORO_VOICES:
        voice = kokoro_tts.DEFAULT_VOICE
    try:
        wav_bytes = kokoro_tts.to_wav_bytes(text[:300], voice)
        return Response(wav_bytes, mimetype='audio/wav')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


_VOICE_SAMPLE_TEXT = (
    "Hello! My name is {name}, and I'm here to help you prepare for the CELPIP exam. "
    "Let me give you some advice on how to improve your speaking skills."
)
_voice_sample_cache = {}   # voice_id -> wav bytes
_voice_sample_lock  = threading.Lock()

_VOICE_SAMPLES_DIR = os.path.join(DATA_DIR, 'voice_samples')
os.makedirs(_VOICE_SAMPLES_DIR, exist_ok=True)


@app.route('/api/voice-sample/<voice_id>')
def voice_sample(voice_id):
    """Return a cached WAV sample for the given voice (generated once, then served from disk)."""
    from flask import Response
    if voice_id not in kokoro_tts.KOKORO_VOICES:
        return jsonify({'error': 'Unknown voice'}), 404

    cache_path = os.path.join(_VOICE_SAMPLES_DIR, f'{voice_id}.wav')

    with _voice_sample_lock:
        # Serve from disk cache if already generated
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                wav_bytes = f.read()
            return Response(wav_bytes, mimetype='audio/wav')

    # Generate (outside lock to avoid blocking other requests)
    try:
        label = kokoro_tts.KOKORO_VOICES[voice_id]
        # Extract first name for personalised sample
        first_name = label.split(' ')[0]
        text = _VOICE_SAMPLE_TEXT.format(name=first_name)
        wav_bytes = kokoro_tts.to_wav_bytes(text, voice_id)
        with open(cache_path, 'wb') as f:
            f.write(wav_bytes)
        return Response(wav_bytes, mimetype='audio/wav')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/voice-sample/status')
def voice_sample_status():
    """Return which voice samples have already been generated (cached on disk)."""
    cached = []
    for vid in kokoro_tts.KOKORO_VOICES:
        if os.path.exists(os.path.join(_VOICE_SAMPLES_DIR, f'{vid}.wav')):
            cached.append(vid)
    return jsonify({'cached': cached})


# ── Video Preview ───────────────────────────────────────────────────────────────
preview_sessions = {}   # psid -> job_data dict


@app.route('/video-preview')
def video_preview():
    return render_template('video_preview.html',
                           voices=kokoro_tts.KOKORO_VOICES,
                           default_voice=kokoro_tts.DEFAULT_VOICE)


@app.route('/api/preview/init', methods=['POST'])
def preview_init():
    data = request.get_json() or {}
    psid = uuid.uuid4().hex
    saved_scales = data.get('font_scales', {})
    font_scales  = {i: float(saved_scales.get(str(i), saved_scales.get(i, 1.0))) for i in range(1, 6)}
    preview_sessions[psid] = {
        'question':    data.get('question', ''),
        'answer':      data.get('answer', ''),
        'vocab':       data.get('vocab', []),
        'task_num':    _int(data.get('task_num', 1)),
        'band':        data.get('band', '7_8'),
        'category':    data.get('category', ''),
        'title':       data.get('title', ''),
        'seeds':       {_int(k): v for k, v in (data.get('seeds') or {}).items()}
                       or style_gen.default_seeds(),
        'font_scales': font_scales,
        'thumb_seed':  data.get('thumb_seed', None),
        'thumb_color': data.get('thumb_color', None),
        'thumb_font':  data.get('thumb_font', None),
    }
    return jsonify({'psid': psid})


@app.route('/api/preview/frame')
def preview_frame():
    """Render a single preview frame and return it as PNG."""
    import io as _io
    psid     = request.args.get('psid', '')
    section  = _int(request.args.get('section', 1))
    slide    = _int(request.args.get('slide', 0), default=0)
    seed     = request.args.get('seed')

    sess = preview_sessions.get(psid)
    if not sess:
        return 'Preview session not found', 404

    question = sess['question']
    answer   = sess['answer']
    vocab    = sess['vocab']
    task_num = sess['task_num']
    seeds    = dict(sess['seeds'])

    if seed is not None:
        seeds[section] = int(seed)
        sess['seeds'][section] = int(seed)    # persist new seed

    task_info  = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    task_name  = task_info['name']
    prep_time  = task_info['prep']
    resp_time  = task_info['response']

    import re
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z])', answer.strip())
    sents = [s.strip() for s in sents if s.strip()] or [answer]

    vocab_words = [{'word': v.get('word',''), 'definition': v.get('definition','')}
                   for v in vocab if v.get('word')]

    sec_style = style_gen.generate_section_style(section, seed=seeds.get(section))

    # font_scale: URL param takes priority (client sends it on every font-size change)
    font_scale_param = request.args.get('font_scale')
    if font_scale_param is not None:
        try:
            scale = float(font_scale_param)
            scale = max(0.5, min(2.0, scale))
            sess.setdefault('font_scales', {})[section] = scale
            sec_style['font_scale'] = scale
        except (ValueError, TypeError):
            sec_style['font_scale'] = sess.get('font_scales', {}).get(section, 1.0)
    else:
        sec_style['font_scale'] = sess.get('font_scales', {}).get(section, 1.0)

    img = _render_preview_frame(
        section, slide, task_name, question, sents,
        vocab, vocab_words, prep_time, resp_time, sec_style)

    buf = _io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype='image/png')


@app.route('/api/preview/section-count')
def preview_section_count():
    psid    = request.args.get('psid', '')
    sess    = preview_sessions.get(psid)
    if not sess:
        return jsonify({'error': 'not found'}), 404

    answer  = sess['answer']
    vocab   = sess['vocab']
    task_num = sess['task_num']
    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    prep_time = task_info['prep']
    resp_time = task_info['response']

    import re
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z])', answer.strip())
    sents = [s.strip() for s in sents if s.strip()] or [answer]

    counts = {
        1: 1 + 1,                              # transition + prep frame
        2: 1 + len(sents),                     # transition + one per sentence
        3: 1 + len(vocab),                     # transition + words
        4: 1 + len(sents) * 2,                 # transition + (tts + pause) per sent
        5: 1 + len(sents),                     # transition + one per sentence
    }
    return jsonify({'counts': counts, 'seeds': sess['seeds'],
                    'font_scales': sess.get('font_scales', {i: 1.0 for i in range(1, 6)})})


@app.route('/api/preview/thumbnail')
def preview_thumbnail():
    """Render the thumbnail for the current preview session and return as JPEG."""
    import io as _io
    psid = request.args.get('psid', '')
    seed = request.args.get('seed')
    seed        = int(seed) if seed is not None else None
    color_theme = request.args.get('color_theme') or None

    sess = preview_sessions.get(psid)
    if not sess:
        return 'Preview session not found', 404

    # Persist color_theme / thumb_font / thumb_font_scale choices to session
    if color_theme is not None:
        sess['thumb_color'] = color_theme
    thumb_font = request.args.get('thumb_font') or None
    if thumb_font is not None:
        sess['thumb_font'] = thumb_font
    thumb_font_scale_param = request.args.get('thumb_font_scale')
    if thumb_font_scale_param is not None:
        try:
            sess['thumb_font_scale'] = float(thumb_font_scale_param)
        except (ValueError, TypeError):
            pass

    task_num  = sess['task_num']
    band      = sess['band']
    from config import TASK_DEFAULTS as _TD
    task_name = _TD.get(task_num, _TD[1])['name']
    category  = sess.get('category', '')
    title     = sess.get('title', '') or category
    eff_color = sess.get('thumb_color') or color_theme
    eff_font  = sess.get('thumb_font')
    eff_scale = sess.get('thumb_font_scale', 1.0)

    img = fr.render_thumbnail(task_num, task_name, band, category, title,
                               seed=seed, color_theme=eff_color, thumb_font=eff_font,
                               font_scale=eff_scale)
    buf = _io.BytesIO()
    img.save(buf, 'JPEG', quality=95)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype='image/jpeg')


@app.route('/api/preview/thumbnail-randomize', methods=['POST'])
def preview_thumbnail_randomize():
    import random as _rand
    data = request.get_json() or {}
    psid = data.get('psid', '')
    sess = preview_sessions.get(psid)
    if not sess:
        return jsonify({'error': 'not found'}), 404
    new_seed = _rand.randint(0, 2**31)
    return jsonify({'seed': new_seed})


@app.route('/api/preview/randomize', methods=['POST'])
def preview_randomize():
    import random as _rand
    data    = request.get_json() or {}
    psid    = data.get('psid', '')
    section = int(data.get('section', 1))
    sess    = preview_sessions.get(psid)
    if not sess:
        return jsonify({'error': 'not found'}), 404
    new_seed = _rand.randint(0, 2**31)
    sess['seeds'][section] = new_seed
    return jsonify({'seed': new_seed})


@app.route('/api/preview/font-scale', methods=['POST'])
def preview_font_scale():
    data    = request.get_json() or {}
    psid    = data.get('psid', '')
    section = int(data.get('section', 1))
    delta   = float(data.get('delta', 0.1))
    sess    = preview_sessions.get(psid)
    if not sess:
        return jsonify({'error': 'not found'}), 404
    scales = sess.setdefault('font_scales', {i: 1.0 for i in range(1, 6)})
    scales[section] = round(max(0.5, min(2.0, scales[section] + delta)), 2)
    return jsonify({'scale': scales[section]})


def _render_preview_frame(section, slide, task_name, question, sents,
                           vocab, vocab_words, prep_time, resp_time, style):
    """Route slide index → correct frame renderer call."""
    sent_dicts = [{'text': s} for s in sents]

    if section == 1:
        if slide == 0:
            return fr.render_section_transition(1, style)
        return fr.render_prep_frame(task_name, question, prep_time, prep_time, style=style)

    elif section == 2:
        if slide == 0:
            return fr.render_section_transition(2, style)
        idx = min(slide - 1, len(sents) - 1)
        fake = []
        t = 0.0
        for s in sents:
            wc = len(s.split())
            d  = max(1.0, wc / 2.5)
            fake.append({'text': s, 'start_time': t, 'end_time': t + d})
            t += d
        return fr.render_response_frame(
            task_name, question, fake, idx,
            max(1, resp_time - idx * 8), resp_time, style=style)

    elif section == 3:
        if slide == 0:
            return fr.render_section_transition(3, style)
        vi = min(slide - 1, len(vocab) - 1)
        if vi < 0 or vi >= len(vocab):
            return fr.render_section_transition(3, style)
        v     = vocab[vi]
        return fr.render_vocab_page(
            v.get('word', ''), v.get('type', 'word'),
            v.get('definition', ''), v.get('example', ''), style,
            word_idx=vi, total_words=len(vocab))

    elif section == 4:
        if slide == 0:
            return fr.render_section_transition(4, style)
        # odd slides = TTS phase, even slides = pause phase
        pair = slide - 1
        si   = min(pair // 2, len(sents) - 1)
        phase = 'tts' if pair % 2 == 0 else 'pause'
        rep  = (pair // (len(sents) * 2)) + 1 if len(sents) > 0 else 1
        return fr.render_shadow_frame(
            sents[si], sent_dicts, si, vocab_words,
            1, 2, phase, 0.5, style)

    elif section == 5:
        if slide == 0:
            return fr.render_section_transition(5, style)
        idx = min(slide - 1, len(sents) - 1)
        return fr.render_final_answer_frame(
            task_name, sent_dicts, idx, vocab_words, style)

    return fr.render_section_transition(section, style)


# ── Video generation (new, Kokoro TTS) ─────────────────────────────────────────
@app.route('/generate-video', methods=['POST'])
def generate_video():
    data = request.get_json() or {}
    for field in ['question', 'answer', 'task_num']:
        if not data.get(field):
            return jsonify({'error': f'Missing field: {field}'}), 400

    try:
        task_num = int(data['task_num'])
    except (TypeError, ValueError):
        return jsonify({'error': 'task_num must be an integer'}), 400
    band        = data.get('band') or DEFAULT_BAND
    category    = data.get('category', 'General')
    title       = data.get('title', '') or category
    # Always pick a fresh random voice per job (excludes am_adam)
    voice = kokoro_tts.random_voice()
    _seeds_raw    = data.get('seeds') or {}
    section_seeds = {_int(k): v for k, v in _seeds_raw.items()} if _seeds_raw \
                    else style_gen.default_seeds()
    thumb_seed  = data.get('thumb_seed', None)
    thumb_color = data.get('thumb_color', None) or None
    thumb_font       = data.get('thumb_font', None) or None
    thumb_font_scale = float(data.get('thumb_font_scale', 1.0) or 1.0)
    _fs_raw     = data.get('font_scales')
    font_scales = ({i: float(_fs_raw.get(str(i), _fs_raw.get(i, 1.0))) for i in range(1, 6)}
                  if _fs_raw else _load_global_font_scales())

    vocab = data.get('vocab', [])
    for item in vocab:
        item.setdefault('type', 'word')

    session_dir = data.get('session_dir', '')
    if not session_dir or not os.path.isdir(session_dir):
        session_dir = output_dirs.create_session_dir(task_num, band, category, title)

    job_id = uuid.uuid4().hex

    job_data = {
        'question':    data['question'],
        'answer':      data['answer'],
        'vocab':       vocab,
        'task_num':    task_num,
        'band':        band,
        'category':    category,
        'title':       title,
        'session_dir':  session_dir,
        'thumb_seed':   thumb_seed,
        'thumb_color':  thumb_color,
        'thumb_font':       thumb_font,
        'thumb_font_scale': thumb_font_scale,
        'font_scales':      font_scales,
        'voice_label':  kokoro_tts.KOKORO_VOICES[voice],  # e.g. "Heart (US, Female)"
    }

    with _queue_lock:
        _queue_order.append(job_id)
        queue_pos = len(_queue_order)

    jobs[job_id] = {
        'progress': 0, 'step': 'Queued…', 'done': False,
        'error': None, 'output_path': None, 'status': 'queued',
        'cancelled': False,
        'label': f'{category} · Part {task_num}',
        'created_at': _time.time(),
        # Private — used by worker
        '_job_data':      job_data,
        '_section_seeds': section_seeds,
        '_voice':         voice,
    }

    _job_queue.put(job_id)
    return jsonify({'job_id': job_id, 'queue_position': queue_pos})


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    j = jobs[job_id]
    with _queue_lock:
        order = list(_queue_order)
    pos = order.index(job_id) + 1 if job_id in order else None
    return jsonify({
        'progress':    j['progress'],
        'step':        j['step'],
        'done':        j['done'],
        'error':       j['error'],
        'output_path': j['output_path'],
        'status':      j['status'],
        'queue_pos':   pos,
        'queue_total': len(order),
    })


@app.route('/api/queue')
def api_queue():
    """Return all queued/running/recent jobs for the queue panel."""
    with _queue_lock:
        pending = list(_queue_order)

    result = []
    # First: queued/running in order
    for jid in pending:
        j = jobs.get(jid, {})
        result.append({
            'job_id':   jid,
            'label':    j.get('label', ''),
            'status':   j.get('status', 'queued'),
            'progress': j.get('progress', 0),
            'step':     j.get('step', ''),
        })
    # Then: recently finished (last 5)
    done_jobs = [
        (jid, j) for jid, j in jobs.items()
        if j.get('done') and jid not in pending
    ]
    done_jobs.sort(key=lambda x: x[1].get('created_at', 0), reverse=True)
    for jid, j in done_jobs[:5]:
        result.append({
            'job_id':   jid,
            'label':    j.get('label', ''),
            'status':   'error' if j.get('error') else 'done',
            'progress': 100,
            'step':     j.get('step', ''),
        })
    return jsonify({'jobs': result, 'pending': len(pending)})


@app.route('/api/queue/<job_id>/cancel', methods=['POST'])
def api_cancel_job(job_id):
    j = jobs.get(job_id)
    if not j:
        return jsonify({'error': 'Job not found'}), 404
    if j.get('status') != 'queued':
        return jsonify({'error': 'Can only cancel queued jobs'}), 400
    j['cancelled'] = True
    j['done']      = True
    j['step']      = 'Cancelled'
    j['status']    = 'cancelled'
    with _queue_lock:
        if job_id in _queue_order:
            _queue_order.remove(job_id)
    return jsonify({'ok': True})


@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return 'Job not found', 404
    j = jobs[job_id]
    if not j['done'] or j['error']:
        return 'Not ready', 400
    path = j['output_path']
    if not path or not os.path.exists(path):
        return 'File not found', 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


# ── Categories ─────────────────────────────────────────────────────────────────
@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    section = request.args.get('section', 'speaking')
    part    = request.args.get('part', 'part1')
    query   = request.args.get('q', '')
    result  = cats_module.search_categories(section, part, query) if query \
              else cats_module.get_categories(section, part)
    return jsonify({'categories': result})

@app.route('/api/categories', methods=['POST'])
def api_add_category():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    updated = cats_module.add_category(
        data.get('section', 'speaking'), data.get('part', 'part1'), name)
    return jsonify({'categories': updated, 'added': name})


# ── Prepare shadowing (PDF + audio + DB save) ──────────────────────────────────
@app.route('/api/prepare-shadowing', methods=['POST'])
def prepare_shadowing():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    for field in ['question', 'answer', 'task_num']:
        if not data.get(field):
            return jsonify({'error': f'Missing field: {field}'}), 400

    try:
        task_num = int(data['task_num'])
    except (TypeError, ValueError):
        return jsonify({'error': 'task_num must be an integer'}), 400
    band      = data.get('band') or DEFAULT_BAND
    category  = data.get('category', 'General')
    title     = data.get('title', '') or category
    voice     = data.get('voice', shadow_mod.DEFAULT_VOICE)
    if not shadow_mod.is_kokoro_voice(voice) and voice not in shadow_mod.VOICES:
        voice = shadow_mod.DEFAULT_VOICE

    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    part_name = task_info['name']

    session_dir = data.get('session_dir', '')
    if not session_dir or not os.path.isdir(session_dir):
        session_dir = output_dirs.create_session_dir(task_num, band, category, title)

    vocab    = data.get('vocab', [])
    job_data = {'question': data['question'], 'answer': data['answer'],
                'vocab': vocab, 'task_num': task_num, 'band': band,
                'category': category, 'title': title}

    # PDF
    pdf_path = None
    try:
        pdf_path = pdf_gen.generate_pdf(job_data, session_dir)
    except Exception as e:
        print(f'[Prepare] PDF error: {e}', file=sys.stderr)

    # Audio — skip if files already exist
    audio_dir      = output_dirs.shadowing_dir(session_dir)
    sentences      = shadow_mod.split_sentences(data['answer'])
    existing_audio = sorted(
        f for f in os.listdir(audio_dir)
        if f.endswith('.mp3') or f.endswith('.wav')
    ) if os.path.isdir(audio_dir) else []

    if existing_audio:
        audio_files = [{'index': i, 'text': s, 'filename': f}
                       for i, (s, f) in enumerate(zip(sentences, existing_audio))]
    else:
        try:
            audio_files = shadow_mod.generate_shadowing_audio(sentences, audio_dir, voice)
        except Exception as e:
            print(f'[Prepare] Audio error: {e}', file=sys.stderr)
            return jsonify({'error': f'Audio generation failed: {e}'}), 500

    session_id = uuid.uuid4().hex
    shadow_sessions[session_id] = {'audio_dir': audio_dir, 'session_dir': session_dir}

    return jsonify({
        'session_id':  session_id,
        'session_dir': session_dir,
        'pdf_path':    pdf_path,
        'audio_dir':   audio_dir,
        'sentences':   audio_files,
        'audio_count': len(audio_files),
    })


# ── Shadowing generate (called from standalone shadowing page) ────────────────
@app.route('/api/shadowing/generate', methods=['POST'])
def shadowing_generate():
    data = request.get_json()
    if not data or not data.get('answer'):
        return jsonify({'error': 'Missing answer'}), 400

    answer     = data['answer']
    voice      = data.get('voice', shadow_mod.DEFAULT_VOICE)
    band       = data.get('band') or DEFAULT_BAND
    category   = data.get('category', 'General')
    title      = data.get('title', '') or category
    task_num   = _int(data.get('task_num', 1))
    session_dir = data.get('session_dir', '')

    force_regen = bool(data.get('force_regen', False))

    if not shadow_mod.is_kokoro_voice(voice) and voice not in shadow_mod.VOICES:
        voice = shadow_mod.DEFAULT_VOICE

    if not session_dir or not os.path.isdir(session_dir):
        session_dir = output_dirs.create_session_dir(task_num, band, category, title)

    audio_dir = output_dirs.shadowing_dir(session_dir)

    # Delete existing audio when caller requests a forced regeneration
    if force_regen and os.path.isdir(audio_dir):
        for fname in os.listdir(audio_dir):
            if fname.endswith('.mp3') or fname.endswith('.wav'):
                try:
                    os.remove(os.path.join(audio_dir, fname))
                except Exception:
                    pass

    sentences      = shadow_mod.split_sentences(answer)
    existing_audio = sorted(
        f for f in os.listdir(audio_dir)
        if f.endswith('.mp3') or f.endswith('.wav')
    ) if os.path.isdir(audio_dir) else []

    if existing_audio:
        audio_files = [{'index': i, 'text': s, 'filename': f}
                       for i, (s, f) in enumerate(zip(sentences, existing_audio))]
    else:
        try:
            audio_files = shadow_mod.generate_shadowing_audio(sentences, audio_dir, voice)
        except Exception as e:
            print(f'[Shadowing] Audio error: {e}', file=sys.stderr)
            return jsonify({'error': f'Audio generation failed: {e}'}), 500

    session_id = uuid.uuid4().hex
    shadow_sessions[session_id] = {'audio_dir': audio_dir, 'session_dir': session_dir}

    return jsonify({
        'session_id':  session_id,
        'session_dir': session_dir,
        'sentences':   audio_files,
        'audio_count': len(audio_files),
    })


# ── Shadowing rehydrate (re-register session after server restart) ─────────────
@app.route('/api/shadowing/rehydrate', methods=['POST'])
def shadowing_rehydrate():
    data = request.get_json() or {}
    session_dir = data.get('session_dir', '').strip()
    if not session_dir:
        return jsonify({'error': 'session_dir required'}), 400
    # Security: must be inside OUTPUT_DIR
    try:
        abs_sd  = os.path.abspath(session_dir)
        abs_out = os.path.abspath(OUTPUT_DIR)
        if not abs_sd.startswith(abs_out + os.sep) and abs_sd != abs_out:
            return jsonify({'error': 'Invalid path'}), 400
    except Exception:
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.isdir(session_dir):
        return jsonify({'error': 'Session directory not found'}), 404
    audio_dir = output_dirs.shadowing_dir(session_dir)
    sess_id   = uuid.uuid4().hex
    shadow_sessions[sess_id] = {'audio_dir': audio_dir, 'session_dir': session_dir}
    return jsonify({'session_id': sess_id})


# ── Shadowing voices API ───────────────────────────────────────────────────────
@app.route('/api/shadowing/voices')
def shadowing_voices():
    edge_sub_groups = []
    for grp in shadow_mod.EDGE_GROUPS:
        voices_list = [
            {'id': vid, 'label': shadow_mod.VOICES[vid]}
            for vid in grp['voices'] if vid in shadow_mod.VOICES
        ]
        edge_sub_groups.append({'label': grp['label'], 'voices': voices_list})

    kv = kokoro_tts.KOKORO_VOICES
    kokoro_sub_groups = []
    for grp in shadow_mod.KOKORO_SUB_GROUPS:
        voices_list = [
            {'id': vid, 'label': kv[vid]}
            for vid in kv if vid.startswith(grp['prefix'])
        ]
        kokoro_sub_groups.append({'label': grp['label'], 'voices': voices_list})

    return jsonify({
        'groups': [
            {
                'engine': 'kokoro',
                'label': 'Kokoro TTS',
                'description': 'Local AI voices — no internet required',
                'available': kokoro_tts.is_available(),
                'sub_groups': kokoro_sub_groups,
            },
            {
                'engine': 'edge',
                'label': 'Edge TTS',
                'description': 'Neural voices — internet required',
                'sub_groups': edge_sub_groups,
            },
        ],
        'default': shadow_mod.DEFAULT_VOICE,
    })


_EDGE_SAMPLE_TEXT = (
    "Hello! My name is {name}, and I'm here to help you prepare for the CELPIP exam. "
    "Let me give you some advice on how to improve your speaking skills."
)
_EDGE_SAMPLES_DIR = os.path.join(DATA_DIR, 'edge_voice_samples')
os.makedirs(_EDGE_SAMPLES_DIR, exist_ok=True)


@app.route('/api/shadowing/edge-sample/<voice_id>')
def shadowing_edge_sample(voice_id):
    """Return a cached MP3 sample for the given Edge TTS voice."""
    if voice_id not in shadow_mod.VOICES:
        return jsonify({'error': 'Unknown voice'}), 404

    cache_path = os.path.join(_EDGE_SAMPLES_DIR, f'{voice_id}.mp3')
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return send_file(cache_path, mimetype='audio/mpeg')

    try:
        label      = shadow_mod.VOICES[voice_id]
        first_name = label.split(' ')[0]
        text       = _EDGE_SAMPLE_TEXT.format(name=first_name)

        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        import edge_tts

        async def _gen():
            tts = edge_tts.Communicate(text, voice_id)
            await tts.save(cache_path)

        asyncio.run(_gen())
        return send_file(cache_path, mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Shadowing page + audio serving ────────────────────────────────────────────
@app.route('/shadowing')
def shadowing():
    return render_template('shadowing.html',
                           default_voice=shadow_mod.DEFAULT_VOICE)


@app.route('/api/shadowing/audio/<session_id>/<filename>')
def shadowing_audio(session_id, filename):
    import re
    if not re.match(r'^[a-f0-9]{32}$', session_id):
        return 'Invalid session', 400
    if not re.match(r'^sentence_\d{3}\.(mp3|wav)$', filename):
        return 'Invalid filename', 400
    sess = shadow_sessions.get(session_id)
    if not sess:
        return 'Session not found', 404
    path = os.path.join(sess['audio_dir'], filename)
    if not os.path.exists(path):
        return 'File not found', 404
    mimetype = 'audio/wav' if filename.endswith('.wav') else 'audio/mpeg'
    return send_file(path, mimetype=mimetype)


@app.route('/api/jobs/<job_id>/open-folder', methods=['POST'])
def api_open_job_folder(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    j = jobs[job_id]
    path = j['output_path']
    folder = os.path.dirname(path) if path and os.path.isfile(path) else path
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Folder not found on disk'}), 404
    try:
        import subprocess
        subprocess.Popen(['explorer', '/select,', os.path.abspath(path)] if path and os.path.isfile(path)
                         else ['explorer', os.path.abspath(folder)])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/api/jobs/<job_id>/open-video', methods=['POST'])
def api_open_job_video(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    j = jobs[job_id]
    if not j['done'] or j['error']:
        return jsonify({'error': 'Video not ready'}), 400
    path = j['output_path']
    if not path or not os.path.exists(path):
        return jsonify({'error': 'File not found on disk'}), 404
    try:
        os.startfile(os.path.abspath(path))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/api/templates/<int:record_id>/open-folder', methods=['POST'])
def api_open_template_folder(record_id):
    """Open Windows Explorer to the folder containing the generated video."""
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404
    video_path = row.get('video_path') or ''
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found on disk'}), 404
    abs_path = os.path.abspath(video_path)
    try:
        import subprocess
        subprocess.Popen(['explorer', '/select,', abs_path])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/api/templates/<int:record_id>/open-video', methods=['POST'])
def api_open_template_video(record_id):
    """Open the generated video file with the default media player."""
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404
    video_path = row.get('video_path') or ''
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found on disk'}), 404
    try:
        os.startfile(os.path.abspath(video_path))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


# ── Pattern Palette Preview ───────────────────────────────────────────────────

@app.route('/patterns')
def patterns_page():
    from modules.style_gen import (CATEGORY_DISPLAY, CATEGORY_ACCENT,
                                    BAND_BG, BAND_DISPLAY,
                                    FREQ_CONFIG, FREQ_DISPLAY,
                                    SECTION_STYLE, SECTION_DISPLAY)
    return render_template(
        'patterns.html',
        categories=CATEGORY_DISPLAY,
        category_accent=CATEGORY_ACCENT,
        bands=BAND_DISPLAY,
        band_bg=BAND_BG,
        freqs=FREQ_DISPLAY,
        freq_config=FREQ_CONFIG,
        sections=SECTION_DISPLAY,
        section_style=SECTION_STYLE,
    )


_FONT_SCALES_PATH = os.path.join(os.path.dirname(__file__), 'data', 'font_scales.json')

def _load_global_font_scales():
    try:
        with open(_FONT_SCALES_PATH) as f:
            raw = json.load(f)
        return {i: float(raw.get(str(i), raw.get(i, 1.0))) for i in range(1, 6)}
    except Exception:
        return {i: 1.0 for i in range(1, 6)}

def _save_global_font_scales(scales):
    os.makedirs(os.path.dirname(_FONT_SCALES_PATH), exist_ok=True)
    with open(_FONT_SCALES_PATH, 'w') as f:
        json.dump({str(k): v for k, v in scales.items()}, f, indent=2)


@app.route('/api/config/font-scales', methods=['GET'])
def api_get_font_scales():
    return jsonify(_load_global_font_scales())


@app.route('/api/config/font-scales', methods=['POST'])
def api_save_font_scales():
    data = request.get_json() or {}
    scales = {i: max(0.5, min(2.0, float(data.get(str(i), data.get(i, 1.0))))) for i in range(1, 6)}
    _save_global_font_scales(scales)
    return jsonify({'ok': True, 'scales': scales})


@app.route('/api/patterns/frame')
def api_patterns_frame():
    import io
    from modules.style_gen import make_group_style, FREQ_CONFIG
    from modules import frame_renderer as fr

    category   = request.args.get('category', 'career_work')
    band       = request.args.get('band', '9_10')
    freq       = request.args.get('freq', 'medium')
    section    = int(request.args.get('section', 3))
    seed       = request.args.get('seed', None)
    seed       = int(seed) if seed is not None else None
    font_scale = float(request.args.get('font_scale', 1.0))

    style = make_group_style(category_slug=category, band=band, freq=freq,
                             section=section, seed=seed)
    style['font_scale'] = max(0.5, min(2.0, font_scale))

    _Q = ("Your friend says: \"I really struggle with public speaking and it is holding "
          "back my career. Every time I have to present, I freeze. What advice would you give me?\"")
    _SENTS = [
        {'text': "First, I would suggest starting small — practise speaking in front of just one or two trusted friends."},
        {'text': "Joining a group like Toastmasters is an excellent way to build confidence in a supportive environment."},
        {'text': "Remember that thorough preparation is the best antidote to anxiety about public speaking."},
    ]
    _VOCAB = [
        {'word': 'resilience', 'definition': 'ability to recover quickly from setbacks'},
        {'word': 'confidence', 'definition': 'belief in one\'s own abilities and judgment'},
        {'word': 'articulate',  'definition': 'able to express thoughts clearly and fluently'},
    ]

    if section == 1:
        img = fr.render_prep_frame('Career & Work', _Q, 25, 30, style=style)
    elif section == 2:
        img = fr.render_response_frame('Career & Work', _Q, _SENTS, 1, 70, 90,
                                       style=style, vocab_words=_VOCAB)
    elif section == 3:
        img = fr.render_vocab_page(
            'Resilience', 'noun',
            'The ability to recover quickly from difficulties; toughness in the face of setbacks',
            'Her resilience helped her overcome every challenge in her new career path.',
            style=style, word_idx=0, total_words=5,
        )
    elif section == 4:
        img = fr.render_shadow_frame(_SENTS[0]['text'], _SENTS, 0, _VOCAB, 1, 3, 'tts', 0.6, style)
    elif section == 5:
        img = fr.render_final_answer_frame('Career & Work', _SENTS, 1, _VOCAB, style)
    elif section == 0:
        # Thumbnail preview
        freq_cfg = FREQ_CONFIG.get(freq, FREQ_CONFIG['medium'])
        img = fr.render_thumbnail(
            task_num=1, task_name='Giving Advice', band=band,
            category=category.replace('_', ' ').title(),
            title='Public Speaking Anxiety',
            seed=42,
            freq_label=freq_cfg['label'],
            freq_color=freq_cfg['color'],
        )
    else:
        img = fr.render_vocab_page('Resilience', 'noun', '...', '...', style=style)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=82)
    buf.seek(0)
    return send_file(buf, mimetype='image/jpeg')


# ── YouTube OAuth & Upload ─────────────────────────────────────────────────────

yt_uploads = {}   # upload_id -> {done, error, progress, video_id, youtube_url}


@app.route('/api/youtube-meta/raw', methods=['POST'])
def api_youtube_meta_raw():
    """Generate YouTube metadata from raw session data (no DB record needed)."""
    import json as _json
    data = request.get_json() or {}
    task_num  = _int(data.get('task_num', 1))
    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    part_name = task_info['name']
    band      = data.get('band', '7_8')
    category  = data.get('category', '')
    title     = data.get('title', '') or category
    question  = data.get('question', '')
    answer    = data.get('answer', '')
    vocab     = data.get('vocab', [])

    yt_title = yt_mod._make_title(task_num, part_name, band, category, title)
    yt_desc  = yt_mod._make_description(task_num, part_name, band, category,
                                        title, question, answer, vocab)
    yt_tags  = yt_mod._make_tags(task_num, band)
    return jsonify({'title': yt_title, 'description': yt_desc, 'tags': ', '.join(yt_tags)})


@app.route('/youtube/auth')
def youtube_auth():
    """Redirect user to Google OAuth consent screen."""
    if not yt_mod.client_secrets_present():
        return (
            '<h2>Setup required</h2>'
            '<p>Place your Google OAuth credentials at '
            '<code>data/client_secrets.json</code>.</p>'
            '<p>Steps:<br>'
            '1. Open <a href="https://console.cloud.google.com/" target="_blank">'
            'Google Cloud Console</a><br>'
            '2. Create a project &rarr; Enable <strong>YouTube Data API v3</strong><br>'
            '3. APIs &amp; Services &rarr; Credentials &rarr; Create OAuth 2.0 Client ID<br>'
            '&nbsp;&nbsp;&nbsp;Type: <strong>Web application</strong><br>'
            '&nbsp;&nbsp;&nbsp;Redirect URI: <code>http://127.0.0.1:5009/youtube/callback</code><br>'
            '4. Download JSON &rarr; rename to <code>client_secrets.json</code> &rarr; '
            'place in the <code>data/</code> folder<br>'
            '5. Restart the server, then try again.</p>'
        ), 400
    redirect_uri = url_for('youtube_callback', _external=True)
    _state, auth_url = yt_mod.get_auth_url(redirect_uri)
    return redirect(auth_url)


@app.route('/youtube/callback')
def youtube_callback():
    """Google redirects here after the user grants permission."""
    code  = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    if error:
        return f'<script>window.close();</script><p>Auth denied: {error}</p>', 400
    if not code or not state:
        return 'Missing OAuth parameters', 400
    try:
        yt_mod.handle_callback(state, code)
    except Exception as e:
        return f'<script>window.close();</script><p>OAuth error: {e}</p>', 400
    # Notify opener (popup flow) then close
    return (
        '<html><body>'
        '<p>Authenticated! You can close this window.</p>'
        '<script>'
        'if(window.opener){window.opener.postMessage("yt_authed","*");}'
        'setTimeout(function(){window.close();},1500);'
        '</script>'
        '</body></html>'
    )


@app.route('/api/youtube/status')
def api_youtube_status():
    return jsonify({
        'authenticated':   yt_mod.is_authenticated(),
        'secrets_present': yt_mod.client_secrets_present(),
    })


@app.route('/api/youtube/upload/<job_id>', methods=['POST'])
def api_youtube_upload_job(job_id):
    """Start YouTube upload for a completed generation job."""
    j = jobs.get(job_id)
    if not j or not j.get('done') or j.get('error'):
        return jsonify({'error': 'Video not ready'}), 400
    video_path = j.get('output_path', '')
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found on disk'}), 404

    jd        = j['_job_data']
    task_num  = jd['task_num']
    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    part_name = task_info['name']
    thumb_path = os.path.join(os.path.dirname(video_path), 'thumbnail.jpg')

    return _start_yt_upload(
        video_path, thumb_path, task_num, part_name,
        jd['band'], jd['category'], jd['title'],
        jd['question'], jd['answer'], jd['vocab'],
    )


def _start_yt_upload(video_path, thumb_path, task_num, part_name,
                      band, category, title, question, answer, vocab):
    if not yt_mod.is_authenticated():
        return jsonify({'error': 'not_authenticated'}), 401

    upload_id = uuid.uuid4().hex
    yt_uploads[upload_id] = {
        'done': False, 'error': None, 'progress': 0,
        'video_id': None, 'youtube_url': None,
    }

    def _run():
        def cb(pct):
            yt_uploads[upload_id]['progress'] = pct

        try:
            video_id = yt_mod.upload_video(
                video_path, thumb_path, task_num, part_name,
                band, category, title, question, answer, vocab,
                progress_cb=cb,
            )
            youtube_url = f'https://youtu.be/{video_id}'
            yt_uploads[upload_id].update(
                done=True, video_id=video_id, youtube_url=youtube_url, progress=100)
        except Exception as e:
            print(f'[YouTube] Upload error: {e}\n{traceback.format_exc()}',
                  file=sys.stderr)
            yt_uploads[upload_id].update(done=True, error=str(e))

    threading.Thread(target=_run, daemon=True, name=f'YTUpload-{upload_id}').start()
    return jsonify({'upload_id': upload_id})


@app.route('/api/youtube/upload-status/<upload_id>')
def api_youtube_upload_status(upload_id):
    u = yt_uploads.get(upload_id)
    if not u:
        return jsonify({'error': 'Upload not found'}), 404
    return jsonify(u)


# ── Template Library ───────────────────────────────────────────────────────────

@app.route('/templates')
def template_library():
    return render_template('template_library.html')


@app.route('/api/templates/list')
def api_templates_list():
    category        = request.args.get('category')        or None
    frequency_label = request.args.get('frequency_label') or None
    video_status    = request.args.get('video_status')    or None
    youtube_status  = request.args.get('youtube_status')  or None
    search          = request.args.get('search')          or None
    rows    = db.get_templates(category, frequency_label, video_status,
                               youtube_status, search)
    filters = db.get_template_filter_options()
    return jsonify({'templates': rows, 'filters': filters})


@app.route('/api/templates/stats')
def api_templates_stats():
    return jsonify(db.get_template_stats())


@app.route('/api/templates/<int:record_id>', methods=['GET'])
def api_template_get(record_id):
    """Return a single template row by DB id."""
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404
    return jsonify(row)


@app.route('/api/templates/generate-batch', methods=['POST'])
def api_templates_generate_batch():
    """Queue the next N ungenerated templates for video generation."""
    import json as _json
    data  = request.get_json() or {}
    count = int(data.get('count', 1))
    count = max(1, min(count, 50))
    rows = db.get_next_ungenerated(count)
    if not rows:
        return jsonify({'queued': 0, 'job_ids': []})

    job_ids = []
    for row in rows:
        vocab = row.get('vocabulary', [])
        if isinstance(vocab, str):
            try:    vocab = _json.loads(vocab)
            except: vocab = []

        session_dir = output_dirs.template_session_dir(
            row['template_id'], row['category'],
            row['frequency_label'], row['title'])

        section_seeds = style_gen.default_seeds()
        job_id = uuid.uuid4().hex
        voice  = kokoro_tts.random_voice()

        job_data = {
            'question':          row['question'],
            'answer':            row['answer'],
            'vocab':             vocab,
            'task_num':          row['part'],
            'band':              row['band'],
            'category':          row['category'],
            'title':             row['title'],
            'freq':              style_gen.freq_key_from_label(row.get('frequency_label')),
            'session_dir':       session_dir,
            'db_record_id':      None,
            'template_record_id': row['id'],
            'thumb_seed':        None,
            'thumb_color':       None,
            'thumb_font':        None,
            'thumb_font_scale':  1.0,
            'font_scales':       _load_global_font_scales(),
            'voice_label':       kokoro_tts.KOKORO_VOICES[voice],
        }

        with _queue_lock:
            _queue_order.append(job_id)

        jobs[job_id] = {
            'progress': 0, 'step': 'Queued…', 'done': False,
            'error': None, 'output_path': None, 'status': 'queued',
            'cancelled': False,
            'label': f'{row["category"]} · {row["template_id"]}',
            'created_at': _time.time(),
            '_job_data':      job_data,
            '_section_seeds': section_seeds,
            '_voice':         voice,
        }
        _job_queue.put(job_id)
        job_ids.append({'job_id': job_id, 'template_id': row['template_id'],
                        'title': row['title']})

    return jsonify({'queued': len(job_ids), 'job_ids': job_ids})


@app.route('/api/templates/<int:record_id>/generate', methods=['POST'])
def api_template_generate(record_id):
    """Queue a single template for (re)generation. Deletes existing video first."""
    import json as _json
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404

    voice = kokoro_tts.random_voice()

    # Delete existing files if regenerating
    old_video = row.get('video_path') or ''
    old_pdf   = row.get('pdf_path')   or ''
    old_dir   = row.get('session_dir') or ''
    if old_video and os.path.exists(old_video):
        try: os.remove(old_video)
        except Exception: pass
    if old_pdf and os.path.exists(old_pdf):
        try: os.remove(old_pdf)
        except Exception: pass
    db.reset_template(record_id)

    vocab = row.get('vocabulary', [])
    if isinstance(vocab, str):
        try:    vocab = _json.loads(vocab)
        except: vocab = []

    session_dir = output_dirs.template_session_dir(
        row['template_id'], row['category'],
        row['frequency_label'], row['title'])

    section_seeds = style_gen.default_seeds()
    job_id = uuid.uuid4().hex

    job_data = {
        'question':           row['question'],
        'answer':             row['answer'],
        'vocab':              vocab,
        'task_num':           row['part'],
        'band':               row['band'],
        'category':           row['category'],
        'title':              row['title'],
        'freq':               style_gen.freq_key_from_label(row.get('frequency_label')),
        'session_dir':        session_dir,
        'db_record_id':       None,
        'template_record_id': record_id,
        'thumb_seed':         None,
        'thumb_color':        None,
        'thumb_font':         None,
        'thumb_font_scale':   1.0,
        'font_scales':        _load_global_font_scales(),
        'voice_label':        kokoro_tts.KOKORO_VOICES[voice],
    }

    with _queue_lock:
        _queue_order.append(job_id)

    jobs[job_id] = {
        'progress': 0, 'step': 'Queued…', 'done': False,
        'error': None, 'output_path': None, 'status': 'queued',
        'cancelled': False,
        'label': f'{row["category"]} · {row["template_id"]}',
        'created_at': _time.time(),
        '_job_data':      job_data,
        '_section_seeds': section_seeds,
        '_voice':         voice,
    }
    _job_queue.put(job_id)

    return jsonify({'job_id': job_id, 'template_id': row['template_id']})


@app.route('/api/templates/<int:record_id>/reset', methods=['POST'])
def api_template_reset(record_id):
    """Delete video/PDF files and reset DB status."""
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404
    for path in (row.get('video_path') or '', row.get('pdf_path') or ''):
        if path and os.path.exists(path):
            try: os.remove(path)
            except Exception: pass
    db.reset_template(record_id)
    return jsonify({'ok': True})


@app.route('/api/templates/<int:record_id>/mark-posted', methods=['POST'])
def api_template_mark_posted(record_id):
    data = request.get_json() or {}
    db.mark_template_posted(record_id,
                            youtube_url=data.get('youtube_url'),
                            youtube_video_id=data.get('youtube_video_id'))
    return jsonify({'ok': True})


@app.route('/api/templates/<int:record_id>/unmark-posted', methods=['POST'])
def api_template_unmark_posted(record_id):
    db.unmark_template_posted(record_id)
    return jsonify({'ok': True})


@app.route('/api/templates/<int:record_id>/youtube-info')
def api_template_youtube_info(record_id):
    import json as _json
    row = db.get_template_by_id(record_id)
    if not row:
        return jsonify({'error': 'Template not found'}), 404

    task_num  = row['part']
    task_info = TASK_DEFAULTS.get(task_num, TASK_DEFAULTS[1])
    part_name = task_info['name']
    vocab     = row.get('vocabulary', [])
    if isinstance(vocab, str):
        try:    vocab = _json.loads(vocab)
        except: vocab = []

    yt_title = yt_mod._make_title(task_num, part_name, row['band'],
                                  row['category'], row['title'])
    yt_desc  = yt_mod._make_description(task_num, part_name, row['band'],
                                        row['category'], row['title'],
                                        row['question'], row['answer'], vocab)
    yt_tags  = yt_mod._make_tags(task_num, row['band'])

    return jsonify({
        'title':            yt_title,
        'description':      yt_desc,
        'tags':             ', '.join(yt_tags),
        'template_id':      row.get('template_id'),
        'video_path':       row.get('video_path') or '',
        'youtube_url':      row.get('youtube_url') or '',
        'youtube_video_id': row.get('youtube_video_id') or '',
    })


# ── Margin Tuner ───────────────────────────────────────────────────────────────

@app.route('/margin-tuner')
def margin_tuner():
    """Interactive page to adjust layout and highlight box margins."""
    # Fetch first DB question for preview; fall back to sample if DB empty
    import json as _json
    all_rows = db.get_templates()
    rows = all_rows[:1] if all_rows else []
    if rows:
        row = rows[0]
        vocab = row.get('vocabulary', [])
        if isinstance(vocab, str):
            try:    vocab = _json.loads(vocab)
            except: vocab = []
        preview_q = {
            'task_name': row.get('category', 'Giving Advice'),
            'question':  row.get('question', ''),
            'answer':    row.get('answer', ''),
            'vocab':     vocab,
        }
    else:
        preview_q = {
            'task_name': 'Giving Advice',
            'question': ('Your friend says: "I really struggle with public speaking and it is '
                         'holding back my career. Every time I have to present, I freeze. '
                         'What advice would you give me?"'),
            'answer':   ('First, I would suggest starting small by practising in front of one '
                         'or two trusted friends, so the stakes feel lower. '
                         'Joining a group like Toastmasters is an excellent way to build '
                         'confidence in a supportive, structured environment. '
                         'Make sure to record yourself occasionally, because hearing your own '
                         'voice helps you identify specific areas to improve. '
                         'Remember that thorough preparation is the best antidote to anxiety, '
                         'so always arrive with a clear outline of your key points. '
                         'With consistent practice, public speaking will start to feel natural '
                         'rather than overwhelming.'),
            'vocab': [
                {'word': 'resilience', 'definition': 'ability to recover quickly from setbacks'},
                {'word': 'antidote', 'definition': 'something that counteracts a problem'},
            ],
        }
    current = fr._SAVED_MARGINS
    return render_template('margin_tuner.html', current=current, preview_q=preview_q)


@app.route('/api/margin-config', methods=['GET'])
def api_margin_config_get():
    return jsonify(fr._SAVED_MARGINS)


@app.route('/api/margin-config', methods=['POST'])
def api_margin_config_save():
    data = request.get_json() or {}
    margins = {
        'side':          max(20, min(300, int(data.get('side', 100)))),
        'top':           max(0,  min(300, int(data.get('top',  100)))),
        'bottom':        max(20, min(300, int(data.get('bottom', 100)))),
        'hl_right_mult': max(-5.0, min(10.0, float(data.get('hl_right_mult', 2.0)))),
        'sentence_gap':  max(0,  min(120, int(data.get('sentence_gap', 16)))),
        'line_gap':      max(0,  min(60,  int(data.get('line_gap', 0)))),
    }
    fr.save_margin_config(margins)
    return jsonify({'ok': True, 'margins': margins})


@app.route('/api/margin-preview/frame')
def api_margin_preview_frame():
    """Render a Section 2 frame with inline margin overrides (no DB, no TTS)."""
    import io as _io, re as _re, random as _rand
    margins = {
        'side':          float(request.args.get('side', 100)),
        'top':           float(request.args.get('top',  100)),
        'bottom':        float(request.args.get('bottom', 100)),
        'hl_right_mult': max(-5.0, float(request.args.get('hl_right_mult', 2.0))),
        'sentence_gap':  max(0, float(request.args.get('sentence_gap', 16))),
        'line_gap':      max(0, float(request.args.get('line_gap', 0))),
    }
    seed  = int(request.args.get('seed', _rand.randint(0, 2**31)))
    q     = request.args.get('question', '')
    ans   = request.args.get('answer',   '')
    tname = request.args.get('task_name', 'Giving Advice')

    sents = _re.split(r'(?<=[.!?])\s+(?=[A-Z])', ans.strip())
    sents = [s.strip() for s in sents if s.strip()] or [ans]

    vocab_words = [
        {'word': 'resilience', 'definition': 'ability to recover quickly from setbacks'},
        {'word': 'confidence', 'definition': 'belief in one\'s own abilities'},
    ]

    style = style_gen.generate_section_style(2, seed=seed)
    style['_margins'] = margins

    fake = []
    t = 0.0
    for s in sents:
        d = max(1.0, len(s.split()) / 2.5)
        fake.append({'text': s, 'start_time': t, 'end_time': t + d})
        t += d

    img = fr.render_response_frame(
        tname, q, fake, 0, 60, 90,
        style=style, vocab_words=vocab_words)

    buf = _io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype='image/jpeg')


# ── Reading Lab ────────────────────────────────────────────────────────────────
from modules import reading_lab as rl_mod

_rl_sessions = {}   # session_id -> audio_dir


@app.route('/reading-lab')
def reading_lab():
    return render_template('reading_lab.html')


@app.route('/api/reading-lab/extract', methods=['POST'])
def rl_extract():
    data = request.get_json(force=True)
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    items    = rl_mod.extract_items(text)
    segments = rl_mod.build_segments(text, items)
    return jsonify({'segments': segments, 'item_count': len(items)})


@app.route('/api/reading-lab/youtube', methods=['POST'])
def rl_youtube():
    data = request.get_json(force=True)
    url  = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    try:
        text, video_id = rl_mod.get_youtube_transcript(url)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'text': text, 'title': f'YouTube: {video_id}'})


@app.route('/api/reading-lab/tts/generate', methods=['POST'])
def rl_tts_generate():
    data      = request.get_json(force=True)
    text      = (data.get('text') or '').strip()
    voice     = data.get('voice', shadow_mod.DEFAULT_VOICE)
    if not text:
        return jsonify({'error': 'No text'}), 400
    if not shadow_mod.is_kokoro_voice(voice) and voice not in shadow_mod.VOICES:
        voice = shadow_mod.DEFAULT_VOICE

    sess_id   = str(uuid.uuid4())
    audio_dir = os.path.join(TEMP_DIR, 'rl_tts', sess_id)
    os.makedirs(audio_dir, exist_ok=True)

    sentences = shadow_mod.split_sentences(text)
    try:
        audio_files = shadow_mod.generate_shadowing_audio(sentences, audio_dir, voice)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    _rl_sessions[sess_id] = {'audio_dir': audio_dir}
    return jsonify({'session_id': sess_id, 'sentences': audio_files})


@app.route('/api/reading-lab/audio/<session_id>/<filename>')
def rl_audio(session_id, filename):
    sess = _rl_sessions.get(session_id)
    if not sess:
        return jsonify({'error': 'Session not found'}), 404
    path = os.path.join(sess['audio_dir'], secure_filename(filename))
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    mime = 'audio/wav' if filename.endswith('.wav') else 'audio/mpeg'
    return send_file(path, mimetype=mime)


@app.route('/api/reading-lab/save', methods=['POST'])
def rl_save():
    data        = request.get_json(force=True)
    source_type = data.get('source_type', 'text')
    source_url  = data.get('source_url')
    raw_text    = (data.get('text') or '').strip()
    title       = data.get('title')
    items       = data.get('items', [])
    if not raw_text:
        return jsonify({'error': 'No text'}), 400
    source_id = db.save_vocab_source(source_type, source_url, raw_text, title)
    if items:
        db.save_vocab_items(source_id, items)
    return jsonify({'ok': True, 'source_id': source_id, 'saved': len(items)})


@app.route('/api/reading-lab/bank', methods=['GET'])
def rl_bank():
    items = db.get_vocab_bank()
    return jsonify({'items': items})


@app.route('/api/reading-lab/bank/<int:item_id>', methods=['DELETE'])
def rl_bank_delete(item_id):
    db.delete_vocab_item(item_id)
    return jsonify({'ok': True})


if __name__ == '__main__':
    print('=== CELPIP Practice Studio ===')
    print(f'Output : {OUTPUT_DIR}')
    print(f'DB     : {db.DB_PATH}')
    print('Server : http://127.0.0.1:5009')
    app.run(debug=True, use_reloader=False, host='127.0.0.1', port=5009)
