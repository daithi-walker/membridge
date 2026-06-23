let REFRESH_MS = 30_000;
let refreshTimer = null;
let sessions = [];
let showStale = false;
let showArchived = false;
let projectFilter = new Set(); // empty = all projects
let activePanel = null;

const tbody = document.getElementById('sessions-body');
const table = document.getElementById('sessions-table');
const emptyState = document.getElementById('empty-state');
const summaryCount = document.getElementById('summary-count');
const indicator = document.getElementById('refresh-btn');
indicator.addEventListener('click', syncAndRefresh);
const showStaleCheckbox = document.getElementById('show-stale');
const showArchivedCheckbox = document.getElementById('show-archived');
const themeToggle = document.getElementById('theme-toggle');
const projFilterBtn = document.getElementById('project-filter-btn');
const projFilterDropdown = document.getElementById('project-filter-dropdown');
const projCheckboxes = document.getElementById('proj-checkboxes');
const panelOverlay = document.getElementById('panel-overlay');
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
showArchived = localStorage.getItem('mb-show-archived') === 'true';
showArchivedCheckbox.checked = showArchived;
try {
  const stored = JSON.parse(localStorage.getItem('mb-project-filter') || '[]');
  projectFilter = new Set(stored);
} catch (_) { projectFilter = new Set(); }

showStaleCheckbox.addEventListener('change', () => {
  showStale = showStaleCheckbox.checked;
  localStorage.setItem('mb-show-stale', showStale);
  render(sessions);
});

showArchivedCheckbox.addEventListener('change', () => {
  showArchived = showArchivedCheckbox.checked;
  localStorage.setItem('mb-show-archived', showArchived);
  render(sessions);
});

// Project filter dropdown
projFilterBtn.addEventListener('click', e => {
  e.stopPropagation();
  const open = projFilterDropdown.style.display !== 'none';
  projFilterDropdown.style.display = open ? 'none' : 'block';
});
document.addEventListener('click', () => { projFilterDropdown.style.display = 'none'; });
projFilterDropdown.addEventListener('click', e => e.stopPropagation());

document.getElementById('proj-select-all').addEventListener('click', () => {
  projCheckboxes.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = true; });
  projectFilter = new Set(); // empty = all
  saveProjectFilter();
  render(sessions);
});
document.getElementById('proj-select-none').addEventListener('click', () => {
  projCheckboxes.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = false; });
  projectFilter = new Set(['__none__']); // sentinel: show nothing
  saveProjectFilter();
  render(sessions);
});

function saveProjectFilter() {
  localStorage.setItem('mb-project-filter', JSON.stringify([...projectFilter]));
  // Button is "active" only when a real subset is selected (not all, not none)
  const isSubset = projectFilter.size > 0 && !projectFilter.has('__none__');
  projFilterBtn.classList.toggle('active', isSubset || projectFilter.has('__none__'));
}

panelClose.addEventListener('click', closePanel);
panelOverlay.addEventListener('click', e => { if (e.target === panelOverlay) closePanel(); });
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
  projCheckboxes.innerHTML = '';
  for (const p of projects) {
    const label = document.createElement('label');
    label.className = 'proj-check-label';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = p;
    // checked = shown; empty set means all shown
    cb.checked = projectFilter.size === 0 || projectFilter.has(p);
    cb.addEventListener('change', () => {
      // Rebuild inclusion set from current checkbox state
      const checked = [...projCheckboxes.querySelectorAll('input')].filter(c => c.checked).map(c => c.value);
      if (checked.length === projects.length) {
        projectFilter = new Set(); // all selected = no filter
      } else if (checked.length === 0) {
        projectFilter = new Set(['__none__']); // none selected
      } else {
        projectFilter = new Set(checked);
      }
      saveProjectFilter();
      render(sessions);
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(p));
    projCheckboxes.appendChild(label);
  }
  saveProjectFilter();
}

function render(all) {
  let visible = showStale ? all : all.filter(s => s.status !== 'stale');
  if (!showArchived) visible = visible.filter(s => !s.archived);
  if (projectFilter.has('__none__')) {
    visible = [];
  } else if (projectFilter.size > 0) {
    visible = visible.filter(s => projectFilter.has(s.project_name));
  }

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
  if (s.archived) tr.classList.add('row-archived');

  const statusTd = td('col-status');
  const badge = document.createElement('span');
  badge.className = `pill badge-${s.status}`;
  badge.textContent = s.status;
  statusTd.appendChild(badge);
  tr.appendChild(statusTd);

  const projTd = td('col-project');
  projTd.innerHTML = `<div class="project-name">${esc(s.project_name)}</div><div class="session-id">${esc(s.session_id.slice(0, 8))}…</div>`;
  tr.appendChild(projTd);

  const itermTd = td('col-iterm');
  itermTd.innerHTML = `<span class="iterm-text">${esc(s.iterm_tab || '—')}</span>`;
  tr.appendChild(itermTd);

  const branchTd = td('col-branch');
  branchTd.innerHTML = `<span class="branch-text">${esc(s.git_branch || '—')}</span>`;
  tr.appendChild(branchTd);

  const lastTd = td('col-last');
  lastTd.innerHTML = `<span class="last-text" title="${esc(s.last_seen)}">${relativeTime(s.last_seen)}</span>`;
  tr.appendChild(lastTd);

  const countTd = td('col-prompts');
  countTd.innerHTML = `<span class="count-text">${s.prompt_count}</span>`;
  tr.appendChild(countTd);

  const descTd = td('col-desc');
  descTd.style.cssText = 'font-size:12px;color:var(--text-muted)';
  const _desc = s.description ? stripMd(s.description) : '';
  descTd.textContent = _desc.slice(0, 100) + (_desc.length > 100 ? '…' : '');
  tr.appendChild(descTd);

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
  renderMarkdown(document.getElementById('panel-summary'), s.description || '');

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

  loadHistory(s.session_id);

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
        setTimeout(async () => {
          await fetchSessions();
          await loadHistory(s.session_id);
        }, 8000);
      }
    } catch (_) {
      summariseBtn.textContent = '✗ Error';
    }
    setTimeout(() => { summariseBtn.textContent = '↻ Summarise'; summariseBtn.disabled = false; }, 3000);
  };

  const archiveBtn = document.getElementById('panel-archive-btn');
  const updateArchiveBtn = () => {
    archiveBtn.textContent = s.archived ? 'Unarchive' : 'Archive';
    archiveBtn.classList.toggle('archived', !!s.archived);
  };
  updateArchiveBtn();
  archiveBtn.onclick = async () => {
    s.archived = !s.archived;
    await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived: s.archived }),
    });
    updateArchiveBtn();
    fetchSessions();
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

  panelOverlay.classList.add('open');
}

