/* Reading Lab */

// ── Voice data ────────────────────────────────────────────────────────────────
const RL_VOICES = [
  {id: 'en-CA-LiamNeural',    name: 'Liam',    accent: 'CA', accentFull: 'Canada',    gender: 'M'},
  {id: 'en-CA-ClaraNeural',   name: 'Clara',   accent: 'CA', accentFull: 'Canada',    gender: 'F'},
  {id: 'en-US-GuyNeural',     name: 'Guy',     accent: 'US', accentFull: 'US',        gender: 'M'},
  {id: 'en-US-JennyNeural',   name: 'Jenny',   accent: 'US', accentFull: 'US',        gender: 'F'},
  {id: 'en-GB-RyanNeural',    name: 'Ryan',    accent: 'UK', accentFull: 'UK',        gender: 'M'},
  {id: 'en-GB-SoniaNeural',   name: 'Sonia',   accent: 'UK', accentFull: 'UK',        gender: 'F'},
  {id: 'en-AU-WilliamNeural', name: 'William', accent: 'AU', accentFull: 'Australia', gender: 'M'},
  {id: 'en-AU-NatashaNeural', name: 'Natasha', accent: 'AU', accentFull: 'Australia', gender: 'F'},
];

let _voiceAccent = 'CA';
let _voiceGender = 'F';

function getSelectedVoice() {
  const v = RL_VOICES.find(v => v.accent === _voiceAccent && v.gender === _voiceGender);
  return v ? v.id : RL_VOICES[0].id;
}

function setVoiceFilter(type, val) {
  if (type === 'accent') _voiceAccent = val;
  else                   _voiceGender = val;
  _ttsSession = null;
  _sentencesWrapped = false;
  const chipId = type === 'accent' ? 'accentChips' : 'genderChips';
  document.querySelectorAll('#' + chipId + ' .rl-chip').forEach(b =>
    b.classList.toggle('active', b.dataset.val === val));
  const v = RL_VOICES.find(v => v.accent === _voiceAccent && v.gender === _voiceGender);
  if (v) {
    document.getElementById('voiceSelectedLabel').textContent =
      v.name + ' · ' + v.accentFull + ' · ' + (v.gender === 'M' ? 'Male' : 'Female');
  }
}

// ── State ─────────────────────────────────────────────────────────────────────
let _mode        = 'text';          // 'text' | 'youtube'
let _sourceText  = '';              // raw text currently displayed
let _sourceType  = 'text';          // 'text' | 'youtube'
let _sourceUrl   = null;
let _sourceTitle = null;
let _segments    = [];              // [{text, type, start?, end?}]
let _selected    = new Map();       // key (start-end) -> {word, item_type}
let _parsedItems = [];              // items from parsed CSV, ready to save
let _ttsSession  = null;            // {session_id, sentences:[{text,filename}]}
let _ttsIdx      = 0;
let _ttsAudio    = null;
let _ttsPlaying  = false;
let _bankItems        = [];
let _sentencesWrapped = false;

// ── Mode toggle ───────────────────────────────────────────────────────────────
function setMode(m) {
  _mode = m;
  document.getElementById('modeText').classList.toggle('active', m === 'text');
  document.getElementById('modeYT').classList.toggle('active',   m === 'youtube');
  document.getElementById('textInputArea').style.display = m === 'text'    ? '' : 'none';
  document.getElementById('ytInputArea').style.display   = m === 'youtube' ? '' : 'none';
  document.getElementById('inputHint').textContent =
    m === 'youtube'
      ? 'Paste a YouTube URL to extract and analyse its transcript'
      : 'Highlights phrasal verbs, noun phrases, and content words';
}

function showInput() {
  document.getElementById('inputPanel').classList.remove('collapsed');
  document.getElementById('btnReload').style.display = 'none';
}

// ── Extract ───────────────────────────────────────────────────────────────────
async function doExtract() {
  const btn  = document.getElementById('btnExtract');
  const hint = document.getElementById('inputHint');

  if (_mode === 'youtube') {
    const url = document.getElementById('ytUrl').value.trim();
    if (!url) { toast('Please enter a YouTube URL'); return; }

    btn.disabled   = true;
    btn.innerHTML  = '<span class="rl-spinner"></span> Fetching transcript…';

    let res;
    try {
      res = await fetch('/api/reading-lab/youtube', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
      });
    } catch (e) {
      showError(hint, 'Network error: ' + e.message);
      btn.disabled  = false;
      btn.innerHTML = '&#128269; Extract Vocabulary';
      return;
    }

    const data = await res.json();
    if (!res.ok || data.error) {
      showError(hint, data.error || 'Failed to fetch transcript');
      btn.disabled  = false;
      btn.innerHTML = '&#128269; Extract Vocabulary';
      return;
    }
    _sourceType  = 'youtube';
    _sourceUrl   = url;
    _sourceTitle = data.title;
    runExtraction(data.text, hint, btn);

  } else {
    const text = document.getElementById('textInput').value.trim();
    if (!text) { toast('Please paste some text first'); return; }
    _sourceType  = 'text';
    _sourceUrl   = null;
    _sourceTitle = null;
    runExtraction(text, hint, btn);
  }
}

