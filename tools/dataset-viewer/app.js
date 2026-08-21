'use strict';

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

let MANIFEST = { tasks: [] };
let activeTask = '';        // task id filter, '' = all
let searchText = '';        // lowercased instruction query
let missingOnly = false;
let autoplayHover = false;

function showToast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.add('hidden'), 2400);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function highlight(text, q) {
  if (!q) return escapeHtml(text);
  const idx = text.toLowerCase().indexOf(q);
  if (idx < 0) return escapeHtml(text);
  return escapeHtml(text.slice(0, idx)) +
    '<mark>' + escapeHtml(text.slice(idx, idx + q.length)) + '</mark>' +
    escapeHtml(text.slice(idx + q.length));
}

// --------------------------------------------------------------- filters ---
function isMissing(ep) {
  return !ep.hasInstr || (ep.seen.length === 0 && ep.unseen.length === 0);
}

function episodeMatches(ep) {
  if (missingOnly && !isMissing(ep)) return false;
  if (searchText) {
    const hit = ep.seen.some(s => s.toLowerCase().includes(searchText)) ||
      ep.unseen.some(s => s.toLowerCase().includes(searchText));
    if (!hit) return false;
  }
  return true;
}

function populateTaskSelect() {
  const sel = $('#task-select');
  const total = MANIFEST.tasks.reduce((n, t) => n + t.episodes.length, 0);
  sel.innerHTML = `<option value="">all tasks (${total})</option>` +
    MANIFEST.tasks.map(t => `<option value="${t.id}">${t.task} · ${t.demo} (${t.episodes.length})</option>`).join('');
  sel.value = activeTask;
}

// ---------------------------------------------------------------- cards ---
// Prefer an instruction that matches the search; else first seen, else unseen.
function displayInstr(ep) {
  if (searchText) {
    const pools = [['seen', ep.seen], ['unseen', ep.unseen]];
    for (const [kind, arr] of pools) {
      const m = arr.find(s => s.toLowerCase().includes(searchText));
      if (m) return { text: m, kind };
    }
  }
  if (ep.seen.length) return { text: ep.seen[0], kind: 'seen' };
  if (ep.unseen.length) return { text: ep.unseen[0], kind: 'unseen' };
  return null;
}

function makeCard(task, ep) {
  const card = document.createElement('div');
  card.className = 'card';

  const vwrap = document.createElement('div');
  vwrap.className = 'card-video';
  const badgeCls = isMissing(ep) ? 'card-badge warn' : 'card-badge';
  const badgeTxt = isMissing(ep) ? ep.name + ' · no instr' : ep.name;
  vwrap.innerHTML = `<span class="${badgeCls}">${badgeTxt}</span><div class="card-play">▶</div>`;

  const video = document.createElement('video');
  video.src = ep.video;
  video.muted = true;
  video.loop = true;
  video.playsInline = true;
  video.preload = 'metadata';
  vwrap.insertBefore(video, vwrap.firstChild);

  vwrap.addEventListener('mouseenter', () => { if (autoplayHover) video.play().catch(() => {}); });
  vwrap.addEventListener('mouseleave', () => { if (autoplayHover) video.pause(); });
  vwrap.addEventListener('click', () => openDetail(task, ep));

  const body = document.createElement('div');
  body.className = 'card-body';
  const d = displayInstr(ep);
  const instrEl = document.createElement('div');
  instrEl.className = 'card-instr' + (d ? '' : ' none');
  if (d) {
    instrEl.innerHTML = highlight(d.text, searchText);
    if (searchText && d.kind === 'unseen') instrEl.innerHTML = '<span class="tag-unseen">unseen</span> ' + instrEl.innerHTML;
  } else {
    instrEl.textContent = 'no instruction file';
  }

  const foot = document.createElement('div');
  foot.className = 'card-foot';
  foot.innerHTML =
    `<span class="pill seen">seen ${ep.seen.length}</span>` +
    `<span class="pill unseen">unseen ${ep.unseen.length}</span>` +
    `<span class="more">all →</span>`;
  foot.querySelector('.more').onclick = (e) => { e.stopPropagation(); openDetail(task, ep); };

  body.appendChild(instrEl);
  body.appendChild(foot);
  card.appendChild(vwrap);
  card.appendChild(body);
  return card;
}

