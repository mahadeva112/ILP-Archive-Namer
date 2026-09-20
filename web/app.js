/* ILP Archive Namer - UI layer.
   All naming rules live in the Python engine; this file only renders fields,
   posts them, and shows what comes back. */

let BOOT = null;
let CAT = null;                 // active category meta
const STATE = {};               // category id -> field values
let debounceTimer = null;

const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------ boot */
async function boot() {
  const resp = await fetch('/api/bootstrap');
  BOOT = await resp.json();

  $('stamp').textContent = 'v' + BOOT.version + '\n' + BOOT.spec_revision;

  renderCategories();
  renderReference();
  selectCategory(BOOT.categories[0].id);
  wireChrome();
  wireDisk();
  loadHistory();
  startHeartbeat();
}

/* When the app runs with no console window there is no Ctrl+C to press, so the
   server quits by itself once this ping stops -- i.e. when the tab is closed. */
function startHeartbeat() {
  const ping = () => fetch('/api/ping', { cache: 'no-store' }).catch(() => {});
  ping();
  setInterval(ping, 4000);
}

/* ---------------------------------------------------------- chrome */
const CRUMBS = {
  make: 'Create a name',
  disk: 'Folder &amp; files',
  check: 'Check a name',
  ref: 'Reference',
  hist: 'History',
};

let SCREEN = 'make';

function go(id) {
  if (!CRUMBS[id]) return;
  SCREEN = id;
  document.querySelectorAll('.screen').forEach((s) => {
    s.classList.toggle('on', s.id === 's-' + id);
  });
  document.querySelectorAll('.nav button').forEach((b) => {
    b.classList.toggle('on', b.dataset.go === id);
  });
  setCrumb();
  window.scrollTo({ top: 0 });
}

function setCrumb(detail) {
  const extra = detail !== undefined ? detail
    : (SCREEN === 'make' && CAT ? CAT.spec_ref + ' ' + CAT.label : '');
  $('crumb').innerHTML = CRUMBS[SCREEN]
    + (extra ? ' <span>&middot; ' + esc(extra) + '</span>' : '');
}

