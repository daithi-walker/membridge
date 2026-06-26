---
description: "Generate a branded HTML slide deck. /slides <topic> [--style dss|biobase|edge] [--from-session [prefix]] [--out <path>]"
allowed-tools:
  - Read
  - Write
  - Bash
argument-hint: "<topic> [--style dss|biobase|edge[-light]] [--from-session [prefix]] [--out <path>]"
---

# /slides — Branded HTML Slide Generator

Generates a self-contained, keyboard-navigable HTML slide deck — from a topic brief or directly from a MemBridge session's work history.

**Arguments:** $ARGUMENTS

## Steps

1. **Parse arguments:**
   - `--style <name>` — theme (default: `dss`). Options: `dss`, `dss-light`, `biobase`, `biobase-light`, `edge`, `edge-light`
   - `--from-session [prefix]` — pull content from MemBridge instead of a topic brief (see below)
   - `--no-agenda` — skip the agenda slide
   - `--out <path>` — output file (default: `/tmp/<topic-slug>.html`)
   - Everything else is the topic/brief for the slide content

2. **Read the theme file:**
   Read `~/.claude/styles/slides-<style>.css` — a `:root { }` block of CSS variable overrides. Embed it verbatim as a `<style>` block after the base styles.

3. **Build the content brief** — either from the topic or from MemBridge:

   **From topic (default):** use the free-text description as the brief.

   **From MemBridge (`--from-session`):**
   - If a prefix is given, resolve it: `curl -s http://localhost:7842/api/sessions` → find the session whose `session_id` starts with the prefix.
   - If no prefix, use `$CLAUDE_CODE_SESSION_ID` as the session ID.
   - Fetch session metadata from the sessions list (project_name, git_branch, description, notes, first_seen, last_seen, prompt_count).
   - Fetch the full summary history: `curl -s http://localhost:7842/api/sessions/<id>/summaries`
   - Assemble the content brief from: project name, branch, description, notes, and summaries in chronological order (oldest first). Each summary entry has `source` (auto/skill/user) and `text`.
   - Use this brief to generate slides covering: what the session was, what was built/fixed/explored, key decisions or outcomes, and notes/next steps.

4. **Generate slides** — aim for 8–12 slides:
   - Slide 1: **Title** — project name (or topic) + one-line subtitle
   - Slide 2: **Agenda** (skip if `--no-agenda`) — numbered list of sections
   - Slide 3: **Context / The Problem** — why this work was done
   - Slides 4–N: Key content using appropriate patterns (feature list, cards, code, row-list)
   - Last slide: **Outcomes / Next Steps** or demo CTA

5. **Write the HTML** to the output path.

6. **Open it:** `open <output-path>`

7. **Report** the path and slide count.

---

## Available themes

| Flag | Brand | File |
|---|---|---|
| `--style dss` | Dual Space Solutions dark (default) | `~/.claude/styles/slides-dss.css` |
| `--style dss-light` | Dual Space Solutions light | `~/.claude/styles/slides-dss-light.css` |
| `--style biobase` | Biobase teal dark | `~/.claude/styles/slides-biobase.css` |
| `--style biobase-light` | Biobase teal light | `~/.claude/styles/slides-biobase-light.css` |
| `--style edge` | Edge Consultants dark | `~/.claude/styles/slides-edge.css` |
| `--style edge-light` | Edge Consultants light | `~/.claude/styles/slides-edge-light.css` |
| `--style <path>` | Custom — full path to a CSS file | read it and embed it |

To add a new theme: create `~/.claude/styles/slides-<name>.css` with a `:root { }` block overriding any of the variables below.

---

## Base HTML template

