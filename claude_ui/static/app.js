let REFRESH_MS = 30_000;
let refreshTimer = null;
let sessions = [];
let showStale = false;
let projectFilter = '';
let activePanel = null;

const tbody = document.getElementById('sessions-body');
const table = document.getElementById('sessions-table');
const emptyState = document.getElementById('empty-state');
const summaryCount = document.getElementById('summary-count');
const indicator = document.getElementById('refresh-btn');
indicator.addEventListener('click', syncAndRefresh);
const showStaleCheckbox = document.getElementById('show-stale');
const themeToggle = document.getElementById('theme-toggle');
const projectSelect = document.getElementById('project-filter');
const panel = document.getElementById('side-panel');
const panelClose = document.getElementById('panel-close');
const settingsBtn = document.getElementById('settings-btn');
const settingsOverlay = document.getElementById('settings-overlay');

// Theme — dark default, persist to localStorage
const savedTheme = localStorage.getItem('membridge-theme') || 'dark';
applyTheme(savedTheme);

themeToggle.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('membridge-theme', next);
});

function applyTheme(theme) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    themeToggle.textContent = '☾';
    themeToggle.title = 'Switch to dark mode';
  } else {
    document.documentElement.removeAttribute('data-theme');
    themeToggle.textContent = '☀';
    themeToggle.title = 'Switch to light mode';
  }
}

// Restore persisted filter state
showStale = localStorage.getItem('mb-show-stale') === 'true';
showStaleCheckbox.checked = showStale;
projectFilter = localStorage.getItem('mb-project-filter') || '';

showStaleCheckbox.addEventListener('change', () => {
  showStale = showStaleCheckbox.checked;
  localStorage.setItem('mb-show-stale', showStale);
  render(sessions);
});

projectSelect.addEventListener('change', () => {
  projectFilter = projectSelect.value;
  localStorage.setItem('mb-project-filter', projectFilter);
  render(sessions);
});

panelClose.addEventListener('click', closePanel);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (settingsOverlay.classList.contains('open')) closeSettings();
    else closePanel();
  }
});

// ── Settings ──────────────────────────────────────────────────────────────────

settingsBtn.addEventListener('click', openSettings);
document.getElementById('settings-cancel').addEventListener('click', closeSettings);
document.getElementById('settings-save').addEventListener('click', saveSettings);
settingsOverlay.addEventListener('click', e => { if (e.target === settingsOverlay) closeSettings(); });

async function openSettings() {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    document.getElementById('set-active').value = s.active_threshold_secs;
    document.getElementById('set-idle').value = s.idle_threshold_secs;
    document.getElementById('set-refresh').value = s.refresh_interval_secs;
  } catch (e) {
    console.error('Failed to load settings', e);
  }
  settingsOverlay.classList.add('open');
}

function closeSettings() {
  settingsOverlay.classList.remove('open');
}

async function saveSettings() {
  const active = parseInt(document.getElementById('set-active').value, 10);
  const idle = parseInt(document.getElementById('set-idle').value, 10);
  const refresh = parseInt(document.getElementById('set-refresh').value, 10);
  if (isNaN(active) || isNaN(idle) || isNaN(refresh)) return;

  try {
    await fetch('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        active_threshold_secs: active,
        idle_threshold_secs: idle,
        refresh_interval_secs: refresh,
      }),
    });
    REFRESH_MS = refresh * 1000;
    restartRefreshTimer();
    closeSettings();
    fetchSessions();
  } catch (e) {
    console.error('Failed to save settings', e);
  }
}

// ── Data fetching ─────────────────────────────────────────────────────────────

async function syncAndRefresh() {
  indicator.classList.add('spinning');
  indicator.title = 'Syncing tab names…';
  try {
    await fetch('http://localhost:7843/sync-tabs', { method: 'POST' });
  } catch (_) {}
  // iTerm2 API takes ~30s; poll every 5s for up to 40s then give up
  let waited = 0;
  const poll = setInterval(async () => {
    waited += 5;
    await fetchSessions();
    if (waited >= 40) {
      clearInterval(poll);
      indicator.classList.remove('spinning');
      indicator.title = 'Click to refresh';
    }
  }, 5000);
}

function restartRefreshTimer() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(fetchSessions, REFRESH_MS);
}

async function fetchSessions() {
  indicator.classList.add('spinning');
  try {
    const res = await fetch('/api/sessions');
    sessions = await res.json();
    updateProjectFilter(sessions);
    render(sessions);
  } catch (e) {
    console.error('Fetch failed', e);
  } finally {
    // small delay so single-click spin is visible
    setTimeout(() => indicator.classList.remove('spinning'), 400);
  }
}