async function runExtraction(text, hint, btn) {
  btn.disabled   = true;
  btn.innerHTML  = '<span class="rl-spinner"></span> Extracting…';
  hint.textContent = '';

  let res;
  try {
    res = await fetch('/api/reading-lab/extract', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text})
    });
  } catch (e) {
    showError(hint, 'Network error: ' + e.message);
    btn.disabled  = false;
    btn.innerHTML = '&#128269; Extract Vocabulary';
    return;
  }

  const data = await res.json();
  if (!res.ok || data.error) {
    showError(hint, data.error || 'Extraction failed');
    btn.disabled  = false;
    btn.innerHTML = '&#128269; Extract Vocabulary';
    return;
  }

  _sourceText       = text;
  _segments         = data.segments;
  _ttsSession       = null;
  _sentencesWrapped = false;
  _selected.clear();

  renderTextDisplay(data.segments, data.item_count);

  document.getElementById('inputPanel').classList.add('collapsed');
  document.getElementById('btnReload').style.display = '';
  btn.disabled  = false;
  btn.innerHTML = '&#128269; Extract Vocabulary';
  hint.textContent = 'Highlights phrasal verbs, noun phrases, and content words';
  document.getElementById('ttsBar').classList.remove('hidden');
  updateSelectedPanel();
  loadBank();
}

function showError(el, msg) {
  el.textContent = '⚠ ' + msg;
  el.style.color = 'var(--red)';
}

// ── Render text with highlights ───────────────────────────────────────────────
function renderTextDisplay(segments, itemCount) {
  document.getElementById('rlEmpty').style.display       = 'none';
  document.getElementById('rlTextContent').style.display = '';

  const label = document.getElementById('statsLabel');
  label.textContent = itemCount + ' extractable items detected — click to select';

  const body = document.getElementById('textBody');
  body.innerHTML = '';

  segments.forEach((seg, idx) => {
    if (seg.type === 'plain') {
      body.appendChild(document.createTextNode(seg.text));
    } else {
      const span       = document.createElement('span');
      span.className   = 'vocab-item vocab-' + seg.type;
      span.dataset.idx = idx;
      span.textContent = seg.text;
      span.onclick     = () => toggleItem(idx, seg, span);
      body.appendChild(span);
    }
  });
}

// ── Selection ─────────────────────────────────────────────────────────────────
function itemKey(seg) {
  return seg.start + '-' + seg.end;
}

function toggleItem(idx, seg, span) {
  const key = itemKey(seg);
  if (_selected.has(key)) {
    _selected.delete(key);
    span.classList.remove('selected');
  } else {
    _selected.set(key, {word: seg.text, item_type: seg.type, _idx: idx});
    span.classList.add('selected');
  }
  updateSelectedPanel();
}

function deselectItem(key) {
  _selected.delete(key);
  // un-highlight in text
  document.querySelectorAll('.vocab-item.selected').forEach(el => {
    const seg = _segments[el.dataset.idx];
    if (seg && itemKey(seg) === key) el.classList.remove('selected');
  });
  updateSelectedPanel();
}

function updateSelectedPanel() {
  const list    = document.getElementById('selectedList');
  const count   = _selected.size;
  document.getElementById('selCount').textContent = '(' + count + ')';
  document.getElementById('btnCopyPrompt').disabled = count === 0;
  document.getElementById('btnPasteDefs').disabled  = count === 0;

  if (count === 0) {
    list.innerHTML = '<div class="rl-selected-empty">Click any highlighted word or phrase in the text to add it here.</div>';
    return;
  }

  list.innerHTML = '';
  _selected.forEach((item, key) => {
    const div = document.createElement('div');
    div.className = 'rl-selected-item';
    div.innerHTML =
      '<span class="rl-selected-item-word">' + escHtml(item.word) + '</span>' +
      '<span class="rl-selected-item-type">' + typeLabel(item.item_type) + '</span>' +
      '<button class="rl-selected-item-remove" title="Remove" onclick="deselectItem(' + JSON.stringify(key) + ')">&#x2715;</button>';
    list.appendChild(div);
  });
}