Use this exact structure. Inject the theme `<style>` block after the base `<style>` block. Populate the slides inside `<div id="deck">`. Update the `<title>` to the topic name.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title><!-- topic name --></title>
<meta name="description" content="<!-- one-line description -->">
<style>
  /* ── Base variables (overridden by theme) ── */
  :root {
    --bg: #1c2333; --surface: #242e42; --border: #3a4558;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --amber: #d29922; --orange: #f0883e;
    --red: #f85149; --purple: #bc8cff;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body {
    height: 100%; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    overflow: hidden;
  }

  #deck { width: 100vw; height: 100vh; position: relative; }

  .slide {
    position: absolute; inset: 0;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    padding: 32px 5vw 64px;
    opacity: 0; pointer-events: none;
    transition: opacity .3s ease;
  }
  .slide.active { opacity: 1; pointer-events: all; }

  /* Nav */
  #nav {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    display: flex; align-items: center; gap: 16px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 32px; padding: 8px 20px;
    font-size: 13px; color: var(--muted); z-index: 100;
  }
  #nav button {
    background: none; border: none; color: var(--accent);
    font-size: 18px; cursor: pointer; line-height: 1; padding: 0 4px;
  }
  #nav button:disabled { color: var(--border); cursor: default; }

  /* Typography */
  .eyebrow {
    font-size: 13px; font-weight: 600; letter-spacing: .12em;
    text-transform: uppercase; color: var(--accent); margin-bottom: 14px;
  }
  h1 { font-size: clamp(48px, 7vw, 80px); font-weight: 700; line-height: 1.1; }
  h2 { font-size: clamp(32px, 4.5vw, 54px); font-weight: 700; line-height: 1.15; margin-bottom: 32px; }
  .subtitle { font-size: clamp(18px, 2.2vw, 26px); color: var(--muted); margin-top: 20px; max-width: 820px; text-align: center; line-height: 1.5; }
  p { font-size: clamp(15px, 1.6vw, 20px); color: var(--muted); line-height: 1.65; max-width: 100%; }

  /* Layout */
  .center { text-align: center; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; width: 100%; align-items: start; }
  .three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; width: 100%; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 22px 26px; }
  .card h3 { font-size: clamp(15px, 1.4vw, 19px); font-weight: 600; margin-bottom: 10px; }
  .card p { font-size: clamp(13px, 1.2vw, 16px); }

  /* Feature list */
  .feat-list { list-style: none; display: flex; flex-direction: column; gap: 16px; width: 100%; max-width: 860px; }
  .feat-list li { display: flex; gap: 16px; align-items: flex-start; font-size: clamp(16px, 1.8vw, 22px); }
  .feat-list li .icon { font-size: clamp(20px, 2vw, 26px); flex-shrink: 0; width: 34px; text-align: center; }

  /* Code */
  pre {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 22px 28px;
    font-size: clamp(13px, 1.3vw, 17px); line-height: 1.7; overflow-x: auto;
    font-family: "SF Mono", "Cascadia Code", "Fira Mono", monospace; width: 100%;
  }

  /* Pills */
  .pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 14px; border-radius: 20px; font-size: clamp(13px, 1.2vw, 16px); font-weight: 600;
  }
  .pill.green  { background: rgba(63,185,80,.15);  color: var(--green);  border: 1px solid rgba(63,185,80,.3); }
  .pill.amber  { background: rgba(210,153,34,.15); color: var(--amber);  border: 1px solid rgba(210,153,34,.3); }
  .pill.red    { background: rgba(248,81,73,.12);  color: var(--red);    border: 1px solid rgba(248,81,73,.3); }
  .pill.accent { background: rgba(88,166,255,.12); color: var(--accent); border: 1px solid rgba(88,166,255,.3); }

  /* Row items (for hook/command lists) */
  .row-list { display: flex; flex-direction: column; gap: 14px; width: 100%; }
  .row-item {
    display: flex; align-items: center; gap: 20px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 18px 24px;
  }
  .row-item .badge {
    font-size: clamp(10px, 1vw, 13px); font-weight: 700; letter-spacing: .02em;
    padding: 5px 11px; border-radius: 5px; white-space: nowrap; flex-shrink: 0;
  }
  .row-item .desc { flex: 1; font-size: clamp(14px, 1.4vw, 18px); line-height: 1.5; }
  .row-item .tag { font-family: monospace; font-size: clamp(12px, 1.1vw, 15px); color: var(--accent); background: rgba(88,166,255,.1); padding: 5px 10px; border-radius: 5px; white-space: nowrap; }
</style>
<!-- THEME STYLE BLOCK GOES HERE -->
</head>
<body>
<div id="deck">
  <!-- SLIDES GO HERE -->
</div>

<div id="nav">
  <button id="prev" disabled>←</button>
  <span id="counter">1 / N</span>
  <button id="next">→</button>
</div>

<script>
  const slides = Array.from(document.querySelectorAll('.slide'));
  let cur = 0;
  function go(n) {
    slides[cur].classList.remove('active');
    cur = Math.max(0, Math.min(n, slides.length - 1));
    slides[cur].classList.add('active');
    document.getElementById('counter').textContent = `${cur + 1} / ${slides.length}`;
    document.getElementById('prev').disabled = cur === 0;
    document.getElementById('next').disabled = cur === slides.length - 1;
  }
  document.getElementById('prev').addEventListener('click', () => go(cur - 1));
  document.getElementById('next').addEventListener('click', () => go(cur + 1));
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') { e.preventDefault(); go(cur + 1); }
    if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')                    { e.preventDefault(); go(cur - 1); }
    if (e.key === 'Home') go(0);
    if (e.key === 'End')  go(slides.length - 1);
  });
