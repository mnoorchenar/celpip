/* CELPIP Shadowing */
(function () {
  'use strict';

  function $(s) { return document.querySelector(s); }

  /* ── Load from localStorage ───────────────────────────────────────── */
  var _data = null;
  var _preSentences = null;
  try { _data = JSON.parse(localStorage.getItem('celpip_shadow_json') || 'null'); } catch(e) {}
  try { _preSentences = JSON.parse(localStorage.getItem('celpip_shadow_sentences') || 'null'); } catch(e) {}

  var emptyEl  = $('#shadowEmpty');
  var loadedEl = $('#shadowLoaded');

  if (!_data || !_data.answer) {
    if (emptyEl)  emptyEl.style.display  = 'flex';
    if (loadedEl) loadedEl.style.display = 'none';
    return;
  }
  emptyEl.style.display  = 'none';
  loadedEl.style.display = 'flex';

  // Show band + category in top bar
  var meta = $('#topMeta');
  if (meta) {
    var parts = [];
    if (_data.category) parts.push(_data.category);
    if (_data.band)     parts.push({ '7_8': 'Band 7–8', '9_10': 'Band 9–10', '11_12': 'Band 11–12' }[_data.band] || _data.band);
    meta.textContent = parts.join('  ·  ');
  }

  /* ── State ────────────────────────────────────────────────────────── */
  var _storedSessionId = (_data && _data._session_id) || null;

  var state = {
    sentences:    _preSentences || [],
    sessionId:    _storedSessionId,
    sessionDir:   localStorage.getItem('celpip_session_dir') || '',
    reps:         1,
    pausePerWord: 1.0,
    currentIdx:   0,
    currentRep:   1,
    isPlaying:    false,
    generated:    !!(_preSentences && _preSentences.length && _storedSessionId),
    _pauseTimer:  null,
  };

  var audio = new Audio();
  audio.preload = 'auto';

  /* ── Re-register session with server (survives server restarts) ───── */
  if (state.sessionDir && state.generated) {
    fetch('/api/shadowing/rehydrate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ session_dir: state.sessionDir }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.error) {
          state.sessionId = res.session_id;
          try {
            var d = JSON.parse(localStorage.getItem('celpip_shadow_json') || '{}');
            d._session_id = res.session_id;
            localStorage.setItem('celpip_shadow_json', JSON.stringify(d));
          } catch (e) {}
        }
      })
      .catch(function (e) { console.warn('Rehydrate failed:', e); });
  }

  /* ── Rep slider ───────────────────────────────────────────────────── */
  var repSlider = $('#repSlider');
  var repValEl  = $('#repVal');
  if (repSlider) {
    repSlider.addEventListener('input', function () {
      state.reps = parseInt(this.value);
      if (repValEl) repValEl.textContent = state.reps + '×';
      updateRepDots();
    });
    state.reps = parseInt(repSlider.value);
  }

  /* ── Speed slider ─────────────────────────────────────────────────── */
  var speedSlider = $('#speedSlider');
  var speedValEl  = $('#speedVal');
  if (speedSlider) {
    speedSlider.addEventListener('input', function () {
      var v = parseFloat(this.value).toFixed(1);
      if (speedValEl) speedValEl.textContent = v + '×';
      audio.playbackRate = parseFloat(v);
    });
  }

  /* ── Pause slider ─────────────────────────────────────────────────── */
  var pauseSlider = $('#pauseSlider');
  var pauseValEl  = $('#pauseVal');
  if (pauseSlider) {
    pauseSlider.addEventListener('input', function () {
      var v = parseFloat(this.value).toFixed(1);
      state.pausePerWord = parseFloat(v);
      if (pauseValEl) pauseValEl.textContent = v + 's';
    });
  }

  /* ── Generate Audio ───────────────────────────────────────────────── */
  var genBtn   = $('#genBtn');
  var genError = $('#genError');
  var voiceSel = $('#voiceSelect');
  if (voiceSel) voiceSel.value = 'en-US-GuyNeural';

  function setError(msg) {
    if (genError) { genError.textContent = msg; genError.style.display = msg ? 'inline' : 'none'; }
  }

  if (genBtn) {
    genBtn.addEventListener('click', function () {
      setError('');
      genBtn.disabled    = true;
      genBtn.textContent = 'Generating…';

      fetch('/api/shadowing/generate', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answer:      _data.answer,
          voice:       voiceSel ? voiceSel.value : '',
          task_num:    _data.task_num  || 1,
          band:        _data.band      || '7_8',
          category:    _data.category  || 'General',
          title:       _data.title     || '',
          session_dir: state.sessionDir,
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          genBtn.disabled    = false;
          genBtn.textContent = 'Regenerate Audio';
          if (res.error) { setError(res.error); return; }

          state.sentences  = res.sentences;
          state.sessionId  = res.session_id;
          state.sessionDir = res.session_dir;
          state.currentIdx = 0;
          state.currentRep = 1;
          state.isPlaying  = false;
          state.generated  = true;

          // Persist session_dir so video generation can reuse it
          try { localStorage.setItem('celpip_session_dir', res.session_dir); } catch(e) {}

          updateUI();
        })
        .catch(function (err) {
          genBtn.disabled    = false;
          genBtn.textContent = 'Generate Audio';
          setError('Network error: ' + err);
        });
    });
  }

  /* ── Playback ─────────────────────────────────────────────────────── */
  var sentBox      = $('#sentBox');
  var sentCounter  = $('#sentCounter');
  var repIndicator = $('#repIndicator');
  var playPauseBtn = $('#playPauseBtn');
  var prevBtn      = $('#prevBtn');
  var nextBtn      = $('#nextBtn');
  var doneMsg      = $('#doneMsg');

  function isDone() {
    return state.generated && state.currentIdx >= state.sentences.length;
  }

  function updateUI() {
    var done = isDone();
    var s    = state.sentences[state.currentIdx];

    // Sentence text
    if (sentBox) {
      if (!state.generated) {
        sentBox.textContent = 'Press Generate Audio to begin.';
        sentBox.className   = 'shadow-sentence-box idle';
      } else if (done) {
        sentBox.textContent = 'All done!';
        sentBox.className   = 'shadow-sentence-box idle';
      } else {
        sentBox.textContent = s ? s.text : '';
        sentBox.className   = 'shadow-sentence-box';
      }
    }

    // Counter
    if (sentCounter) {
      sentCounter.textContent = state.generated && !done
        ? 'Sentence ' + (state.currentIdx + 1) + ' of ' + state.sentences.length
        : '';
    }

    // Rep dots
    updateRepDots();

    // Controls
    if (playPauseBtn) {
      playPauseBtn.textContent = state.isPlaying ? '⏸' : '▶';
      playPauseBtn.disabled    = !state.generated || done;
    }
    if (prevBtn) prevBtn.disabled = !state.generated || state.currentIdx === 0;
    if (nextBtn) nextBtn.disabled = !state.generated || done;

    if (doneMsg) doneMsg.classList.toggle('visible', done);
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

  function audioUrl() {
    var s = state.sentences[state.currentIdx];
    if (!s) return null;
    return '/api/shadowing/audio/' + state.sessionId + '/' + s.filename;
  }

  function skipToNext() {
    if (state._pauseTimer) { clearTimeout(state._pauseTimer); state._pauseTimer = null; }
    state.isPlaying = false;
    state.currentRep = 1;
    state.currentIdx++;
    updateUI();
    if (!isDone()) setTimeout(playNow, 200);
  }

  function playNow() {
    var url = audioUrl();
    if (!url) { skipToNext(); return; }
    audio.src = url;
    audio.load();
    if (speedSlider) audio.playbackRate = parseFloat(speedSlider.value);
    state.isPlaying = true;
    updateUI();
    audio.play().catch(function (e) {
      console.warn('Audio play failed:', e);
      skipToNext();
    });
  }

  audio.addEventListener('error', function () {
    console.warn('Audio load error, skipping sentence', state.currentIdx);
    skipToNext();
  });

  function pause() {
    audio.pause();
    if (state._pauseTimer) { clearTimeout(state._pauseTimer); state._pauseTimer = null; }
    state.isPlaying = false;
    updateUI();
  }

  function wordCount(text) {
    return (text || '').trim().split(/\s+/).filter(Boolean).length;
  }

  function pauseThenPlay(nextAction) {
    var sentence = state.sentences[state.currentIdx];
    var words    = sentence ? wordCount(sentence.text) : 0;
    var ms       = Math.round(state.pausePerWord * words * 1000);
    if (ms <= 0) { nextAction(); return; }

    // Show countdown in rep indicator area
    var remaining = Math.ceil(ms / 1000);
    var startTime = Date.now();

    function tick() {
      var elapsed = Date.now() - startTime;
      var left = Math.ceil((ms - elapsed) / 1000);
      if (left !== remaining) {
        remaining = left;
        if (repIndicator) {
          var dots = repIndicator.innerHTML;
          repIndicator.innerHTML = dots.replace(/\s*⏳.*$/, '') +
            (remaining > 0 ? '&nbsp; ⏳ ' + remaining + 's' : '');
        }
      }
    }

    var tickInterval = setInterval(tick, 250);
    state._pauseTimer = setTimeout(function () {
      clearInterval(tickInterval);
      nextAction();
    }, ms);
  }

  audio.addEventListener('ended', function () {
    if (state.currentRep < state.reps) {
      // More reps of the same sentence — pause then play again (stay on same sentence)
      state.currentRep++;
      updateUI();
      pauseThenPlay(playNow);
    } else {
      // All reps done — pause while still showing this sentence, then advance
      state.currentRep = 1;
      updateUI(); // stay on current sentence during pause
      var nextIdx = state.currentIdx + 1;
      if (nextIdx < state.sentences.length) {
        pauseThenPlay(function () {
          state.currentIdx = nextIdx;
          updateUI();
          playNow();
        });
      } else {
        // Last sentence finished — pause, then mark done
        pauseThenPlay(function () {
          state.currentIdx = nextIdx;
          updateUI();
        });
      }
    }
  });

  if (playPauseBtn) {
    playPauseBtn.addEventListener('click', function () {
      if (state.isPlaying) { pause(); } else { playNow(); }
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (!state.generated) return;
      pause();
      if (state.currentIdx > 0) state.currentIdx--;
      state.currentRep = 1;
      updateUI();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      if (!state.generated) return;
      pause();
      state.currentRep = 1;
      state.currentIdx++;
      updateUI();
    });
  }

  updateUI();
})();
