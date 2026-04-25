/* Video Preview Page */
(function () {
  'use strict';

  // ── Session data from localStorage ─────────────────────────────────
  var _data = null;
  try { _data = JSON.parse(localStorage.getItem('celpip_shadow_json') || 'null'); } catch(e) {}

  // ── Persisted preview settings ───────────────────────────────────────
  var _savedSettings = {};
  try { _savedSettings = JSON.parse(localStorage.getItem('celpip_preview_settings') || '{}'); } catch(e) {}

  function _saveSettings() {
    try {
      localStorage.setItem('celpip_preview_settings', JSON.stringify({
        fontScales:       state.fontScales,
        seeds:            state.seeds,
        thumbSeed:        state.thumbSeed,
        thumbColor:       state.thumbColor,
        thumbFontScale:   state.thumbFontScale,
        voice:            voiceSel ? voiceSel.value : null,
      }));
    } catch(e) {}
  }

  if (!_data || !_data.answer) {
    document.querySelector('.vp-viewer').innerHTML =
      '<div style="color:#8890aa;font-size:14px;text-align:center">' +
      'No session loaded. Go back to the Studio, load a JSON file, then click Preview Video.' +
      '</div>';
  }

  // ── State ────────────────────────────────────────────────────────────
  var state = {
    psid:             null,
    section:          'thumb',
    slide:            0,
    counts:           { 1: 2, 2: 2, 3: 2, 4: 2, 5: 2 },
    seeds:            {},
    fontScales:       { 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0 },
    thumbSeed:        null,
    thumbColor:       null,   // null = auto (band-based)
    thumbFontScale:   1.0,
    loading:          false,
  };

  var frameEl     = document.getElementById('vpFrame');
  var loadingEl   = document.getElementById('vpLoading');
  var errorEl     = document.getElementById('vpError');
  var slideInfoEl = document.getElementById('slideInfo');
  var dotsEl      = document.getElementById('vpDots');
  var prevBtn     = document.getElementById('prevBtn');
  var nextBtn     = document.getElementById('nextBtn');
  var voiceSel    = document.getElementById('vpVoiceSelect');
  if (voiceSel) voiceSel.addEventListener('change', function () { _saveSettings(); });

  // ── Init: POST session data to server ────────────────────────────────
  function init() {
    if (!_data) return;

    // Restore persisted settings
    if (_savedSettings.fontScales)       state.fontScales       = _savedSettings.fontScales;
    if (_savedSettings.seeds)            state.seeds            = _savedSettings.seeds;
    if (_savedSettings.thumbSeed !== undefined)      state.thumbSeed      = _savedSettings.thumbSeed;
    if (_savedSettings.thumbColor !== undefined)     state.thumbColor     = _savedSettings.thumbColor;
    if (_savedSettings.thumbFontScale !== undefined) state.thumbFontScale = _savedSettings.thumbFontScale;
    if (_savedSettings.voice && voiceSel) voiceSel.value = _savedSettings.voice;
    updateScaleDisplay();
    _updateSwatches();
    // Apply initial thumb tab UI state
    var navbar  = document.querySelector('.vp-navbar');
    var toolbar = document.getElementById('vpThumbToolbar');
    if (navbar)  navbar.style.visibility = 'hidden';
    if (toolbar) toolbar.classList.remove('hidden');

    var sessionDir = localStorage.getItem('celpip_session_dir') || '';
    var task_num   = parseInt(localStorage.getItem('celpip_task_num') || '1');
    var band       = localStorage.getItem('celpip_band') || '7_8';

    fetch('/api/preview/init', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question:    _data.question || '',
        answer:      _data.answer   || '',
        vocab:       _data.vocabulary || [],
        task_num:    _data.task_num || task_num || 1,
        band:        _data.band     || band,
        category:    _data.category || '',
        title:       _data.title    || '',
        session_dir: sessionDir,
        seeds:       state.seeds,
        font_scales: state.fontScales,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.error) { showError(res.error); return; }
        state.psid = res.psid;
        loadCounts().then(function () { loadFrame(); });
      })
      .catch(function (e) { showError('Init failed: ' + e); });
  }

  function loadCounts() {
    return fetch('/api/preview/section-count?psid=' + state.psid)
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.counts) state.counts = res.counts;
        if (res.seeds)  state.seeds  = res.seeds;
        updateScaleDisplay();
        updateDots();
        _saveSettings();
      });
  }

  // ── Frame loading ─────────────────────────────────────────────────────
  function loadFrame() {
    if (!state.psid) return;
    state.loading = true;
    loadingEl.style.display = 'block';
    frameEl.classList.add('hidden');
    errorEl.classList.add('hidden');

    var url;
    if (state.section === 'thumb') {
      var params = new URLSearchParams({ psid: state.psid });
      if (state.thumbSeed !== null) params.set('seed', state.thumbSeed);
      if (state.thumbColor) params.set('color_theme', state.thumbColor);
      params.set('thumb_font_scale', state.thumbFontScale);
      params.set('_t', Date.now());
      url = '/api/preview/thumbnail?' + params.toString();
    } else {
      var params = new URLSearchParams({
        psid:       state.psid,
        section:    state.section,
        slide:      state.slide,
        seed:       state.seeds[state.section] || 0,
        font_scale: state.fontScales[state.section] || 1.0,
      });
      url = '/api/preview/frame?' + params.toString() + '&_t=' + Date.now();
    }

    var img = new Image();
    img.onload = function () {
      frameEl.src = url;
      frameEl.classList.remove('hidden');
      loadingEl.style.display = 'none';
      state.loading = false;
      updateControls();
    };
    img.onerror = function () {
      loadingEl.style.display = 'none';
      errorEl.classList.remove('hidden');
      state.loading = false;
    };
    img.src = url;
  }

  function showError(msg) {
    loadingEl.style.display = 'none';
    errorEl.classList.remove('hidden');
    errorEl.textContent = msg;
  }

  // ── Navigation ────────────────────────────────────────────────────────
  function goSection(n) {
    state.section = n;
    state.slide   = 0;
    document.querySelectorAll('.vp-tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.section == String(n));
    });
    var isThumb = n === 'thumb';
    var navbar   = document.querySelector('.vp-navbar');
    var toolbar  = document.getElementById('vpThumbToolbar');
    if (navbar)  navbar.style.visibility = isThumb ? 'hidden' : '';
    if (toolbar) toolbar.classList.toggle('hidden', !isThumb);
    updateScaleDisplay();
    loadFrame();
    updateDots();
  }

  function goSlide(delta) {
    var count = state.counts[state.section] || 1;
    var next  = state.slide + delta;
    if (next < 0 || next >= count) return;
    state.slide = next;
    loadFrame();
    updateDots();
  }

  function goSlideAbs(idx) {
    var count = state.counts[state.section] || 1;
    if (idx < 0 || idx >= count) return;
    state.slide = idx;
    loadFrame();
    updateDots();
  }

  function changeFontScale(delta) {
    if (state.section === 'thumb') {
      state.thumbFontScale = Math.round(Math.max(0.5, Math.min(2.0, state.thumbFontScale + delta)) * 100) / 100;
    } else {
      var cur = state.fontScales[state.section] || 1.0;
      state.fontScales[state.section] = Math.round(Math.max(0.5, Math.min(2.0, cur + delta)) * 100) / 100;
    }
    updateScaleDisplay();
    _saveSettings();
    loadFrame();
  }

  function updateScaleDisplay() {
    var el  = document.getElementById('fontScaleVal');
    var val = state.section === 'thumb'
      ? state.thumbFontScale
      : (state.fontScales[state.section] || 1.0);
    if (el) el.textContent = Math.round(val * 100) + '%';
  }

  function randomize() {
    if (!state.psid) return;
    if (state.section === 'thumb') {
      fetch('/api/preview/thumbnail-randomize', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ psid: state.psid }),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.seed !== undefined) {
            state.thumbSeed = res.seed;
            _saveSettings();
            loadFrame();
          }
        });
    } else {
      fetch('/api/preview/randomize', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ psid: state.psid, section: state.section }),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.seed !== undefined) {
            state.seeds[state.section] = res.seed;
            _saveSettings();
            loadFrame();
          }
        });
    }
  }

  // ── Thumbnail color ───────────────────────────────────────────────────
  function changeThumbColor(theme) {
    state.thumbColor = theme || null;
    _updateSwatches();
    _saveSettings();
    if (state.section === 'thumb') loadFrame();
  }

  function _updateSwatches() {
    document.querySelectorAll('.vp-swatch').forEach(function (sw) {
      var c = sw.dataset.color || '';
      sw.classList.toggle('active', (c === (state.thumbColor || '')));
    });
  }

  // Wire swatch clicks
  document.querySelectorAll('.vp-swatch').forEach(function (sw) {
    sw.addEventListener('click', function () { changeThumbColor(sw.dataset.color || null); });
  });

  // ── UI updates ────────────────────────────────────────────────────────
  function updateControls() {
    var count = state.counts[state.section] || 1;
    if (slideInfoEl)
      slideInfoEl.textContent = 'Slide ' + (state.slide + 1) + ' / ' + count;
    if (prevBtn) prevBtn.disabled = state.slide === 0;
    if (nextBtn) nextBtn.disabled = state.slide >= count - 1;
  }

  function updateDots() {
    if (!dotsEl) return;
    var count = state.counts[state.section] || 1;
    dotsEl.innerHTML = '';
    var maxDots = 30;
    var step = count <= maxDots ? 1 : Math.ceil(count / maxDots);
    for (var i = 0; i < count; i += step) {
      var dot = document.createElement('div');
      dot.className = 'vp-dot' + (i === state.slide ? ' active' : '');
      dot.dataset.idx = i;
      (function (idx) {
        dot.addEventListener('click', function () { goSlideAbs(idx); });
      })(i);
      dotsEl.appendChild(dot);
    }
    updateControls();
  }

  // ── Keyboard shortcuts ────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    switch (e.key) {
      case '1': goSection(1); break;
      case '2': goSection(2); break;
      case '3': goSection(3); break;
      case '4': goSection(4); break;
      case '5': goSection(5); break;
      case '0': goSection('thumb'); break;
      case '.': randomize(); break;
      case 'ArrowLeft':  goSlide(-1); break;
      case 'ArrowRight': goSlide(1);  break;
      case 'ArrowUp':   e.preventDefault(); changeFontScale(0.1);  break;
      case 'ArrowDown': e.preventDefault(); changeFontScale(-0.1); break;
    }
  });

  // ── Button bindings ───────────────────────────────────────────────────
  document.querySelectorAll('.vp-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      var s = tab.dataset.section;
      goSection(s === 'thumb' ? 'thumb' : parseInt(s));
    });
  });

  if (prevBtn) prevBtn.addEventListener('click', function () { goSlide(-1); });
  if (nextBtn) nextBtn.addEventListener('click', function () { goSlide(1); });

  var randomizeBtn = document.getElementById('randomizeBtn');
  if (randomizeBtn) randomizeBtn.addEventListener('click', randomize);

  var fontScaleUpBtn   = document.getElementById('fontScaleUp');
  var fontScaleDownBtn = document.getElementById('fontScaleDown');
  if (fontScaleUpBtn)   fontScaleUpBtn.addEventListener('click',   function () { changeFontScale(0.1); });
  if (fontScaleDownBtn) fontScaleDownBtn.addEventListener('click', function () { changeFontScale(-0.1); });

  // ── Generate Video (non-blocking floating toast) ────────────────────────
  var toast        = document.getElementById('genToast');
  var genLoadingEl = document.getElementById('genLoading');
  var genSuccessEl = document.getElementById('genSuccess');
  var genErrorEl   = document.getElementById('genError');
  var genProgressBar = document.getElementById('genProgressBar');
  var genStepEl    = document.getElementById('genStep');
  var _currentJobId = null;

  function _dismissToast() { if (toast) toast.classList.add('hidden'); }

  document.getElementById('genToastClose') &&
    document.getElementById('genToastClose').addEventListener('click', _dismissToast);
  document.getElementById('closeGenBtn') &&
    document.getElementById('closeGenBtn').addEventListener('click', _dismissToast);
  document.getElementById('closeGenErrBtn') &&
    document.getElementById('closeGenErrBtn').addEventListener('click', _dismissToast);

  var generateBtn = document.getElementById('generateBtn');
  if (generateBtn) {
    generateBtn.addEventListener('click', function () {
      if (!_data) { alert('No session loaded.'); return; }
      startGenerate();
    });
  }

  function startGenerate() {
    // Show toast (non-blocking — user can keep browsing sections)
    if (toast) toast.classList.remove('hidden');
    genLoadingEl.style.display = 'block';
    genSuccessEl.style.display = 'none';
    genErrorEl.style.display   = 'none';
    if (genProgressBar) genProgressBar.style.width = '0%';
    if (genStepEl)      genStepEl.textContent = 'Queuing…';
    var titleEl = document.getElementById('genTitle');
    if (titleEl) titleEl.textContent = '▶ Generating Video';

    var sessionDir = localStorage.getItem('celpip_session_dir') || '';

    fetch('/generate-video', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question:     _data.question    || '',
        answer:       _data.answer      || '',
        vocab:        _data.vocabulary  || [],
        task_num:     _data.task_num    || 1,
        band:         _data.band        || '7_8',
        category:     _data.category    || 'General',
        title:        _data.title       || '',
        voice:             voiceSel ? voiceSel.value : 'af_heart',
        seeds:             state.seeds,
        font_scales:       state.fontScales,
        thumb_seed:        state.thumbSeed,
        thumb_color:       state.thumbColor || null,
        thumb_font_scale:  state.thumbFontScale,
        session_dir:       sessionDir,
        db_record_id:      _data._db_record_id || null,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.error) { showGenError(res.error); return; }
        _currentJobId = res.job_id;
        var pos = res.queue_position;
        if (genStepEl && pos > 1) genStepEl.textContent = 'Position ' + pos + ' in queue…';
        pollJob(res.job_id);
      })
      .catch(function (e) { showGenError('Network error: ' + e); });
  }

  function pollJob(jobId) {
    var interval = setInterval(function () {
      fetch('/status/' + jobId)
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var isQueued = j.status === 'queued';
          if (genProgressBar) genProgressBar.style.width = (isQueued ? 0 : (j.progress || 0)) + '%';
          if (genStepEl) {
            if (isQueued && j.queue_pos) {
              genStepEl.textContent = 'Position ' + j.queue_pos + ' in queue…';
            } else {
              genStepEl.textContent = j.step || 'Working…';
            }
          }
          if (j.done) {
            clearInterval(interval);
            if (j.error) {
              showGenError(j.error);
            } else {
              genLoadingEl.style.display = 'none';
              genSuccessEl.style.display = 'block';
              if (genProgressBar) genProgressBar.style.width = '100%';
              var titleEl = document.getElementById('genTitle');
              if (titleEl) titleEl.textContent = '▶ Video Ready';
              document.getElementById('genSuccessMsg').textContent =
                j.output_path || '';
              // Wire up "Open" button
              var openBtn = document.getElementById('genOpenBtn');
              if (openBtn) {
                openBtn.onclick = function () {
                  fetch('/api/jobs/' + jobId + '/open-video', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (res) { if (res.error) alert(res.error); })
                    .catch(function () {});
                };
              }
              // Wire up "Open Folder" button
              var folderBtn = document.getElementById('genFolderBtn');
              if (folderBtn) {
                folderBtn.onclick = function () {
                  fetch('/api/jobs/' + jobId + '/open-folder', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (res) { if (res.error) alert(res.error); })
                    .catch(function () {});
                };
              }
              // Wire up "YT Info" button
              var ytInfoBtn = document.getElementById('genYTInfoBtn');
              if (ytInfoBtn) {
                ytInfoBtn.onclick = function () { openVPYTInfo(); };
              }
            }
          }
        })
        .catch(function () { clearInterval(interval); });
    }, 1500);
  }

  function showGenError(msg) {
    genLoadingEl.style.display = 'none';
    genErrorEl.style.display   = 'block';
    document.getElementById('genErrorMsg').textContent = msg;
    var titleEl = document.getElementById('genTitle');
    if (titleEl) titleEl.textContent = '▶ Generation Failed';
  }

  // ── Video Preview YT Info modal ───────────────────────────────────────
  var vpYTOverlay = document.getElementById('vpYTInfoOverlay');
  var vpYTLoading = document.getElementById('vpYTInfoLoading');
  var vpYTBody    = document.getElementById('vpYTInfoBody');

  function openVPYTInfo() {
    if (!vpYTOverlay || !_data) return;
    vpYTOverlay.classList.remove('hidden');
    vpYTLoading.classList.remove('hidden');
    vpYTBody.classList.add('hidden');

    // Use DB record if available, else raw endpoint
    var recordId = _data._db_record_id;
    var p;
    if (recordId) {
      p = fetch('/api/sessions/' + recordId + '/youtube-meta').then(function(r){return r.json();});
    } else {
      p = fetch('/api/youtube-meta/raw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_num: _data.task_num || 1,
          band:     _data.band || '7_8',
          category: _data.category || '',
          title:    _data.title || '',
          question: _data.question || '',
          answer:   _data.answer || '',
          vocab:    _data.vocabulary || [],
        }),
      }).then(function(r){return r.json();});
    }

    p.then(function(data) {
      if (data.error) { alert('Error: ' + data.error); vpYTOverlay.classList.add('hidden'); return; }
      document.getElementById('vpYTInfoTitle').textContent = data.title;
      document.getElementById('vpYTInfoDesc').value        = data.description;
      document.getElementById('vpYTInfoTags').textContent  = data.tags;
      vpYTLoading.classList.add('hidden');
      vpYTBody.classList.remove('hidden');
    }).catch(function(e) { alert('Error: ' + e); vpYTOverlay.classList.add('hidden'); });
  }

  function closeVPYTInfo() { if (vpYTOverlay) vpYTOverlay.classList.add('hidden'); }

  document.getElementById('vpYTInfoClose')   && document.getElementById('vpYTInfoClose').addEventListener('click',   closeVPYTInfo);
  document.getElementById('vpYTInfoDismiss') && document.getElementById('vpYTInfoDismiss').addEventListener('click', closeVPYTInfo);
  vpYTOverlay && vpYTOverlay.addEventListener('click', function(e) { if (e.target === vpYTOverlay) closeVPYTInfo(); });

  // YT Info button in topbar
  var vpYTBtn = document.getElementById('vpYTInfoBtn');
  if (vpYTBtn) vpYTBtn.addEventListener('click', openVPYTInfo);

  // Copy buttons (shared handler for both this page and browse page)
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.ytinfo-copy-btn');
    if (!btn) return;
    var targetId = btn.dataset.target;
    var el = document.getElementById(targetId);
    if (!el) return;
    var text = el.tagName === 'TEXTAREA' ? el.value : el.textContent;
    navigator.clipboard.writeText(text).then(function() {
      var orig = btn.textContent;
      btn.textContent = 'Copied!';
      btn.classList.add('ytinfo-copy-ok');
      setTimeout(function() { btn.textContent = orig; btn.classList.remove('ytinfo-copy-ok'); }, 1800);
    }).catch(function() { el.select && el.select(); document.execCommand('copy'); });
  });

  // ── Start ─────────────────────────────────────────────────────────────
  init();
})();
