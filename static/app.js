/* ============================================================
   Atlas — frontend controller
   Consumes the agent pipeline over SSE (/api/ask, /api/resume),
   renders the live steps, answer, chart, and glass-box trust panel.
   ============================================================ */
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; };
  const uid = () => 't' + Math.random().toString(36).slice(2, 10);

  const SAMPLES = [
    'Total revenue by customer segment from completed orders',
    'Top 5 products by units sold',
    'How many high-priority support tickets are still open?',
    'Which regions have the most churned customers?',
    'What is our refund policy and how long do refunds take?',
    'Show me the email addresses of customers who churned',
  ];

  const STEP_TITLES = {
    plan: 'Planned the approach', sql: 'Wrote the SQL', approved: 'Safety check',
    result: 'Ran the query', result_error: 'Query error', review: 'Validated the result',
    sources: 'Searched the documents', chart: 'Chose a visualization',
  };

  let busy = false;

  /* ---------- Theme ---------- */
  function initTheme() {
    const saved = localStorage.getItem('atlas-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    $('#theme-toggle').addEventListener('click', () => {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('atlas-theme', next);
      document.querySelectorAll('.turn canvas').forEach((c) => c._chart && c._chart.update());
    });
  }
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  /* ---------- Schema explorer ---------- */
  async function loadSchema() {
    try {
      const data = await (await fetch('/api/schema')).json();
      const wrap = $('#schema-list'); wrap.innerHTML = '';
      data.tables.forEach((t) => {
        const d = el('details', 'schema-table');
        const cols = t.columns.map((c) => {
          const key = c.pk ? '<span class="key">PK</span>' : c.fk ? `<span class="key">FK</span>` : '';
          return `<div class="schema-col"><span>${esc(c.name)}</span><span class="ty">${esc(c.type)}</span>${key}</div>`;
        }).join('');
        d.innerHTML = `<summary>${esc(t.name)}<span class="cnt">${t.columns.length}</span></summary><div class="schema-cols">${cols}</div>`;
        wrap.appendChild(d);
      });
    } catch (e) { $('#schema-list').innerHTML = '<div class="muted small">Schema unavailable.</div>'; }
  }

  function renderSamples() {
    const wrap = $('#samples');
    SAMPLES.forEach((q) => {
      const b = el('button', 'sample', esc(q));
      b.addEventListener('click', () => { if (!busy) ask(q); });
      wrap.appendChild(b);
    });
  }

  /* ---------- Markdown answer + citations ---------- */
  function renderAnswer(md) {
    let html = window.marked ? window.marked.parse(md) : esc(md).replace(/\n/g, '<br>');
    return html.replace(/\[(\d+)\]/g, '<span class="cite">$1</span>');
  }

  /* ---------- A turn ---------- */
  function newTurn(question) {
    $('#empty')?.remove();
    const turn = el('div', 'turn');
    turn.appendChild(el('div', 'q-bubble', esc(question)));
    const pipe = el('div', 'pipeline');
    pipe.innerHTML = '<div class="pipeline-head"><span class="spinner"></span><span>Agent pipeline</span><span class="toggle"></span></div><div class="steps"></div>';
    turn.appendChild(pipe);
    $('#thread').appendChild(turn);
    scrollDown();
    return { question, root: turn, pipe, steps: pipe.querySelector('.steps'), ctx: {}, lastStep: null };
  }

  function addStep(turn, key, detailHtml) {
    if (turn.lastStep) turn.lastStep.classList.replace('active', 'done');
    const s = el('div', 'step active');
    s.innerHTML = `<div class="dot"></div><div class="step-body"><div class="step-title">${esc(STEP_TITLES[key] || key)}</div>${detailHtml ? `<div class="step-detail">${detailHtml}</div>` : ''}</div>`;
    turn.steps.appendChild(s); turn.lastStep = s; scrollDown();
    return s;
  }

  function finishPipeline(turn) {
    if (turn.lastStep) turn.lastStep.classList.replace('active', 'done');
    const head = turn.pipe.querySelector('.pipeline-head');
    head.querySelector('.spinner').replaceWith(el('span', '', '✓'));
    head.classList.add('collapsed');
    head.querySelector('.toggle').textContent = 'hide';
    head.style.cursor = 'pointer';
    head.addEventListener('click', () => {
      const st = turn.steps; st.classList.toggle('hidden');
      head.querySelector('.toggle').textContent = st.classList.contains('hidden') ? 'show' : 'hide';
    });
    turn.steps.classList.add('hidden');
    head.querySelector('.toggle').textContent = 'show';
  }

  /* ---------- Event handling ---------- */
  function handle(turn, ev) {
    const c = turn.ctx;
    switch (ev.type) {
      case 'plan': {
        c.route = ev.route;
        const steps = (ev.steps || []).map((s) => `<li>${esc(s)}</li>`).join('');
        addStep(turn, 'plan', `${esc(ev.intent || '')}<div><span class="pill">route: ${esc(ev.route)}</span></div>${steps ? `<ol class="plan-steps">${steps}</ol>` : ''}`);
        break;
      }
      case 'sql':
        c.sql = ev.sql;
        addStep(turn, 'sql', `${esc(ev.rationale || '')}<div class="code mono">${esc(ev.sql)}</div>`);
        break;
      case 'approved':
        addStep(turn, 'approved', ev.auto ? 'Read-only and safe — approved automatically.' : (ev.approved ? 'Approved by you.' : 'Rejected by you.'));
        break;
      case 'approval_required':
        renderApproval(turn, ev); break;
      case 'result':
        c.result = ev;
        addStep(turn, 'result', `Returned <span class="pill">${ev.row_count} rows</span>${ev.truncated ? ' (capped)' : ''}.`);
        break;
      case 'result_error':
        addStep(turn, 'result_error', `<span style="color:var(--danger)">${esc(ev.error)}</span> — the agent will try to fix it.`);
        break;
      case 'review':
        c.review = ev;
        addStep(turn, 'review', ev.answers_question ? 'Result looks correct.' : `Needs a fix: ${esc(ev.issue || '')} — retrying.`);
        break;
      case 'sources':
        c.docs = ev.docs || [];
        addStep(turn, 'sources', c.docs.length ? `<div class="srcs">${c.docs.map((d, i) => `<div class="src"><span class="n">[${i + 1}]</span><span>${esc(d.title)}</span></div>`).join('')}</div>` : 'No matching documents.');
        break;
      case 'chart':
        c.chart = ev.spec; break;
      case 'answer':
        c.answer = ev.text; renderAnswerCard(turn); break;
      case 'done':
        finishPipeline(turn); endRun(turn); break;
      case 'error':
        turn.root.appendChild(el('div', 'err', esc(ev.message || 'Something went wrong.'))); endRun(turn); break;
    }
  }

  /* ---------- Approval card ---------- */
  function renderApproval(turn, ev) {
    if (turn.lastStep) turn.lastStep.classList.replace('active', 'done');
    const card = el('div', 'approval');
    card.innerHTML =
      `<div class="approval-head">⚠ Approval needed before running this query</div>
       <div class="small muted">${esc(ev.reason || '')}</div>
       <div class="code mono">${esc(ev.sql)}</div>
       <div class="approval-actions"><button class="btn btn-approve">Approve &amp; run</button><button class="btn btn-reject">Reject</button></div>`;
    turn.root.insertBefore(card, turn.root.querySelector('.answer-card') || null);
    const decide = (approved) => {
      card.remove();
      run(turn, `/api/resume?thread_id=${turn.threadId}&approved=${approved}`);
    };
    card.querySelector('.btn-approve').addEventListener('click', () => decide(true));
    card.querySelector('.btn-reject').addEventListener('click', () => decide(false));
  }

  /* ---------- Answer card (answer + chart + trust panel) ---------- */
  function renderAnswerCard(turn) {
    const c = turn.ctx;
    const card = el('div', 'answer-card');
    card.appendChild(el('div', 'answer-body', `<div class="answer">${renderAnswer(c.answer || '')}</div>`));

    const chartable = c.chart && c.chart.type && c.chart.type !== 'none' && c.result && (c.result.rows || []).length > 1;
    if (chartable) {
      const box = el('div', 'chart-box', '<div class="chart-wrap"><canvas></canvas></div>');
      card.appendChild(box);
      setTimeout(() => drawChart(box.querySelector('canvas'), c.chart, c.result), 30);
    }

    if (c.sql || c.result) card.appendChild(buildTrust(c));

    const actions = el('div', 'answer-actions');
    const copy = el('button', 'act', 'Copy answer');
    copy.addEventListener('click', () => navigator.clipboard.writeText(c.answer || ''));
    actions.appendChild(copy);
    if (c.result && (c.result.rows || []).length) {
      const csv = el('button', 'act', 'Download CSV');
      csv.addEventListener('click', () => downloadCSV(c.result, turn.question));
      actions.appendChild(csv);
    }
    card.appendChild(actions);
    turn.root.appendChild(card); scrollDown();
  }

  function buildTrust(c) {
    const det = el('details', 'trust');
    const chips = [];
    if (c.sql) chips.push('<span class="tchip">SQL</span>');
    if (c.result && c.result.row_count != null) chips.push(`<span class="tchip">${c.result.row_count} rows</span>`);
    if (c.review) chips.push(`<span class="tchip ${c.review.answers_question ? 'ok' : ''}">${c.review.answers_question ? '✓ validated' : 'flagged'}</span>`);
    chips.push('<span class="tchip">traced in LangSmith</span>');
    let body = '';
    if (c.sql) body += `<div class="lbl">Query that ran</div><div class="code mono">${esc(c.sql)}</div>`;
    if (c.result && (c.result.rows || []).length) body += `<div class="lbl">Result</div>${resultTable(c.result)}`;
    det.innerHTML = `<summary>How this answer was produced ${chips.join('')}</summary><div class="trust-body">${body}</div>`;
    return det;
  }

  function resultTable(r) {
    const cols = r.columns || [];
    const head = cols.map((c) => `<th>${esc(c)}</th>`).join('');
    const rows = (r.rows || []).slice(0, 100).map((row) => `<tr>${cols.map((c) => `<td>${esc(row[c])}</td>`).join('')}</tr>`).join('');
    return `<div class="result-table-wrap"><table class="result"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  /* ---------- Chart (monochrome / emerald) ---------- */
  function drawChart(canvas, spec, result) {
    const rows = result.rows || [];
    const labels = rows.map((r) => r[spec.x]);
    const values = rows.map((r) => Number(r[spec.y]));
    const accent = cssVar('--accent') || '#10b981';
    const grid = cssVar('--border') || '#262629';
    const text = cssVar('--muted') || '#888';
    const palette = [accent, '#52525b', '#a1a1aa', '#3f3f46', '#71717a', '#d4d4d8'];
    const cfg = {
      type: spec.type === 'pie' ? 'pie' : spec.type,
      data: {
        labels,
        datasets: [{
          label: spec.y, data: values,
          backgroundColor: spec.type === 'line' ? 'transparent' : (spec.type === 'pie' ? labels.map((_, i) => palette[i % palette.length]) : accent),
          borderColor: accent, borderWidth: spec.type === 'line' ? 2 : 0, tension: 0.3,
          pointBackgroundColor: accent, borderRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: spec.type === 'pie', labels: { color: text, font: { size: 11 } } },
          title: { display: !!spec.title, text: spec.title, color: text, font: { size: 12, weight: '600' } } },
        scales: spec.type === 'pie' ? {} : {
          x: { ticks: { color: text, font: { size: 10 } }, grid: { color: grid } },
          y: { ticks: { color: text, font: { size: 10 } }, grid: { color: grid }, beginAtZero: true },
        },
      },
    };
    canvas._chart = new Chart(canvas, cfg);
  }

  function downloadCSV(result, name) {
    const cols = result.columns || [];
    const lines = [cols.join(',')].concat((result.rows || []).map((r) => cols.map((c) => JSON.stringify(r[c] ?? '')).join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = el('a'); a.href = URL.createObjectURL(blob); a.download = (name || 'atlas').slice(0, 40).replace(/[^\w]+/g, '-') + '.csv';
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------- Run lifecycle ---------- */
  function run(turn, url) {
    const es = new EventSource(url);
    turn.es = es;
    es.onmessage = (e) => { let d; try { d = JSON.parse(e.data); } catch { return; } if (d.type === 'approval_required') turn.threadId = d.thread_id; handle(turn, d); };
    es.onerror = () => { if (turn.es) { es.close(); turn.es = null; if (busy) { endRun(turn); } } };
  }

  function ask(question) {
    question = (question || '').trim();
    if (!question || busy) return;
    setBusy(true);
    $('#q').value = '';
    const turn = newTurn(question);
    turn.threadId = uid();
    run(turn, `/api/ask?question=${encodeURIComponent(question)}&thread_id=${turn.threadId}`);
  }

  function endRun(turn) {
    if (turn.es) { turn.es.close(); turn.es = null; }
    setBusy(false);
  }

  function setBusy(b) {
    busy = b;
    $('#ask-btn').disabled = b;
    $('.run-label').hidden = b; $('.run-spin').hidden = !b;
  }

  function scrollDown() { const t = $('#thread'); requestAnimationFrame(() => { t.scrollTop = t.scrollHeight; }); }

  /* ---------- Wire up ---------- */
  initTheme();
  loadSchema();
  renderSamples();
  $('#ask-form').addEventListener('submit', (e) => { e.preventDefault(); ask($('#q').value); });
})();