function wireChrome() {
  document.querySelectorAll('[data-go]').forEach((b) => {
    b.onclick = () => go(b.dataset.go);
  });

  // Numbers move between screens; a field being typed in always wins.
  const KEYS = { 1: 'make', 2: 'disk', 3: 'check', 4: 'ref', 5: 'hist' };
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.target.matches('input, select, textarea')) return;
    if (KEYS[e.key]) go(KEYS[e.key]);
  });

  const root = document.documentElement;
  const saved = localStorage.getItem('theme');
  if (saved) root.dataset.theme = saved;
  $('themeBtn').onclick = () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', root.dataset.theme);
  };

  document.querySelectorAll('[data-view]').forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll('[data-view]').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      const tree = b.dataset.view === 'tree';
      $('outTree').style.display = tree ? 'block' : 'none';
      $('outFiles').style.display = tree ? 'none' : 'block';
    };
  });

  $('btnReset').onclick = () => { STATE[CAT.id] = {}; renderForm(); build(); };
  $('btnCheck').onclick = runCheck;
  $('checkInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runCheck();
  });
  $('histSearch').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    [...$('histBody').children].forEach((tr) => {
      tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ------------------------------------------------------ categories */
const TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
  + 'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
  + '<path d="m5 13 4 4L19 7"/></svg>';

function renderCategories() {
  const grid = $('catGrid');
  grid.innerHTML = '';
  BOOT.categories.forEach((c) => {
    const b = document.createElement('button');
    b.className = 'cat-btn';
    b.dataset.cat = c.id;
    // The worked example is the fastest way to recognise the right category.
    b.innerHTML = '<div class="cat-top">'
      + '<span class="cat-ref">' + esc(c.spec_ref) + '</span>'
      + '<span class="cat-name">' + esc(c.label) + '</span>'
      + '<span class="cat-check">' + TICK + '</span></div>'
      + '<div class="cat-shape" title="' + esc(c.example) + '">'
      + esc(c.example) + '</div>';
    b.onclick = () => selectCategory(c.id);
    grid.appendChild(b);
  });
}

function selectCategory(id) {
  CAT = BOOT.categories.find((c) => c.id === id);
  document.querySelectorAll('.cat-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.cat === id);
  });
  $('catBadge').textContent = CAT.spec_ref;
  $('catLabel').textContent = CAT.label;
  $('catBlurb').textContent = CAT.blurb;
  setCrumb();

  if (!STATE[id]) STATE[id] = defaultsFor(CAT);
  renderForm();
  build();
}

function defaultsFor(cat) {
  const v = {};
  cat.fields.forEach((f) => { if (f.default) v[f.key] = f.default; });
  if (cat.fields.some((f) => f.key === 'lang')) v.lang = v.lang || 'hin';
  const today = new Date();
  const iso = today.getFullYear() + '-' +
    String(today.getMonth() + 1).padStart(2, '0') + '-' +
    String(today.getDate()).padStart(2, '0');
  cat.fields.forEach((f) => {
    if (f.type === 'date' && !v[f.key]) v[f.key] = iso;
    if (f.type === 'month' && !v[f.key]) v[f.key] = iso.slice(0, 7);
  });
  if (cat.has_inner_files) v.voices = v.voices || 2;
  return v;
}

/* ------------------------------------------------------------ form */

function renderForm() {
  const v = STATE[CAT.id];
  const host = $('form');
  host.innerHTML = '';

  CAT.fields.forEach((f) => {
    if (f.show_if) {
      const [k, want] = Object.entries(f.show_if)[0];
      if ((v[k] || '') !== want) return;
    }
    host.appendChild(buildField(f, v));
  });

  if (CAT.has_inner_files) {
    host.appendChild(buildField({
      key: 'voices', label: 'How many voice tracks?', type: 'number',
      required: false,
      hint: 'One WAV per voice in the video. Mono, 24 bit, 48 kHz.',
    }, v));
  }

  const wrap = document.createElement('div');
  wrap.className = 'checkline';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.id = 'forceTC';
  cb.checked = !!v.force_title_case;
  cb.onchange = () => { v.force_title_case = cb.checked; build(); };
  const lb = document.createElement('label');
  lb.htmlFor = 'forceTC';
  lb.style.cssText = 'text-transform:none;letter-spacing:0;margin:0;font-size:12px';
  lb.textContent = 'Force Title Case (fold acronyms like USA to Usa)';
  wrap.append(cb, lb);
  host.appendChild(wrap);
}

function buildField(f, v) {
  const wrap = document.createElement('div');
  wrap.className = 'field';

  const lab = document.createElement('label');
  lab.textContent = f.label + ' ';
  if (f.required) {
    const s = document.createElement('span');
    s.className = 'req';
    s.textContent = '*';
    lab.appendChild(s);
  }
  wrap.appendChild(lab);

  let el;

  if (f.type === 'channel') {
    el = document.createElement('select');
    const wanted = CAT.channel_filter;
    BOOT.channels
      .filter((c) => !wanted || wanted.includes(c.platform))
      .forEach((c) => {
        const o = document.createElement('option');
        o.value = c.code;
        o.textContent = c.code + '  -  ' + c.name;
        el.appendChild(o);
      });
    el.value = v[f.key] || (el.options[0] && el.options[0].value) || '';
    v[f.key] = el.value;
  } else if (f.type === 'department') {
    el = document.createElement('select');
    BOOT.departments.forEach((d) => {
      const o = document.createElement('option');
      o.value = d.code;
      o.textContent = d.code + '  -  ' + d.name;
      el.appendChild(o);
    });
    el.value = v[f.key] || 'ILP';
    v[f.key] = el.value;
  } else if (f.type === 'select') {
    el = document.createElement('select');
    f.options.forEach((o) => {
      const op = document.createElement('option');
      op.value = o.value;
      op.textContent = o.label;
      el.appendChild(op);
    });
    el.value = v[f.key] || f.default || f.options[0].value;
    v[f.key] = el.value;
  } else if (f.type === 'lang') {
    el = document.createElement('select');
    // data/languages.json is ordered by group, so a running label is enough.
    let og = null;
    BOOT.languages.forEach((l) => {
      if (!og || og.label !== l.group) {
        og = document.createElement('optgroup');
        og.label = l.group || 'Languages';
        el.appendChild(og);
      }
      const o = document.createElement('option');
      o.value = l.code;
      o.textContent = l.name + '  -  ' + l.code;
      og.appendChild(o);
    });
    el.value = v[f.key] || 'hin';
    v[f.key] = el.value;
  } else if (f.type === 'date') {
    el = document.createElement('input');
    el.type = 'date';
    el.value = v[f.key] || '';
  } else if (f.type === 'month') {
    el = document.createElement('input');
    el.type = 'month';
    el.value = v[f.key] || '';
  } else if (f.type === 'number') {
    el = document.createElement('input');
    el.type = 'number';
    el.min = 1;
    el.max = 12;
    el.value = v[f.key] || 2;
  } else {
    el = document.createElement('input');
    el.type = 'text';
    if (f.placeholder) el.placeholder = f.placeholder;
    if (f.type === 'video_url') el.className = 'mono';
    el.value = v[f.key] || '';
  }

  el.dataset.key = f.key;

  const onInput = () => {
    let val = el.value;
    if (f.type === 'lang') {
      val = val.toLowerCase().replace(/[^a-z]/g, '');
      el.value = val;
    }
    v[f.key] = val;
    // A field that other fields are conditioned on must re-render the form.
    if (CAT.fields.some((o) => o.show_if && Object.keys(o.show_if)[0] === f.key)) {
      renderForm();
    }
    scheduleBuild();
  };

  el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', onInput);
  wrap.appendChild(el);

  /* -------- per-type extras -------- */
  if (f.type === 'lang') {
    const h = document.createElement('div');
    h.className = 'hint';
    h.id = 'langHint';
    wrap.appendChild(h);
    setTimeout(() => updateLangHint(v[f.key]), 0);
  }

  if (f.type === 'video_url') {
    const h = document.createElement('div');
    h.className = 'hint';
    h.innerHTML = 'Paste the full <strong>English</strong> URL &mdash; the code '
      + 'and the title are pulled out automatically. A bare code works too.';
    wrap.appendChild(h);

    const status = document.createElement('div');
    status.className = 'hint';
    status.id = 'urlStatus';
    wrap.appendChild(status);

    let lookupTimer = null;
    el.addEventListener('input', () => {
      clearTimeout(lookupTimer);
      const raw = el.value.trim();
      if (raw.length < 8) return;
      lookupTimer = setTimeout(() => lookup(raw, el, status), 350);
    });
  }

  if (f.hint) {
    const h = document.createElement('div');
    h.className = 'hint';
    h.textContent = f.hint;
    wrap.appendChild(h);
  }

  if (f.key === 'title') {
    const h = document.createElement('div');
    h.className = 'hint';
    h.id = 'slugHint';
    wrap.appendChild(h);
  }

  return wrap;
}

function updateLangHint(code) {
  const h = $('langHint');
  if (!h) return;
  const found = BOOT.languages.find((l) => l.code === code);
  if (found) {
    h.textContent = found.standard + ': ' + found.name + ' (' + found.code + ')';
    h.style.color = 'var(--success)';
  } else if (code) {
    // Only reachable if a saved draft carries a code no longer in the register.
    h.textContent = code + ' is not in the bundled Indian-language list - '
      + 'double-check it before archiving.';
    h.style.color = 'var(--warn)';
  } else {
    h.textContent = 'Pick the dubbing language.';
    h.style.color = 'var(--muted)';
  }
}

/* ------------------------------------------------------- URL lookup */
async function lookup(raw, inputEl, statusEl) {
  statusEl.style.color = 'var(--muted)';
  statusEl.textContent = 'Looking up...';
  let data;
  try {
    const r = await fetch('/api/lookup?url=' + encodeURIComponent(raw));
    data = await r.json();
  } catch (e) {
    statusEl.style.color = 'var(--warn)';
    statusEl.textContent = 'Lookup failed. Enter the code and title by hand.';
    return;
  }

  const v = STATE[CAT.id];

  if (data.video_id && data.video_id !== raw) {
    inputEl.value = data.video_id;
    v.video_id = data.video_id;
  }

  // Suggest the matching channel, but never overwrite a deliberate choice.
  if (data.channel && CAT.fields.some((f) => f.type === 'channel')) {
    const sel = document.querySelector('#form select[data-key="channel"]');
    if (sel && !v._channel_touched
        && [...sel.options].some((o) => o.value === data.channel)) {
      sel.value = data.channel;
      v.channel = data.channel;
    }
  }

  const bits = [];
  if (data.platform) bits.push('Platform <strong>' + esc(data.platform) + '</strong>');
  if (data.video_id) bits.push('code <strong>' + esc(data.video_id) + '</strong>');

  if (data.title) {
    const titleEl = document.querySelector('#form input[data-key="title"]');
    if (titleEl && !titleEl.value.trim()) {
      titleEl.value = data.title;
      v.title = data.title;
    }
    bits.push('title fetched');
    if (data.title_raw && data.title_raw !== data.title) {
      bits.push('trimmed from &ldquo;' + esc(data.title_raw) + '&rdquo;');
    }
  }

  statusEl.style.color = data.note ? 'var(--warn)' : 'var(--success)';
  statusEl.innerHTML = bits.join(' &middot; ') + (data.note
    ? (bits.length ? '<br>' : '') + esc(data.note) : '');

  build();
}

/* ----------------------------------------------------------- build */
function scheduleBuild() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(build, 180);
}

