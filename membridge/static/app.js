let REFRESH_MS = 30_000;
let refreshTimer = null;
let sessions = [];
// showFilter: which session types are visible. Default: active + idle (not stale, not archived)
let showFilter = new Set(['active', 'idle']);
let projectFilter = new Set(); // empty = all projects
let activePanel = null;

// Use the page's own origin so focus/sync work from LAN (phone), not just localhost
const BASE = window.location.origin;

const cardsView = document.getElementById('cards-view');
const tbody = document.getElementById('sessions-body');
const table = document.getElementById('sessions-table');
const emptyState = document.getElementById('empty-state');
const summaryCount = document.getElementById('summary-count');
const indicator = document.getElementById('refresh-btn');
indicator.addEventListener('click', syncAndRefresh);
const themeToggle = document.getElementById('theme-toggle');
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

// Migrate old per-checkbox keys
localStorage.removeItem('mb-show-stale');
localStorage.removeItem('mb-show-archived');

// Restore persisted filter state
try {
  const stored = JSON.parse(localStorage.getItem('mb-show-filter') || '["active","idle"]');
  showFilter = new Set(stored);
} catch (_) { showFilter = new Set(['active', 'idle']); }
try {
  const stored = JSON.parse(localStorage.getItem('mb-project-filter') || '[]');
  projectFilter = new Set(stored);
} catch (_) { projectFilter = new Set(); }

// Show filter dropdown
const showFilterBtn = document.getElementById('show-filter-btn');
const showFilterDropdown = document.getElementById('show-filter-dropdown');
const showCheckboxes = document.getElementById('show-checkboxes');

// Sync checkbox state from showFilter
function syncShowCheckboxes() {
  showCheckboxes.querySelectorAll('input').forEach(cb => {
    cb.checked = showFilter.has(cb.value);
  });
  const isNonDefault = !(showFilter.has('active') && showFilter.has('idle') &&
    !showFilter.has('stale') && !showFilter.has('archived'));
  showFilterBtn.classList.toggle('active', isNonDefault);
}
syncShowCheckboxes();

showFilterBtn.addEventListener('click', e => {
  e.stopPropagation();
  const open = showFilterDropdown.style.display !== 'none';
  showFilterDropdown.style.display = open ? 'none' : 'block';
});
showFilterDropdown.addEventListener('click', e => e.stopPropagation());

showCheckboxes.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    showFilter = new Set(
      [...showCheckboxes.querySelectorAll('input')].filter(c => c.checked).map(c => c.value)
    );
    localStorage.setItem('mb-show-filter', JSON.stringify([...showFilter]));
    syncShowCheckboxes();
    render(sessions);
  });
});

document.getElementById('show-select-all').addEventListener('click', () => {
  showFilter = new Set(['active', 'idle', 'stale', 'archived']);
  localStorage.setItem('mb-show-filter', JSON.stringify([...showFilter]));
  syncShowCheckboxes();
  render(sessions);
});
document.getElementById('show-select-none').addEventListener('click', () => {
  showFilter = new Set();
  localStorage.setItem('mb-show-filter', JSON.stringify([]));
  syncShowCheckboxes();
  render(sessions);
});

// Project filter dropdown
const projFilterBtn = document.getElementById('project-filter-btn');
const projFilterDropdown = document.getElementById('project-filter-dropdown');
const projCheckboxes = document.getElementById('proj-checkboxes');
projFilterBtn.addEventListener('click', e => {
  e.stopPropagation();
  const open = projFilterDropdown.style.display !== 'none';
  projFilterDropdown.style.display = open ? 'none' : 'block';
});
document.addEventListener('click', () => {
  projFilterDropdown.style.display = 'none';
  showFilterDropdown.style.display = 'none';
});
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

// ── Toast notifications ───────────────────────────────────────────────────────

