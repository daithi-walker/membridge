const REFRESH_MS = 30_000;
let sessions = [];
let showStale = false;
let projectFilter = '';
let activePanel = null;

const tbody = document.getElementById('sessions-body');
const table = document.getElementById('sessions-table');
const emptyState = document.getElementById('empty-state');
const summaryCount = document.getElementById('summary-count');
const indicator = document.getElementById('refresh-indicator');
const showStaleCheckbox = document.getElementById('show-stale');
const themeToggle = document.getElementById('theme-toggle');
const projectSelect = document.getElementById('project-filter');
const panel = document.getElementById('side-panel');
const panelClose = document.getElementById('panel-close');

// Theme — dark default, persist to localStorage
const savedTheme = localStorage.getItem('claude-ui-theme') || 'dark';
applyTheme(savedTheme);

themeToggle.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('claude-ui-theme', next);
});

function applyTheme(theme) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    themeToggle.textContent = 'Dark';
  } else {
    document.documentElement.removeAttribute('data-theme');
    themeToggle.textContent = 'Light';
  }
}

showStaleCheckbox.addEventListener('change', () => {
  showStale = showStaleCheckbox.checked;
  render(sessions);
});

projectSelect.addEventListener('change', () => {
  projectFilter = projectSelect.value;
  render(sessions);
});

panelClose.addEventListener('click', closePanel);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

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
    indicator.classList.remove('spinning');
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

  // Re-render open panel if its session was refreshed
  if (activePanel) {
    const fresh = sessions.find(s => s.session_id === activePanel);
    if (fresh) openPanel(fresh, false);
  }
}

function buildRow(s) {
  const tr = document.createElement('tr');
  if (activePanel === s.session_id) tr.classList.add('row-active');

  // Status
  const statusTd = td('col-status');
  const badge = document.createElement('span');
  badge.className = `pill badge-${s.status}`;
  badge.textContent = s.status;
  statusTd.appendChild(badge);
  tr.appendChild(statusTd);

  // Project + session ID
  const projTd = td('col-project');
  projTd.innerHTML = `<div class="project-name">${esc(s.project_name)}</div><div class="session-id">${esc(s.session_id.slice(0, 8))}…</div>`;
  tr.appendChild(projTd);

  // Branch
  const branchTd = td('col-branch');
  branchTd.innerHTML = `<span class="branch-text">${esc(s.git_branch || '—')}</span>`;
  tr.appendChild(branchTd);

  // Last active
  const lastTd = td('col-last');
  lastTd.innerHTML = `<span class="last-text" title="${esc(s.last_seen)}">${relativeTime(s.last_seen)}</span>`;
  tr.appendChild(lastTd);

  // Prompt count
  const countTd = td('col-prompts');
  countTd.innerHTML = `<span class="count-text">${s.prompt_count}</span>`;
  tr.appendChild(countTd);

  // Summary (short, read-only in table — edit in panel)
  const summaryTd = td('col-summary');
  const summaryEl = document.createElement('div');
  summaryEl.className = 'summary-text' + (s.summary ? '' : ' empty');
  summaryEl.textContent = s.summary ? s.summary.slice(0, 120) + (s.summary.length > 120 ? '…' : '') : '';
  if (!s.summary) {
    summaryEl.textContent = '';
  }
  if (s.summary && s.summary_source === 'auto') {
    const autoBadge = document.createElement('span');
    autoBadge.className = 'auto-badge';
    autoBadge.textContent = 'auto';
    summaryEl.appendChild(autoBadge);
  }
  summaryTd.appendChild(summaryEl);
  tr.appendChild(summaryTd);

  // Chevron — opens panel
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

  // Highlight row
  document.querySelectorAll('#sessions-body tr').forEach(r => r.classList.remove('row-active'));
  const rows = document.querySelectorAll('#sessions-body tr');
  rows.forEach(r => {
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
  focusBtn.textContent = s.iterm_tab ? '⌘ Focus' : '⌘ Open';
  focusBtn.onclick = async () => {
    focusBtn.textContent = '…';
    try {
      const res = await fetch('http://localhost:7843/focus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: s.session_id, tab: s.iterm_tab || '' }),
      });
      const data = await res.json();
      focusBtn.textContent = data.action === 'focused' ? '✓ Focused' : '✓ Opened';
    } catch {
      focusBtn.textContent = '✗ No focus server';
    }
    setTimeout(() => { focusBtn.textContent = s.iterm_tab ? '⌘ Focus' : '⌘ Open'; }, 2000);
  };

  const resumeBtn = document.getElementById('panel-resume-btn');
  resumeBtn.onclick = () => {
    const cmd = `claude --resume ${s.session_id}`;
    navigator.clipboard.writeText(cmd).then(() => {
      resumeBtn.textContent = 'Copied!';
      resumeBtn.classList.add('copied');
      setTimeout(() => { resumeBtn.textContent = 'Copy resume'; resumeBtn.classList.remove('copied'); }, 2000);
    });
  };

  // Notes — editable textarea
  const notesArea = document.getElementById('panel-notes');
  notesArea.value = s.notes || '';
  notesArea._session = s;
  notesArea._saveTimer = null;

  panel.classList.add('open');
  document.getElementById('layout').classList.add('panel-open');
}

function closePanel() {
  activePanel = null;
  panel.classList.remove('open');
  document.getElementById('layout').classList.remove('panel-open');
  document.querySelectorAll('#sessions-body tr').forEach(r => r.classList.remove('row-active'));
}

// Auto-save notes on input (debounced 1s)
document.getElementById('panel-notes').addEventListener('input', function() {
  clearTimeout(this._saveTimer);
  this._saveTimer = setTimeout(() => saveNotes(this), 1000);
});

async function saveNotes(textarea) {
  const s = textarea._session;
  if (!s) return;
  const notes = textarea.value;
  await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  s.notes = notes;
}

// Summary edit in panel
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

// Initial load + polling
fetchSessions();
setInterval(fetchSessions, REFRESH_MS);
