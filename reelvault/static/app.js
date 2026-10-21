/* ReelVault workspace UI. Vanilla JS, hash routing, no external assets. */
(() => {
  'use strict';
  const $ = (sel, el = document) => el.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtDate = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(); };
  const state = {
    status: null, categories: [], trips: [], filters: loadFilters(), view: localStorage.getItem('rv.view') || 'grid',
    pollTimer: null,
  };
  function loadFilters() { try { return JSON.parse(localStorage.getItem('rv.filters') || '{}'); } catch { return {}; } }
  function saveFilters() { localStorage.setItem('rv.filters', JSON.stringify(state.filters)); }

  // ------------------------------------------------------------------ api
  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body instanceof FormData) init.body = opts.body;
    else if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    const r = await fetch(path, init);
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = text; }
    if (!r.ok) { const msg = (data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : r.statusText; throw new Error(msg); }
    return data;
  }
  function toast(msg, kind = '') {
    const el = document.createElement('div'); el.className = 'toast ' + kind; el.textContent = msg;
    $('#toasts').appendChild(el); setTimeout(() => el.remove(), kind === 'err' ? 7000 : 3500);
  }
  function modal(html) { $('#modal-card').innerHTML = html; $('#modal').classList.remove('hidden'); return $('#modal-card'); }
  function closeModal() { $('#modal').classList.add('hidden'); }
  $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeModal(); });

  // --------------------------------------------------------------- loaders
  async function refreshStatus() {
    state.status = await api('/api/status');
    const c = state.status.counts;
    for (const el of document.querySelectorAll('[data-count]')) el.textContent = c[el.dataset.count] || '';
    const s = state.status;
    $('#server-info').innerHTML = `v${esc(s.version)}<br>${s.lan_enabled_running ? `LAN: <span class="mono">${esc(s.lan_ip || '?')}:${s.port}</span>` : 'LAN access off'}`;
  }
  async function loadRefs() {
    [state.categories, state.trips] = await Promise.all([api('/api/categories'), api('/api/trips?include_archived=true')]);
  }

  // ---------------------------------------------------------------- routing
  const routes = {
    inbox: () => renderList({ title: 'Inbox', inbox: true, key: 'inbox' }),
    all: () => renderList({ title: 'All Ideas', key: 'all' }),
    priority: () => renderList({ title: 'High priority', priority: 'High', key: 'priority' }),
    published: () => renderList({ title: 'Published', status: 'Published', key: 'published' }),
    trips: renderTrips, trip: renderTrip, idea: renderIdea, settings: renderSettings,
  };
  async function route() {
    const parts = location.hash.replace(/^#\/?/, '').split('/');
    const name = parts[0] || 'inbox';
    for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.route === (name === 'trip' ? 'trips' : name === 'idea' ? '' : name));
    clearInterval(state.pollTimer);
    try {
      await loadRefs();
      await (routes[name] || routes.inbox)(parts[1]);
    } catch (e) { $('#view').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
    refreshStatus().catch(() => {});
  }
  window.addEventListener('hashchange', route);

  // ------------------------------------------------------------ list views
  function filterBar(ctx) {
    const f = state.filters[ctx.key] || {};
    const opt = (list, cur, label) => `<option value="">${label}</option>` + list.map((v) => `<option value="${esc(v.id ?? v)}" ${(v.id ?? v) === cur ? 'selected' : ''}>${esc(v.name ?? v)}</option>`).join('');
    return `<div class="toolbar">
      <input type="search" id="f-q" placeholder="Search titles, captions, notes, creators" value="${esc(f.q || '')}">
      ${ctx.status ? '' : `<select id="f-status">${opt(state.status.statuses, f.status, 'Any status')}</select>`}
      ${ctx.priority ? '' : `<select id="f-priority">${opt(state.status.priorities, f.priority, 'Any priority')}</select>`}
      <select id="f-category">${opt(state.categories, f.category_id, 'Any category')}</select>
      ${ctx.inbox ? '' : `<select id="f-trip">${opt(state.trips, f.trip_id, 'Any trip')}</select>`}
      <select id="f-download">${opt(state.status.download_statuses.map((d) => ({ id: d, name: d.replace('_', ' ') })), f.download_status, 'Any download state')}</select>
      <input type="date" id="f-from" value="${esc(f.captured_from || '')}" title="Captured from"><input type="date" id="f-to" value="${esc(f.captured_to || '')}" title="Captured to">
      <button class="btn small" id="f-clear">Clear</button>
      <span style="flex:1"></span>
      <button class="btn small" id="v-grid" ${state.view === 'grid' ? 'disabled' : ''}>Grid</button><button class="btn small" id="v-list" ${state.view === 'list' ? 'disabled' : ''}>List</button>
    </div>`;
  }
  function readFilters(ctx) {
    const g = (id) => ($(id) ? $(id).value : '');
    state.filters[ctx.key] = { q: g('#f-q'), status: g('#f-status'), priority: g('#f-priority'), category_id: g('#f-category'), trip_id: g('#f-trip'), download_status: g('#f-download'), captured_from: g('#f-from'), captured_to: g('#f-to') };
    saveFilters();
  }
  async function renderList(ctx) {
    const v = $('#view');
    v.innerHTML = `<div class="row between"><h1>${esc(ctx.title)}</h1><span class="muted small" id="list-count"></span></div>${filterBar(ctx)}<div id="list"></div>`;
    const reload = async () => {
      readFilters(ctx);
      const f = state.filters[ctx.key];
      const p = new URLSearchParams();
      for (const [k, val] of Object.entries(f)) if (val) p.set(k, val);
      if (ctx.inbox) p.set('inbox', 'true');
      if (ctx.status) p.set('status', ctx.status);
      if (ctx.priority) p.set('priority', ctx.priority);
      const data = await api('/api/ideas?' + p.toString());
      $('#list-count').textContent = `${data.count} idea${data.count === 1 ? '' : 's'}`;
      renderCards($('#list'), data.items, reload);
    };
    for (const el of v.querySelectorAll('.toolbar input, .toolbar select')) el.addEventListener(el.type === 'search' ? 'input' : 'change', debounce(reload, 250));
    $('#f-clear').onclick = () => { state.filters[ctx.key] = {}; saveFilters(); route(); };
    $('#v-grid').onclick = () => { state.view = 'grid'; localStorage.setItem('rv.view', 'grid'); route(); };
    $('#v-list').onclick = () => { state.view = 'list'; localStorage.setItem('rv.view', 'list'); route(); };
    await reload();
    state.pollTimer = setInterval(async () => { if (document.hidden) return; const anyPending = $('#list').querySelector('[data-pending]'); if (anyPending) reload().catch(() => {}); }, 4000);
  }
  function thumbStyle(i) { return i.thumbnail_path ? `style="background-image:url('/api/ideas/${i.id}/thumbnail?v=${encodeURIComponent(i.updated_at)}')"` : ''; }
  function metaBadge(i) {
    const m = { pending: ['warn', 'metadata pending'], fetching: ['warn', 'fetching metadata'], ok: ['ok', 'metadata ok'], unavailable: ['bad', 'metadata unavailable'] }[i.metadata_status] || ['', i.metadata_status];
    return `<span class="badge ${m[0]}" title="${esc(i.metadata_error || '')}">${m[1]}</span>`;
  }
  function renderCards(container, items, reload) {
    container.className = state.view;
    if (!items.length) { container.innerHTML = '<div class="empty">Nothing here yet. Share a Reel from your phone, or add an idea by link.</div>'; return; }
    container.innerHTML = items.map((i) => `<div class="card" data-id="${i.id}" ${['pending', 'fetching'].includes(i.metadata_status) || ['queued', 'downloading'].includes(i.download_status) ? 'data-pending="1"' : ''}>
      <div class="thumb" ${thumbStyle(i)} data-open>${i.thumbnail_path ? '' : '<span>no thumbnail</span>'}</div>
      <div class="body">
        <div class="title" data-open>${esc(i.title || i.original_url)}</div>
        <div class="muted small">${esc(i.creator || '')}${i.creator ? ' · ' : ''}${fmtDate(i.captured_at)}</div>
        <div class="row">
          <select class="inline" data-field="priority">${state.status.priorities.map((p) => `<option ${p === i.priority ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select>
          <select class="inline" data-field="status">${state.status.statuses.map((s) => `<option ${s === i.status ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>
        </div>
        <div class="row small">${metaBadge(i)}${i.download_status !== 'not_downloaded' ? `<span class="badge ${i.download_status === 'downloaded' ? 'ok' : i.download_status === 'failed' ? 'bad' : 'warn'}">${esc(i.download_status.replace('_', ' '))}</span>` : ''}${i.category_name ? `<span class="badge">${esc(i.category_name)}</span>` : ''}${i.trips.map((t) => `<span class="badge">${esc(t.name)}</span>`).join('')}</div>
      </div></div>`).join('');
    for (const card of container.querySelectorAll('.card')) {
      const id = card.dataset.id;
      for (const o of card.querySelectorAll('[data-open]')) o.onclick = () => { location.hash = '#/idea/' + id; };
      for (const sel of card.querySelectorAll('select[data-field]')) sel.onchange = async () => {
        try { await api('/api/ideas/' + id, { method: 'PUT', body: { fields: { [sel.dataset.field]: sel.value } } }); toast('Saved', 'ok'); refreshStatus(); if (reload) reload(); }
        catch (e) { toast(e.message, 'err'); }
      };
    }
  }

  // ------------------------------------------------------------ idea detail
  async function renderIdea(id) {
    const i = await api('/api/ideas/' + id);
    const v = $('#view');
    const opt = (list, cur) => list.map((x) => `<option value="${esc(x.id ?? x)}" ${(x.id ?? x) === cur ? 'selected' : ''}>${esc(x.name ?? x)}</option>`).join('');
    const tools = state.status.tools, ai = state.status.ai;
    v.innerHTML = `
    <div class="row between"><h1 style="margin:0">${esc(i.title || 'Untitled idea')}</h1><div class="row"><a class="btn small" href="${esc(i.original_url)}" target="_blank" rel="noopener">Open original</a><button class="btn small danger" id="btn-delete">Delete</button></div></div>
    <div class="detail" style="margin-top:14px">
      <div>
        <div class="panel"><div class="form">
          <label>Title</label><input id="e-title" value="${esc(i.title)}">
          <label>Creator</label><input id="e-creator" value="${esc(i.creator)}">
          <label>Original URL</label><div class="mono small" style="padding-top:8px;word-break:break-all">${esc(i.original_url)}</div>
          <label>Canonical URL</label><input id="e-canonical_url" value="${esc(i.canonical_url || '')}" placeholder="filled by metadata when known">
          <label>Caption / metadata</label><textarea id="e-caption">${esc(i.caption)}</textarea>
          <label>Personal notes</label><textarea id="e-notes">${esc(i.notes)}</textarea>
          <label>Category</label><select id="e-category_id"><option value="">None</option>${opt(state.categories, i.category_id)}</select>
          <label>Priority</label><select id="e-priority">${opt(state.status.priorities, i.priority)}</select>
          <label>Status</label><select id="e-status">${opt(state.status.statuses, i.status)}</select>
          <label>Trips</label><div class="chips" id="e-trips">${state.trips.filter((t) => !t.archived || i.trips.some((x) => x.id === t.id)).map((t) => `<span class="chip ${i.trips.some((x) => x.id === t.id) ? 'on' : ''}" data-trip="${t.id}">${esc(t.name)}</span>`).join('') || '<span class="muted">No trips yet. Create one under Trips &amp; Projects.</span>'}</div>
          <label>Shooting notes</label><textarea id="e-shooting_notes">${esc(i.shooting_notes)}</textarea>
          <label>Editing notes</label><textarea id="e-editing_notes">${esc(i.editing_notes)}</textarea>
          <label>Transcript (optional)</label><textarea id="e-transcript" placeholder="Paste a transcript or spoken lines; used as analysis input">${esc(i.transcript)}</textarea>
          <label>Finished video link</label><input id="e-finished_video_url" value="${esc(i.finished_video_url)}" placeholder="https://... (when Published)">
          <label>Follow-up date</label><input type="date" id="e-follow_up_date" value="${esc(i.follow_up_date || '')}" title="Used by reminders for High priority ideas">
          <label></label><div class="row"><button class="btn primary" id="btn-save">Save</button><span class="muted small">Captured ${fmtDate(i.captured_at)} · updated ${fmtDate(i.updated_at)} · source ${esc(i.source)}</span></div>
        </div></div>

        <div class="panel" id="analysis-panel"></div>
      </div>
      <div class="side">
        <div class="thumb" ${thumbStyle(i)}></div>
        <div class="panel" style="margin-top:12px">
          <h3 style="margin-top:0">Metadata</h3>
          <div class="status-line">${metaBadge(i)}${i.metadata_provider ? `<span class="muted small">via ${esc(i.metadata_provider)}</span>` : ''}</div>
          ${i.metadata_error ? `<div class="small muted">${esc(i.metadata_error)}</div>` : ''}
          ${i.metadata_status === 'unavailable' ? '<div class="small muted">The link is kept. Add a title and notes by hand, or retry later.</div>' : ''}
          <button class="btn small" id="btn-meta-retry" style="margin-top:6px">Retry metadata</button>
        </div>
        <div class="panel">
          <h3 style="margin-top:0">Reference download</h3>
          <div class="status-line"><span class="badge ${i.download_status === 'downloaded' ? 'ok' : i.download_status === 'failed' ? 'bad' : i.download_status === 'not_downloaded' ? '' : 'warn'}">${esc(i.download_status.replace('_', ' '))}</span>${i.jobs.download && i.download_status === 'downloading' ? `<span class="small muted">${Math.round(i.jobs.download.progress)}%</span>` : ''}</div>
          ${i.download_error ? `<div class="small muted">${esc(i.download_error)}</div>` : ''}
          ${i.local_path ? `<div class="small mono" style="word-break:break-all">${esc(i.local_path)}</div>` : ''}
          ${tools.ytdlp.found ? '' : `<div class="small muted">yt-dlp not found. ${esc(tools.ytdlp.install_hint)}</div>`}
          <div class="row" style="margin-top:6px">
            <button class="btn small" id="btn-download" ${!tools.ytdlp.found || ['queued', 'downloading'].includes(i.download_status) ? 'disabled' : ''}>${i.download_status === 'downloaded' ? 'Download again' : 'Download reference'}</button>
            ${i.local_path ? '<button class="btn small" id="btn-open">Open in player</button><button class="btn small" id="btn-reveal">Reveal in Explorer</button>' : ''}
          </div>
        </div>
        <div class="panel">
          <h3 style="margin-top:0">Screenshots</h3>
          <div class="small muted">Optional inputs for AI analysis (PNG/JPG/WEBP).</div>
          <div id="att-list">${i.attachments.map((a) => `<div class="row small"><a href="/api/attachments/${a.id}" target="_blank">${esc(a.filename)}</a><button class="btn small" data-del-att="${a.id}">x</button></div>`).join('')}</div>
          <input type="file" id="att-file" accept=".png,.jpg,.jpeg,.webp" style="margin-top:6px">
        </div>
      </div>
    </div>`;
    const fields = ['title', 'creator', 'canonical_url', 'caption', 'notes', 'category_id', 'priority', 'status', 'shooting_notes', 'editing_notes', 'transcript', 'finished_video_url', 'follow_up_date'];
    $('#btn-save').onclick = async () => {
      const f = {}; for (const k of fields) f[k] = $('#e-' + k).value;
      if (!f.category_id) f.category_id = null;
      if (!f.follow_up_date) f.follow_up_date = null;
      try { await api('/api/ideas/' + id, { method: 'PUT', body: { fields: f, expected_updated_at: i.updated_at } }); toast('Saved', 'ok'); renderIdea(id); }
      catch (e) { toast(e.message, 'err'); }
    };
    for (const chip of v.querySelectorAll('[data-trip]')) chip.onclick = async () => {
      chip.classList.toggle('on');
      const ids = [...v.querySelectorAll('[data-trip].on')].map((c) => c.dataset.trip);
      try { await api(`/api/ideas/${id}/trips`, { method: 'PUT', body: { trip_ids: ids } }); toast('Trips updated', 'ok'); refreshStatus(); } catch (e) { toast(e.message, 'err'); }
    };
    $('#btn-delete').onclick = async () => { if (!confirm('Delete this idea? (The original link stays in the backup DB; local files are never deleted.)')) return; await api('/api/ideas/' + id, { method: 'DELETE' }); toast('Deleted'); location.hash = '#/inbox'; };
    $('#btn-meta-retry').onclick = async () => { await api(`/api/ideas/${id}/metadata/retry`, { method: 'POST' }); toast('Metadata retry queued'); setTimeout(() => renderIdea(id), 2500); };
    const dl = $('#btn-download'); if (dl) dl.onclick = async () => { try { const r = await api(`/api/ideas/${id}/download`, { method: 'POST' }); if (!r.ok) toast(r.error, 'err'); else { toast('Download queued'); renderIdea(id); } } catch (e) { toast(e.message, 'err'); } };
    const op = $('#btn-open'); if (op) op.onclick = () => api(`/api/ideas/${id}/open`, { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    const rv = $('#btn-reveal'); if (rv) rv.onclick = () => api(`/api/ideas/${id}/reveal`, { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    $('#att-file').onchange = async (e) => { const fd = new FormData(); fd.append('file', e.target.files[0]); try { await api(`/api/ideas/${id}/attachments`, { method: 'POST', body: fd }); toast('Uploaded', 'ok'); renderIdea(id); } catch (err) { toast(err.message, 'err'); } };
    for (const b of v.querySelectorAll('[data-del-att]')) b.onclick = async () => { await api('/api/attachments/' + b.dataset.delAtt, { method: 'DELETE' }); renderIdea(id); };
    renderAnalysis(i, ai);
    if (['queued', 'downloading'].includes(i.download_status) || ['queued', 'running'].includes(i.analysis_status) || i.metadata_status === 'fetching') {
      state.pollTimer = setInterval(async () => { if (document.hidden) return; const cur = await api('/api/ideas/' + id); if (cur.download_status !== i.download_status || cur.analysis_status !== i.analysis_status || cur.metadata_status !== i.metadata_status || (cur.jobs.download && i.jobs.download && cur.jobs.download.progress !== i.jobs.download.progress)) { if (document.activeElement && document.activeElement.tagName === 'TEXTAREA') return; renderIdea(id); } }, 2500);
    }
  }
  function renderAnalysis(i, ai) {
    const p = $('#analysis-panel');
    const a = i.analysis, b = a && a.brief;
    const inputs = a && a.inputs ? a.inputs : null;
    const inputLine = inputs ? `Inputs given to the model: ${['title', 'creator', 'caption', 'notes', 'transcript'].filter((k) => inputs[k]).join(', ') || 'URL only'}${inputs.frames ? `, ${inputs.frames} extracted frame(s)` : ''}${inputs.screenshots ? `, ${inputs.screenshots} screenshot(s)` : ''}. The video itself was not watched.` : '';
    p.innerHTML = `<div class="row between"><h3 style="margin:0">AI analysis <span class="muted small">(optional, on demand)</span></h3>
      <div class="row"><button class="btn small primary" id="btn-analyze" ${!ai.configured || ['queued', 'running'].includes(i.analysis_status) ? 'disabled' : ''}>${['queued', 'running'].includes(i.analysis_status) ? 'Analyzing...' : b ? 'Re-analyze' : 'Analyze Reel'}</button>${b ? `<a class="btn small" href="/api/ideas/${i.id}/analysis.md" download="brief.md">Export .md</a>` : ''}</div></div>
      ${ai.configured ? `<div class="small muted">Provider ${esc(ai.provider)} · model ${esc(ai.model)}. Each run calls the provider and may cost money; nothing runs automatically.</div>` : `<div class="small muted">No AI key configured, so analysis is unavailable. ${esc(ai.how_to_configure)}</div>`}
      ${i.analysis_status === 'failed' ? `<div class="small" style="color:var(--danger)">Last attempt failed: ${esc(i.analysis_error || '')} <button class="btn small" id="btn-analyze-retry" ${ai.configured ? '' : 'disabled'}>Retry</button></div>` : ''}
      ${['queued', 'running'].includes(i.analysis_status) ? '<div class="small muted">Working... this view refreshes automatically.</div>' : ''}
      ${b ? `<div class="small muted" style="margin:6px 0">${esc(inputLine)} ${a.edited ? '· edited by you' : ''}</div><div class="brief" id="brief"></div>` : ''}`;
    const run = async () => { try { const r = await api(`/api/ideas/${i.id}/analyze`, { method: 'POST' }); if (!r.ok) toast(r.error, 'err'); else { toast('Analysis started'); renderIdea(i.id); } } catch (e) { toast(e.message, 'err'); } };
    $('#btn-analyze').onclick = run; const rr = $('#btn-analyze-retry'); if (rr) rr.onclick = run;
    if (!b) return;
    const textFields = [['core_idea', 'Core idea'], ['opening_hook', 'Opening hook'], ['story_structure', 'Story structure'], ['camera_approach', 'Camera approach'], ['editing_approach', 'Editing approach'], ['sound_design', 'Sound design'], ['recreation_plan', 'Recreation plan'], ['personal_notes', 'Personal notes'], ['confidence_note', 'Confidence note']];
    const el = $('#brief');
    el.innerHTML = `<div class="field"><label>Observed facts (only what the inputs showed; one per line)</label><textarea id="b-observed_facts">${esc((b.observed_facts || []).join('\n'))}</textarea></div>
      ${textFields.map(([k, l]) => `<div class="field"><label>${l} <span class="muted">(AI suggestion)</span></label><textarea id="b-${k}">${esc(b[k] || '')}</textarea></div>`).join('')}
      <div class="field"><label>Shot list (AI suggestion)</label><table class="shots" id="b-shots"><tr><th>#</th><th>Shot</th><th>Description</th><th>Sec</th><th>Camera</th><th></th></tr>${(b.shot_list || []).map((s, n) => shotRow(s, n)).join('')}</table><button class="btn small" id="b-add-shot">+ shot</button></div>
      <div class="field"><label>Production requirements (one per line)</label><textarea id="b-production_requirements">${esc((b.production_requirements || []).join('\n'))}</textarea></div>
      <button class="btn primary" id="b-save">Save brief</button>`;
    $('#b-add-shot').onclick = () => { const tb = $('#b-shots'); const tr = document.createElement('tr'); tr.innerHTML = shotRow({}, tb.rows.length - 1).replace(/^<tr>|<\/tr>$/g, ''); tb.appendChild(tr); bindShotDel(tb); };
    const bindShotDel = (tb) => { for (const d of tb.querySelectorAll('[data-del]')) d.onclick = () => d.closest('tr').remove(); };
    bindShotDel($('#b-shots'));
    $('#b-save').onclick = async () => {
      const lines = (id) => $(id).value.split('\n').map((s) => s.trim()).filter(Boolean);
      const brief = { observed_facts: lines('#b-observed_facts'), production_requirements: lines('#b-production_requirements'), shot_list: [] };
      for (const [k] of textFields) brief[k] = $('#b-' + k).value;
      for (const tr of [...$('#b-shots').rows].slice(1)) { const c = tr.querySelectorAll('input'); if (!c[0].value.trim()) continue; brief.shot_list.push({ shot: c[0].value, description: c[1].value, duration_seconds: c[2].value ? Number(c[2].value) : null, camera: c[3].value }); }
      try { await api(`/api/ideas/${i.id}/analysis`, { method: 'PUT', body: { brief } }); toast('Brief saved', 'ok'); } catch (e) { toast(e.message, 'err'); }
    };
  }
  function shotRow(s, n) { return `<tr><td>${n + 1}</td><td><input value="${esc(s.shot || '')}"></td><td><input value="${esc(s.description || '')}"></td><td style="width:60px"><input value="${s.duration_seconds ?? ''}"></td><td><input value="${esc(s.camera || '')}"></td><td><button class="btn small" data-del>x</button></td></tr>`; }

  // ------------------------------------------------------------------ trips
  async function renderTrips() {
    const trips = state.trips;
    $('#view').innerHTML = `<div class="row between"><h1>Trips &amp; Projects</h1><button class="btn primary" id="btn-new-trip">+ New trip</button></div>
      <div class="muted small" style="margin-bottom:12px">Lightweight collections. Ideas stay in the Inbox until you assign them; nothing is assigned automatically.</div>
      ${trips.length ? `<table><tr><th>Name</th><th>Location</th><th>Dates</th><th>Ideas</th><th></th></tr>${trips.map((t) => `<tr style="${t.archived ? 'opacity:.55' : ''}"><td><a href="#/trip/${t.id}">${esc(t.name)}</a>${t.archived ? ' <span class="badge">archived</span>' : ''}</td><td>${esc(t.location)}</td><td class="small muted">${esc(t.start_date || '')}${t.end_date ? ' to ' + esc(t.end_date) : ''}</td><td>${t.idea_count}</td><td class="row"><button class="btn small" data-arch="${t.id}" data-val="${t.archived ? 0 : 1}">${t.archived ? 'Unarchive' : 'Archive'}</button><button class="btn small danger" data-del="${t.id}">Delete</button></td></tr>`).join('')}</table>` : '<div class="empty">No trips yet. Examples: Udaipur, Kedarnath, Tungnath, Future Travel Vlogs, General Reel Inspiration.</div>'}`;
    $('#btn-new-trip').onclick = () => tripForm();
    for (const b of document.querySelectorAll('[data-arch]')) b.onclick = async () => { await api('/api/trips/' + b.dataset.arch, { method: 'PUT', body: { fields: { archived: b.dataset.val === '1' } } }); route(); };
    for (const b of document.querySelectorAll('[data-del]')) b.onclick = async () => { if (!confirm('Delete this trip? Ideas are kept (they go back to the Inbox); local files are never touched.')) return; await api('/api/trips/' + b.dataset.del, { method: 'DELETE' }); route(); };
  }
  function tripForm(t = {}) {
    const m = modal(`<h2 style="margin-top:0">${t.id ? 'Edit trip' : 'New trip'}</h2><div class="form">
      <label>Name</label><input id="t-name" value="${esc(t.name || '')}" placeholder="e.g. Udaipur">
      <label>Location</label><input id="t-location" value="${esc(t.location || '')}">
      <label>Description</label><input id="t-description" value="${esc(t.description || '')}">
      <label>Start date</label><input type="date" id="t-start_date" value="${esc(t.start_date || '')}">
      <label>End date</label><input type="date" id="t-end_date" value="${esc(t.end_date || '')}">
      <label></label><div class="row"><button class="btn primary" id="t-save">Save</button><button class="btn" id="t-cancel">Cancel</button></div></div>`);
    $('#t-cancel', m).onclick = closeModal;
    $('#t-save', m).onclick = async () => {
      const f = {}; for (const k of ['name', 'location', 'description', 'start_date', 'end_date']) f[k] = $('#t-' + k, m).value || null;
      try {
        if (t.id) await api('/api/trips/' + t.id, { method: 'PUT', body: { fields: f } });
        else { f.description = f.description || ''; f.location = f.location || ''; const nt = await api('/api/trips', { method: 'POST', body: f }); closeModal(); location.hash = '#/trip/' + nt.id; return; }
        closeModal(); route();
      } catch (e) { toast(e.message, 'err'); }
    };
  }
  async function renderTrip(id) {
    const t = await api('/api/trips/' + id);
    const v = $('#view');
    const high = t.ideas.filter((i) => i.priority === 'High');
    const resolve = state.status.resolve;
    v.innerHTML = `<div class="row between"><h1 style="margin:0">${esc(t.name)} ${t.archived ? '<span class="badge">archived</span>' : ''}</h1>
      <div class="row"><button class="btn small" id="t-edit">Edit</button><button class="btn small" id="t-export">Export trip folder</button><button class="btn small" id="t-shotlist">Build shot list</button><button class="btn small" id="t-suggest">Suggest ideas</button></div></div>
      <div class="muted small" style="margin:6px 0 14px">${esc(t.location || '')} ${t.start_date ? '· ' + esc(t.start_date) : ''}${t.end_date ? ' to ' + esc(t.end_date) : ''} ${t.description ? '· ' + esc(t.description) : ''}</div>
      <div class="detail">
        <div><h2 style="margin-top:0">Assigned references (${t.ideas.length})</h2><div id="t-ideas"></div></div>
        <div class="side">
          <div class="panel"><h3 style="margin-top:0">Notes</h3><textarea id="t-notes">${esc(t.notes)}</textarea><button class="btn small" id="t-notes-save" style="margin-top:6px">Save notes</button></div>
          <div class="panel"><h3 style="margin-top:0">Checklist</h3><ul class="checklist" id="t-check" style="padding:0;margin:0">${t.checklist.map((c, n) => `<li><input type="checkbox" data-n="${n}" ${c.done ? 'checked' : ''}><span style="flex:1;${c.done ? 'text-decoration:line-through;color:var(--muted)' : ''}">${esc(c.text)}</span><button class="btn small" data-rm="${n}">x</button></li>`).join('')}</ul><div class="row" style="margin-top:6px"><input id="t-check-new" placeholder="Add item" style="flex:1"><button class="btn small" id="t-check-add">Add</button></div></div>
          <div class="panel"><h3 style="margin-top:0">High priority</h3>${high.length ? high.map((i) => `<div><a href="#/idea/${i.id}">${esc(i.title || i.original_url)}</a></div>`).join('') : '<span class="muted small">none</span>'}</div>
          <div class="panel"><h3 style="margin-top:0">DaVinci Resolve</h3><div class="small muted">${esc(resolve.note)}</div><div class="row" style="margin-top:6px"><button class="btn small" id="t-media-folder">Open media folder</button><button class="btn small" id="t-resolve" ${resolve.detected ? '' : 'disabled'}>Import references into a Resolve bin</button></div></div>
        </div>
      </div>`;
    renderCards($('#t-ideas'), t.ideas, () => renderTrip(id));
    $('#t-edit').onclick = () => tripForm(t);
    $('#t-export').onclick = async () => { try { const r = await api(`/api/trips/${id}/export`, { method: 'POST' }); toast('Exported to ' + r.folder, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('#t-shotlist').onclick = () => shotListDialog(t.ideas, 'Shot list: ' + t.name);
    $('#t-suggest').onclick = async () => {
      const s = await api(`/api/trips/${id}/suggestions`);
      const m = modal(`<h2 style="margin-top:0">Suggested inbox ideas</h2><div class="small muted">Matched on the trip name/location in titles, captions or notes. Nothing is assigned until you tick it.</div>${s.length ? s.map((x) => `<div class="row"><input type="checkbox" data-sug="${x.id}"><a href="#/idea/${x.id}">${esc(x.title || x.original_url)}</a></div>`).join('') : '<div class="empty">No matches.</div>'}<div class="row" style="margin-top:10px"><button class="btn primary" id="sug-assign">Assign selected</button><button class="btn" id="sug-close">Close</button></div>`);
      $('#sug-close', m).onclick = closeModal;
      $('#sug-assign', m).onclick = async () => { for (const c of m.querySelectorAll('[data-sug]:checked')) { const cur = await api('/api/ideas/' + c.dataset.sug); await api(`/api/ideas/${c.dataset.sug}/trips`, { method: 'PUT', body: { trip_ids: [...cur.trips.map((x) => x.id), id] } }); } closeModal(); renderTrip(id); };
    };
    $('#t-notes-save').onclick = async () => { await api('/api/trips/' + id, { method: 'PUT', body: { fields: { notes: $('#t-notes').value } } }); toast('Saved', 'ok'); };
    const saveCheck = async (list) => { await api('/api/trips/' + id, { method: 'PUT', body: { fields: { checklist: list } } }); renderTrip(id); };
    $('#t-check-add').onclick = () => { const txt = $('#t-check-new').value.trim(); if (txt) saveCheck([...t.checklist, { text: txt, done: false }]); };
    for (const c of v.querySelectorAll('#t-check input[type=checkbox]')) c.onchange = () => { t.checklist[c.dataset.n].done = c.checked; saveCheck(t.checklist); };
    for (const b of v.querySelectorAll('[data-rm]')) b.onclick = () => { t.checklist.splice(Number(b.dataset.rm), 1); saveCheck(t.checklist); };
    $('#t-media-folder').onclick = () => api('/api/open-folder?which=media', { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    $('#t-resolve').onclick = async () => { try { const r = await api(`/api/trips/${id}/resolve-import`, { method: 'POST' }); toast(r.ok ? `Imported ${r.imported} file(s) into bin "${r.bin}"` : r.error, r.ok ? 'ok' : 'err'); } catch (e) { toast(e.message, 'err'); } };
  }
  function shotListDialog(ideas, heading) {
    const m = modal(`<h2 style="margin-top:0">Build shot list</h2><div class="small muted">Select ideas. Saved AI briefs are included; ideas without a brief contribute their notes.</div>
      <div style="max-height:40vh;overflow:auto;margin:8px 0">${ideas.map((i) => `<div class="row"><input type="checkbox" data-sl="${i.id}" ${i.analysis ? 'checked' : ''}><span>${esc(i.title || i.original_url)}</span>${i.analysis ? '<span class="badge ok">brief</span>' : ''}</div>`).join('') || '<div class="empty">No ideas.</div>'}</div>
      <div class="row"><select id="sl-fmt"><option value="md">Markdown</option><option value="txt">Plain text</option></select><button class="btn primary" id="sl-go">Download</button><button class="btn" id="sl-close">Close</button></div>`);
    $('#sl-close', m).onclick = closeModal;
    $('#sl-go', m).onclick = async () => {
      const ids = [...m.querySelectorAll('[data-sl]:checked')].map((c) => c.dataset.sl);
      if (!ids.length) return toast('Select at least one idea', 'err');
      const fmt = $('#sl-fmt', m).value;
      const r = await fetch('/api/exports/shotlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idea_ids: ids, format: fmt, heading }) });
      const blob = await r.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'shotlist.' + fmt; a.click(); closeModal();
    };
  }

  // --------------------------------------------------------------- settings
  async function renderSettings() {
    const [cfg, pair, devices] = await Promise.all([api('/api/settings'), api('/api/pairing'), api('/api/devices')]);
    const s = cfg.settings, st = state.status;
    const v = $('#view');
    v.innerHTML = `<h1>Settings</h1>
    <div class="panel"><h2 style="margin-top:0">Pair your phone</h2>
      <div class="row" style="align-items:flex-start;gap:24px">
        <div class="qr">${pair.qr_svg}</div>
        <div>
          <div>1. Enable LAN access below and restart ReelVault (the phone must be on the same WiFi).</div>
          <div>2. In the ReelVault Android app, open Settings and scan this QR, or type:</div>
          <table style="width:auto;margin:8px 0"><tr><td>Host</td><td class="mono">${esc(pair.host)}</td></tr><tr><td>Port</td><td class="mono">${pair.port}</td></tr><tr><td>Token</td><td class="mono" id="tok" style="cursor:pointer" title="click to reveal">${'•'.repeat(12)}</td></tr></table>
          <div class="row"><button class="btn small" id="btn-copy-token">Copy token</button><button class="btn small danger" id="btn-rotate">Generate new token</button></div>
          <div class="small muted" style="margin-top:8px">${st.lan_enabled_running ? `LAN access is on; the server is reachable at http://${esc(pair.host)}:${pair.port}/ from private networks only.` : 'LAN access is currently OFF. The phone cannot connect until it is enabled and ReelVault is restarted.'}</div>
          <div class="small muted">Sync uses plain HTTP on your private WiFi; every request is token-gated. See docs/SECURITY.md.</div>
        </div>
      </div>
      ${devices.length ? `<h3>Paired devices</h3><table><tr><th>Device</th><th>Last seen</th><th>Captures</th></tr>${devices.map((d) => `<tr><td>${esc(d.name || d.device_id.slice(0, 8))}</td><td>${fmtDate(d.last_seen_at)}</td><td>${d.captures_received}</td></tr>`).join('')}</table>` : ''}
    </div>
    <div class="panel"><h2 style="margin-top:0">Server</h2><div class="form">
      <label>LAN access</label><div><label><input type="checkbox" id="s-lan_enabled" ${s.lan_enabled ? 'checked' : ''}> Allow phones on the same private network to sync (restart required)</label></div>
      <label>Port</label><input type="number" id="s-port" value="${s.port}" min="1024" max="65535" style="width:120px">
      <label>Server name</label><input id="s-server_name" value="${esc(s.server_name)}">
      <label>Media folder</label><div><input id="s-media_dir" value="${esc(s.media_dir)}" placeholder="${esc(st.media_dir)}"><div class="small muted">Downloaded references go here, in one subfolder per trip. Leave blank for the default.</div></div>
      <label>Data folder</label><div class="mono small" style="padding-top:8px">${esc(st.data_dir)} <button class="btn small" id="btn-open-data">Open</button> <button class="btn small" id="btn-backup">Backup DB now</button></div>
    </div></div>
    <div class="panel"><h2 style="margin-top:0">Metadata and downloads</h2><div class="form">
      <label>Auto-fetch metadata</label><div><label><input type="checkbox" id="s-metadata_auto" ${s.metadata_auto ? 'checked' : ''}> Try to fetch title, creator and thumbnail when an idea arrives (best effort, documented endpoints only)</label></div>
      <label>Provider order</label><input id="s-metadata_providers" value="${esc((s.metadata_providers || []).join(','))}" placeholder="ytdlp,oembed">
      <label>Instagram oEmbed token</label><div><input id="s-instagram_oembed_token" value="${esc(s.instagram_oembed_token)}" placeholder="optional Facebook Graph access token"><div class="small muted">Instagram's official oEmbed endpoint needs an app token. Without it, Instagram metadata relies on yt-dlp.</div></div>
      <label>yt-dlp</label><div>${toolLine(st.tools.ytdlp)}<input id="s-ytdlp_path" value="${esc(s.ytdlp_path)}" placeholder="optional path to yt-dlp.exe"></div>
      <label>ffmpeg</label><div>${toolLine(st.tools.ffmpeg)}<input id="s-ffmpeg_path" value="${esc(s.ffmpeg_path)}" placeholder="optional folder containing ffmpeg.exe"></div>
    </div></div>
    <div class="panel"><h2 style="margin-top:0">AI analysis (optional)</h2><div class="form">
      <label>Status</label><div>${st.ai.configured ? '<span class="badge ok">key configured</span>' : '<span class="badge warn">no key</span>'}<div class="small muted">${esc(st.ai.how_to_configure)}</div></div>
      <label>Provider</label><select id="s-ai_provider"><option value="anthropic" ${s.ai_provider === 'anthropic' ? 'selected' : ''}>Anthropic (Claude)</option></select>
      <label>Model</label><input id="s-ai_model" value="${esc(s.ai_model)}">
      <label>Frames from reference</label><input type="number" id="s-ai_frames" value="${s.ai_frames}" min="0" max="12" style="width:100px">
    </div></div>
    <div class="panel"><h2 style="margin-top:0">Reminders</h2><div class="form">
      <label>Enabled</label><div><label><input type="checkbox" id="s-reminders_enabled" ${s.reminders_enabled ? 'checked' : ''}> Remind me about High-priority ideas whose follow-up date has arrived</label></div>
      <label>Quiet period (hours)</label><input type="number" id="s-reminder_quiet_hours" value="${s.reminder_quiet_hours}" min="1" style="width:100px">
      <label>Browser notifications</label><div><button class="btn small" id="btn-notify-perm">Allow notifications</button> <span class="small muted">current: ${typeof Notification !== 'undefined' ? Notification.permission : 'unsupported'}</span></div>
    </div></div>
    <div class="panel"><h2 style="margin-top:0">Priorities and categories</h2><div class="form">
      <label>Priorities</label><input id="s-priorities" value="${esc(s.priorities.join(','))}">
      <label>Categories</label><div id="cats">${state.categories.map((c) => `<div class="row small" style="margin-bottom:4px"><span style="min-width:140px">${esc(c.name)} <span class="muted">(${c.idea_count})</span></span><button class="btn small" data-ren="${c.id}">Rename</button><button class="btn small danger" data-delc="${c.id}">Delete</button></div>`).join('')}<div class="row"><input id="cat-new" placeholder="New category"><button class="btn small" id="cat-add">Add</button></div></div>
      <label>DaVinci Resolve</label><div><div class="small muted">${esc(st.resolve.note)}</div><input id="s-resolve_scripting_path" value="${esc(s.resolve_scripting_path)}" placeholder="optional path to Resolve's Scripting\\Modules folder"></div>
    </div></div>
    <div class="row"><button class="btn primary" id="btn-save-settings">Save settings</button><span class="muted small">LAN access and port changes take effect after restarting ReelVault.</span></div>`;
    $('#tok').onclick = () => { $('#tok').textContent = pair.token; };
    $('#btn-copy-token').onclick = () => navigator.clipboard.writeText(pair.token).then(() => toast('Token copied', 'ok'), () => { $('#tok').textContent = pair.token; });
    $('#btn-rotate').onclick = async () => { if (!confirm('Generate a new pairing token? The phone must be paired again.')) return; await api('/api/pairing/rotate', { method: 'POST' }); renderSettings(); };
    $('#btn-open-data').onclick = () => api('/api/open-folder?which=data', { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    $('#btn-backup').onclick = async () => { const r = await api('/api/backup', { method: 'POST' }); toast('Backup written to ' + r.path, 'ok'); };
    $('#btn-notify-perm').onclick = () => { if (typeof Notification !== 'undefined') Notification.requestPermission().then(() => renderSettings()); };
    $('#cat-add').onclick = async () => { try { await api('/api/categories', { method: 'POST', body: { name: $('#cat-new').value } }); route(); } catch (e) { toast(e.message, 'err'); } };
    for (const b of v.querySelectorAll('[data-ren]')) b.onclick = async () => { const n = prompt('New name'); if (!n) return; try { await api('/api/categories/' + b.dataset.ren, { method: 'PUT', body: { name: n } }); route(); } catch (e) { toast(e.message, 'err'); } };
    for (const b of v.querySelectorAll('[data-delc]')) b.onclick = async () => {
      const others = state.categories.filter((c) => c.id !== b.dataset.delc);
      const m = modal(`<h2 style="margin-top:0">Delete category</h2><div>Move its ideas to:</div><select id="dc-target" style="margin:8px 0"><option value="">No category</option>${others.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><div class="row"><button class="btn danger" id="dc-go">Delete</button><button class="btn" id="dc-close">Cancel</button></div>`);
      $('#dc-close', m).onclick = closeModal;
      $('#dc-go', m).onclick = async () => { const t = $('#dc-target', m).value; await api('/api/categories/' + b.dataset.delc + (t ? '?reassign_to=' + t : ''), { method: 'DELETE' }); closeModal(); route(); };
    };
    $('#btn-save-settings').onclick = async () => {
      const values = {
        lan_enabled: $('#s-lan_enabled').checked, port: Number($('#s-port').value), server_name: $('#s-server_name').value, media_dir: $('#s-media_dir').value,
        metadata_auto: $('#s-metadata_auto').checked, metadata_providers: $('#s-metadata_providers').value.split(',').map((x) => x.trim()).filter(Boolean),
        instagram_oembed_token: $('#s-instagram_oembed_token').value, ytdlp_path: $('#s-ytdlp_path').value, ffmpeg_path: $('#s-ffmpeg_path').value,
        ai_provider: $('#s-ai_provider').value, ai_model: $('#s-ai_model').value, ai_frames: Number($('#s-ai_frames').value),
        reminders_enabled: $('#s-reminders_enabled').checked, reminder_quiet_hours: Number($('#s-reminder_quiet_hours').value),
        priorities: $('#s-priorities').value.split(',').map((x) => x.trim()).filter(Boolean), resolve_scripting_path: $('#s-resolve_scripting_path').value,
      };
      try { await api('/api/settings', { method: 'PUT', body: { values } }); toast('Settings saved', 'ok'); await refreshStatus(); renderSettings(); } catch (e) { toast(e.message, 'err'); }
    };
  }
  function toolLine(t) { return t.found ? `<div class="small"><span class="badge ok">found</span> <span class="mono">${esc(t.path)}</span> ${esc(t.version || '')}</div>` : `<div class="small"><span class="badge warn">not found</span> ${esc(t.install_hint)}</div>`; }

  // ------------------------------------------------------------- add idea
  $('#btn-add-idea').onclick = () => {
    const m = modal(`<h2 style="margin-top:0">Add idea by link</h2><input id="ai-url" placeholder="Paste an Instagram Reel link (or any http(s) link)" style="width:100%"><div class="row" style="margin-top:10px"><label><input type="checkbox" id="ai-dup"> Save even if this link already exists</label></div><div class="row" style="margin-top:10px"><button class="btn primary" id="ai-go">Add</button><button class="btn" id="ai-close">Cancel</button></div>`);
    $('#ai-close', m).onclick = closeModal;
    $('#ai-go', m).onclick = async () => {
      try { const r = await api('/api/ideas', { method: 'POST', body: { url: $('#ai-url', m).value, allow_duplicate: $('#ai-dup', m).checked } }); closeModal(); toast(r.created ? 'Idea added' : 'Already saved; opening the existing idea', r.created ? 'ok' : ''); location.hash = '#/idea/' + r.idea.id; }
      catch (e) { toast(e.message, 'err'); }
    };
    $('#ai-url', m).focus();
  };

  // ------------------------------------------------------------- reminders
  async function checkReminders() {
    try {
      const r = await api('/api/reminders/due');
      const b = $('#reminder-banner');
      if (!r.enabled || !r.due.length) { b.classList.add('hidden'); return; }
      b.classList.remove('hidden');
      b.innerHTML = `<b>Follow-up reminder:</b> ${r.due.map((d) => `<a href="#/idea/${d.id}">${esc(d.title || d.original_url)}</a>`).join(', ')} <button class="btn small" id="rem-ack" style="margin-left:10px">Dismiss</button>`;
      $('#rem-ack').onclick = async () => { await api('/api/reminders/ack', { method: 'POST', body: { idea_ids: r.due.map((d) => d.id) } }); b.classList.add('hidden'); };
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && !sessionStorage.getItem('rv.notified')) { sessionStorage.setItem('rv.notified', '1'); new Notification('ReelVault', { body: `${r.due.length} high-priority idea(s) are due for follow-up` }); }
    } catch { /* offline or disabled */ }
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

  // ------------------------------------------------------------------ boot
  (async () => {
    await refreshStatus();
    await route();
    checkReminders(); setInterval(checkReminders, 5 * 60 * 1000);
    setInterval(() => refreshStatus().catch(() => {}), 15000);
  })();
})();