</script>
</body>
</html>
```

---

## Layout rules

These rules apply to every deck. Follow them before choosing a pattern.

**Slide types — two kinds only:**
- `center` — title, section divider, CTA. No header bar. Content fully centred.
- content — `.slide-header` bar at top (title left, slide number right, `border-bottom`), `.slide-body` fills the rest.

**Always wrap content in `.slide-body`** — never put content directly inside a `.slide`. The body provides the content boundary and consistent padding.

**Content boundary** — `.slide-body` uses `padding: 28px clamp(48px, 5vw, 80px)` so side margins match the bottom gap. Content never bleeds to the viewport edge.

**Choose layout by item count:**
| Items | Layout | Notes |
|---|---|---|
| 2 | `.two-col` + `max-width:760px` | Cap width or cards become uncomfortably wide |
| 3 | `.three-col` | Default gap 20px; bump to 36px if content is sparse |
| 4–6 | Single centred column, `width:580px` | Stack cards vertically, centred in body |
| 6+ | `.three-col` grid | Works as a 2-row grid |

**Prefer cards over full-width rows** — for commands, features, or any labelled list, use card grid layouts rather than `.hook-row` / `.row-list` full-width rows. Cards read better at scale.

**No em dashes** — use a regular hyphen (`-`) in all slide copy.

---

## Slide structure patterns

**Title slide** (`center` type):
```html
<section class="slide active center" id="s1">
  <div class="eyebrow">Context line · subtitle</div>
  <h1>Title</h1>
  <p class="subtitle">One or two sentence description.</p>
</section>
```

**Agenda slide** (content type):
```html
<section class="slide" id="s2">
  <div class="slide-header">
    <h2>Agenda</h2>
    <span class="slide-num">2 / N</span>
  </div>
  <div class="slide-body left">
    <ol style="list-style:none;display:flex;flex-direction:column;gap:24px;width:100%;max-width:640px;">
      <li style="display:flex;gap:16px;align-items:baseline;font-size:clamp(18px,2.1vw,26px);"><span style="color:var(--accent);font-weight:700;min-width:28px;">01</span><span>Topic One</span></li>
      <li style="display:flex;gap:16px;align-items:baseline;font-size:clamp(18px,2.1vw,26px);"><span style="color:var(--accent);font-weight:700;min-width:28px;">02</span><span>Topic Two</span></li>
    </ol>
  </div>
</section>
```

**Feature list slide** (content type):
```html
<section class="slide" id="sN">
  <div class="slide-header">
    <h2>Heading</h2>
    <span class="slide-num">N / Total</span>
  </div>
  <div class="slide-body">
    <ul class="feat-list">
      <li><span class="icon">🔌</span><span><strong>Bold term</strong> - explanation</span></li>
    </ul>
  </div>
</section>
```

**Two-column cards** (content type, 2 items):
```html
<section class="slide" id="sN">
  <div class="slide-header">
    <h2>Heading</h2>
    <span class="slide-num">N / Total</span>
  </div>
  <div class="slide-body">
    <div class="two-col" style="max-width:760px;">
      <div class="card"><h3>Card title</h3><p>Content.</p></div>
      <div class="card"><h3>Card title</h3><p>Content.</p></div>
    </div>
  </div>
</section>
```

**Three-column cards** (content type, 3 items):
```html
<section class="slide" id="sN">
  <div class="slide-header">
    <h2>Heading</h2>
    <span class="slide-num">N / Total</span>
  </div>
  <div class="slide-body">
    <div class="three-col">
      <div class="card"><h3>Title</h3><p>Content.</p></div>
      <div class="card"><h3>Title</h3><p>Content.</p></div>
      <div class="card"><h3>Title</h3><p>Content.</p></div>
    </div>
  </div>
</section>
```

**Stacked centred cards** (content type, 4–6 items):
```html
<section class="slide" id="sN">
  <div class="slide-header">
    <h2>Heading</h2>
    <span class="slide-num">N / Total</span>
  </div>
  <div class="slide-body">
    <div style="display:flex;flex-direction:column;gap:12px;width:580px;max-width:100%;">
      <div class="card">
        <div style="margin-bottom:8px;"><code style="color:var(--accent);background:rgba(88,166,255,.1);padding:4px 8px;border-radius:5px;">/command-name</code></div>
        <p style="font-size:clamp(13px,1.2vw,15px);">Description of what this does.</p>
      </div>
    </div>
  </div>
</section>
```

**CTA / demo slide** (`center` type):
```html
<section class="slide center" id="sN">
  <div class="eyebrow">Live Demo</div>
  <h1 style="font-size:clamp(28px,4vw,52px);">Let's see it in action</h1>
  <p class="subtitle">Supporting text or URL.</p>
</section>
```

---

After writing the file, open it in the browser:
```bash
open <output-path>
```