async function build() {
  const v = STATE[CAT.id];
  updateLangHint(v.lang);

  let res;
  try {
    const r = await fetch('/api/build', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: CAT.id, fields: v }),
    });
    res = await r.json();
  } catch (e) {
    return;
  }

  const nameEl = $('outFolder');
  const issuesEl = $('outIssues');
  issuesEl.innerHTML = '';

  if (res.error) {
    // Before anything has been typed, a missing field is not a mistake worth
    // colouring red - it is just an empty form.
    const started = CAT.fields.some(
      (f) => f.required && String(v[f.key] || '').trim() && f.type !== 'date');
    $('outSegments').innerHTML = '';
    nameEl.style.display = 'block';
    nameEl.textContent = started ? res.error : 'Fill in the fields to generate a name';
    nameEl.classList.toggle('bad', started);
    nameEl.style.color = started ? '' : 'var(--text-3)';
    $('outVerdict').style.display = 'none';
    $('filesCard').style.display = 'none';
    $('nasWrap').style.display = 'none';
    $('slugHint') && ($('slugHint').textContent = '');
    setLive(null);
    setMakeSummary(null);
    clearDiskContext();
    return;
  }

  nameEl.style.display = 'none';
  nameEl.classList.remove('bad');
  renderSegments($('outSegments'), res.segments, res.folder, true);
  renderVerdict($('outVerdict'), res.issues, res.ok);
  setLive(res.folder, res.ok);
  setMakeSummary(res);

  if (res.issues.length) {
    res.issues.forEach((i) => issuesEl.appendChild(issue(i.level, i.message, i.rule)));
  }

  if (res.nas) {
    $('nasWrap').style.display = 'block';
    $('outNas').innerHTML = '';
    $('outNas').append(
      iconSvg('<rect x="3" y="4" width="18" height="7" rx="2"/>'
        + '<rect x="3" y="13" width="18" height="7" rx="2"/>'
        + '<path d="M7 7.5h.01M7 16.5h.01"/>'),
      textSpan(res.nas.path + '/' + res.folder),
      copyIconBtn(res.nas.path + '/' + res.folder, 'Copy NAS path'));
  } else {
    $('nasWrap').style.display = 'none';
  }

  const sh = $('slugHint');
  if (sh) {
    const slug = slugOf(res.folder, res.category);
    sh.innerHTML = slug
      ? 'Becomes <code style="font-family:var(--mono)">' + esc(slug) + '</code>'
      : '';
  }

  renderFiles(res);
  $('btnCopyFolder').onclick = (e) => copy(res.folder, e.target);

  // The scaffold/ingest tab always works on the name shown here. Only a name
  // that passes every rule may be written to disk.
  if (res.ok) {
    setDiskContext(res, Object.assign({}, v, { _slug: slugOf(res.folder, res.category) }));
  } else {
    clearDiskContext();
  }
}

/* -------------------------------------------------- name breakdown
   The name is drawn as its labelled pieces rather than as one string: the
   engine returns the same segments it concatenated to make the name, so a
   field in the wrong slot or a lowercase language code is visible without
   reading the whole thing character by character. */
function renderSegments(host, segments, folder, clickable) {
  host.innerHTML = '';
  if (!segments || !segments.length) {
    host.textContent = '';
    return;
  }

  let colour = 0;
  segments.forEach((s) => {
    if (s.kind === 'sep') {
      const d = document.createElement('div');
      d.className = 'seg sep';
      d.innerHTML = '<span class="tok">' + esc(s.text) + '</span>'
        + '<span class="cap">&nbsp;</span>';
      host.appendChild(d);
      return;
    }

    // A field the form can focus becomes a button; otherwise it is inert.
    const canFocus = clickable && s.field
      && document.querySelector('#form [data-key="' + s.field + '"]');
    const el = document.createElement(canFocus ? 'button' : 'div');
    el.className = 'seg c' + (colour++ % 4)
      + (s.flag ? ' flag-' + s.flag : '');
    el.innerHTML = '<span class="tok">' + esc(s.text) + '</span>'
      + '<span class="cap">' + esc(s.label) + '</span>';
    el.title = s.note || (s.label + ': ' + s.text);
    if (canFocus) {
      el.type = 'button';
      el.onclick = () => {
        const f = document.querySelector('#form [data-key="' + s.field + '"]');
        if (f) { f.focus(); f.scrollIntoView({ block: 'center' }); }
      };
    }
    host.appendChild(el);
  });
}

function renderVerdict(host, issues, ok) {
  const errors = (issues || []).filter((i) => i.level === 'error').length;
  const warnings = (issues || []).filter((i) => i.level === 'warning').length;
  host.style.display = 'flex';
  host.innerHTML = '';

  const pill = document.createElement('span');
  if (errors) {
    pill.className = 'pill bad';
    pill.textContent = errors + (errors === 1 ? ' rule broken' : ' rules broken');
  } else if (warnings) {
    pill.className = 'pill warn';
    pill.textContent = warnings + (warnings === 1 ? ' warning' : ' warnings');
  } else {
    pill.className = 'pill ok';
    pill.innerHTML = TICK.replace('<svg', '<svg width="11" height="11"')
      + ' Spec compliant';
  }
  host.appendChild(pill);

  const words = document.createElement('span');
  words.textContent = errors
    ? 'Archives would reject this name'
    : (warnings ? 'Readable, but check the warnings below'
                : 'Passes every rule in the spec');
  host.appendChild(words);

  // One dot per rule the checker enforces, so "what was actually checked"
  // is visible rather than implied.
  const dots = document.createElement('span');
  dots.className = 'rule-dots';
  dots.title = RULE_COUNT + ' naming rules checked';
  for (let i = 0; i < RULE_COUNT; i += 1) {
    const d = document.createElement('i');
    if (i < errors) d.className = 'bad';
    else if (i < errors + warnings) d.className = 'warn';
    dots.appendChild(d);
  }
  host.appendChild(dots);
  if (ok === false && !errors) host.appendChild(document.createTextNode(''));
}