function renderContent() {
  const root = $('#content');
  root.innerHTML = '';
  const tasks = activeTask ? MANIFEST.tasks.filter(t => t.id === activeTask) : MANIFEST.tasks;

  let shown = 0;
  for (const t of tasks) {
    const eps = t.episodes.filter(episodeMatches);
    if (!eps.length) continue;
    const sec = document.createElement('section');
    sec.className = 'task-section';
    const head = document.createElement('div');
    head.className = 'task-head';
    head.innerHTML = `<h2>${t.task}</h2><span class="demo">${t.demo}</span>` +
      `<span class="ep-count">${eps.length}${eps.length !== t.episodes.length ? ' / ' + t.episodes.length : ''} episodes</span>`;
    const grid = document.createElement('div');
    grid.className = 'grid';
    for (const ep of eps) { grid.appendChild(makeCard(t, ep)); shown++; }
    sec.appendChild(head);
    sec.appendChild(grid);
    root.appendChild(sec);
  }

  if (!shown) {
    const why = missingOnly ? '没有缺 instruction 的 episode 🎉'
      : searchText ? `没有匹配 “${searchText}” 的 instruction`
        : 'No datasets found. Run gen_manifest.py.';
    root.innerHTML = `<div class="empty">${escapeHtml(why)}</div>`;
  }
  $('#count').textContent = `${shown} episode${shown === 1 ? '' : 's'}`;
}

// --------------------------------------------------------------- detail ---
let detailKind = 'seen';
let detailEp = null;

function renderInstrList() {
  const list = $('#instr-list');
  const items = (detailEp[detailKind] || []);
  list.innerHTML = '';
  if (!items.length) {
    list.innerHTML = '<li style="color:var(--muted);list-style:none;margin-left:-20px">— none —</li>';
  } else {
    for (const s of items) {
      const li = document.createElement('li');
      if (searchText && s.toLowerCase().includes(searchText)) {
        li.innerHTML = highlight(s, searchText);
        li.classList.add('hit');
      } else {
        li.textContent = s;
      }
      list.appendChild(li);
    }
  }
  $$('.instr-tab').forEach(b => b.classList.toggle('active', b.dataset.kind === detailKind));
}

function openDetail(task, ep) {
  detailEp = ep;
  detailKind = (ep.seen.length ? 'seen' : (ep.unseen.length ? 'unseen' : 'seen'));
  $('#detail-title').textContent = `${task.task} · ${ep.name}`;
  $('#detail-meta').textContent = task.id;
  $('#cnt-seen').textContent = ep.seen.length;
  $('#cnt-unseen').textContent = ep.unseen.length;
  const v = $('#detail-video');
  v.src = ep.video;
  v.play().catch(() => {});
  renderInstrList();
  const dd = $('#detail');
  dd.classList.remove('hidden');
  dd.setAttribute('aria-hidden', 'false');
}

function closeDetail() {
  const dd = $('#detail');
  dd.classList.add('hidden');
  dd.setAttribute('aria-hidden', 'true');
  const v = $('#detail-video');
  v.pause();
  v.removeAttribute('src');
  v.load();
}

// ----------------------------------------------------------------- init ---
async function init() {
  $('#detail-close').onclick = closeDetail;
  $('#detail').addEventListener('click', (e) => { if (e.target.id === 'detail') closeDetail(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });
  $$('.instr-tab').forEach(b => b.onclick = () => { detailKind = b.dataset.kind; renderInstrList(); });

  $('#task-select').onchange = (e) => { activeTask = e.target.value; renderContent(); };
  $('#opt-missing').onchange = (e) => { missingOnly = e.target.checked; renderContent(); };
  $('#opt-autoplay').onchange = (e) => { autoplayHover = e.target.checked; };

  const search = $('#search');
  search.addEventListener('input', (e) => {
    clearTimeout(search._t);
    search._t = setTimeout(() => {
      searchText = e.target.value.trim().toLowerCase();
      renderContent();
    }, 180);
  });

  try {
    const res = await fetch('manifest.json', { cache: 'no-store' });
    MANIFEST = await res.json();
  } catch (err) {
    showToast('Failed to load manifest.json');
    MANIFEST = { tasks: [] };
  }
  populateTaskSelect();
  renderContent();
}

init();