function showToast(message, isError = true) {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = [
    'position:fixed', 'bottom:1.5rem', 'right:1.5rem', 'z-index:9999',
    'padding:0.5rem 1rem', 'border-radius:6px', 'font-size:13px',
    'background:' + (isError ? '#c0392b' : '#2ecc71'), 'color:#fff',
    'box-shadow:0 2px 8px rgba(0,0,0,.4)', 'opacity:0',
    'transition:opacity 0.2s',
  ].join(';');
  document.body.appendChild(toast);
  requestAnimationFrame(() => { toast.style.opacity = '1'; });
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.addEventListener('transitionend', () => toast.remove());
  }, 3000);
}

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
    document.getElementById('set-notif-popup').checked = !!s.notif_popup;
    document.getElementById('set-notif-sound').checked = !!s.notif_sound;
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
    const notifPopup = document.getElementById('set-notif-popup').checked;
    const notifSound = document.getElementById('set-notif-sound').checked;
    localStorage.setItem('mb-notif-popup', notifPopup);
    localStorage.setItem('mb-notif-sound', notifSound);
    await fetch('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notif_popup: notifPopup ? 1 : 0, notif_sound: notifSound ? 1 : 0 }),
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
    await fetch(`${BASE}/sync-tabs`, { method: 'POST' });
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
  let visible = all.filter(s => {
    if (s.starred && showFilter.has('starred')) return true;
    if (s.archived) return showFilter.has('archived');
    return showFilter.has(s.status);
  });
  if (projectFilter.has('__none__')) {
    visible = [];
  } else if (projectFilter.size > 0) {
    visible = visible.filter(s => projectFilter.has(s.project_name));
  }
  // Starred sessions float to the top
  visible.sort((a, b) => (b.starred || 0) - (a.starred || 0));

  const active = all.filter(s => s.status === 'active').length;
  const idle = all.filter(s => s.status === 'idle').length;
  summaryCount.textContent = `${active} active · ${idle} idle · ${all.length} total`;

  const awaitingN = all.filter(s => s.awaiting_input && s.status !== 'stale').length;
  const awaitingBadge = document.getElementById('awaiting-badge');
  const awaitingCount = document.getElementById('awaiting-count');
  if (awaitingN > 0) {
    awaitingCount.textContent = `◉ ${awaitingN} awaiting input`;
    awaitingBadge.style.display = 'block';
  } else {
    awaitingBadge.style.display = 'none';
  }

  if (visible.length === 0) {
    table.style.display = 'none';
    cardsView.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }

  table.style.display = 'table';
  emptyState.style.display = 'none';
  tbody.innerHTML = '';
  cardsView.innerHTML = '';

  for (const s of visible) {
    tbody.appendChild(buildRow(s));
    cardsView.appendChild(buildCard(s));
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
  statusTd.style.whiteSpace = 'nowrap';

  // Star button
  const starBtn = document.createElement('button');
  starBtn.className = 'btn-star' + (s.starred ? ' btn-star-on' : '');
  starBtn.title = s.starred ? 'Unstar session' : 'Star session';
  starBtn.textContent = '★';
  starBtn.addEventListener('click', async e => {
    e.stopPropagation();
    const newVal = !s.starred;
    s.starred = newVal;
    starBtn.className = 'btn-star' + (newVal ? ' btn-star-on' : '');
    starBtn.title = newVal ? 'Unstar session' : 'Star session';
    await fetch(`/api/sessions/${s.session_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred: newVal }),
    });
    render(sessions);
  });
  statusTd.appendChild(starBtn);

  // Focus button — state machine:
  //   awaiting_input → yellow (wants your response: ? for decision, ✎ for text)
  //   active + working → green ◉ (Claude is processing)
  //   stale → amber ↩ (needs resume)
  //   idle → grey ⌘
  const focusRowBtn = document.createElement('button');
  let _focusCls = 'btn-focus-row';
  let _focusIcon = '⌘';
  let _focusTitle = 'Focus tab';
  if (s.awaiting_input) {
    _focusCls += ' btn-focus-row-awaiting';
    const isDecision = s.last_stop_reason && (
      s.last_stop_reason.includes('permission_prompt') ||
      s.last_stop_reason.includes('ask_user_question')
    );
    if (isDecision) {
      _focusIcon = '?';
      _focusTitle = 'Needs a decision';
    } else {
      _focusIcon = '✎';
      _focusTitle = 'Awaiting your input';
    }
  } else if (s.status === 'stale') {
    _focusCls += ' btn-focus-row-resume';
    _focusIcon = '↩';
    _focusTitle = 'Resume session';
  } else if (s.status === 'active') {
    _focusCls += ' btn-focus-row-working';
    _focusIcon = '◉';
    _focusTitle = 'Claude is working…';
  }
  focusRowBtn.className = _focusCls;
  focusRowBtn.title = _focusTitle;
  focusRowBtn.textContent = _focusIcon;
  focusRowBtn.addEventListener('click', async e => {
    e.stopPropagation();
    focusRowBtn.textContent = '…';
    focusRowBtn.disabled = true;
    try {
      const res = await fetch(`${BASE}/focus`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: s.session_id,
          pid: s.pid,
          cwd: s.cwd,
          iterm_session_uuid: s.iterm_session_uuid,
          tab_name: s.iterm_tab || s.project_name,
        }),
      });
      const data = await res.json();
      focusRowBtn.textContent = data.action === 'focused' ? '✓' : '↗';
    } catch {
      focusRowBtn.textContent = '✗';
    }
    setTimeout(() => {
      focusRowBtn.textContent = s.status === 'stale' ? '↩' : '⌘';
      focusRowBtn.disabled = false;
    }, 2000);
  });
  statusTd.appendChild(focusRowBtn);

  // Status pill
  const badge = document.createElement('span');
  badge.className = `pill badge-${s.status}`;
  badge.textContent = s.status;
  statusTd.appendChild(badge);

  tr.appendChild(statusTd);

  const projTd = td('col-project');
  projTd.textContent = s.project_name;
  tr.appendChild(projTd);

  const descTd = td('col-desc');
  descTd.style.cssText = 'font-size:12px;color:var(--text-muted)';

  function renderDescText() {
    const _desc = s.description ? stripMd(s.description) : '';
    descTd.textContent = _desc.slice(0, 120) + (_desc.length > 120 ? '…' : '');
    descTd.title = 'Click to edit description';
    descTd.style.cursor = 'text';
  }
  renderDescText();

  descTd.addEventListener('click', e => {
    e.stopPropagation();
    if (descTd.querySelector('input')) return;
    const orig = s.description ? stripMd(s.description) : '';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = orig;
    input.style.cssText = 'width:100%;font-size:12px;background:var(--surface2);color:var(--text);border:1px solid var(--accent);border-radius:3px;padding:1px 4px;box-sizing:border-box;outline:none';
    descTd.textContent = '';
    descTd.style.cursor = '';
    descTd.appendChild(input);
    input.focus();
    input.select();

    async function save() {
      const val = input.value.trim();
      if (val !== orig) {
        await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: val }),
        });
        s.description = val;
      }
      renderDescText();
    }

    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { s.description = orig; renderDescText(); }
    });
    input.addEventListener('blur', save);
  });

  tr.appendChild(descTd);

  const branchTd = td('col-branch');
  branchTd.innerHTML = `<span class="branch-text">${esc(s.git_branch || '—')}</span>`;
  tr.appendChild(branchTd);

  const lastTd = td('col-last');
  lastTd.innerHTML = `<span class="last-text" title="${esc(s.last_seen)}">${relativeTime(s.last_seen)}</span>`;
  tr.appendChild(lastTd);

  const idTd = td('col-id');
  const shortId = s.session_id.slice(0, 8);
  idTd.innerHTML = `<span class="session-id" title="Click to copy full session ID">${esc(shortId)}…</span>`;
  idTd.querySelector('.session-id').addEventListener('click', e => {
    e.stopPropagation();
    navigator.clipboard.writeText(s.session_id).then(() => {
      const el = idTd.querySelector('.session-id');
      const prev = el.textContent;
      el.textContent = 'copied!';
      setTimeout(() => { el.textContent = prev; }, 1500);
    });
  });
  tr.appendChild(idTd);

  const countTd = td('col-prompts');
  countTd.innerHTML = `<span class="count-text">${s.prompt_count}</span>`;
  tr.appendChild(countTd);

  tr.addEventListener('click', () => openPanel(s, true));
  tr.style.cursor = 'pointer';

  return tr;
}

function buildCard(s) {
  const card = document.createElement('div');
  card.className = 'session-card' + (s.archived ? ' row-archived' : '') + (activePanel === s.session_id ? ' row-active' : '');
  card.dataset.sessionId = s.session_id;
  card.addEventListener('click', () => openPanel(s, false));

  // Top row: star, focus, project, status pill
  const top = document.createElement('div');
  top.className = 'card-top';

  // Star
  const starBtn = document.createElement('button');
  starBtn.className = 'btn-star' + (s.starred ? ' btn-star-on' : '');
  starBtn.title = s.starred ? 'Unstar' : 'Star';
  starBtn.textContent = '★';
  starBtn.addEventListener('click', async e => {
    e.stopPropagation();
    s.starred = !s.starred;
    render(sessions);
    await fetch(`/api/sessions/${s.session_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred: s.starred }),
    });
  });
  top.appendChild(starBtn);

  // Focus button
  const focusBtn = document.createElement('button');
  let _cls = 'btn-focus-row';
  let _icon = '⌘';
  if (s.awaiting_input) {
    _cls += ' btn-focus-row-awaiting';
    _icon = (s.last_stop_reason && (
      s.last_stop_reason.includes('permission_prompt') ||
      s.last_stop_reason.includes('ask_user_question')
    )) ? '?' : '✎';
  } else if (s.status === 'stale') {
    _cls += ' btn-focus-row-resume'; _icon = '↩';
  } else if (s.status === 'active') {
    _cls += ' btn-focus-row-working'; _icon = '◉';
  }
  focusBtn.className = _cls;
  focusBtn.textContent = _icon;
  focusBtn.addEventListener('click', async e => {
    e.stopPropagation();
    focusBtn.textContent = '…';
    focusBtn.disabled = true;
    try {
      await fetch(`${BASE}/focus`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: s.session_id, pid: s.pid, cwd: s.cwd, iterm_session_uuid: s.iterm_session_uuid, tab_name: s.iterm_tab || s.project_name }),
      });
    } catch (_) {}
    setTimeout(() => { focusBtn.textContent = _icon; focusBtn.disabled = false; }, 2000);
  });
  top.appendChild(focusBtn);

  const proj = document.createElement('span');
  proj.className = 'card-project';
  proj.textContent = s.project_name;
  top.appendChild(proj);

  const badge = document.createElement('span');
  badge.className = `pill badge-${s.status}`;
  badge.textContent = s.status;
  top.appendChild(badge);

  card.appendChild(top);

  // Description
  if (s.description) {
    const desc = document.createElement('div');
    desc.className = 'card-desc';
    const plain = stripMd(s.description);
    desc.textContent = plain.slice(0, 100) + (plain.length > 100 ? '…' : '');
    card.appendChild(desc);
  }

  // Bottom meta row: branch · last active · id
  const bottom = document.createElement('div');
  bottom.className = 'card-bottom';
  if (s.git_branch) {
    const b = document.createElement('span');
    b.style.fontFamily = 'monospace';
    b.textContent = s.git_branch;
    bottom.appendChild(b);
  }
  const last = document.createElement('span');
  last.textContent = relativeTime(s.last_seen);
  bottom.appendChild(last);
  const id = document.createElement('span');
  id.style.fontFamily = 'monospace';
  id.textContent = s.session_id.slice(0, 8) + '…';
  bottom.appendChild(id);
  card.appendChild(bottom);

  return card;
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
  document.querySelectorAll('#cards-view .session-card').forEach(c => {
    c.classList.toggle('row-active', c.dataset.sessionId === s.session_id);
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
  const existingSummaryEl = document.getElementById('panel-summary');
  const newSummaryEl = makeSummaryEl(s);
  existingSummaryEl.replaceWith(newSummaryEl);

  const focusBtn = document.getElementById('panel-focus-btn');
  const focusLabel = () => s.status === 'stale' ? '↩ Resume' : '⌘ Focus';
  focusBtn.textContent = focusLabel();
  focusBtn.onclick = async () => {
    focusBtn.textContent = '…';
    try {
      const res = await fetch(`${BASE}/focus`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: s.session_id, pid: s.pid || null, cwd: s.cwd || null, tab_name: s.iterm_tab || null, iterm_session_uuid: s.iterm_session_uuid || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      focusBtn.textContent = data.action === 'focused' ? '✓ Focused' : '✓ Resumed';
    } catch (err) {
      focusBtn.textContent = '✗ Failed';
      console.error('Focus error:', err);
    }
    setTimeout(() => { focusBtn.textContent = focusLabel(); }, 2500);
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

  initTicketsInput(s);

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

function initTicketsInput(s) {
  const wrap = document.getElementById('panel-tickets-wrap');
  const input = document.getElementById('panel-ticket-input');
  wrap.querySelectorAll('.ticket-tag').forEach(t => t.remove());
  const tickets = (s.tickets || '').split(',').map(t => t.trim()).filter(Boolean);
  for (const t of tickets) wrap.insertBefore(makeTicketTag(t, s), input);
  input.value = '';
  input.onkeydown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const val = input.value.trim().replace(/^#/, '');
      if (val) { addTicket(s, val); input.value = ''; }
    } else if (e.key === 'Backspace' && !input.value) {
      const tags = wrap.querySelectorAll('.ticket-tag');
      if (tags.length) {
        const last = tags[tags.length - 1];
        last.remove();
        saveTickets(s);
      }
    }
  };
  wrap.addEventListener('click', () => input.focus());
}

function makeTicketTag(ticket, s) {
  const tag = document.createElement('span');
  tag.className = 'ticket-tag';
  tag.dataset.ticket = ticket;
  const label = document.createTextNode(`#${ticket} `);
  tag.appendChild(label);
  const x = document.createElement('button');
  x.className = 'ticket-tag-x';
  x.textContent = '×';
  x.title = 'Remove';
  x.onclick = (e) => { e.stopPropagation(); tag.remove(); saveTickets(s); };
  tag.appendChild(x);
  return tag;
}

function addTicket(s, ticket) {
  const wrap = document.getElementById('panel-tickets-wrap');
  const input = document.getElementById('panel-ticket-input');
  const existing = [...wrap.querySelectorAll('.ticket-tag')].map(t => t.dataset.ticket);
  if (existing.includes(ticket)) return;
  wrap.insertBefore(makeTicketTag(ticket, s), input);
  saveTickets(s);
}

async function saveTickets(s) {
  const wrap = document.getElementById('panel-tickets-wrap');
  const tickets = [...wrap.querySelectorAll('.ticket-tag')].map(t => t.dataset.ticket).join(',');
  s.tickets = tickets;
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickets }),
    });
    if (!res.ok) showToast('Failed to save tickets');
  } catch (_) {
    showToast('Failed to save tickets');
  }
}