function typeLabel(t) {
  if (t === 'phrasal_verb') return 'phrasal verb';
  if (t === 'noun_chunk')   return 'noun phrase';
  if (t === 'verb')         return 'verb';
  if (t === 'noun')         return 'noun';
  if (t === 'adjective')    return 'adjective';
  if (t === 'adverb')       return 'adverb';
  return t;
}

// ── Copy Prompt ───────────────────────────────────────────────────────────────
function copyPrompt() {
  if (_selected.size === 0) return;
  const words = [];
  _selected.forEach(item => words.push(item.word));

  const prompt =
    'For each word or phrase in the list below, provide the following in this exact CSV format (no header row, one item per line):\n' +
    'word,part_of_speech,definition,example_sentence\n\n' +
    'Rules:\n' +
    '- part_of_speech: use one of: noun, verb, adjective, adverb, phrasal verb, noun phrase, idiom, collocation\n' +
    '- definition: clear and plain, suitable for an intermediate English learner (B1–B2 level)\n' +
    '- example_sentence: one natural sentence, preferably in a workplace or advice context\n' +
    '- If the word is a phrasal verb, keep it exactly as written\n\n' +
    'Words to define:\n' +
    words.join('\n');

  navigator.clipboard.writeText(prompt).then(() => toast('Prompt copied — paste it into your AI chatbot'));
}

// ── Paste Definitions Modal ───────────────────────────────────────────────────
function openPasteModal() {
  document.getElementById('pasteModal').classList.remove('hidden');
  document.getElementById('csvInput').value = '';
  document.getElementById('parseError').style.display = 'none';
  document.getElementById('previewArea').style.display = 'none';
  document.getElementById('btnModalSave').style.display = 'none';
  document.getElementById('previewBody').innerHTML = '';
  _parsedItems = [];
}
function closePasteModal() {
  document.getElementById('pasteModal').classList.add('hidden');
}
function modalOverlayClick(e) {
  if (e.target === document.getElementById('pasteModal')) closePasteModal();
}

function parseCsv() {
  const raw = document.getElementById('csvInput').value.trim();
  const errEl = document.getElementById('parseError');
  errEl.style.display = 'none';
  if (!raw) { errEl.textContent = 'Nothing to parse.'; errEl.style.display = ''; return; }

  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
  const items = [];
  const errors = [];

  lines.forEach((line, i) => {
    // Simple CSV parse: split on comma but respect quoted fields
    const cols = splitCsvLine(line);
    if (cols.length < 3) {
      errors.push('Line ' + (i + 1) + ': expected at least 3 columns, got ' + cols.length);
      return;
    }
    items.push({
      word:      cols[0].trim(),
      word_type: cols[1].trim(),
      definition: cols[2].trim(),
      example:   cols[3] ? cols[3].trim() : '',
      item_type: guessItemType(cols[0].trim()),
    });
  });

  if (errors.length) {
    errEl.textContent = errors.join(' | ');
    errEl.style.display = '';
    if (items.length === 0) return;
  }

  // Show preview
  const tbody = document.getElementById('previewBody');
  tbody.innerHTML = '';
  items.forEach(it => {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + escHtml(it.word) + '</td>' +
      '<td>' + escHtml(it.word_type) + '</td>' +
      '<td>' + escHtml(it.definition) + '</td>' +
      '<td>' + escHtml(it.example) + '</td>';
    tbody.appendChild(tr);
  });
  document.getElementById('previewArea').style.display = '';
  document.getElementById('btnModalSave').style.display = '';
  _parsedItems = items;
}

function splitCsvLine(line) {
  const result = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQ = !inQ;
    } else if (ch === ',' && !inQ) {
      result.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  result.push(cur);
  return result;
}

function guessItemType(word) {
  const lower = word.toLowerCase();
  // Check if it matches a selected phrasal verb
  for (const [, item] of _selected) {
    if (item.word.toLowerCase() === lower) return item.item_type;
  }
  return word.includes(' ') ? 'noun_chunk' : 'word';
}