const RULE_COUNT = 9;

/* The name follows the user across screens, so switching to Reference
   mid-task does not lose it. */
function setLive(folder, ok) {
  const bar = $('liveBar');
  $('liveName').textContent = folder || 'No name yet';
  bar.classList.toggle('empty', !folder);
  bar.title = folder || 'The name you are working on';
  $('liveCopy').onclick = folder ? (e) => copyIcon(folder, e.currentTarget) : null;
  $('liveCopy').style.visibility = folder ? 'visible' : 'hidden';
  const dot = bar.querySelector('.dot');
  dot.style.background = folder && ok === false ? 'var(--bad)' : '';
  dot.style.boxShadow = folder && ok === false ? '0 0 0 3px var(--bad-bg)' : '';
}

function setMakeSummary(res) {
  const sum = $('makeSummary');
  const btn = $('btnGoDisk');
  if (!res) {
    sum.textContent = 'Fill in the fields to generate a name';
    btn.disabled = true;
    $('btnCopyFolder2').onclick = null;
    return;
  }
  const folders = (res.template || []).length;
  const files = (res.files || []).length;
  sum.innerHTML = res.ok
    ? 'Ready &middot; <b>1 folder</b>'
      + (folders ? ', ' + folders + ' subfolders' : '')
      + (files ? ', ' + files + ' filenames' : '')
    : '<b>Not ready</b> &middot; fix the errors before writing this to disk';
  btn.disabled = !res.ok;
  $('btnCopyFolder2').onclick = (e) => copy(res.folder, e.target);
}

/* ------------------------------------------------- small builders */
function iconSvg(inner, cls) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  if (cls) svg.setAttribute('class', cls);
  svg.innerHTML = inner;
  return svg;
}

function textSpan(text) {
  const s = document.createElement('span');
  s.style.flex = '1';
  s.style.minWidth = '0';
  s.textContent = text;
  return s;
}

function copyIconBtn(text, title) {
  const b = document.createElement('button');
  b.className = 'icon-btn';
  b.title = title || 'Copy';
  b.appendChild(iconSvg('<rect x="9" y="9" width="12" height="12" rx="2"/>'
    + '<path d="M5 15V5a2 2 0 0 1 2-2h10"/>'));
  b.onclick = () => copyIcon(text, b);
  return b;
}

function slugOf(folder, category) {
  const parts = folder.split('_');
  if (category === 'sg_exclusive') return parts.slice(1).join('_');
  if (category === 'department') return parts[1] || '';
  if (category === 'satsang') return parts.length > 2 ? parts[parts.length - 2] : parts[1];
  return parts[2] || '';
}

function renderFiles(res) {
  if (!res.files || !res.files.length) {
    $('filesCard').style.display = 'none';
    return;
  }

  $('filesCard').style.display = 'block';
  $('filesTitle').textContent = 'What goes inside · ' + res.files.length
    + ' file' + (res.files.length === 1 ? '' : 's');

  /* Grouped by destination subfolder, because that is the question being
     asked: what goes where. */
  const byFolder = {};
  res.files.forEach((f) => {
    (byFolder[f.folder] = byFolder[f.folder] || []).push(f);
  });

  const host = $('outFiles');
  host.innerHTML = '';
  (res.template || []).forEach((t) => {
    const kids = byFolder[t.name];
    if (!kids || !kids.length) return;

    const group = document.createElement('div');
    group.className = 'fgroup';

    const hd = document.createElement('div');
    hd.className = 'fgroup-hd';
    hd.append(iconSvg('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 '
      + '2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'));
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = t.name;
    hd.appendChild(nm);
    if (t.mandatory) {
      const p = document.createElement('span');
      p.className = 'pill bad';
      p.textContent = 'mandatory';
      hd.appendChild(p);
    }
    const ct = document.createElement('span');
    ct.className = 'ct';
    ct.textContent = kids.length + ' file' + (kids.length === 1 ? '' : 's');
    hd.appendChild(ct);
    group.appendChild(hd);

    kids.forEach((f) => {
      const row = document.createElement('div');
      row.className = 'file-row';

      const main = document.createElement('div');
      main.className = 'file-main';
      const fn = document.createElement('div');
      fn.className = 'file-name';
      fn.textContent = f.name;
      const meta = document.createElement('div');
      meta.className = 'file-meta';
      meta.textContent = f.note;
      main.append(fn, meta);

      const tag = document.createElement('span');
      tag.className = 'file-tag ' + (f.mandatory ? 'must' : 'opt');
      tag.textContent = f.mandatory ? 'required' : 'optional';

      row.append(main, tag, copyIconBtn(f.name, 'Copy filename'));
      group.appendChild(row);
    });

    host.appendChild(group);
  });

  let tree = '<span class="fold">' + esc(res.folder) + '/</span>\n';
  const order = res.template.map((t) => t.name);
  order.forEach((folderName, fi) => {
    const isLastFolder = fi === order.length - 1;
    const kids = byFolder[folderName] || [];
    const tmpl = res.template.find((t) => t.name === folderName);
    tree += (isLastFolder ? '  └── ' : '  ├── ')
      + '<span class="fold">' + esc(folderName) + '/</span>'
      + (tmpl && tmpl.mandatory ? '  <span class="c">(mandatory)</span>' : '')
      + '\n';
    kids.forEach((k, ki) => {
      const last = ki === kids.length - 1;
      tree += (isLastFolder ? '  ' : '  │') + '   '
        + (last ? '└── ' : '├── ')
        + '<span class="f">' + esc(k.name) + '</span>\n';
    });
  });
  $('outTree').innerHTML = tree;

  const flat = [res.folder].concat(res.files.map((f) => f.folder + '/' + f.name));
  $('btnCopyAll').onclick = (e) => copy(flat.join('\n'), e.target);
  $('btnCopyTree').onclick = (e) =>
    copy($('outTree').textContent.replace(/\(mandatory\)/g, '').trimEnd(), e.target);
}