function closePanel() {
  activePanel = null;
  panelOverlay.classList.remove('open');
  document.querySelectorAll('#sessions-body tr').forEach(r => r.classList.remove('row-active'));
  document.querySelectorAll('#cards-view .session-card').forEach(c => c.classList.remove('row-active'));

}

document.getElementById('panel-notes').addEventListener('input', function() {
  clearTimeout(this._saveTimer);
  this._saveTimer = setTimeout(() => saveNotes(this), 1000);
});

async function saveNotes(textarea) {
  const s = textarea._session;
  if (!s) return;
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: textarea.value }),
    });
    if (res.ok) {
      s.notes = textarea.value;
    } else {
      showToast('Failed to save notes');
    }
  } catch (_) {
    showToast('Failed to save notes');
  }
}

document.getElementById('panel-summary').addEventListener('click', function() {
  const s = sessions.find(x => x.session_id === activePanel);
  if (!s || !activePanel) return;
  startPanelSummaryEdit(s, this);
});

function startPanelSummaryEdit(s, el) {
  // Re-read from sessions array by session_id to avoid stale closure
  const fresh = sessions.find(x => x.session_id === s.session_id) || s;
  const orig = fresh.description || '';
  const textarea = document.createElement('textarea');
  textarea.className = 'summary-edit panel-summary-edit';
  textarea.value = orig;
  el.replaceWith(textarea);
  textarea.focus();

  async function save() {
    const newSummary = textarea.value.trim();
    if (newSummary !== orig.trim()) {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: newSummary }),
        });
        if (res.ok) {
          s.description = newSummary;
          s.description_source = 'user';
          await loadHistory(s.session_id);
        } else {
          showToast('Failed to save description');
        }
      } catch (_) {
        showToast('Failed to save description');
      }
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
    const raw = marked.parse(text, { breaks: true, gfm: true });
    el.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
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