async function saveToBank() {
  if (_parsedItems.length === 0) return;
  const btn = document.getElementById('btnModalSave');
  btn.disabled  = true;
  btn.innerHTML = '<span class="rl-spinner"></span> Saving…';

  const res = await fetch('/api/reading-lab/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      source_type: _sourceType,
      source_url:  _sourceUrl,
      text:        _sourceText,
      title:       _sourceTitle,
      items:       _parsedItems,
    })
  });
  const data = await res.json();
  btn.disabled  = false;
  btn.innerHTML = '&#10003; Save to Bank';

  if (res.ok && data.ok) {
    closePasteModal();
    toast('Saved ' + data.saved + ' items to your vocab bank');
    loadBank();
    switchTab('bank');
  } else {
    toast('Save failed: ' + (data.error || 'unknown error'));
  }
}

// ── Bank tab ──────────────────────────────────────────────────────────────────
async function loadBank() {
  const res  = await fetch('/api/reading-lab/bank');
  const data = await res.json();
  _bankItems = data.items || [];
  renderBank();
}

function renderBank() {
  const list  = document.getElementById('bankList');
  const count = _bankItems.length;
  document.getElementById('bankCount').textContent = '(' + count + ')';

  if (count === 0) {
    list.innerHTML = '<div class="rl-bank-empty">Your saved vocabulary will appear here.</div>';
    return;
  }

  list.innerHTML = '';
  _bankItems.forEach(item => {
    const div = document.createElement('div');
    div.className = 'rl-bank-item';
    div.innerHTML =
      '<div class="rl-bank-item-header">' +
        '<span class="rl-bank-word">' + escHtml(item.word) + '</span>' +
        (item.word_type ? '<span class="rl-bank-word-type">· ' + escHtml(item.word_type) + '</span>' : '') +
      '</div>' +
      (item.definition ? '<div class="rl-bank-def">' + escHtml(item.definition) + '</div>' : '') +
      (item.example    ? '<div class="rl-bank-ex">"' + escHtml(item.example) + '"</div>'  : '') +
      '<div class="rl-bank-item-footer">' +
        '<span class="rl-bank-source">' + escHtml(item.source_type || '') + (item.title ? ' · ' + escHtml(item.title) : '') + '</span>' +
        '<button class="btn-delete-item" title="Delete" onclick="deleteItem(' + item.id + ')">&#128465;</button>' +
      '</div>';
    list.appendChild(div);
  });
}

async function deleteItem(id) {
  await fetch('/api/reading-lab/bank/' + id, {method: 'DELETE'});
  _bankItems = _bankItems.filter(it => it.id !== id);
  renderBank();
}

function copyBank() {
  if (_bankItems.length === 0) { toast('Bank is empty'); return; }
  const lines = _bankItems.map(it => {
    let line = it.word;
    if (it.word_type)  line += ' (' + it.word_type + ')';
    if (it.definition) line += ' — ' + it.definition;
    if (it.example)    line += '\n  e.g. ' + it.example;
    return line;
  });
  navigator.clipboard.writeText(lines.join('\n\n')).then(() => toast('Bank copied to clipboard'));
}

// ── Sentence wrapping for TTS highlighting ────────────────────────────────────
function wrapSentences() {
  if (_sentencesWrapped || !_ttsSession || !_segments.length) return;
  _sentencesWrapped = true;

  // Map each TTS sentence to its char range in _sourceText
  const sentRanges = [];
  let searchFrom = 0;
  for (const s of _ttsSession.sentences) {
    const idx = _sourceText.indexOf(s.text, searchFrom);
    if (idx === -1) { sentRanges.push(null); continue; }
    sentRanges.push({start: idx, end: idx + s.text.length});
    searchFrom = idx + s.text.length;
  }

  // Compute absolute char position for each segment (plain segments have no start/end)
  let charPos = 0;
  const segWithPos = _segments.map(seg => {
    const absStart = charPos;
    charPos += seg.text.length;
    return {...seg, _absStart: absStart};
  });

  function sentIdxFor(pos) {
    for (let i = 0; i < sentRanges.length; i++) {
      const r = sentRanges[i];
      if (r && pos >= r.start && pos < r.end) return i;
    }
    return -1;
  }

  // Re-render textBody with sentence wrapper spans
  const body = document.getElementById('textBody');
  body.innerHTML = '';
  const sentSpans = {};

  segWithPos.forEach((seg, idx) => {
    const si = sentIdxFor(seg._absStart);
    let container;
    if (si >= 0) {
      if (!sentSpans[si]) {
        const s = document.createElement('span');
        s.className = 'rl-sentence';
        s.dataset.sentIdx = si;
        body.appendChild(s);
        sentSpans[si] = s;
      }
      container = sentSpans[si];
    } else {
      container = body;
    }

    if (seg.type === 'plain') {
      container.appendChild(document.createTextNode(seg.text));
    } else {
      const span = document.createElement('span');
      span.className = 'vocab-item vocab-' + seg.type;
      span.dataset.idx = idx;
      span.textContent = seg.text;
      if (_selected.has(itemKey(seg))) span.classList.add('selected');
      span.onclick = () => toggleItem(idx, seg, span);
      container.appendChild(span);
    }
  });
}