function updateProjectFilter(all) {
  const projects = [...new Set(all.map(s => s.project_name))].sort();
  const current = projectSelect.value;
  projectSelect.innerHTML = '<option value="">All projects</option>';
  for (const p of projects) {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    if (p === current) opt.selected = true;
    projectSelect.appendChild(opt);
  }
}

function render(all) {
  let visible = showStale ? all : all.filter(s => s.status !== 'stale');
  if (projectFilter) visible = visible.filter(s => s.project_name === projectFilter);

  const active = all.filter(s => s.status === 'active').length;
  const idle = all.filter(s => s.status === 'idle').length;
  summaryCount.textContent = `${active} active · ${idle} idle · ${all.length} total`;

  if (visible.length === 0) {
    table.style.display = 'none';
    emptyState.style.display = 'block';
    return;
  }

  table.style.display = 'table';
  emptyState.style.display = 'none';
  tbody.innerHTML = '';

  for (const s of visible) {
    tbody.appendChild(buildRow(s));
  }

  if (activePanel) {
    const fresh = sessions.find(s => s.session_id === activePanel);
    if (fresh) openPanel(fresh, false);
  }
}

function buildRow(s) {
  const tr = document.createElement('tr');
  if (activePanel === s.session_id) tr.classList.add('row-active');

  const statusTd = td('col-status');
  const badge = document.createElement('span');
  badge.className = `pill badge-${s.status}`;
  badge.textContent = s.status;
  statusTd.appendChild(badge);
  tr.appendChild(statusTd);

  const projTd = td('col-project');
  projTd.innerHTML = `<div class="project-name">${esc(s.project_name)}</div><div class="session-id">${esc(s.session_id.slice(0, 8))}…</div>`;
  tr.appendChild(projTd);

  const branchTd = td('col-branch');
  branchTd.innerHTML = `<span class="branch-text">${esc(s.git_branch || '—')}</span>`;
  tr.appendChild(branchTd);

  const lastTd = td('col-last');
  lastTd.innerHTML = `<span class="last-text" title="${esc(s.last_seen)}">${relativeTime(s.last_seen)}</span>`;
  tr.appendChild(lastTd);

  const countTd = td('col-prompts');
  countTd.innerHTML = `<span class="count-text">${s.prompt_count}</span>`;
  tr.appendChild(countTd);

  const summaryTd = td('col-summary');
  const summaryEl = document.createElement('div');
  summaryEl.className = 'summary-text' + (s.summary ? '' : ' empty');
  summaryEl.textContent = s.summary ? s.summary.slice(0, 120) + (s.summary.length > 120 ? '…' : '') : '';
  if (s.summary && s.summary_source === 'auto') {
    const autoBadge = document.createElement('span');
    autoBadge.className = 'auto-badge';
    autoBadge.textContent = 'auto';
    summaryEl.appendChild(autoBadge);
  }
  summaryTd.appendChild(summaryEl);
  tr.appendChild(summaryTd);

  const chevTd = td('col-chevron');
  chevTd.innerHTML = `<span class="chevron">›</span>`;
  tr.appendChild(chevTd);

  tr.addEventListener('click', () => openPanel(s, true));
  tr.style.cursor = 'pointer';

  return tr;
}

// ── Side panel ────────────────────────────────────────────────────────────────