// ── Column resize ─────────────────────────────────────────────────────────────
// Widths are set on <col> elements — table is width:max-content so resizing
// one column never affects another. Container scrolls horizontally if needed.

const COL_WIDTHS_KEY = 'membridge_col_widths';
const COL_DEFAULTS = {
  'col-status':  160,
  'col-project': 120,

  'col-desc':    320,
  'col-branch':  140,
  'col-last':    110,
  'col-id':       96,
  'col-prompts':  70,
};

let colWidths = {};

function loadColWidths() {
  try { return JSON.parse(localStorage.getItem(COL_WIDTHS_KEY) || '{}'); } catch { return {}; }
}

function saveColWidths() {
  localStorage.setItem(COL_WIDTHS_KEY, JSON.stringify(colWidths));
}

function applyColWidths() {
  document.querySelectorAll('#sessions-table colgroup col').forEach(col => {
    const key = col.dataset.col;
    if (colWidths[key]) col.style.width = colWidths[key] + 'px';
  });
}

function initColResize() {
  colWidths = Object.assign({}, COL_DEFAULTS, loadColWidths());
  applyColWidths();

  document.querySelectorAll('#sessions-table thead th').forEach(th => {
    const col = th.className.match(/col-[\w]+/)?.[0];
    if (!col) return;

    th.addEventListener('mousedown', e => {
      // Only trigger on right 6px of the header
      if (e.offsetX < th.offsetWidth - 6) return;
      e.preventDefault();
      const startW = colWidths[col] || th.getBoundingClientRect().width;
      const startX = e.clientX;
      th.classList.add('col-resizing');

      function onMove(e) {
        const w = Math.max(40, startW + e.clientX - startX);
        colWidths[col] = w;
        const colEl = document.querySelector(`#sessions-table col[data-col="${col}"]`);
        if (colEl) colEl.style.width = w + 'px';
      }

      function onUp() {
        th.classList.remove('col-resizing');
        saveColWidths();
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    // Pointer cursor on right edge
    th.addEventListener('mousemove', e => {
      th.style.cursor = e.offsetX >= th.offsetWidth - 6 ? 'col-resize' : '';
    });
    th.addEventListener('mouseleave', () => { th.style.cursor = ''; });
  });
}

// ── SSE — push-refresh from server ───────────────────────────────────────────

function jumpToAwaiting() {
  const rows = [...document.querySelectorAll('#sessions-body tr')];
  const target = rows.find(r => r.querySelector('.btn-focus-row-awaiting'));
  if (target) {
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    target.classList.add('row-flash');
    setTimeout(() => target.classList.remove('row-flash'), 1200);
  }
}
document.getElementById('awaiting-badge').addEventListener('click', jumpToAwaiting);
document.getElementById('awaiting-count').addEventListener('click', jumpToAwaiting);

function connectSSE() {
  const es = new EventSource('/api/events');
  es.onmessage = (e) => {
    if (e.data === 'refresh') fetchSessions();
  };
  es.onerror = () => {
    es.close();
    // Reconnect after 5s if connection drops
    setTimeout(connectSSE, 5000);
  };
}

// ── Boot ──────────────────────────────────────────────────────────────────────

(async () => {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    REFRESH_MS = s.refresh_interval_secs * 1000;
  } catch (_) {}
  initColResize();
  fetchSessions();
  restartRefreshTimer();
  connectSSE();
})();
