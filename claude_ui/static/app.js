const REFRESH_MS = 30_000;
let sessions = [];
let showStale = false;

const tbody = document.getElementById('sessions-body');
const table = document.getElementById('sessions-table');
const emptyState = document.getElementById('empty-state');
const summaryCount = document.getElementById('summary-count');
const indicator = document.getElementById('refresh-indicator');
const showStaleCheckbox = document.getElementById('show-stale');
const themeToggle = document.getElementById('theme-toggle');

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

async function fetchSessions() {
  indicator.classList.add('spinning');
  try {
    const res = await fetch('/api/sessions');
    sessions = await res.json();
    render(sessions);
  } catch (e) {
    console.error('Fetch failed', e);
  } finally {
    indicator.classList.remove('spinning');
  }
}

function render(all) {
  const visible = showStale ? all : all.filter(s => s.status !== 'stale');
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
}

function buildRow(s) {
  const tr = document.createElement('tr');

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

  // iTerm tab
  const tabTd = td('col-tab');
  tabTd.innerHTML = `<span class="tab-text">${esc(s.iterm_tab || '—')}</span>`;
  tr.appendChild(tabTd);

  // Last active
  const lastTd = td('col-last');
  lastTd.innerHTML = `<span class="last-text" title="${esc(s.last_seen)}">${relativeTime(s.last_seen)}</span>`;
  tr.appendChild(lastTd);

  // Prompt count
  const countTd = td('col-prompts');
  countTd.innerHTML = `<span class="count-text">${s.prompt_count}</span>`;
  tr.appendChild(countTd);

  // Summary (editable)
  const summaryTd = td('col-summary');
  summaryTd.appendChild(buildSummaryCell(s));
  tr.appendChild(summaryTd);

  // Resume button
  const actionTd = td('col-actions');
  const btn = document.createElement('button');
  btn.className = 'btn-resume';
  btn.textContent = 'Copy Resume';
  btn.addEventListener('click', () => {
    const cmd = `claude --resume ${s.session_id}`;
    navigator.clipboard.writeText(cmd).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy Resume'; btn.classList.remove('copied'); }, 2000);
    });
  });
  actionTd.appendChild(btn);
  tr.appendChild(actionTd);

  return tr;
}

function buildSummaryCell(s) {
  const wrapper = document.createElement('div');

  const display = document.createElement('div');
  display.className = 'summary-text' + (s.summary ? '' : ' empty');
  display.textContent = s.summary || '';

  if (s.summary && s.summary_source === 'auto') {
    const autoBadge = document.createElement('span');
    autoBadge.className = 'auto-badge';
    autoBadge.textContent = 'auto';
    display.appendChild(autoBadge);
  }

  display.addEventListener('click', () => startEdit(s, wrapper, display));
  wrapper.appendChild(display);
  return wrapper;
}

function startEdit(s, wrapper, display) {
  const textarea = document.createElement('textarea');
  textarea.className = 'summary-edit';
  textarea.value = s.summary || '';
  wrapper.replaceChild(textarea, display);
  textarea.focus();

  async function save() {
    const newSummary = textarea.value.trim();
    if (newSummary !== (s.summary || '').trim()) {
      await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summary: newSummary }),
      });
      s.summary = newSummary;
      s.summary_source = 'user';
    }
    wrapper.replaceChild(display, textarea);
    display.textContent = s.summary || '';
    display.className = 'summary-text' + (s.summary ? '' : ' empty');
    if (s.summary && s.summary_source === 'auto') {
      const b = document.createElement('span');
      b.className = 'auto-badge';
      b.textContent = 'auto';
      display.appendChild(b);
    }
  }

  textarea.addEventListener('blur', save);
  textarea.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      wrapper.replaceChild(display, textarea);
    }
  });
}

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

// Initial load + polling
fetchSessions();
setInterval(fetchSessions, REFRESH_MS);