// ── TTS ────────────────────────────────────────────────────────────────────────
async function ttsPlay() {
  if (_ttsPlaying) return;
  if (!_ttsSession) {
    const btn = document.getElementById('btnTtsPlay');
    btn.innerHTML = '<span class="rl-spinner"></span> Generating…';
    btn.disabled  = true;

    const res  = await fetch('/api/reading-lab/tts/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: _sourceText, voice: getSelectedVoice()})
    });
    const data = await res.json();
    btn.disabled  = false;
    btn.innerHTML = '&#9654; Read aloud';

    if (!res.ok || data.error) { toast('TTS failed: ' + (data.error || 'unknown')); return; }
    _ttsSession = {session_id: data.session_id, sentences: data.sentences};
    _ttsIdx     = 0;
    wrapSentences();
  }
  _ttsPlaying = true;
  document.getElementById('btnTtsPlay').style.display = 'none';
  document.getElementById('btnTtsStop').style.display = '';
  playNextSentence();
}

function playNextSentence() {
  if (!_ttsPlaying || !_ttsSession) return;
  if (_ttsIdx >= _ttsSession.sentences.length) {
    ttsStop();
    return;
  }
  const sent = _ttsSession.sentences[_ttsIdx];
  document.getElementById('ttsSentenceLabel').textContent =
    (_ttsIdx + 1) + '/' + _ttsSession.sentences.length + ' — ' + (sent.text || '');

  // Highlight active sentence
  document.querySelectorAll('.rl-sentence.tts-active').forEach(el => el.classList.remove('tts-active'));
  const activeSent = document.querySelector('.rl-sentence[data-sent-idx="' + _ttsIdx + '"]');
  if (activeSent) {
    activeSent.classList.add('tts-active');
    activeSent.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  _ttsAudio     = new Audio('/api/reading-lab/audio/' + _ttsSession.session_id + '/' + sent.filename);
  _ttsAudio.onended = () => { _ttsIdx++; playNextSentence(); };
  _ttsAudio.onerror = () => { _ttsIdx++; playNextSentence(); };
  _ttsAudio.play().catch(() => { _ttsIdx++; playNextSentence(); });
}

function ttsStop() {
  _ttsPlaying = false;
  if (_ttsAudio) { _ttsAudio.pause(); _ttsAudio = null; }
  document.getElementById('btnTtsPlay').style.display = '';
  document.getElementById('btnTtsStop').style.display = 'none';
  document.getElementById('ttsSentenceLabel').textContent = '';
  document.querySelectorAll('.rl-sentence.tts-active').forEach(el => el.classList.remove('tts-active'));
}

// ── Tab switch ─────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.getElementById('tabSelected').classList.toggle('active', name === 'selected');
  document.getElementById('tabBank').classList.toggle('active',     name === 'bank');
  document.getElementById('paneSelected').classList.toggle('active', name === 'selected');
  document.getElementById('paneBank').classList.toggle('active',     name === 'bank');
  if (name === 'bank') loadBank();
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toast(msg, duration = 2800) {
  const el = document.getElementById('rlToast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

// ── Font size & Access ─────────────────────────────────────────────────────────
const _fontSizes   = ['15px', '17px', '19px'];
const _fontLabels  = ['Aa', 'AA', 'A+'];
let   _fontIdx     = 0;
let   _highlights  = true;

function cycleFontSize() {
  _fontIdx = (_fontIdx + 1) % _fontSizes.length;
  document.getElementById('textBody').style.fontSize = _fontSizes[_fontIdx];
  document.getElementById('btnFontSize').textContent = _fontLabels[_fontIdx];
}

function toggleHighlights() {
  _highlights = !_highlights;
  const btn = document.getElementById('btnAccess');
  btn.classList.toggle('active', !_highlights);
  btn.title = _highlights ? 'Toggle highlights' : 'Highlights hidden — click to restore';
  document.querySelectorAll('.vocab-item').forEach(el => {
    el.style.background   = _highlights ? '' : 'transparent';
    el.style.borderBottom = _highlights ? '' : 'none';
    el.style.color        = _highlights ? '' : 'inherit';
    el.style.cursor       = _highlights ? 'pointer' : 'default';
  });
}

// ── Init ───────────────────────────────────────────────────────────────────────
loadBank();