/* ----------------------------------------------------------- check */
async function runCheck() {
  const name = $('checkInput').value.trim();
  const host = $('checkResult');
  if (!name) {
    host.className = 'empty';
    host.textContent = 'Paste a folder name first.';
    return;
  }

  const r = await fetch('/api/parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  const res = await r.json();

  host.className = '';
  host.innerHTML = '';

  const errors = (res.issues || []).filter((i) => i.level === 'error').length;
  const cat = BOOT.categories.find((c) => c.id === (res.matched || res.reads_as));

  const pill = $('checkVerdictPill');
  pill.className = 'pill ' + (errors ? 'bad' : (res.issues || []).length ? 'warn' : 'ok');
  pill.textContent = errors
    ? errors + (errors === 1 ? ' rule broken' : ' rules broken')
    : ((res.issues || []).length ? 'check the warnings' : 'spec compliant');

  /* The breakdown, in the same shape as the one on Create a name. */
  if (res.segments && res.segments.length) {
    const stage = document.createElement('div');
    stage.className = 'name-stage';
    const segs = document.createElement('div');
    segs.className = 'segs';
    renderSegments(segs, res.segments, name, false);
    stage.appendChild(segs);

    const verdict = document.createElement('div');
    verdict.className = 'verdict';
    stage.appendChild(verdict);
    host.appendChild(stage);
    renderVerdict(verdict, res.issues);

    // A name that matches is one thing; a name that was evidently meant to be
    // a category but breaks its rules is another, and must not be conflated.
    const reading = document.createElement('span');
    reading.className = 'pill ' + (res.matched ? 'info' : 'warn');
    reading.textContent = cat
      ? (res.matched ? 'Category ' + cat.spec_ref : 'Reads as ' + cat.spec_ref)
      : 'No pattern recognised';
    reading.title = cat ? cat.label : '';
    verdict.insertBefore(reading, verdict.firstChild);
  }

  if (!res.matched && !res.reads_as) {
    host.appendChild(issue('warning',
      'This does not match any naming pattern in the spec. It may be an older '
      + 'folder, or a category the spec does not cover.'));
  }

  if (!res.issues || res.issues.length === 0) {
    host.appendChild(issue('ok', 'No rule violations found.'));
  } else {
    res.issues.forEach((i) => host.appendChild(issue(i.level, i.message, i.rule)));
  }

  /* A suggestion is only ever a name the engine would have generated itself;
     it is offered, never applied. */
  if (res.suggestion) {
    const title = document.createElement('div');
    title.className = 'section-title';
    title.style.margin = '18px 0 8px';
    title.textContent = 'Suggested correction';
    host.appendChild(title);

    const bar = document.createElement('div');
    bar.className = 'nas ok';
    bar.append(iconSvg('<path d="m5 13 4 4L19 7"/>'),
      textSpan(res.suggestion),
      copyIconBtn(res.suggestion, 'Copy the corrected name'));
    host.appendChild(bar);

    const why = document.createElement('div');
    why.className = 'hint';
    why.textContent = 'Generated by the same engine that builds new names, so '
      + 'it passes every rule. The video code is copied across untouched. '
      + 'Check it before renaming anything on the NAS.';
    host.appendChild(why);
  }
}

/* ------------------------------------------------------- reference */
function renderReference() {
  const fill = (bodyId, rows) => {
    const tb = $(bodyId);
    tb.innerHTML = '';
    rows.forEach((r) => tb.appendChild(r));
  };

  const chRows = () => BOOT.channels.map((c) => {
    const tr = document.createElement('tr');
    tr.dataset.hay = (c.code + ' ' + c.name).toLowerCase();
    const link = c.url
      ? '<a href="' + esc(c.url) + '" target="_blank" rel="noopener">' + esc(c.name) + '</a>'
      : esc(c.name);
    tr.innerHTML = '<td><code>' + esc(c.code) + '</code></td>'
      + '<td><code>' + esc(c.prefix_literal) + '</code></td>'
      + '<td>' + link + '</td>'
      + '<td>' + esc(c.platform) + '</td>';
    return tr;
  });

  const deptRows = () => BOOT.departments.map((d) => {
    const tr = document.createElement('tr');
    tr.dataset.hay = (d.code + ' ' + d.name).toLowerCase();
    tr.innerHTML = '<td><code>' + esc(d.code) + '</code></td><td>' + esc(d.name) + '</td>';
    return tr;
  });

  const langRows = () => BOOT.languages.map((l) => {
    const tr = document.createElement('tr');
    tr.dataset.hay = (l.code + ' ' + l.name + ' ' + (l.group || '')).toLowerCase();
    tr.innerHTML = '<td><code>' + esc(l.code) + '</code></td>'
      + '<td>' + esc(l.name) + '</td>'
      + '<td>' + esc(l.group || '') + '</td>';
    return tr;
  });

  fill('chBody', chRows());
  fill('deptBody', deptRows());
  fill('langBody', langRows());

  const nasTb = $('nasBody');
  nasTb.innerHTML = '';
  BOOT.categories.forEach((c) => {
    if (!c.nas) return;
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + esc(c.spec_ref + '  ' + c.label) + '</td>'
      + '<td><code>' + esc(c.nas.path) + '</code></td>';
    nasTb.appendChild(tr);
  });
  Object.values(BOOT.nas.other || {}).forEach((o) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + esc(o.label) + '</td>'
      + '<td><code>' + esc(o.path) + '</code></td>';
    nasTb.appendChild(tr);
  });

  // One box across every table: nobody remembers which of the three a code
  // lives in, which was the point of looking it up.
  const bodies = ['chBody', 'deptBody', 'langBody', 'nasBody'];
  $('refSearch').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    let shown = 0;
    bodies.forEach((id) => {
      let hits = 0;
      [...$(id).children].forEach((tr) => {
        const hay = tr.dataset.hay || tr.textContent.toLowerCase();
        const hit = !q || hay.includes(q);
        tr.style.display = hit ? '' : 'none';
        if (hit) hits += 1;
      });
      // A table with nothing in it is noise, so its card steps aside.
      const card = $(id).closest('.card');
      if (card) card.style.display = (q && !hits) ? 'none' : '';
      shown += hits;
    });
    // ... and a column with no cards left in it closes up rather than
    // leaving a hole beside the results.
    document.querySelectorAll('#s-ref .grid2 > div').forEach((col) => {
      const live = [...col.querySelectorAll('.card')]
        .some((c) => c.style.display !== 'none');
      col.style.display = live ? '' : 'none';
    });

    $('refCount').textContent = q
      ? shown + ' match' + (shown === 1 ? '' : 'es') + ' across all tables'
      : 'One box for every table below.';
  });
}

