/* Browse Sessions — with Publish Queue */
(function () {
  'use strict';

  function $(s) { return document.querySelector(s); }
  function $all(s) { return Array.from(document.querySelectorAll(s)); }

  var BAND_LABELS = { '7_8': 'Band 7–8', '9_10': 'Band 9–10', '11_12': 'Band 11–12' };

  /* ── Filter state ─────────────────────────────────────────────── */
  var filters = { band: '', part: '', category: '', publish_status: '' };
  var titleQuery = '';
  var _allSessions = [];

  function fetchJSON(url, opts) {
    return fetch(url, opts).then(function (r) {
      var ct = r.headers.get('content-type') || '';
      if (!ct.includes('application/json'))
        return r.text().then(function () { throw new Error('HTTP ' + r.status); });
      return r.json();
    });
  }

  /* ── Load sessions ────────────────────────────────────────────── */
  function load() {
    var params = new URLSearchParams();
    if (filters.band)           params.set('band',           filters.band);
    if (filters.part)           params.set('part',           filters.part);
    if (filters.category)       params.set('category',       filters.category);
    if (filters.publish_status) params.set('publish_status', filters.publish_status);

    fetchJSON('/api/sessions?' + params.toString())
      .then(function (data) {
        _allSessions = data.sessions;
        renderCategoryPills(data.filters.categories);
        renderCards(applyTitleSearch(_allSessions));
      })
      .catch(function (e) { console.error('Load error:', e); });
  }

  function applyTitleSearch(sessions) {
    var q = titleQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(function (s) {
      return (s.title || '').toLowerCase().includes(q) ||
             (s.question || '').toLowerCase().includes(q) ||
             (s.category || '').toLowerCase().includes(q);
    });
  }

  /* ── Filter pills ─────────────────────────────────────────────── */
  function bindPills(containerId, key) {
    var container = $('#' + containerId);
    if (!container) return;
    container.addEventListener('click', function (e) {
      var btn = e.target.closest('.fpill');
      if (!btn) return;
      $all('.fpill', container).forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      filters[key] = btn.dataset.val;
      if (key !== 'category') filters.category = '';
      load();
    });
  }

  bindPills('bandFilter',   'band');
  bindPills('partFilter',   'part');
  bindPills('statusFilter', 'publish_status');

  /* ── Title search ─────────────────────────────────────────────── */
  var titleSearchEl    = $('#titleSearch');
  var titleSearchClear = $('#titleSearchClear');

  if (titleSearchEl) {
    titleSearchEl.addEventListener('input', function () {
      titleQuery = this.value;
      if (titleSearchClear) titleSearchClear.style.display = titleQuery ? 'inline-flex' : 'none';
      renderCards(applyTitleSearch(_allSessions));
    });
  }
  if (titleSearchClear) {
    titleSearchClear.addEventListener('click', function () {
      titleQuery = '';
      if (titleSearchEl) titleSearchEl.value = '';
      titleSearchClear.style.display = 'none';
      renderCards(applyTitleSearch(_allSessions));
    });
  }

  /* ── Category search ──────────────────────────────────────────── */
  var _allCategories  = [];
  var catSearchEl     = $('#catSearch');
  var catDropdownEl   = $('#catDropdown');
  var catClearBtn     = $('#catClearBtn');

  function renderCategoryPills(cats) {
    _allCategories = cats;
    updateCatDropdown('');
  }

  function updateCatDropdown(query) {
    if (!catDropdownEl) return;
    var q = query.trim().toLowerCase();
    var filtered = q
      ? _allCategories.filter(function (c) { return c.toLowerCase().includes(q); })
      : _allCategories;

    catDropdownEl.innerHTML = '';
    if (!filtered.length) {
      catDropdownEl.innerHTML = '<div class="cat-no-results">No matches</div>';
    } else {
      filtered.forEach(function (cat) {
        var item = document.createElement('div');
        item.className = 'cat-item' + (cat === filters.category ? ' active' : '');
        item.textContent = cat;
        item.addEventListener('mousedown', function (e) {
          e.preventDefault();
          selectCategory(cat);
        });
        catDropdownEl.appendChild(item);
      });
    }
  }

  function selectCategory(cat) {
    filters.category = cat;
    if (catSearchEl) catSearchEl.value = cat;
    if (catDropdownEl) catDropdownEl.classList.add('hidden');
    if (catClearBtn) catClearBtn.style.display = cat ? 'inline-flex' : 'none';
    load();
  }

  if (catSearchEl) {
    catSearchEl.addEventListener('focus', function () {
      updateCatDropdown(this.value);
      if (catDropdownEl) catDropdownEl.classList.remove('hidden');
    });
    catSearchEl.addEventListener('input', function () {
      updateCatDropdown(this.value);
      if (catDropdownEl) catDropdownEl.classList.remove('hidden');
    });
    catSearchEl.addEventListener('blur', function () {
      setTimeout(function () {
        if (catDropdownEl) catDropdownEl.classList.add('hidden');
      }, 150);
    });
  }

  if (catClearBtn) {
    catClearBtn.addEventListener('click', function () {
      filters.category = '';
      if (catSearchEl) catSearchEl.value = '';
      catClearBtn.style.display = 'none';
      load();
    });
  }

  /* ── Publish status helpers ───────────────────────────────────── */
  var STATUS_LABEL = { waiting: 'Waiting', queued: 'Queued', published: 'Published' };
  var STATUS_CLASS = { waiting: 'badge-waiting', queued: 'badge-queued', published: 'badge-published' };

  function setPublishStatus(recordId, status, cardEl) {
    fetchJSON('/api/sessions/' + recordId + '/publish-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status }),
    })
      .then(function (res) {
        if (res.error) { alert('Error: ' + res.error); return; }
        // Update session in cache and re-render just this card
        _allSessions = _allSessions.map(function (s) {
          return s.id === recordId ? Object.assign({}, s, { publish_status: status }) : s;
        });
        // If a status filter is active, reload to properly hide/show
        if (filters.publish_status) {
          load();
        } else {
          renderCards(applyTitleSearch(_allSessions));
        }
      })
      .catch(function (e) { alert('Error: ' + e); });
  }

  /* ── YouTube upload from browse ───────────────────────────────── */
  var _activeUploads = {}; // recordId -> upload_id

  function startYouTubeUpload(recordId, cardEl) {
    fetchJSON('/api/youtube/status')
      .then(function (res) {
        if (!res.authenticated) {
          alert('YouTube not authenticated. Go to Settings → YouTube to connect.');
          return;
        }
        return fetchJSON('/api/youtube/upload/session/' + recordId, { method: 'POST' });
      })
      .then(function (res) {
        if (!res) return;
        if (res.error) {
          if (res.error === 'not_authenticated') {
            alert('YouTube not authenticated. Go to Settings → YouTube to connect.');
          } else {
            alert('Upload error: ' + res.error);
          }
          return;
        }
        var uploadId = res.upload_id;
        _activeUploads[recordId] = uploadId;
        pollUpload(recordId, uploadId, cardEl);
      })
      .catch(function (e) { alert('Upload error: ' + e); });
  }

  function pollUpload(recordId, uploadId, cardEl) {
    fetchJSON('/api/youtube/upload-status/' + uploadId)
      .then(function (u) {
        if (u.error && !u.done) { alert('Upload error: ' + u.error); delete _activeUploads[recordId]; return; }

        // Update progress badge on card
        var progEl = cardEl ? cardEl.querySelector('.upload-progress') : null;
        if (progEl) progEl.textContent = u.progress + '%';

        if (!u.done) {
          setTimeout(function () { pollUpload(recordId, uploadId, cardEl); }, 1200);
          return;
        }

        delete _activeUploads[recordId];
        if (u.error) {
          alert('Upload failed: ' + u.error);
          load();
          return;
        }
        // Success — db already set to 'published' by server; reload
        load();
      })
      .catch(function (e) { console.error('Poll error:', e); });
  }

  /* ── Cards ────────────────────────────────────────────────────── */
  function renderCards(sessions) {
    var grid  = $('#browseGrid');
    var empty = $('#browseEmpty');
    var count = $('#browseCount');
    if (!grid) return;

    $all('.session-card', grid).forEach(function (c) { c.remove(); });

    if (count) count.textContent = sessions.length + ' session' + (sessions.length !== 1 ? 's' : '');
    if (empty) empty.style.display = sessions.length ? 'none' : 'block';

    sessions.forEach(function (s) {
      var card = document.createElement('div');
      card.className = 'session-card';
      card.dataset.id = s.id;

      var bandLabel    = BAND_LABELS[s.band] || s.band;
      var date         = s.created_at ? s.created_at.slice(0, 10) : '';
      var hasPdf       = s.pdf_path   ? 'has-file' : '';
      var hasAudio     = s.audio_count > 0 ? 'has-file' : '';
      var hasVideo     = s.video_path  ? 'has-file' : '';
      var pubStatus    = s.publish_status || 'waiting';
      var statusCls    = STATUS_CLASS[pubStatus] || 'badge-waiting';
      var statusLabel  = STATUS_LABEL[pubStatus] || pubStatus;

      var ytLinkHtml = '';
      if (pubStatus === 'published' && s.youtube_url) {
        ytLinkHtml = '<a class="yt-published-link" href="' + _esc(s.youtube_url) + '" target="_blank">&#9654; YouTube</a>';
      }

      var isUploading = !!_activeUploads[s.id];

      card.innerHTML = [
        '<div class="card-top">',
          '<div class="card-title">' + _esc(s.title || s.category) + '</div>',
          '<div class="card-badges">',
            '<span class="badge badge-band">' + bandLabel + '</span>',
            '<span class="badge ' + statusCls + '">' + statusLabel + '</span>',
          '</div>',
        '</div>',
        '<div class="card-meta">',
          '<span>Part ' + s.part + '</span>',
          '<span class="card-meta-sep">·</span>',
          '<span>' + _esc(s.category) + '</span>',
          '<span class="card-meta-sep">·</span>',
          '<span>' + date + '</span>',
        '</div>',
        '<div class="card-q">' + _esc(s.question) + '</div>',
        '<div class="card-files">',
          '<span class="file-chip ' + hasPdf   + '">PDF</span>',
          '<span class="file-chip ' + hasAudio + '">' + (s.audio_count || 0) + ' audio</span>',
          '<span class="file-chip ' + hasVideo + '">Video</span>',
        '</div>',
        ytLinkHtml,
        '<div class="card-actions">',
          '<button class="btn-practice">&#127897; Practice</button>',
          s.video_path ? '<button class="btn-openvideo" title="Play video">&#9654;</button>' : '',
          s.video_path && pubStatus !== 'published'
            ? '<button class="btn-ytinfo" title="Get YouTube metadata">YT Info</button>'
            : '',
          // Queue / Unqueue / Upload buttons
          s.video_path && pubStatus === 'waiting'
            ? '<button class="btn-queue" title="Add to upload queue">+ Queue</button>'
            : '',
          pubStatus === 'queued' && !isUploading
            ? '<button class="btn-unqueue" title="Remove from queue">&#8722; Unqueue</button>'
            : '',
          pubStatus === 'queued' && !isUploading
            ? '<button class="btn-upload" title="Upload to YouTube now">&#8679; Upload</button>'
            : '',
          isUploading
            ? '<span class="upload-progress file-chip has-file">0%</span>'
            : '',
          '<button class="btn-folder" title="Open folder">&#128193;</button>',
          '<button class="btn-delete" title="Delete permanently">&#128465;</button>',
        '</div>',
      ].join('');

      /* ── Button bindings ──────────────────────────────────────── */
      card.querySelector('.btn-practice').addEventListener('click', function () {
        startPractice(s.id);
      });

      var openVideoBtn = card.querySelector('.btn-openvideo');
      if (openVideoBtn) {
        openVideoBtn.addEventListener('click', function () {
          fetchJSON('/api/sessions/' + s.id + '/open-video', { method: 'POST' })
            .catch(function (e) { alert('Could not open video: ' + e); });
        });
      }

      var ytInfoBtn = card.querySelector('.btn-ytinfo');
      if (ytInfoBtn) {
        ytInfoBtn.addEventListener('click', function () { openYTInfo(s.id); });
      }

      var queueBtn = card.querySelector('.btn-queue');
      if (queueBtn) {
        queueBtn.addEventListener('click', function () { setPublishStatus(s.id, 'queued', card); });
      }

      var unqueueBtn = card.querySelector('.btn-unqueue');
      if (unqueueBtn) {
        unqueueBtn.addEventListener('click', function () { setPublishStatus(s.id, 'waiting', card); });
      }

      var uploadBtn = card.querySelector('.btn-upload');
      if (uploadBtn) {
        uploadBtn.addEventListener('click', function () { startYouTubeUpload(s.id, card); });
      }

      card.querySelector('.btn-folder').addEventListener('click', function () {
        fetchJSON('/api/sessions/' + s.id + '/open-folder', { method: 'POST' })
          .catch(function (e) { alert('Could not open folder: ' + e); });
      });

      card.querySelector('.btn-delete').addEventListener('click', function () {
        if (!confirm('Permanently delete "' + (s.title || s.category) + '"?\nThis cannot be undone.')) return;
        fetchJSON('/api/sessions/' + s.id + '/delete', { method: 'POST' })
          .then(load).catch(function (e) { alert('Error: ' + e); });
      });

      grid.appendChild(card);
    });
  }

  /* ── Practice modal ───────────────────────────────────────────── */
  var overlay    = $('#prepOverlay');
  var loadingEl  = $('#prepLoading');
  var successEl  = $('#prepSuccess');
  var errorEl    = $('#prepError');
  var titleEl    = $('#prepTitle');
  var fileListEl = $('#prepFileList');
  var errMsgEl   = $('#prepErrorMsg');

  function showModal(state, msg) {
    overlay.classList.remove('hidden');
    loadingEl.style.display = state === 'loading'  ? 'block' : 'none';
    successEl.style.display = state === 'success'  ? 'block' : 'none';
    errorEl.style.display   = state === 'error'    ? 'block' : 'none';
    if (state === 'loading' && titleEl) titleEl.textContent = 'Preparing Session…';
    if (state === 'error'   && errMsgEl) errMsgEl.textContent = msg;
  }

  $('#closePrepBtn')    && $('#closePrepBtn').addEventListener('click',    function () { overlay.classList.add('hidden'); });
  $('#closePrepErrBtn') && $('#closePrepErrBtn').addEventListener('click', function () { overlay.classList.add('hidden'); });

  $('#startPracticingBtn') && $('#startPracticingBtn').addEventListener('click', function () {
    overlay.classList.add('hidden');
    window.location.href = '/shadowing';
  });

  function startPractice(recordId) {
    showModal('loading');
    fetchJSON('/api/sessions/' + recordId + '/prepare', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
      .then(function (res) {
        if (res.error) { showModal('error', res.error); return; }
        try {
          localStorage.setItem('celpip_session_dir',      res.session_dir);
          localStorage.setItem('celpip_shadow_sentences', JSON.stringify(res.sentences));
          var existing = {};
          try { existing = JSON.parse(localStorage.getItem('celpip_shadow_json') || '{}'); } catch(e){}
          existing._session_id = res.session_id;
          localStorage.setItem('celpip_shadow_json', JSON.stringify(existing));
        } catch(e) {}
        if (titleEl) titleEl.textContent = 'Ready';
        loadingEl.style.display = 'none';
        successEl.style.display = 'block';
        if (fileListEl) {
          var html = '<strong>Session Folder</strong>' + res.session_dir;
          if (res.pdf_path) html += '<strong>PDF</strong>' + res.pdf_path;
          html += '<strong>Audio (' + res.audio_count + ' sentences)</strong>' + res.audio_dir;
          fileListEl.innerHTML = html;
        }
      })
      .catch(function (e) { showModal('error', 'Network error: ' + e); });
  }

  /* ── YouTube Info modal ───────────────────────────────────────── */
  var ytOverlay  = $('#ytInfoOverlay');
  var ytLoading  = $('#ytInfoLoading');
  var ytBody     = $('#ytInfoBody');

  function openYTInfo(recordId) {
    if (!ytOverlay) return;
    ytOverlay.classList.remove('hidden');
    ytLoading.classList.remove('hidden');
    ytBody.classList.add('hidden');

    fetchJSON('/api/sessions/' + recordId + '/youtube-meta')
      .then(function (data) {
        if (data.error) { alert('Error: ' + data.error); ytOverlay.classList.add('hidden'); return; }
        $('#ytInfoTitle').textContent = data.title;
        $('#ytInfoDesc').value        = data.description;
        $('#ytInfoTags').textContent  = data.tags;
        ytLoading.classList.add('hidden');
        ytBody.classList.remove('hidden');
      })
      .catch(function (e) { alert('Error: ' + e); ytOverlay.classList.add('hidden'); });
  }

  function closeYTInfo() { if (ytOverlay) ytOverlay.classList.add('hidden'); }

  $('#ytInfoClose')   && $('#ytInfoClose').addEventListener('click',   closeYTInfo);
  $('#ytInfoDismiss') && $('#ytInfoDismiss').addEventListener('click', closeYTInfo);
  ytOverlay && ytOverlay.addEventListener('click', function (e) {
    if (e.target === ytOverlay) closeYTInfo();
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.ytinfo-copy-btn');
    if (!btn) return;
    var targetId = btn.dataset.target;
    var el = $('#' + targetId);
    if (!el) return;
    var text = el.tagName === 'TEXTAREA' ? el.value : el.textContent;
    navigator.clipboard.writeText(text).then(function () {
      var orig = btn.textContent;
      btn.textContent = 'Copied!';
      btn.classList.add('ytinfo-copy-ok');
      setTimeout(function () { btn.textContent = orig; btn.classList.remove('ytinfo-copy-ok'); }, 1800);
    }).catch(function () {
      el.select && el.select();
      document.execCommand('copy');
    });
  });

  /* ── Helpers ──────────────────────────────────────────────────── */
  function _esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  load();
})();