async function loadHistory(sessionId) {
  const historyList = document.getElementById('panel-history-list');
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/summaries`);
    const entries = await res.json();
    if (!entries.length) {
      historyList.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:4px 0">No summaries yet.</div>';
      return;
    }

    // Group by file_path (skill entries), ungrouped for auto/user
    const groups = [];
    const byFile = new Map();
    for (const e of entries) {
      if (e.file_path) {
        if (!byFile.has(e.file_path)) {
          const g = { file_path: e.file_path, entries: [] };
          byFile.set(e.file_path, g);
          groups.push(g);
        }
        byFile.get(e.file_path).entries.push(e);
      } else {
        groups.push({ file_path: null, entries: [e] });
      }
    }

    historyList.innerHTML = '';
    for (const g of groups) {
      if (g.file_path) {
        // Collapsible file group
        const label = g.file_path.split('/').pop();
        const groupEl = document.createElement('div');
        groupEl.className = 'history-group';
        const header = document.createElement('div');
        header.className = 'history-group-header';
        header.innerHTML = `<span class="history-group-chevron">▾</span><span>${esc(label)}</span><span style="font-weight:400;margin-left:auto">${relativeTime(g.entries[0].created_at)}</span>`;
        header.addEventListener('click', () => groupEl.classList.toggle('collapsed'));
        const body = document.createElement('div');
        body.className = 'history-group-body';
        for (const e of g.entries) {
          body.appendChild(makeHistoryEntry(e));
        }
        groupEl.appendChild(header);
        groupEl.appendChild(body);
        historyList.appendChild(groupEl);
      } else {
        historyList.appendChild(makeHistoryEntry(g.entries[0]));
      }
    }
  } catch (_) {
    historyList.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Failed to load history.</div>';
  }
}

function makeHistoryEntry(e) {
  const div = document.createElement('div');
  div.className = 'history-entry';
  const meta = document.createElement('div');
  meta.className = 'history-meta';
  meta.innerHTML = `<span class="history-source history-source-${esc(e.source)}">${esc(e.source)}</span><span>${relativeTime(e.created_at)}</span>`;
  const text = document.createElement('div');
  text.className = 'history-text';
  renderMarkdown(text, e.text);
  div.appendChild(meta);
  div.appendChild(text);
  return div;
}

function closePanel() {
  activePanel = null;
  panelOverlay.classList.remove('open');
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
  const orig = s.description || '';
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
        body: JSON.stringify({ description: newSummary }),
      });
      s.description = newSummary;
      s.description_source = 'user';
      await loadHistory(s.session_id);
    }
    const newEl = makeSummaryEl(s);
    textarea.replaceWith(newEl);
  }

  textarea.addEventListener('blur', save);
  textarea.addEventListener('keydown', e => {
    if (e.key === 'Escape') textarea.replaceWith(makeSummaryEl(s));
  });
}

function makeSummaryEl(s) {
  const el = document.createElement('div');
  el.id = 'panel-summary';
  el.className = 'panel-summary-text';
  el.title = 'Click to edit';
  renderMarkdown(el, s.description || '');
  el.addEventListener('click', function() { startPanelSummaryEdit(s, this); });
  return el;
}

function stripMd(text) {
  return text
    .replace(/^#{1,6}\s+/gm, '')     // headings
    .replace(/\*\*(.+?)\*\*/g, '$1') // bold
    .replace(/\*(.+?)\*/g, '$1')     // italic
    .replace(/^[-*+]\s+/gm, '')      // list bullets
    .replace(/`(.+?)`/g, '$1')       // inline code
    .replace(/\n+/g, ' ')            // newlines → space
    .trim();
}

function renderMarkdown(el, text) {
  if (!text) { el.innerHTML = ''; return; }
  if (typeof marked !== 'undefined') {
    el.innerHTML = marked.parse(text, { breaks: true, gfm: true });
    el.classList.add('md-prose');
  } else {
    el.textContent = text;
  }
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