/* ============================ SCAFFOLD + INGEST ==================== */

const DISK = {
  folder: null,      // the name currently being archived
  category: null,
  fields: null,
  target: null,      // absolute path, once the folders exist
  files: [],         // scanned source files, with editable roles
  scanRoot: null,
  ingested: 0,       // files actually archived, for the step rail
};

const ROLE_OPTIONS = [
  { value: 'output', label: 'Output MP4 (required)' },
  { value: 'fb_output', label: 'Facebook MP4' },
  { value: 'voice1', label: 'Voice 1' },
  { value: 'voice2', label: 'Voice 2' },
  { value: 'voice3', label: 'Voice 3' },
  { value: 'voice4', label: 'Voice 4' },
  { value: 'script', label: 'Script (docx)' },
  { value: 'subtitles', label: 'Subtitles (srt)' },
  { value: 'project', label: 'Project file' },
  { value: 'font', label: 'Font' },
  { value: 'skip', label: '- do not archive -' },
];

function wireDisk() {
  $('btnBrowseDest').onclick = () => browseInto('destRoot', 'Choose where the archive folder goes');
  $('btnBrowseSrc').onclick = () => browseInto('srcRoot', 'Choose the folder holding your files');
  $('btnScaffoldPlan').onclick = () => scaffold(false);
  $('btnScaffoldApply').onclick = () => scaffold(true);
  $('btnScan').onclick = scanSource;
  $('btnIngestPlan').onclick = () => ingest(false);
  $('btnIngestApply').onclick = () => ingest(true);
  $('btnHistRefresh').onclick = loadHistory;
  $('btnHistClear').onclick = clearHistory;

  $('ingestMode').onchange = () => {
    const isMove = $('ingestMode').value === 'move';
    $('moveConfirmRow').style.display = isMove ? 'flex' : 'none';
    if (!isMove) $('confirmMove').checked = false;
  };

  if (BOOT.settings && BOOT.settings.last_dest) $('destRoot').value = BOOT.settings.last_dest;
  if (BOOT.settings && BOOT.settings.last_source) $('srcRoot').value = BOOT.settings.last_source;
  if (BOOT.settings && BOOT.settings.on_conflict) $('onConflict').value = BOOT.settings.on_conflict;
}

/* Called by build() whenever a valid name exists, so this tab always
   reflects the name the user is actually looking at. */
function setDiskContext(res, fields) {
  const changed = DISK.folder !== res.folder;
  DISK.folder = res.folder;
  DISK.category = res.category;
  DISK.fields = Object.assign({}, fields);
  DISK.nas = res.nas;
  if (changed) {
    // A different name means the previous target no longer applies.
    DISK.target = null;
    DISK.ingested = 0;
    DISK.files = [];
    $('ingestOut').innerHTML = '';
    $('scaffoldOut').innerHTML = '';
  }
  renderDiskHeader();
}

function clearDiskContext() {
  DISK.folder = null;
  DISK.target = null;
  renderDiskHeader();
}

function renderDiskHeader() {
  const has = !!DISK.folder;
  $('diskNoName').style.display = has ? 'none' : 'block';
  $('diskWork').style.display = has ? 'block' : 'none';
  if (!has) return;

  $('diskFolder').textContent = DISK.folder;
  const cat = BOOT.categories.find((c) => c.id === DISK.category);
  $('diskMeta').textContent = cat ? cat.spec_ref + ' ' + cat.label : '';
  $('diskNasHint').innerHTML = DISK.nas
    ? 'Per Appendix 2 this belongs under <code>' + esc(DISK.nas.path)
      + '</code> (' + esc(DISK.nas.label) + ').'
    : '';
  $('ingestCard').style.display = (cat && cat.has_inner_files) ? 'block' : 'none';

  renderSteps();
  checkSeen();
}

/* The rail states which step you are on, not where the NAS lives, so a long
   destination is shown by its last two folders with the rest on hover. */
function shortPath(text) {
  const t = String(text || '');
  // Backslashes only: a category label such as "Sadhguru / Isha Foundation"
  // is prose, not a path, and must not be chopped up.
  if (!t.includes('\\') || t.length < 48) return t;
  const parts = t.replace(/\\+$/, '').split('\\');
  return '…\\' + parts.slice(-2).join('\\');
}

/* Which of the three steps is actually done, from the real state rather
   than from which button was pressed last. */

function renderSteps() {
  const cat = BOOT.categories.find((c) => c.id === DISK.category);
  const scanned = DISK.files && DISK.files.length;

  const set = (id, state, sub) => {
    const el = $(id);
    el.className = 'step' + (state ? ' ' + state : '');
    $(id + 'Sub').textContent = shortPath(sub);
    $(id + 'Sub').title = sub;
    const num = el.querySelector('.num');
    num.innerHTML = state === 'done'
      ? TICK.replace('<svg', '<svg width="12" height="12"')
      : num.dataset.n || num.textContent;
    if (!num.dataset.n) num.dataset.n = { stepName: '1', stepFolders: '2', stepFiles: '3' }[id];
    if (state !== 'done') num.textContent = num.dataset.n;
  };

  set('stepName', 'done', cat ? cat.spec_ref + ' ' + cat.label : '');
  set('stepFolders', DISK.target ? 'done' : 'now',
      DISK.target ? DISK.target : 'Not created yet');
  set('stepFiles',
      DISK.target ? (DISK.ingested ? 'done' : 'now') : '',
      DISK.ingested
        ? DISK.ingested + ' file(s) archived'
        : (scanned ? scanned + ' file(s) found, not archived yet'
                   : (DISK.target ? 'Point at your finished files'
                                  : 'Waiting for the folders')));
}

async function checkSeen() {
  const host = $('diskSeen');
  host.innerHTML = '';
  const r = await post('/api/seen', { folder: DISK.folder });
  if (r.seen && r.seen.length) {
    host.appendChild(issue('warning',
      'This exact folder name was already archived from this machine '
      + r.seen.length + ' time(s), most recently ' + r.seen[0].at
      + '. Check you are not archiving it twice.'));
  }
}

async function browseInto(inputId, title) {
  const r = await post('/api/pick-folder', {
    initial: $(inputId).value || null, title,
  });
  if (r.path) {
    $(inputId).value = r.path;
  } else if (r.error) {
    alert(r.error);
  }
}