function openPanel(s, scrollIntoView) {
  activePanel = s.session_id;

  document.querySelectorAll('#sessions-body tr').forEach(r => r.classList.remove('row-active'));
  document.querySelectorAll('#sessions-body tr').forEach(r => {
    const idEl = r.querySelector('.session-id');
    if (idEl && idEl.textContent.startsWith(s.session_id.slice(0, 8))) {
      r.classList.add('row-active');
      if (scrollIntoView) r.scrollIntoView({ block: 'nearest' });
    }
  });

  document.getElementById('panel-project').textContent = s.project_name;
  document.getElementById('panel-status').textContent = s.status;
  document.getElementById('panel-status').className = `pill badge-${s.status}`;
  document.getElementById('panel-session-id').textContent = s.session_id;
  document.getElementById('panel-cwd').textContent = s.cwd;
  document.getElementById('panel-branch').textContent = s.git_branch || '—';
  document.getElementById('panel-iterm').textContent = s.iterm_tab || '—';
  document.getElementById('panel-pid').textContent = s.pid || '—';
  document.getElementById('panel-first').textContent = formatDateTime(s.first_seen);
  document.getElementById('panel-last').textContent = relativeTime(s.last_seen);
  document.getElementById('panel-prompts').textContent = s.prompt_count;
  document.getElementById('panel-summary').textContent = s.summary || '';

  const focusBtn = document.getElementById('panel-focus-btn');
  focusBtn.textContent = s.pid ? '⌘ Focus' : '⌘ Open';
  focusBtn.onclick = async () => {
    focusBtn.textContent = '…';
    try {
      const res = await fetch('http://localhost:7843/focus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: s.session_id, pid: s.pid || null, cwd: s.cwd || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      focusBtn.textContent = data.action === 'focused' ? '✓ Focused' : '✓ Opened';
    } catch (err) {
      focusBtn.textContent = '✗ Failed';
      console.error('Focus error:', err);
    }
    setTimeout(() => { focusBtn.textContent = s.pid ? '⌘ Focus' : '⌘ Open'; }, 2500);
  };

  const resumeBtn = document.getElementById('panel-resume-btn');
  resumeBtn.onclick = () => {
    navigator.clipboard.writeText(`claude --resume ${s.session_id}`).then(() => {
      resumeBtn.textContent = 'Copied!';
      resumeBtn.classList.add('copied');
      setTimeout(() => { resumeBtn.textContent = 'Copy resume'; resumeBtn.classList.remove('copied'); }, 2000);
    });
  };

  const summariseBtn = document.getElementById('panel-summarise-btn');
  summariseBtn.textContent = '↻ Summarise';
  summariseBtn.onclick = async () => {
    summariseBtn.textContent = '…';
    summariseBtn.disabled = true;
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}/summarise`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        summariseBtn.textContent = err.detail === 'Transcript not found' ? '✗ No transcript' : '✗ Failed';
      } else {
        summariseBtn.textContent = '✓ Queued';
        // Poll once after 8s to pick up the new summary
        setTimeout(fetchSessions, 8000);
      }
    } catch (_) {
      summariseBtn.textContent = '✗ Error';
    }
    setTimeout(() => { summariseBtn.textContent = '↻ Summarise'; summariseBtn.disabled = false; }, 3000);
  };

  const deleteBtn = document.getElementById('panel-delete-btn');
  deleteBtn.textContent = '✕ Delete';
  deleteBtn.onclick = async () => {
    if (!confirm(`Delete session ${s.session_id.slice(0, 8)}…? This cannot be undone.`)) return;
    try {
      await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, { method: 'DELETE' });
      closePanel();
      fetchSessions();
    } catch (_) {}
  };

  const notesArea = document.getElementById('panel-notes');
  notesArea.value = s.notes || '';
  notesArea._session = s;

  panel.classList.add('open');
  document.getElementById('layout').classList.add('panel-open');
}

function closePanel() {
  activePanel = null;
  panel.classList.remove('open');
  document.getElementById('layout').classList.remove('panel-open');
  document.querySelectorAll('#sessions-body tr').forEach(r => r.classList.remove('row-active'));
}

document.getElementById('panel-notes').addEventListener('input', function() {
  clearTimeout(this._saveTimer);
  this._saveTimer = setTimeout(() => saveNotes(this), 1000);
});

async function saveNotes(textarea) {
  const s = textarea._session;
  if (!s) return;
  await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: textarea.value }),
  });
  s.notes = textarea.value;
}

document.getElementById('panel-summary').addEventListener('click', function() {
  const s = sessions.find(x => x.session_id === activePanel);
  if (!s) return;
  startPanelSummaryEdit(s, this);
});

function startPanelSummaryEdit(s, el) {
  const orig = s.summary || '';
  const textarea = document.createElement('textarea');
  textarea.className = 'summary-edit panel-summary-edit';
  textarea.value = orig;
  el.replaceWith(textarea);
  textarea.focus();

  async function save() {
    const newSummary = textarea.value.trim();
    if (newSummary !== orig.trim()) {
      await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summary: newSummary }),
      });
      s.summary = newSummary;
      s.summary_source = 'user';
    }
    const newEl = document.createElement('div');
    newEl.id = 'panel-summary';
    newEl.className = 'panel-summary-text';
    newEl.textContent = s.summary || '';
    newEl.title = 'Click to edit';
    newEl.addEventListener('click', function() { startPanelSummaryEdit(s, this); });
    textarea.replaceWith(newEl);
  }

  textarea.addEventListener('blur', save);
  textarea.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const newEl = document.createElement('div');
      newEl.id = 'panel-summary';
      newEl.className = 'panel-summary-text';
      newEl.textContent = s.summary || '';
      newEl.title = 'Click to edit';
      newEl.addEventListener('click', function() { startPanelSummaryEdit(s, this); });
      textarea.replaceWith(newEl);
    }
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function td(cls) {
  const el = document.createElement('td');
  if (cls) el.className = cls;
  return el;
}

function esc(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function relativeTime(isoStr) {
  if (!isoStr) return '—';
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function formatDateTime(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleString();
}

// ── Boot ──────────────────────────────────────────────────────────────────────

(async () => {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    REFRESH_MS = s.refresh_interval_secs * 1000;
  } catch (_) {}
  fetchSessions();
  restartRefreshTimer();
})();
