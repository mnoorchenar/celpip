/* CELPIP Shadowing Practice */
(function () {
  'use strict';

  function $(s) { return document.querySelector(s); }

  /* ── Load stored data ─────────────────────────────────────────────── */
  var _data = null;
  try { _data = JSON.parse(localStorage.getItem('celpip_shadow_json') || 'null'); } catch(e) {}

  var emptyEl  = $('#shadowEmpty');
  var loadedEl = $('#shadowLoaded');

  if (!_data || !_data.answer) {
    if (emptyEl)  emptyEl.style.display  = 'flex';
    if (loadedEl) loadedEl.style.display = 'none';
    return;
  }
  emptyEl.style.display  = 'none';
  loadedEl.style.display = 'flex';

  // Top bar meta
  var meta = $('#topMeta');
  if (meta) {
    var parts = [];
    if (_data.category) parts.push(_data.category);
    if (_data.band) parts.push({ '7_8': 'Band 7–8', '9_10': 'Band 9–10', '11_12': 'Band 11–12' }[_data.band] || _data.band);
    meta.textContent = parts.join('  ·  ');
  }

  /* ── Vocab / sentence helpers ─────────────────────────────────────── */

  function stripVocab(text) {
    return text.replace(/\{([^}]+)\}/g, '$1');
  }

  function splitSentences(text) {
    text = text.trim();
    var parts = text.split(/(?<=[.!?]) +(?=[A-Z])/);
    return parts.map(function(p) { return p.trim(); }).filter(Boolean);
  }

  // Returns safe HTML with {word} → <span class="vocab-hl">word</span>
  // Wrapped in a <p> so it is the ONLY flex child inside the sentence box,
  // preventing each text node / span from becoming a separate flex item.
  function buildSentenceHTML(text) {
    var escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    var inner = escaped.replace(/\{([^}]+)\}/g, '<span class="vocab-hl">$1</span>');
    return '<p class="sent-text">' + inner + '</p>';
  }

  var _displaySentences = splitSentences(_data.answer);

  /* ── Voice state ──────────────────────────────────────────────────── */
  var currentVoice   = localStorage.getItem('celpip_shadow_voice')
                       || (typeof SHADOW_DEFAULT_VOICE !== 'undefined' ? SHADOW_DEFAULT_VOICE : 'af_heart');
  var _voiceGroups   = null;
  var _svpAudio      = null;
  var _svpPlayingVid = null;

  function isKokoro(vid) { return /^(af_|am_|bf_|bm_)/.test(vid); }

  function voiceLabelFor(vid) {
    if (!_voiceGroups) return vid;
    for (var gi = 0; gi < _voiceGroups.groups.length; gi++) {
      var subs = _voiceGroups.groups[gi].sub_groups || [];
      for (var si = 0; si < subs.length; si++) {
        var voices = subs[si].voices || [];
        for (var vi = 0; vi < voices.length; vi++) {
          if (voices[vi].id === vid) return voices[vi].label;
        }
      }
    }
    return vid;
  }

  function updateVoiceBtn() {
    var labelEl  = $('#voicePickerLabel');
    var engineEl = $('#voicePickerEngine');
    if (labelEl)  labelEl.textContent  = voiceLabelFor(currentVoice);
    if (engineEl) engineEl.textContent = isKokoro(currentVoice) ? 'Kokoro' : 'Edge';
  }

  /* ── Playback state ───────────────────────────────────────────────── */
  var state = {
    sentences:    [],
    sessionId:    (_data && _data._session_id) || null,
    sessionDir:   localStorage.getItem('celpip_session_dir') || '',
    reps:         1,
    speed:        1.0,
    pausePerWord: 0.6,
    currentIdx:   0,
    currentRep:   1,
    isPlaying:    false,
    generated:    false,
    _pauseTimer:  null,
  };

  var audio = new Audio();
  audio.preload = 'auto';

  /* ── UI element refs ──────────────────────────────────────────────── */
  var sentBox       = $('#sentBox');
  var sentCounter   = $('#sentCounter');
  var repIndicator  = $('#repIndicator');
  var playPauseBtn  = $('#playPauseBtn');
  var prevBtn       = $('#prevBtn');
  var nextBtn       = $('#nextBtn');
  var doneMsg       = $('#doneMsg');
  var genBtn        = $('#genBtn');
  var genError      = $('#genError');
  var kbdHint       = $('#kbdHint');
  var pauseBarTrack = $('#pauseBarTrack');
  var pauseBarFill  = $('#pauseBarFill');
  var repSlider     = $('#repSlider');
  var repValEl      = $('#repVal');
  var speedSlider   = $('#speedSlider');
  var speedValEl    = $('#speedVal');
  var pauseSlider   = $('#pauseSlider');
  var pauseValEl    = $('#pauseVal');

  /* ── Sliders ──────────────────────────────────────────────────────── */
  if (repSlider) {
    repSlider.addEventListener('input', function () {
      state.reps = parseInt(this.value);
      if (repValEl) repValEl.textContent = state.reps + '×';
      updateRepDots();
    });
    state.reps = parseInt(repSlider.value);
  }
  if (speedSlider) {
    speedSlider.addEventListener('input', function () {
      state.speed = parseFloat(this.value);
      if (speedValEl) speedValEl.textContent = state.speed.toFixed(1) + '×';
      audio.playbackRate = state.speed;
    });
    state.speed = parseFloat(speedSlider.value);
  }
  if (pauseSlider) {
    pauseSlider.addEventListener('input', function () {
      state.pausePerWord = parseFloat(this.value);
      if (pauseValEl) pauseValEl.textContent = state.pausePerWord.toFixed(1) + 's';
    });
    state.pausePerWord = parseFloat(pauseSlider.value);
  }

  /* ── Generate / auto-generate ─────────────────────────────────────── */

  // Sequence counter — any response from an older generation is silently dropped.
  var _genSeq = 0;

  function setError(msg) {
    if (genError) { genError.textContent = msg; genError.style.display = msg ? 'inline' : 'none'; }
  }

  // force=true  → delete existing audio, regenerate with current voice (user action)
  // force=false → reuse existing audio if present (auto-load on page open)
  function triggerGenerate(force) {
    var seq = ++_genSeq;
    setError('');

    if (genBtn) {
      genBtn.classList.add('gen-btn--loading');
      genBtn.innerHTML = '&#8987;&nbsp; Generating…';
    }
    if (sentBox && !state.generated) {
      sentBox.innerHTML  = '<p class="sent-text" style="font-style:italic">Generating audio…</p>';
      sentBox.className  = 'shadow-sentence-box shadow-sentence-box--idle';
    }

    fetch('/api/shadowing/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        answer:      stripVocab(_data.answer),
        voice:       currentVoice,
        task_num:    _data.task_num  || 1,
        band:        _data.band      || '7_8',
        category:    _data.category  || 'General',
        title:       _data.title     || '',
        session_dir: force ? state.sessionDir : state.sessionDir,
        force_regen: !!force,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (seq !== _genSeq) return;  // stale — a newer generation started, ignore

        if (genBtn) {
          genBtn.classList.remove('gen-btn--loading');
          genBtn.innerHTML = '&#9654;&nbsp; Regenerate';
        }
        if (res.error) { setError(res.error); return; }

        state.sentences  = res.sentences;
        state.sessionId  = res.session_id;
        state.sessionDir = res.session_dir;
        state.currentIdx = 0;
        state.currentRep = 1;
        state.isPlaying  = false;
        state.generated  = true;

        try { localStorage.setItem('celpip_session_dir', res.session_dir); } catch(e) {}
        try {
          var d = JSON.parse(localStorage.getItem('celpip_shadow_json') || '{}');
          d._session_id = res.session_id;
          localStorage.setItem('celpip_shadow_json', JSON.stringify(d));
        } catch(e) {}

        updateUI();
        if (!isDone()) setTimeout(playNow, 400);
      })
      .catch(function (err) {
        if (seq !== _genSeq) return;
        if (genBtn) {
          genBtn.classList.remove('gen-btn--loading');
          genBtn.innerHTML = '&#9654;&nbsp; Regenerate';
        }
        setError('Failed — check connection and retry.');
        if (sentBox && !state.generated) {
          sentBox.innerHTML = '<p class="sent-text" style="font-style:italic">Generation failed. Click Regenerate.</p>';
        }
      });
  }

  // Regenerate button: always force new audio, keep same session dir
  if (genBtn) {
    genBtn.addEventListener('click', function () {
      triggerGenerate(true);
    });
  }

  /* ── Playback ─────────────────────────────────────────────────────── */
  function isDone() {
    return state.generated && state.currentIdx >= state.sentences.length;
  }

  function updateUI() {
    var done = isDone();
    var idx  = state.currentIdx;

    if (sentBox) {
      if (!state.generated) {
        sentBox.innerHTML = '<p class="sent-text" style="font-style:italic">Preparing audio…</p>';
        sentBox.className = 'shadow-sentence-box shadow-sentence-box--idle';
      } else if (done) {
        sentBox.innerHTML = '<p class="sent-text" style="font-style:italic">All done!</p>';
        sentBox.className = 'shadow-sentence-box shadow-sentence-box--idle';
      } else {
        var displayText = _displaySentences[idx] || (state.sentences[idx] ? state.sentences[idx].text : '');
        sentBox.innerHTML = buildSentenceHTML(displayText);
        sentBox.className = 'shadow-sentence-box';
      }
    }

    if (sentCounter) {
      sentCounter.textContent = state.generated && !done
        ? 'Sentence ' + (idx + 1) + ' of ' + state.sentences.length
        : '';
    }

    updateRepDots();

    if (playPauseBtn) {
      playPauseBtn.innerHTML = state.isPlaying ? '&#9646;&#9646;' : '&#9654;';
      playPauseBtn.disabled  = !state.generated || done;
    }
    if (prevBtn) prevBtn.disabled = !state.generated || idx === 0;
    if (nextBtn) nextBtn.disabled = !state.generated || done;
    if (doneMsg) doneMsg.classList.toggle('visible', done);
    if (kbdHint) kbdHint.style.display = state.generated ? 'flex' : 'none';
  }

  function updateRepDots() {
    if (!repIndicator || !state.generated || isDone()) {
      if (repIndicator) repIndicator.innerHTML = '';
      return;
    }
    var html = '';
    for (var i = 1; i <= state.reps; i++) {
      html += '<div class="rep-dot' + (i <= state.currentRep ? ' filled' : '') + '"></div>';
    }
    repIndicator.innerHTML = html;
  }

  /* ── Pause progress bar ───────────────────────────────────────────── */
  function showPauseBar(ms) {
    if (!pauseBarFill || !pauseBarTrack) return;
    pauseBarFill.style.transition = 'none';
    pauseBarFill.style.width = '100%';
    pauseBarTrack.classList.add('active');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        pauseBarFill.style.transition = 'width ' + ms + 'ms linear';
        pauseBarFill.style.width = '0%';
      });
    });
  }

  function hidePauseBar() {
    if (!pauseBarFill || !pauseBarTrack) return;
    pauseBarFill.style.transition = 'none';
    pauseBarFill.style.width = '0%';
    pauseBarTrack.classList.remove('active');
  }

  /* ── Audio playback ───────────────────────────────────────────────── */
  function audioUrl() {
    var s = state.sentences[state.currentIdx];
    if (!s) return null;
    return '/api/shadowing/audio/' + state.sessionId + '/' + s.filename;
  }

  function wordCount(text) {
    return (text || '').trim().split(/\s+/).filter(Boolean).length;
  }

  function skipToNext() {
    hidePauseBar();
    if (state._pauseTimer) { clearTimeout(state._pauseTimer); state._pauseTimer = null; }
    state.isPlaying  = false;
    state.currentRep = 1;
    state.currentIdx++;
    updateUI();
    if (!isDone()) setTimeout(playNow, 150);
  }

  function playNow() {
    var url = audioUrl();
    if (!url) { skipToNext(); return; }
    hidePauseBar();
    audio.src = url;
    audio.load();
    audio.playbackRate = state.speed;
    state.isPlaying = true;
    updateUI();
    audio.play().catch(function (e) {
      console.warn('Audio play failed:', e);
      skipToNext();
    });
  }

  function pausePlayback() {
    hidePauseBar();
    if (state._pauseTimer) { clearTimeout(state._pauseTimer); state._pauseTimer = null; }
    audio.pause();
    state.isPlaying = false;
    updateUI();
  }

  function pauseThenPlay(nextAction) {
    var sentence = state.sentences[state.currentIdx];
    var words    = sentence ? wordCount(sentence.text) : 0;
    var ms       = Math.round(state.pausePerWord * words * 1000);
    if (ms <= 50) { nextAction(); return; }

    showPauseBar(ms);
    state._pauseTimer = setTimeout(function () {
      hidePauseBar();
      nextAction();
    }, ms);
  }

  audio.addEventListener('error', function () {
    console.warn('Audio error, skipping sentence', state.currentIdx);
    skipToNext();
  });

  audio.addEventListener('ended', function () {
    if (state.currentRep < state.reps) {
      state.currentRep++;
      updateUI();
      pauseThenPlay(playNow);
    } else {
      state.currentRep = 1;
      updateUI();
      var nextIdx = state.currentIdx + 1;
      if (nextIdx < state.sentences.length) {
        pauseThenPlay(function () {
          state.currentIdx = nextIdx;
          updateUI();
          playNow();
        });
      } else {
        pauseThenPlay(function () {
          state.currentIdx = nextIdx;
          updateUI();
        });
      }
    }
  });

  /* ── Controls ─────────────────────────────────────────────────────── */
  if (playPauseBtn) {
    playPauseBtn.addEventListener('click', function () {
      if (state.isPlaying) { pausePlayback(); } else { playNow(); }
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (!state.generated) return;
      pausePlayback();
      if (state.currentIdx > 0) state.currentIdx--;
      state.currentRep = 1;
      updateUI();
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      if (!state.generated) return;
      pausePlayback();
      state.currentRep = 1;
      state.currentIdx++;
      updateUI();
    });
  }

  /* ── Keyboard shortcuts ───────────────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    var tag = (document.activeElement || {}).tagName || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (document.getElementById('voicePickerModal').classList.contains('open')) return;

    if (e.code === 'Space') {
      e.preventDefault();
      if (!state.generated || isDone()) return;
      if (state.isPlaying) { pausePlayback(); } else { playNow(); }
    } else if (e.code === 'ArrowLeft') {
      e.preventDefault();
      if (!state.generated || state.currentIdx === 0) return;
      pausePlayback();
      state.currentIdx--;
      state.currentRep = 1;
      updateUI();
    } else if (e.code === 'ArrowRight') {
      e.preventDefault();
      if (!state.generated || isDone()) return;
      pausePlayback();
      state.currentRep = 1;
      state.currentIdx++;
      updateUI();
    } else if (e.code === 'KeyR' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      triggerGenerate(true);
    }
  });

  /* ── Voice picker modal ───────────────────────────────────────────── */
  function openVoicePicker() {
    document.getElementById('voicePickerModal').classList.add('open');
    renderVoicePicker();
  }
  function closeVoicePicker() {
    document.getElementById('voicePickerModal').classList.remove('open');
    svpStopPreview();
  }
  function svpOverlayClick(e) {
    if (e.target === document.getElementById('voicePickerModal')) closeVoicePicker();
  }
  window.openVoicePicker  = openVoicePicker;
  window.closeVoicePicker = closeVoicePicker;
  window.svpOverlayClick  = svpOverlayClick;

  function svpStopPreview() {
    if (_svpAudio) { _svpAudio.pause(); _svpAudio = null; }
    if (_svpPlayingVid) {
      var oldBtn = document.getElementById('svp-play-' + _svpPlayingVid);
      if (oldBtn) oldBtn.innerHTML = '&#9654;';
      _svpPlayingVid = null;
    }
  }

  async function renderVoicePicker() {
    var body = document.getElementById('svpBody');
    if (!body) return;

    if (!_voiceGroups) {
      body.innerHTML = '<div class="svp-loading">Loading voices…</div>';
      try {
        _voiceGroups = await fetch('/api/shadowing/voices').then(function(r) { return r.json(); });
        updateVoiceBtn();
      } catch(e) {
        body.innerHTML = '<div class="svp-loading" style="color:#ef4444">Failed to load voices.</div>';
        return;
      }
    }

    body.innerHTML = '';
    var groups = _voiceGroups.groups || [];

    groups.forEach(function(engine, engineIdx) {
      var section = document.createElement('div');
      section.className = 'svp-engine';

      var unavailable = engine.engine === 'kokoro' && engine.available === false;

      var hdr = document.createElement('div');
      hdr.className = 'svp-engine-header';
      hdr.innerHTML =
        '<span class="svp-engine-label">' + engine.label + '</span>' +
        '<span class="svp-engine-desc">' + engine.description +
          (unavailable ? '&nbsp;&mdash; <em>not installed</em>' : '') +
        '</span>';
      section.appendChild(hdr);

      (engine.sub_groups || []).forEach(function(sub) {
        var groupEl = document.createElement('div');
        groupEl.className = 'svp-group';

        var title = document.createElement('div');
        title.className = 'svp-group-title';
        title.textContent = sub.label;
        groupEl.appendChild(title);

        (sub.voices || []).forEach(function(v) {
          var isActive  = v.id === currentVoice;
          var sampleUrl = engine.engine === 'kokoro'
            ? '/api/voice-sample/' + v.id
            : '/api/shadowing/edge-sample/' + v.id;

          var row = document.createElement('div');
          row.className = 'svp-voice-row' + (isActive ? ' svp-active' : '');
          row.id = 'svp-row-' + v.id;
          row.innerHTML =
            '<span class="svp-voice-name">' + v.label + '</span>' +
            '<button class="svp-play-btn" id="svp-play-' + v.id + '" ' +
              'data-url="' + sampleUrl + '" data-vid="' + v.id + '" ' +
              (unavailable ? 'disabled ' : '') +
              'title="Preview">&#9654;</button>' +
            '<button class="svp-use-btn' + (isActive ? ' svp-use-active' : '') + '" ' +
              'id="svp-use-' + v.id + '" data-vid="' + v.id + '" data-label="' + v.label + '" ' +
              (unavailable ? 'disabled ' : '') + '>' +
              (isActive ? '&#10003; Selected' : 'Use This') +
            '</button>';
          groupEl.appendChild(row);
        });

        section.appendChild(groupEl);
      });

      body.appendChild(section);

      if (engineIdx < groups.length - 1) {
        var sep = document.createElement('hr');
        sep.className = 'svp-sep';
        body.appendChild(sep);
      }
    });

    body.querySelectorAll('.svp-play-btn').forEach(function(btn) {
      btn.addEventListener('click', function() { svpPlay(this.dataset.vid, this.dataset.url); });
    });
    body.querySelectorAll('.svp-use-btn').forEach(function(btn) {
      btn.addEventListener('click', function() { svpSelectVoice(this.dataset.vid, this.dataset.label); });
    });
  }

  async function svpPlay(vid, url) {
    var btn = document.getElementById('svp-play-' + vid);
    if (_svpPlayingVid === vid) { svpStopPreview(); return; }
    svpStopPreview();
    if (!btn) return;

    btn.innerHTML = '&#8987;';
    btn.disabled  = true;

    try {
      var resp = await fetch(url);
      if (!resp.ok) throw new Error(resp.status);
      var blob   = await resp.blob();
      var objUrl = URL.createObjectURL(blob);

      _svpAudio      = new Audio(objUrl);
      _svpPlayingVid = vid;
      btn.innerHTML  = '&#9646;&#9646;';
      btn.disabled   = false;

      _svpAudio.onended = function() {
        btn.innerHTML  = '&#9654;';
        _svpPlayingVid = null;
        _svpAudio      = null;
        URL.revokeObjectURL(objUrl);
      };
      _svpAudio.onerror = function() {
        btn.innerHTML  = '&#9654;';
        btn.disabled   = false;
        _svpPlayingVid = null;
        _svpAudio      = null;
      };
      _svpAudio.play();
    } catch(e) {
      if (btn) { btn.innerHTML = '&#9654;'; btn.disabled = false; }
      var note = document.getElementById('svpNote');
      if (note) note.textContent = 'Preview failed — check your connection.';
    }
  }

  function svpSelectVoice(vid, label) {
    currentVoice = vid;
    try { localStorage.setItem('celpip_shadow_voice', vid); } catch(e) {}

    document.querySelectorAll('.svp-voice-row').forEach(function(r) { r.classList.remove('svp-active'); });
    document.querySelectorAll('.svp-use-btn').forEach(function(b) {
      b.classList.remove('svp-use-active');
      b.textContent = 'Use This';
    });

    var row    = document.getElementById('svp-row-' + vid);
    if (row) row.classList.add('svp-active');

    var useBtn = document.getElementById('svp-use-' + vid);
    if (useBtn) { useBtn.classList.add('svp-use-active'); useBtn.innerHTML = '&#10003; Selected'; }

    var note = document.getElementById('svpNote');
    if (note) note.textContent = '"' + label + '" selected — click Regenerate to apply.';

    updateVoiceBtn();
  }

  /* ── Bootstrap ────────────────────────────────────────────────────── */
  fetch('/api/shadowing/voices')
    .then(function(r) { return r.json(); })
    .then(function(data) { _voiceGroups = data; updateVoiceBtn(); })
    .catch(function() {});

  updateVoiceBtn();
  updateUI();

  // Auto-generate on page open (reuses existing audio if present — no force)
  setTimeout(function() { triggerGenerate(false); }, 200);

})();