/* ------------------------------------------------------- scaffold */
async function scaffold(apply) {
  const host = $('scaffoldOut');
  host.innerHTML = '';

  const payload = {
    dest_root: $('destRoot').value,
    folder: DISK.folder,
    category: DISK.category,
    fields: DISK.fields,
    mandatory_only: $('mandatoryOnly').checked,
  };

  const r = await post(apply ? '/api/scaffold/apply' : '/api/scaffold/plan', payload);

  if (r.error) {
    host.appendChild(issue('error', r.error));
    return;
  }

  if (apply) {
    DISK.target = r.target;
    renderSteps();
    host.appendChild(issue('ok',
      r.created.length
        ? 'Created ' + r.created.length + ' folder(s) at ' + r.target
        : 'Everything already existed at ' + r.target + ' - nothing changed.'));
    (r.warnings || []).forEach((w) => host.appendChild(issue('warning', w)));
    host.appendChild(pathBar(r.target));
    if (r.manifest) {
      host.appendChild(hintLine('manifest.json written (' + r.manifest.events
        + ' event' + (r.manifest.events === 1 ? '' : 's') + ' logged).'));
    }
  } else {
    (r.warnings || []).forEach((w) => host.appendChild(issue('warning', w)));
    host.appendChild(hintLine(
      r.to_create + ' of ' + r.steps.length + ' folders would be created:'));
    const box = document.createElement('div');
    box.className = 'boxed';
    box.style.marginTop = '8px';
    r.steps.forEach((s) => {
      const row = document.createElement('div');
      row.className = 'file-row';
      row.innerHTML =
        '<div class="file-main"><div class="file-name">' + esc(s.rel) + '</div>'
        + '<div class="file-meta">' + esc(s.note) + '</div></div>'
        + '<span class="file-tag ' + (s.exists ? 'opt' : 'must') + '">'
        + (s.exists ? 'exists' : 'new') + '</span>';
      box.appendChild(row);
    });
    host.appendChild(box);
  }
}

/* --------------------------------------------------------- scan */
async function scanSource() {
  const host = $('scanOut');
  host.innerHTML = '';
  $('ingestControls').style.display = 'none';

  const r = await post('/api/source/scan', { dir: $('srcRoot').value });
  if (r.error) {
    host.appendChild(issue('error', r.error));
    return;
  }
  if (!r.files.length) {
    host.appendChild(issue('warning', 'No files found in that folder.'));
    return;
  }

  DISK.files = r.files;
  DISK.scanRoot = r.root;
  renderSteps();

  if (r.truncated) {
    host.appendChild(issue('warning',
      'That folder holds a lot of files - only the first ' + r.files.length
      + ' were listed.'));
  }

  host.appendChild(hintLine('Found ' + r.files.length
    + ' file(s). Check the role guessed for each one:'));

  const box = document.createElement('div');
  box.className = 'boxed';
  box.style.marginTop = '8px';

  r.files.forEach((f, i) => {
    const row = document.createElement('div');
    row.className = 'file-row';

    const main = document.createElement('div');
    main.className = 'file-main';
    const nm = document.createElement('div');
    nm.className = 'file-name';
    nm.style.color = 'var(--text)';
    nm.textContent = f.rel;
    const meta = document.createElement('div');
    meta.className = 'file-meta';
    meta.textContent = humanSize(f.size) + (f.role_note ? '  ·  ' + f.role_note : '');
    main.append(nm, meta);

    const sel = document.createElement('select');
    sel.style.cssText = 'flex:0 0 195px;width:195px';
    ROLE_OPTIONS.forEach((o) => {
      const op = document.createElement('option');
      op.value = o.value;
      op.textContent = o.label;
      sel.appendChild(op);
    });
    sel.value = ROLE_OPTIONS.some((o) => o.value === f.role) ? f.role : 'skip';
    DISK.files[i].role = sel.value;
    sel.onchange = () => {
      DISK.files[i].role = sel.value;
      // Locked, so the server's guesser never overrides a deliberate choice.
      DISK.files[i].role_locked = true;
      $('ingestOut').innerHTML = '';
    };

    row.append(main, sel);
    box.appendChild(row);
  });

  host.appendChild(box);
  $('ingestControls').style.display = 'block';
}

/* ------------------------------------------------------- ingest */
async function ingest(apply) {
  const host = $('ingestOut');
  host.innerHTML = '';

  if (!DISK.target) {
    host.appendChild(issue('error',
      'Create the folders first (Step 1) so there is somewhere to put the files.'));
    return;
  }

  const mode = $('ingestMode').value;
  if (apply && mode === 'move' && !$('confirmMove').checked) {
    host.appendChild(issue('error',
      'Tick the confirmation box before moving files, or switch to Copy.'));
    return;
  }

  const payload = {
    target: DISK.target,
    folder: DISK.folder,
    category: DISK.category,
    fields: DISK.fields,
    files: DISK.files,
    mode,
    on_conflict: $('onConflict').value,
    source_dir: DISK.scanRoot,
    confirm_move: $('confirmMove').checked,
  };

  const r = await post(apply ? '/api/ingest/apply' : '/api/ingest/plan', payload);

  if (r.error) {
    host.appendChild(issue('error', r.error));
    return;
  }

  const rows = apply ? r.results : r.actions;

  if (apply) {
    DISK.ingested = r.transferred || 0;
    renderSteps();
    host.appendChild(issue(r.failed ? 'warning' : 'ok',
      r.transferred + ' file(s) ' + (r.mode === 'move' ? 'moved' : 'copied')
      + ' (' + humanSize(r.bytes) + '), ' + r.skipped + ' skipped'
      + (r.failed ? ', ' + r.failed + ' FAILED' : '') + '.'));
  } else {
    host.appendChild(hintLine('Dry run - nothing has been changed. '
      + r.will_transfer + ' file(s) would be '
      + (mode === 'move' ? 'moved' : 'copied') + ', ' + r.will_skip + ' skipped.'));
  }

  (r.warnings || []).forEach((w) => host.appendChild(issue('warning', w)));

  const box = document.createElement('div');
  box.className = 'boxed';
  box.style.marginTop = '10px';

  rows.forEach((a) => {
    const row = document.createElement('div');
    row.className = 'file-row';

    const main = document.createElement('div');
    main.className = 'file-main';

    const from = document.createElement('div');
    from.className = 'file-meta';
    from.textContent = a.name;

    const to = document.createElement('div');
    to.className = 'file-name';
    if (a.rel) {
      to.textContent = '→ ' + a.rel;
    } else {
      to.textContent = '→ not archived';
      to.style.color = 'var(--muted)';
    }

    main.append(from, to);

    if (a.reason) {
      const why = document.createElement('div');
      why.className = 'file-meta';
      why.textContent = a.reason;
      main.appendChild(why);
    }
    if (a.warn) {
      const w = document.createElement('div');
      w.className = 'file-meta';
      w.style.color = 'var(--warn)';
      w.textContent = a.warn;
      main.appendChild(w);
    }
    if (a.error) {
      const e = document.createElement('div');
      e.className = 'file-meta';
      e.style.color = 'var(--red)';
      e.textContent = a.error;
      main.appendChild(e);
    }

    const status = a.status || a.action;
    const tag = document.createElement('span');
    tag.className = 'file-tag ' + (status === 'failed' ? 'must' : 'opt');
    if (status === 'copied' || status === 'moved') {
      tag.style.cssText = 'background:var(--success-soft);color:var(--success)';
    } else if (status === 'copy' || status === 'move') {
      tag.style.cssText = 'background:var(--accent-soft);color:var(--accent)';
    }
    tag.textContent = status;

    row.append(main, tag);
    box.appendChild(row);
  });

  host.appendChild(box);

  if (apply) {
    host.appendChild(pathBar(r.target));
    loadHistory();
  }
}

