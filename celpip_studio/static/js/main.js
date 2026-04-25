/* CELPIP Practice Studio — main.js */
(function () {
  'use strict';

  function $(s, c) { return (c || document).querySelector(s); }

  function fetchJSON(url, options) {
    return fetch(url, options).then(function (r) {
      var ct = r.headers.get('content-type') || '';
      if (!ct.includes('application/json')) {
        return r.text().then(function (body) {
          var hint = r.status === 404 ? ' (restart the server — new route not loaded yet)' : '';
          throw new Error('HTTP ' + r.status + hint);
        });
      }
      return r.json();
    });
  }

  /* ── Persistent Settings (localStorage) ──────────────────────────────── */
  var SETTINGS_KEY = 'celpip_settings';

  function loadSettings() {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch(e) { return {}; }
  }

  function saveSettings() {
    var s = {
      section:  ($('#section') || {}).value  || 'speaking',
      task_num: ($('#task_num') || {}).value || '1',
      band:     (document.querySelector('input[name="band"]:checked') || {}).value || '7_8',
    };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
    flashSaved();
  }

  function applySettings() {
    var s = loadSettings();
    if (s.section  && $('#section'))  $('#section').value = s.section;
    if (s.task_num && $('#task_num')) $('#task_num').value = s.task_num;
    if (s.band) {
      var r = document.querySelector('input[name="band"][value="' + s.band + '"]');
      if (r) r.checked = true;
    }
  }

  function flashSaved() {
    var el = $('#settingSaved');
    if (!el) return;
    el.classList.add('visible');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove('visible'); }, 1500);
  }

  applySettings();

  ['change'].forEach(function(ev) {
    ['#section', '#task_num'].forEach(function(sel) {
      var el = $(sel);
      if (el) el.addEventListener(ev, saveSettings);
    });
    document.querySelectorAll('input[name="band"]').forEach(function(r) {
      r.addEventListener(ev, saveSettings);
    });
  });

  /* ── JSON Hint Toggle ─────────────────────────────────────────────────── */
  var hintToggle = $('#hintToggle');
  var jsonHint   = $('#jsonHint');
  if (hintToggle && jsonHint) {
    hintToggle.addEventListener('click', function () {
      var hidden = jsonHint.classList.toggle('hidden');
      hintToggle.textContent = hidden ? 'See JSON format' : 'Hide format';
    });
  }

  /* ── JSON File Drop Zone ──────────────────────────────────────────────── */
  var jsonDropZone   = $('#jsonDropZone');
  var jsonBrowseBtn  = $('#jsonBrowseBtn');
  var jsonFileInput  = $('#jsonFileInput');
  var jsonPreview    = $('#jsonPreview');
  var jsonErrorEl    = $('#jsonError');
  var removeJsonBtn  = $('#removeJsonBtn');

  var jsonPasteArea = $('#jsonPasteArea');
  var _parsedJson = null;

  function showJsonError(msg) {
    if (jsonErrorEl) { jsonErrorEl.textContent = msg; jsonErrorEl.classList.remove('hidden'); }
  }
  function clearJsonError() {
    if (jsonErrorEl) { jsonErrorEl.textContent = ''; jsonErrorEl.classList.add('hidden'); }
  }

  function parseAndRender(text, sourceName) {
    try {
      var data = JSON.parse(text);
      var missing = [];
      if (!data.category)               missing.push('category');
      if (!data.question)               missing.push('question');
      if (!data.answer)                 missing.push('answer');
      if (!Array.isArray(data.vocabulary)) missing.push('vocabulary');
      if (missing.length) { showJsonError('Missing fields: ' + missing.join(', ')); return; }
      _parsedJson = data;

      // Apply band from JSON if present
      if (data.band) {
        var r = document.querySelector('input[name="band"][value="' + data.band + '"]');
        if (r) { r.checked = true; saveSettings(); }
      }

      renderJsonPreview(sourceName, data);
    } catch(ex) {
      showJsonError('Invalid JSON: ' + ex.message);
    }
  }

  if (jsonPasteArea) {
    var _pasteTimer = null;
    jsonPasteArea.addEventListener('input', function () {
      clearTimeout(_pasteTimer);
      var txt = jsonPasteArea.value.trim();
      if (!txt) { clearJsonError(); return; }
      _pasteTimer = setTimeout(function () { parseAndRender(txt, 'pasted content'); }, 400);
    });
  }

  function handleJsonFile(file) {
    if (!file) return;
    if (!file.name.endsWith('.json')) { showJsonError('Please select a .json file.'); return; }
    clearJsonError();
    var reader = new FileReader();
    reader.onload = function (e) { parseAndRender(e.target.result, file.name); };
    reader.readAsText(file);
  }

  function renderJsonPreview(filename, data) {
    $('#jsonFilenameLabel').textContent = filename;
    $('#pvCategory').textContent = data.category;
    $('#pvQuestion').textContent = data.question.slice(0, 120) + (data.question.length > 120 ? '…' : '');
    $('#pvAnswer').textContent   = data.answer.slice(0, 120)   + (data.answer.length > 120   ? '…' : '');
    var vcount = data.vocabulary.length;
    var vwords = data.vocabulary.slice(0, 4).map(function(v){ return v.word; }).join(', ');
    $('#pvVocab').textContent = vcount + ' item' + (vcount !== 1 ? 's' : '') +
                                (vcount > 0 ? ' — ' + vwords + (vcount > 4 ? '…' : '') : '');
    jsonDropZone.classList.add('hidden');
    jsonPreview.classList.remove('hidden');

    // Store for shadowing and show button
    // Store for shadowing page (also store task_num from settings for session dir creation)
    var s = loadSettings();
    var enriched = Object.assign({}, data, {
      task_num: s.task_num || '1',
      band:     data.band  || s.band || '7_8'   // fallback to UI selection if JSON omits band
    });
    try { localStorage.setItem('celpip_shadow_json', JSON.stringify(enriched)); } catch(e) {}
    // Clear stale session dir when new JSON is loaded
    try { localStorage.removeItem('celpip_session_dir'); } catch(e) {}
    var _shadowBtnEl = $('#shadowBtn');
    if (_shadowBtnEl) _shadowBtnEl.classList.remove('hidden');
  }

  function resetJson() {
    _parsedJson = null;
    jsonDropZone.classList.remove('hidden');
    jsonPreview.classList.add('hidden');
    clearJsonError();
    if (jsonFileInput) jsonFileInput.value = '';
    if (jsonPasteArea) jsonPasteArea.value = '';
    try { localStorage.removeItem('celpip_shadow_json'); } catch(e) {}
    try { localStorage.removeItem('celpip_session_dir'); } catch(e) {}
    var _shadowBtnEl2 = $('#shadowBtn');
    if (_shadowBtnEl2) _shadowBtnEl2.classList.add('hidden');
  }

  if (jsonDropZone) {
    jsonDropZone.addEventListener('dragover',  function(e){ e.preventDefault(); jsonDropZone.classList.add('dz-over'); });
    jsonDropZone.addEventListener('dragleave', function(){ jsonDropZone.classList.remove('dz-over'); });
    jsonDropZone.addEventListener('drop', function(e){
      e.preventDefault(); jsonDropZone.classList.remove('dz-over');
      handleJsonFile(e.dataTransfer.files[0]);
    });
    jsonDropZone.addEventListener('click', function(e){
      if (e.target === jsonBrowseBtn || (jsonBrowseBtn && jsonBrowseBtn.contains(e.target))) return;
      jsonFileInput && jsonFileInput.click();
    });
  }
  if (jsonBrowseBtn) jsonBrowseBtn.addEventListener('click', function(e){ e.stopPropagation(); jsonFileInput && jsonFileInput.click(); });
  if (jsonFileInput) jsonFileInput.addEventListener('change', function(){ handleJsonFile(jsonFileInput.files[0]); });
  if (removeJsonBtn) removeJsonBtn.addEventListener('click', resetJson);

  /* ── Kokoro Voice Grid ────────────────────────────────────────────────── */
  var voiceGrid       = $('#voiceGrid');
  var previewVoiceBtn = $('#previewVoiceBtn');
  var previewTextEl   = $('#previewText');
  var voiceAudioEl    = $('#voicePreviewAudio');
  var kokoroStatus    = $('#kokoroStatus');
  var _selectedVoice  = 'af_heart';

  fetch('/api/kokoro/voices')
    .then(function(r){ return r.json(); })
    .then(function(res){
      _selectedVoice = res.default_voice || 'af_heart';
      if (kokoroStatus) kokoroStatus.textContent = res.available ? 'Ready' : 'Not installed';
      if (!voiceGrid) return;
      voiceGrid.innerHTML = '';
      Object.keys(res.voices).forEach(function(key) {
        var label = res.voices[key];
        var parts = label.match(/^(.*?)\s*\((.*?)\)$/) || ['', label, ''];
        var card  = document.createElement('button');
        card.type = 'button';
        card.className = 'voice-card' + (key === _selectedVoice ? ' active' : '');
        card.innerHTML =
          '<div class="voice-card-name">' + parts[1] + '</div>' +
          '<div class="voice-card-sub">'  + parts[2] + '</div>';
        card.addEventListener('click', function() {
          _selectedVoice = key;
          document.querySelectorAll('.voice-card').forEach(function(c){ c.classList.remove('active'); });
          card.classList.add('active');
          try { localStorage.setItem('celpip_voice', key); } catch(e) {}
        });
        voiceGrid.appendChild(card);
      });
      // Restore saved voice
      try {
        var saved = localStorage.getItem('celpip_voice');
        if (saved && res.voices[saved]) {
          _selectedVoice = saved;
          document.querySelectorAll('.voice-card').forEach(function(c){ c.classList.remove('active'); });
          var cards = document.querySelectorAll('.voice-card');
          var keys  = Object.keys(res.voices);
          var idx   = keys.indexOf(saved);
          if (idx >= 0 && cards[idx]) cards[idx].classList.add('active');
        }
      } catch(e) {}
    })
    .catch(function(){ if (kokoroStatus) kokoroStatus.textContent = 'Error loading voices'; });

  if (previewVoiceBtn) {
    previewVoiceBtn.addEventListener('click', function() {
      var text = (previewTextEl ? previewTextEl.value : '').trim();
      if (!text) return;
      previewVoiceBtn.disabled = true;
      previewVoiceBtn.textContent = '…';
      fetch('/api/kokoro/preview', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text: text, voice: _selectedVoice }),
      })
        .then(function(r){
          if (!r.ok) throw new Error('TTS failed');
          return r.blob();
        })
        .then(function(blob){
          if (voiceAudioEl) {
            voiceAudioEl.src = URL.createObjectURL(blob);
            voiceAudioEl.play();
          }
        })
        .catch(function(e){ alert('Voice preview failed: ' + e); })
        .finally(function(){
          previewVoiceBtn.disabled = false;
          previewVoiceBtn.textContent = '▶ Preview';
        });
    });
  }

  /* ── Generate Video (navigate to preview page) ────────────────────────── */
  var generateBtn    = $('#generateBtn');
  var previewVideoBtn = $('#previewVideoBtn');
  var formError      = $('#formError');

  function showError(msg) { if (formError){ formError.textContent = msg; formError.classList.remove('hidden'); } }
  function hideError()    { if (formError){ formError.textContent = ''; formError.classList.add('hidden'); } }

  function _saveForVideo() {
    var s = loadSettings();
    var enriched = Object.assign({}, _parsedJson, {
      task_num: parseInt(s.task_num || '1'),
      band:     _parsedJson.band || s.band || '7_8',
    });
    try { localStorage.setItem('celpip_shadow_json', JSON.stringify(enriched)); } catch(e) {}
    try { localStorage.setItem('celpip_task_num', s.task_num || '1'); } catch(e) {}
    try { localStorage.setItem('celpip_band', _parsedJson.band || s.band || '7_8'); } catch(e) {}
  }

  if (previewVideoBtn) {
    previewVideoBtn.addEventListener('click', function() {
      hideError();
      if (!_parsedJson) { showError('Please load a JSON file first.'); return; }
      _saveForVideo();
      window.location.href = '/video-preview';
    });
  }

  if (generateBtn) {
    generateBtn.addEventListener('click', function() {
      hideError();
      if (!_parsedJson) { showError('Please load a JSON file first.'); return; }
      _saveForVideo();
      window.location.href = '/video-preview';
    });
  }

  /* ── Practice Shadowing — prepare then show modal ─────────────────────── */
  var shadowBtn    = $('#shadowBtn');
  var prepOverlay  = $('#prepOverlay');
  var prepLoading  = $('#prepLoading');
  var prepSuccess  = $('#prepSuccess');
  var prepError    = $('#prepError');
  var prepTitle    = $('#prepTitle');
  var prepLoadMsg  = $('#prepLoadingMsg');
  var prepFileList = $('#prepFileList');
  var prepErrMsg   = $('#prepErrorMsg');
  var startBtn     = $('#startPracticingBtn');
  var closeBtn     = $('#closePrepBtn');
  var closeErrBtn  = $('#closePrepErrBtn');

  var _shadowSessionId  = null;
  var _shadowSessionDir = null;
  var _shadowSentences  = null;

  function showPrepModal() {
    if (!prepOverlay) return;
    prepOverlay.classList.remove('hidden');
    prepLoading.style.display = 'block';
    prepSuccess.style.display = 'none';
    prepError.style.display   = 'none';
    if (prepTitle) prepTitle.textContent = 'Preparing Practice Session…';
    if (prepLoadMsg) prepLoadMsg.textContent = 'Generating audio and PDF…';
  }

  function showPrepSuccess(res) {
    if (prepTitle) prepTitle.textContent = 'Files Ready';
    prepLoading.style.display = 'none';
    prepSuccess.style.display = 'block';
    if (prepFileList) {
      var html = '<strong>Session Folder</strong>' + res.session_dir;
      if (res.pdf_path) html += '<strong>PDF</strong>' + res.pdf_path;
      html += '<strong>Audio (' + res.audio_count + ' sentences)</strong>' + res.audio_dir;
      prepFileList.innerHTML = html;
    }
  }

  function showPrepError(msg) {
    if (prepTitle) prepTitle.textContent = 'Preparation Failed';
    prepLoading.style.display = 'none';
    prepError.style.display   = 'block';
    if (prepErrMsg) prepErrMsg.textContent = msg;
  }

  function closePrepModal() {
    if (prepOverlay) prepOverlay.classList.add('hidden');
  }

  if (closeBtn)    closeBtn.addEventListener('click', closePrepModal);
  if (closeErrBtn) closeErrBtn.addEventListener('click', closePrepModal);

  if (startBtn) {
    startBtn.addEventListener('click', function () {
      closePrepModal();
      window.location.href = '/shadowing';
    });
  }

  if (shadowBtn) {
    shadowBtn.addEventListener('click', function () {
      if (!_parsedJson) return;
      showPrepModal();
      shadowBtn.disabled = true;

      var s = loadSettings();
      var sessionDir = '';
      try { sessionDir = localStorage.getItem('celpip_session_dir') || ''; } catch(e) {}

      fetchJSON('/api/prepare-shadowing', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question:    _parsedJson.question,
          answer:      _parsedJson.answer,
          category:    _parsedJson.category,
          title:       _parsedJson.title     || '',
          vocab:       _parsedJson.vocabulary || [],
          task_num:    s.task_num || '1',
          band:        _parsedJson.band || s.band || '7_8',
          session_dir: sessionDir,
        }),
      })
        .then(function (res) {
          shadowBtn.disabled = false;
          if (res.error) { showPrepError(res.error); return; }

          _shadowSessionId  = res.session_id;
          _shadowSessionDir = res.session_dir;
          _shadowSentences  = res.sentences;

          try {
            localStorage.setItem('celpip_session_dir', res.session_dir);
            var enriched = Object.assign({}, _parsedJson, {
              task_num:   s.task_num || '1',
              _session_id: res.session_id,
            });
            localStorage.setItem('celpip_shadow_json', JSON.stringify(enriched));
            localStorage.setItem('celpip_shadow_sentences', JSON.stringify(res.sentences));
          } catch(e) {}

          showPrepSuccess(res);
        })
        .catch(function (err) {
          shadowBtn.disabled = false;
          showPrepError('Network error: ' + err);
        });
    });
  }

  /* ── Global queue badge ───────────────────────────────────────────────── */
  (function () {
    var badge     = document.getElementById('navQueueBadge');
    var countEl   = document.getElementById('navQueueCount');
    if (!badge || !countEl) return;
    function refreshBadge() {
      fetch('/api/queue')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var n = data.pending || 0;
          if (n > 0) {
            countEl.textContent = n;
            badge.classList.remove('hidden');
          } else {
            badge.classList.add('hidden');
          }
        })
        .catch(function () {});
    }
    refreshBadge();
    setInterval(refreshBadge, 4000);
  })();

})();