/* ------------------------------------------------------ history */
async function loadHistory() {
  const r = await fetch('/api/history').then((x) => x.json());
  const tb = $('histBody');
  tb.innerHTML = '';
  $('histPath').textContent = 'Logged to ' + (r.path || '');
  $('histEmpty').style.display = (r.entries || []).length ? 'none' : 'block';

  // Nothing to clear on an empty log; the button says so rather than no-opping.
  $('btnHistClear').disabled = !(r.entries || []).length;

  (r.entries || []).forEach((e) => {
    const tr = document.createElement('tr');
    const result = e.action === 'ingest'
      ? (e.transferred || 0) + ' file(s) ' + (e.mode === 'move' ? 'moved' : 'copied')
        + (e.failed ? ', ' + e.failed + ' failed' : '')
      : (e.created || 0) + ' folder(s) created';
    tr.innerHTML = '<td>' + esc((e.at || '').replace('T', ' ')) + '</td>'
      + '<td>' + esc(e.action || '') + '</td>'
      + '<td><code>' + esc(e.folder || '') + '</code></td>'
      + '<td>' + esc(result) + '</td>';
    tb.appendChild(tr);
  });
}

/* The log is also what warns you about re-archiving a name, so say so before
   wiping it -- and keep the old rows in a file the user can rename back. */
async function clearHistory() {
  const shown = $('histBody').children.length;
  const ok = confirm(
    'Clear the archiving history on this machine?\n\n'
    + shown + ' entr' + (shown === 1 ? 'y' : 'ies') + ' will be removed from '
    + 'this list, and the tool will stop warning you when a folder name has '
    + 'been archived before.\n\n'
    + 'The old log is kept as a dated backup file next to it, so this can be '
    + 'undone by hand. No archived folders or files are touched.');
  if (!ok) return;

  const r = await post('/api/history/clear', {});
  if (r.error) {
    alert(r.error);
    return;
  }
  await loadHistory();
  alert('History cleared — ' + (r.cleared || 0) + ' entr'
        + (r.cleared === 1 ? 'y' : 'ies') + ' removed.'
        + (r.backup ? '\n\nBacked up to:\n' + r.backup : ''));
}

/* ------------------------------------------------ small helpers */
async function post(route, payload) {
  try {
    const r = await fetch(route, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await r.json();
  } catch (e) {
    return { error: 'Could not reach the local app. Is it still running?' };
  }
}

function hintLine(text) {
  const d = document.createElement('div');
  d.className = 'hint';
  d.style.marginTop = '10px';
  d.textContent = text;
  return d;
}

function pathBar(path) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;gap:9px;align-items:center;margin-top:10px';
  const p = document.createElement('div');
  p.className = 'nas';
  p.style.flex = '1';
  p.textContent = path;
  const open = document.createElement('button');
  open.className = 'copy';
  open.textContent = 'Open folder';
  open.onclick = async () => {
    const r = await post('/api/reveal', { path });
    if (r.error) alert(r.error);
  };
  const cp = document.createElement('button');
  cp.className = 'copy';
  cp.textContent = 'Copy path';
  cp.onclick = (e) => copy(path, e.target);
  wrap.append(p, open, cp);
  return wrap;
}

function humanSize(bytes) {
  const b = Number(bytes) || 0;
  if (b < 1024) return b + ' B';
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
  if (b < 1024 * 1024 * 1024) return (b / 1048576).toFixed(1) + ' MB';
  return (b / 1073741824).toFixed(2) + ' GB';
}

/* ---------------------------------------------------------- helpers */
function issue(level, message, rule) {
  const d = document.createElement('div');
  d.className = 'issue ' + level;
  const icon = level === 'error' ? '✖' : level === 'warning' ? '⚠' : '✔';
  d.innerHTML = '<span>' + icon + '</span><span style="flex:1">' + esc(message) + '</span>'
    + (rule ? '<span class="rule">' + esc(rule) + '</span>' : '');
  return d;
}

function copy(text, btn) {
  const done = () => {
    toast('Copied to clipboard');
    if (!btn) return;
    const old = btn.textContent;
    btn.textContent = '✓ Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = old; btn.classList.remove('copied'); }, 1600);
  };
  writeClipboard(text, done);
}

/* An icon button has no label to swap, so it flashes and the toast carries
   the message. */
function copyIcon(text, btn) {
  writeClipboard(text, () => {
    toast('Copied to clipboard');
    if (!btn) return;
    btn.classList.add('copied');
    setTimeout(() => btn.classList.remove('copied'), 1600);
  });
}

function writeClipboard(text, done) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

let toastTimer = null;
function toast(message) {
  const el = $('toast');
  $('toastText').textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 1700);
}

// http://127.0.0.1 is a secure context in Chrome and Edge, but this keeps the
// copy buttons working in anything older.
function fallbackCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); done(); } catch (e) { /* nothing else to try */ }
  document.body.removeChild(ta);
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Remember that the user picked a channel deliberately, so URL lookup
// never silently overrides them.
document.addEventListener('change', (e) => {
  if (e.target.dataset && e.target.dataset.key === 'channel' && CAT) {
    STATE[CAT.id]._channel_touched = true;
  }
});

boot();
