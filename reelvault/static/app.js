/* ReelVault v2 workspace UI. Vanilla JS, hash routing, no external assets. */
(() => {
  'use strict';
  const $ = (sel, el = document) => el.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtDate = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(); };
  const P = window.RVPlayer;
  const state = { status: null, categories: [], trips: [], recentTrips: [], filters: load('rv.filters', {}), mode: localStorage.getItem('rv.mode') || 'grid',
    pollTimer: null, players: [], listScroll: {}, selected: new Set(), lastList: null };
  function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
  const saveFilters = () => localStorage.setItem('rv.filters', JSON.stringify(state.filters));

  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body instanceof FormData) init.body = opts.body;
    else if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    const r = await fetch(path, init); const text = await r.text(); let data; try { data = JSON.parse(text); } catch { data = text; }
    if (!r.ok) { const d = data && data.detail; throw new Error(typeof d === 'string' ? d : d && d.reason ? d.reason : JSON.stringify(d || r.statusText)); }
    return data;
  }
  function toast(msg, kind = '') { const el = document.createElement('div'); el.className = 'toast ' + kind; el.textContent = msg; $('#toasts').appendChild(el); setTimeout(() => el.remove(), kind === 'err' ? 8000 : 3500); }
  function modal(html) { $('#modal-card').innerHTML = html; $('#modal').classList.remove('hidden'); return $('#modal-card'); }
  function closeModal() { $('#modal').classList.add('hidden'); }
  $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeModal(); });
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const sel = (list, cur, label) => (label ? `<option value="">${label}</option>` : '') + list.map((v) => `<option value="${esc(v.id ?? v)}" ${(v.id ?? v) === cur ? 'selected' : ''}>${esc(v.name ?? v)}</option>`).join('');

  async function refreshStatus() {
    state.status = await api('/api/status');
    for (const el of document.querySelectorAll('[data-count]')) el.textContent = state.status.counts[el.dataset.count] || '';
    const s = state.status;
    $('#server-info').innerHTML = `v${esc(s.version)} · ${s.lan_enabled_running ? `LAN <span class="mono">${esc(s.lan_ip || '?')}:${s.port}</span>` : 'LAN off'}<br>${s.ai.configured ? 'Local AI ready' : 'Local AI not ready'}${s.pipeline.paused ? ' · pipeline paused' : ''}`;
  }
  async function loadRefs() { [state.categories, state.trips, state.recentTrips] = await Promise.all([api('/api/categories'), api('/api/trips?include_archived=true'), api('/api/trips-recent')]); }

  // ---------------------------------------------------------------- routing
  const routes = {
    inbox: () => renderGallery({ title: 'Inbox', inbox: true, key: 'inbox' }), all: () => renderGallery({ title: 'Library', key: 'all' }),
    priority: () => renderGallery({ title: 'High priority', priority: 'High', key: 'priority' }), published: () => renderGallery({ title: 'Published', status: 'Published', key: 'published' }),
    trips: renderTrips, trip: renderTrip, settings: renderSettings, repair: renderRepair,
  };
  function parseHash() { const h = location.hash.replace(/^#\/?/, ''); const [path, qs] = h.split('?'); const parts = path.split('/'); return { name: parts[0] || 'inbox', arg: parts[1], q: new URLSearchParams(qs || '') }; }
  let currentRoute = '';
  async function route() {
    const { name, arg, q } = parseHash();
    const key = name + '/' + (arg || '');
    if (key !== currentRoute) {
      currentRoute = key;
      for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.route === (name === 'trip' ? 'trips' : name));
      clearInterval(state.pollTimer); destroyPlayers();
      try { await loadRefs(); await (routes[name] || routes.inbox)(arg); } catch (e) { $('#view').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
      refreshStatus().catch(() => {});
    }
    const ideaId = q.get('idea');
    if (ideaId) openDetail(ideaId); else closeDetail();
  }
  window.addEventListener('hashchange', route);
  function setQuery(k, v) { const { name, arg, q } = parseHash(); if (v == null) q.delete(k); else q.set(k, v); const qs = q.toString(); location.hash = '#/' + name + (arg ? '/' + arg : '') + (qs ? '?' + qs : ''); }
  function destroyPlayers() { for (const p of state.players) p.destroy(); state.players = []; }

  // ---------------------------------------------------------------- gallery
  function filterBar(ctx) {
    const f = state.filters[ctx.key] || {};
    const st = state.status;
    return `<div class="toolbar" role="search">
      <input type="search" id="f-q" placeholder="Search title, notes, tags, creator" value="${esc(f.q || '')}" aria-label="Search">
      ${ctx.status ? '' : `<select id="f-status">${sel(st.statuses, f.status, 'Any status')}</select>`}
      ${ctx.priority ? '' : `<select id="f-priority">${sel(st.priorities, f.priority, 'Any priority')}</select>`}
      <select id="f-category">${sel(state.categories, f.category_id, 'Any category')}</select>
      ${ctx.inbox || ctx.trip_id ? '' : `<select id="f-trip">${sel(state.trips, f.trip_id, 'Any trip')}</select>`}
      <input id="f-tag" placeholder="tag" list="taglist" value="${esc(f.tag || '')}" style="width:110px" aria-label="Tag"><datalist id="taglist"></datalist>
      <select id="f-download">${sel(st.download_statuses.map((d) => ({ id: d, name: d.replace('_', ' ') })), f.download_status, 'Any download state')}</select>
      <label class="small"><input type="checkbox" id="f-playable" ${f.playable ? 'checked' : ''}> playable</label>
      <input type="date" id="f-from" value="${esc(f.captured_from || '')}" aria-label="Captured from"><input type="date" id="f-to" value="${esc(f.captured_to || '')}" aria-label="Captured to">
      <button class="btn small" id="f-clear">Clear</button><span class="grow"></span>
      <button class="btn small" id="b-select" aria-pressed="false">Select</button>
      <div class="seg" role="group" aria-label="View mode"><button id="m-grid" aria-pressed="${state.mode === 'grid'}">Grid</button><button id="m-feed" aria-pressed="${state.mode === 'feed'}">Feed</button></div>
    </div>
    <div id="bulkbar" class="row hidden" style="margin:-8px 0 12px"><span id="selcount" class="small muted"></span><button class="btn small" id="b-trip">Add selected to trip</button><button class="btn small" id="b-download">Download selected</button><button class="btn small" id="b-clear">Clear</button></div>`;
  }
  function readFilters(ctx) { const g = (id) => ($(id) ? $(id).value : ''); state.filters[ctx.key] = { q: g('#f-q'), status: g('#f-status'), priority: g('#f-priority'), category_id: g('#f-category'), trip_id: g('#f-trip'), tag: g('#f-tag'), download_status: g('#f-download'), playable: $('#f-playable') && $('#f-playable').checked, captured_from: g('#f-from'), captured_to: g('#f-to') }; saveFilters(); }
  async function fetchIdeas(ctx) {
    const f = state.filters[ctx.key] || {}; const p = new URLSearchParams();
    for (const [k, val] of Object.entries(f)) if (val) p.set(k, val);
    if (ctx.inbox) p.set('inbox', 'true'); if (ctx.status) p.set('status', ctx.status); if (ctx.priority) p.set('priority', ctx.priority); if (ctx.trip_id) p.set('trip_id', ctx.trip_id);
    return api('/api/ideas?' + p.toString());
  }
  async function renderGallery(ctx, container) {
    const v = container || $('#view');
    if (!container) v.innerHTML = `<div class="row between"><h1 style="margin:0">${esc(ctx.title)}</h1><span class="muted small" id="list-count"></span></div>${filterBar(ctx)}<div id="list"></div>`;
    else v.innerHTML = `${filterBar(ctx)}<div id="list"></div>`;
    api('/api/tags').then((t) => { $('#taglist').innerHTML = t.tags.map((x) => `<option value="${esc(x.tag)}">`).join(''); }).catch(() => {});
    const reload = async (keepScroll = true) => {
      readFilters(ctx); const data = await fetchIdeas(ctx); state.lastList = data.items;
      const lc = $('#list-count'); if (lc) lc.textContent = `${data.count} idea${data.count === 1 ? '' : 's'}`;
      const y = window.scrollY; destroyPlayers();
      if (state.mode === 'feed') renderFeed($('#list'), data.items, reload); else renderCards($('#list'), data.items, reload);
      if (keepScroll) window.scrollTo(0, y);
      updateBulk();
    };
    for (const el of v.querySelectorAll('.toolbar input, .toolbar select')) el.addEventListener(el.type === 'search' || el.id === 'f-tag' ? 'input' : 'change', debounce(() => reload(false), 250));
    $('#f-clear').onclick = () => { state.filters[ctx.key] = {}; saveFilters(); currentRoute = ''; route(); };
    $('#m-grid').onclick = () => { state.mode = 'grid'; localStorage.setItem('rv.mode', 'grid'); $('#m-grid').setAttribute('aria-pressed', 'true'); $('#m-feed').setAttribute('aria-pressed', 'false'); reload(false); };
    $('#m-feed').onclick = () => { state.mode = 'feed'; localStorage.setItem('rv.mode', 'feed'); $('#m-feed').setAttribute('aria-pressed', 'true'); $('#m-grid').setAttribute('aria-pressed', 'false'); reload(false); };
    $('#b-select').onclick = () => { const on = $('#b-select').getAttribute('aria-pressed') !== 'true'; $('#b-select').setAttribute('aria-pressed', String(on)); $('#list').classList.toggle('selecting', on); if (!on) state.selected.clear(); updateBulk(); reload(); };
    $('#b-clear').onclick = () => { state.selected.clear(); updateBulk(); reload(); };
    $('#b-trip').onclick = () => tripPicker([...state.selected], () => { state.selected.clear(); reload(); });
    $('#b-download').onclick = async () => { let n = 0; for (const id of state.selected) { const r = await api(`/api/ideas/${id}/download`, { method: 'POST' }).catch((e) => ({ ok: false, error: e.message })); if (r.ok) n++; else toast(r.error, 'err'); } toast(`${n} download(s) queued`); state.selected.clear(); reload(); };
    await reload(false);
    state.pollTimer = setInterval(() => { if (!document.hidden && $('#list') && $('#list').querySelector('[data-pending]') && $('#overlay').classList.contains('hidden')) reload().catch(() => {}); }, 4000);
    enableDrop(v);
  }
  function updateBulk() { const n = state.selected.size; const bb = $('#bulkbar'); if (!bb) return; bb.classList.toggle('hidden', n === 0); const sc = $('#selcount'); if (sc) sc.textContent = `${n} selected`; }
  const pending = (i) => ['pending', 'fetching'].includes(i.metadata_status) || ['queued', 'downloading'].includes(i.download_status) || ['queued', 'running'].includes(i.analysis_status);
  function stateBadges(i) {
    const out = [];
    if (i.priority === 'High') out.push('<span class="badge hi">High</span>');
    if (i.download_status === 'downloading') out.push('<span class="badge warn">downloading</span>'); else if (i.download_status === 'failed') out.push(`<span class="badge bad" title="${esc(i.download_error || '')}">${i.media_status === 'audio_only' ? 'audio only' : 'download failed'}</span>`);
    if (i.media_status === 'missing') out.push('<span class="badge bad">file missing</span>');
    if (['queued', 'running'].includes(i.analysis_status)) out.push('<span class="badge warn">analyzing</span>'); else if (i.analysis_status === 'done') out.push('<span class="badge ok">brief</span>');
    return out.join('');
  }
  function coverHtml(i) {
    const img = i.has_thumbnail ? `style="background-image:url('/api/ideas/${i.id}/cover?v=${encodeURIComponent(i.updated_at)}')"` : '';
    return `<div class="cover ${i.has_thumbnail ? '' : 'empty'}" ${img} data-open role="button" tabindex="0" aria-label="Open ${esc(i.title || 'idea')}">${i.has_thumbnail ? '' : `<div class="ph">${i.playable ? 'video' : (i.metadata_status === 'unavailable' ? 'no preview available' : 'no preview yet')}</div>`}${i.playable ? '<div class="play">&#9654;</div>' : ''}<div class="badges">${stateBadges(i)}</div></div>`;
  }
  function renderCards(container, items, reload) {
    container.className = 'grid';
    if (!items.length) { container.className = ''; container.innerHTML = '<div class="empty">Nothing here yet. Share a Reel from your phone, or use + Add to paste links or import a video.</div>'; return; }
    const selecting = $('#b-select') && $('#b-select').getAttribute('aria-pressed') === 'true';
    container.innerHTML = items.map((i) => `<article class="card" data-id="${i.id}" ${pending(i) ? 'data-pending="1"' : ''}>
      ${coverHtml(i)}
      <div class="body">
        ${selecting ? `<label class="small"><input type="checkbox" data-sel="${i.id}" ${state.selected.has(i.id) ? 'checked' : ''}> select</label>` : ''}
        <div class="title" data-open>${esc(i.title || i.original_url.replace(/^https?:\/\/(www\.)?/, ''))}</div>
        ${i.notes ? `<div class="small muted" style="overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${esc(i.notes)}</div>` : ''}
        <div class="chips">${(i.tags || []).map((t) => `<span class="chip">${esc(t)}</span>`).join('')}</div>
        <div class="row small"><select class="small" data-field="status" aria-label="Status">${sel(state.status.statuses, i.status)}</select><span class="grow"></span><button class="btn small" data-trip aria-label="Add to trip">+ Trip</button></div>
        ${i.trips.length ? `<div class="chips">${i.trips.map((t) => `<a class="badge" href="#/trip/${t.id}">${esc(t.name)}</a>`).join('')}</div>` : ''}
      </div></article>`).join('');
    for (const card of container.querySelectorAll('.card')) {
      const id = card.dataset.id;
      for (const o of card.querySelectorAll('[data-open]')) { o.onclick = () => setQuery('idea', id); o.onkeydown = (e) => { if (e.key === 'Enter') setQuery('idea', id); }; }
      const s = card.querySelector('[data-field=status]'); s.onchange = async () => { try { await api('/api/ideas/' + id, { method: 'PUT', body: { fields: { status: s.value } } }); toast('Saved', 'ok'); refreshStatus(); } catch (e) { toast(e.message, 'err'); } };
      card.querySelector('[data-trip]').onclick = () => tripPicker([id], reload);
      const cb = card.querySelector('[data-sel]'); if (cb) cb.onchange = () => { cb.checked ? state.selected.add(id) : state.selected.delete(id); updateBulk(); };
    }
  }
  function renderFeed(container, items, reload) {
    container.className = 'feed'; container.tabIndex = 0;
    if (!items.length) { container.className = ''; container.innerHTML = '<div class="empty">Nothing to browse yet.</div>'; return; }
    container.innerHTML = items.map((i, n) => `<section class="feed-item" data-id="${i.id}" data-n="${n}" tabindex="0" ${pending(i) ? 'data-pending="1"' : ''}>
      <div class="pl"></div>
      <div class="side">
        <input class="title" data-f="title" value="${esc(i.title)}" placeholder="Title" aria-label="Title">
        <textarea data-f="notes" placeholder="Short note: why this inspires you" aria-label="Note">${esc(i.notes)}</textarea>
        <div class="row"><input data-tags value="${esc((i.tags || []).join(', '))}" placeholder="tags: hook, lighting, transition" class="grow" aria-label="Tags"><button class="btn small" data-save>Save</button></div>
        <div class="row"><button class="btn small" data-trip>+ Trip</button>${i.trips.map((t) => `<a class="badge" href="#/trip/${t.id}">${esc(t.name)}</a>`).join('')}<span class="grow"></span><span class="chips">${stateBadges(i)}</span><button class="btn small" data-details>Details</button></div>
        <div class="notes" data-notes></div>
      </div></section>`).join('');
    const sections = [...container.querySelectorAll('.feed-item')];
    const players = new Map();
    const ensurePlayer = (sec, autoplay) => {
      const id = sec.dataset.id; const i = items.find((x) => x.id === id);
      if (!players.has(id)) {
        const p = P.mount(sec.querySelector('.pl'), i, { api, preload: 'metadata', autoplay: false, onAddNote: async (t, text) => { await api(`/api/ideas/${id}/notes`, { method: 'POST', body: { t, text } }); const fresh = await api('/api/ideas/' + id); i.timed_notes = fresh.timed_notes; P.notesList(sec.querySelector('[data-notes]'), i, p, api, () => reload()); } });
        players.set(id, p); state.players.push(p); P.notesList(sec.querySelector('[data-notes]'), i, p, api, () => reload());
      }
      if (autoplay) players.get(id).play();
    };
    let active = null;
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        const sec = e.target;
        if (e.intersectionRatio >= 0.6) { if (active && active !== sec) { active.classList.remove('active'); const p = players.get(active.dataset.id); p && p.pause(); } active = sec; sec.classList.add('active'); ensurePlayer(sec, true); const n = Number(sec.dataset.n); [sections[n - 1], sections[n + 1]].forEach((s) => s && ensurePlayer(s, false)); }
        else if (e.intersectionRatio < 0.3) { const p = players.get(sec.dataset.id); p && p.pause(); if (active === sec) { sec.classList.remove('active'); active = null; } }
      }
    }, { threshold: [0, 0.3, 0.6, 1] });
    sections.forEach((s) => io.observe(s));
    state.players.push({ destroy: () => io.disconnect() });
    for (const sec of sections) {
      const id = sec.dataset.id;
      sec.querySelector('[data-save]').onclick = async () => { const tags = sec.querySelector('[data-tags]').value.split(',').map((x) => x.trim()).filter(Boolean); try { await api('/api/ideas/' + id, { method: 'PUT', body: { fields: { title: sec.querySelector('[data-f=title]').value, notes: sec.querySelector('[data-f=notes]').value, tags } } }); toast('Saved', 'ok'); } catch (e) { toast(e.message, 'err'); } };
      sec.querySelector('[data-trip]').onclick = () => tripPicker([id], reload);
      sec.querySelector('[data-details]').onclick = () => setQuery('idea', id);
    }
    container.onkeydown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); const n = active ? Number(active.dataset.n) + 1 : 0; sections[n] && sections[n].scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); const n = active ? Number(active.dataset.n) - 1 : 0; sections[n] && sections[n].scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    };
  }
  function enableDrop(v) {
    v.addEventListener('dragover', (e) => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); v.classList.add('dropzone'); } });
    v.addEventListener('dragleave', () => v.classList.remove('dropzone'));
    v.addEventListener('drop', async (e) => { e.preventDefault(); v.classList.remove('dropzone'); for (const f of e.dataTransfer.files) await importFile(f); currentRoute = ''; route(); });
  }
  async function importFile(f) { const fd = new FormData(); fd.append('file', f); try { const r = await api('/api/ideas/import', { method: 'POST', body: fd }); toast(r.created ? `Imported ${f.name}` : `${f.name} was already in the library`, r.created ? 'ok' : ''); } catch (e) { toast(`${f.name}: ${e.message}`, 'err'); } }

  // ---------------------------------------------------------- trip picker
  function tripPicker(ideaIds, done) {
    const m = modal(`<h2 style="margin-top:0">Add ${ideaIds.length} idea${ideaIds.length > 1 ? 's' : ''} to a trip</h2>
      ${state.recentTrips.length ? `<h3>Recent</h3><div class="chips">${state.recentTrips.map((t) => `<button class="chip" data-tid="${t.id}">${esc(t.name)}</button>`).join('')}</div>` : ''}
      <h3>All trips</h3><div class="row"><select id="tp-sel" class="grow">${sel(state.trips.filter((t) => !t.archived), '', 'Choose a trip')}</select><button class="btn" id="tp-add">Add</button></div>
      <h3>New trip</h3><div class="row"><input id="tp-new" placeholder="e.g. Udaipur" class="grow"><button class="btn primary" id="tp-create">Create and add</button></div>
      <div class="row" style="margin-top:14px"><button class="btn" id="tp-close">Close</button></div>`);
    const go = async (body) => { try { const r = await api('/api/trips/add-ideas', { method: 'POST', body: { idea_ids: ideaIds, ...body } }); toast(`Added ${r.added} idea(s)`, 'ok'); closeModal(); await loadRefs(); done && done(); refreshStatus(); } catch (e) { toast(e.message, 'err'); } };
    for (const c of m.querySelectorAll('[data-tid]')) c.onclick = () => go({ trip_id: c.dataset.tid });
    $('#tp-add', m).onclick = () => { const t = $('#tp-sel', m).value; if (t) go({ trip_id: t }); };
    $('#tp-create', m).onclick = () => { const n = $('#tp-new', m).value.trim(); if (n) go({ new_trip_name: n }); };
    $('#tp-close', m).onclick = closeModal; $('#tp-new', m).focus();
  }

  // ------------------------------------------------------------ detail sheet
  let detailPlayer = null, detailPoll = null;
  function closeDetail() { $('#overlay').classList.add('hidden'); if (detailPlayer) { detailPlayer.destroy(); detailPlayer = null; } clearInterval(detailPoll); }
  $('#overlay').addEventListener('click', (e) => { if (e.target.id === 'overlay') setQuery('idea', null); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#overlay').classList.contains('hidden')) setQuery('idea', null); });
  async function openDetail(id) {
    let i; try { i = await api('/api/ideas/' + id); } catch (e) { toast(e.message, 'err'); return; }
    const sheet = $('#sheet'); const st = state.status, tools = st.tools, ai = st.ai;
    const wasHidden = $('#overlay').classList.contains('hidden');
    const focusEl = document.activeElement && document.activeElement.id;
    $('#overlay').classList.remove('hidden');
    if (detailPlayer) { detailPlayer.destroy(); detailPlayer = null; }
    const media = i.media || {};
    sheet.innerHTML = `
      <div class="row between"><button class="btn small" id="d-close" aria-label="Close">&larr; Back</button><div class="row"><a class="btn small" href="${esc(i.original_url)}" target="_blank" rel="noopener">Open original</a><button class="btn small danger" id="d-delete">Delete</button></div></div>
      <div class="feed-item" style="margin-top:12px;border:0;padding:0;background:transparent">
        <div><div class="pl" id="d-player"></div><div class="notes" id="d-notes" style="margin-top:8px"></div></div>
        <div class="side">
          <input class="title" id="d-title" value="${esc(i.title)}" placeholder="Title" aria-label="Title">
          <textarea id="d-notes-text" placeholder="Short note: why this inspires you">${esc(i.notes)}</textarea>
          <div class="row"><input id="d-tags" class="grow" value="${esc((i.tags || []).join(', '))}" placeholder="tags: hook, lighting, transition" list="taglist2"><datalist id="taglist2">${['hook', 'lighting', 'camera movement', 'transition', 'colour', 'sound', 'storytelling', 'pacing'].map((t) => `<option value="${t}">`).join('')}</datalist></div>
          <div class="row"><select id="d-status">${sel(st.statuses, i.status)}</select><select id="d-priority">${sel(st.priorities, i.priority)}</select><select id="d-category"><option value="">No category</option>${sel(state.categories, i.category_id)}</select></div>
          <div class="row"><button class="btn small" id="d-trip">+ Trip</button><span class="chips" id="d-trips">${i.trips.map((t) => `<span class="badge">${esc(t.name)} <a href="#" data-rm="${t.id}" aria-label="Remove from ${esc(t.name)}">x</a></span>`).join('')}</span></div>
          <div class="row"><button class="btn primary" id="d-save">Save</button><span class="small muted" id="d-saved"></span></div>
          <div class="row">
            ${i.source !== 'local' ? `<button class="btn small" id="d-download" ${!tools.ytdlp.found || ['queued', 'downloading'].includes(i.download_status) ? 'disabled' : ''}>${i.download_status === 'downloaded' ? 'Download again' : 'Download reference'}</button>` : ''}
            ${['queued', 'downloading'].includes(i.download_status) ? `<button class="btn small" id="d-cancel-dl">Cancel</button><span class="small muted">${i.jobs.download ? Math.round(i.jobs.download.progress) + '%' : ''}</span>` : ''}
            ${i.local_path ? '<button class="btn small" id="d-open">Open in player app</button><button class="btn small" id="d-reveal">Reveal file</button>' : ''}
            ${i.playable ? '<button class="btn small" id="d-cover">Use current frame as cover</button>' : ''}
            <label class="btn small">Upload cover<input type="file" id="d-cover-up" accept=".png,.jpg,.jpeg,.webp" hidden></label>
          </div>
          ${i.download_error ? `<div class="small" style="color:var(--danger)">${esc(i.download_error)}</div>` : ''}
          ${!tools.ytdlp.found && i.source !== 'local' ? `<div class="small muted">yt-dlp not found. ${esc(tools.ytdlp.install_hint)}</div>` : ''}
          <div id="d-analysis" class="panel" style="margin:4px 0 0"></div>
          <details class="more"><summary>Details: source, dates, metadata, media, screenshots</summary>
            <table class="small" style="margin-top:8px">
              <tr><td>Creator</td><td><input id="d-creator" value="${esc(i.creator)}" style="width:100%"></td></tr>
              <tr><td>Source</td><td class="mono" style="word-break:break-all">${esc(i.original_url)}${i.canonical_url ? '<br>' + esc(i.canonical_url) : ''}</td></tr>
              <tr><td>Captured</td><td>${fmtDate(i.captured_at)} via ${esc(i.source)}</td></tr>
              <tr><td>Updated</td><td>${fmtDate(i.updated_at)}</td></tr>
              <tr><td>Metadata</td><td><span class="badge ${i.metadata_status === 'ok' ? 'ok' : i.metadata_status === 'unavailable' ? 'bad' : 'warn'}">${esc(i.metadata_status)}</span> ${esc(i.metadata_error || '')} ${i.source !== 'local' ? '<button class="btn small" id="d-meta">Retry</button>' : ''}</td></tr>
              <tr><td>Caption</td><td><textarea id="d-caption">${esc(i.caption)}</textarea></td></tr>
              <tr><td>Transcript</td><td><textarea id="d-transcript" placeholder="Optional; local transcription fills this when available">${esc(i.transcript)}</textarea></td></tr>
              <tr><td>Shooting / editing notes</td><td><textarea id="d-shooting" placeholder="Shooting notes">${esc(i.shooting_notes)}</textarea><textarea id="d-editing" placeholder="Editing notes">${esc(i.editing_notes)}</textarea></td></tr>
              <tr><td>Finished video</td><td><input id="d-finished" value="${esc(i.finished_video_url)}" placeholder="https://..." style="width:100%"></td></tr>
              <tr><td>Follow-up</td><td><input type="date" id="d-follow" value="${esc(i.follow_up_date || '')}"></td></tr>
              <tr><td>Media</td><td class="mono">${esc(i.download_status)} · ${esc(i.media_status)}${media.width ? ` · ${media.width}x${media.height} ${esc(media.video_codec)}/${esc(media.audio_codec || 'no audio')} ${P.fmt(media.duration || 0)}` : ''}<br>${esc(i.local_path || '')}${i.playback_path && i.playback_path !== i.local_path ? '<br>playback copy: ' + esc(i.playback_path) : ''} ${i.local_path ? '<button class="btn small" id="d-verify">Verify</button>' : ''}</td></tr>
              <tr><td>Screenshots</td><td><div id="d-att">${i.attachments.map((a) => `<div class="row small"><a href="/api/attachments/${a.id}" target="_blank">${esc(a.filename)}</a><button class="btn small" data-del-att="${a.id}">x</button></div>`).join('')}</div><input type="file" id="d-att-file" accept=".png,.jpg,.jpeg,.webp"></td></tr>
            </table></details>
        </div></div>`;
    detailPlayer = P.mount($('#d-player'), i, { api, preload: 'auto', autoplay: !wasHidden ? false : false, onAddNote: async (t, text) => { await api(`/api/ideas/${id}/notes`, { method: 'POST', body: { t, text } }); const fresh = await api('/api/ideas/' + id); P.notesList($('#d-notes'), fresh, detailPlayer, api, () => openDetail(id)); } });
    P.notesList($('#d-notes'), i, detailPlayer, api, () => openDetail(id));
    $('#d-close').onclick = () => setQuery('idea', null);
    $('#d-save').onclick = async () => {
      const f = { title: $('#d-title').value, notes: $('#d-notes-text').value, tags: $('#d-tags').value.split(',').map((x) => x.trim()).filter(Boolean), status: $('#d-status').value, priority: $('#d-priority').value, category_id: $('#d-category').value || null, creator: $('#d-creator').value, caption: $('#d-caption').value, transcript: $('#d-transcript').value, shooting_notes: $('#d-shooting').value, editing_notes: $('#d-editing').value, finished_video_url: $('#d-finished').value, follow_up_date: $('#d-follow').value || null };
      try { await api('/api/ideas/' + id, { method: 'PUT', body: { fields: f } }); $('#d-saved').textContent = 'Saved'; toast('Saved', 'ok'); i = await api('/api/ideas/' + id); refreshStatus(); if (state.lastList) { currentRoute = ''; } } catch (e) { toast(e.message, 'err'); }
    };
    $('#d-trip').onclick = () => tripPicker([id], () => openDetail(id));
    for (const rm of sheet.querySelectorAll('[data-rm]')) rm.onclick = async (e) => { e.preventDefault(); await api(`/api/trips/${rm.dataset.rm}/ideas/${id}`, { method: 'DELETE' }); openDetail(id); };
    $('#d-delete').onclick = async () => { if (!confirm('Delete this idea? Local files are never deleted.')) return; await api('/api/ideas/' + id, { method: 'DELETE' }); toast('Deleted'); setQuery('idea', null); currentRoute = ''; route(); };
    const b = (sel, fn) => { const el = $(sel); if (el) el.onclick = fn; };
    b('#d-download', async () => { try { const r = await api(`/api/ideas/${id}/download`, { method: 'POST' }); r.ok ? toast('Download queued') : toast(r.error, 'err'); openDetail(id); } catch (e) { toast(e.message, 'err'); } });
    b('#d-cancel-dl', async () => { await api(`/api/ideas/${id}/download/cancel`, { method: 'POST' }); toast('Cancel requested'); });
    b('#d-open', () => api(`/api/ideas/${id}/open`, { method: 'POST' }).catch((e) => toast(e.message, 'err')));
    b('#d-reveal', () => api(`/api/ideas/${id}/reveal`, { method: 'POST' }).catch((e) => toast(e.message, 'err')));
    b('#d-verify', async () => { await api(`/api/ideas/${id}/download/verify`, { method: 'POST' }); openDetail(id); });
    b('#d-meta', async () => { await api(`/api/ideas/${id}/metadata/retry`, { method: 'POST' }); toast('Metadata retry queued'); setTimeout(() => openDetail(id), 2500); });
    b('#d-cover', async () => { const t = detailPlayer.video ? detailPlayer.video.currentTime : 0; try { await api(`/api/ideas/${id}/cover/frame`, { method: 'POST', body: { t } }); toast('Cover updated', 'ok'); openDetail(id); } catch (e) { toast(e.message, 'err'); } });
    $('#d-cover-up').onchange = async (e) => { const fd = new FormData(); fd.append('file', e.target.files[0]); try { await api(`/api/ideas/${id}/cover/upload`, { method: 'POST', body: fd }); toast('Cover uploaded', 'ok'); openDetail(id); } catch (err) { toast(err.message, 'err'); } };
    $('#d-att-file').onchange = async (e) => { const fd = new FormData(); fd.append('file', e.target.files[0]); try { await api(`/api/ideas/${id}/attachments`, { method: 'POST', body: fd }); toast('Uploaded', 'ok'); openDetail(id); } catch (err) { toast(err.message, 'err'); } };
    for (const d of sheet.querySelectorAll('[data-del-att]')) d.onclick = async () => { await api('/api/attachments/' + d.dataset.delAtt, { method: 'DELETE' }); openDetail(id); };
    renderAnalysis(i, ai, () => openDetail(id));
    clearInterval(detailPoll);
    if (pending(i)) detailPoll = setInterval(async () => { if (document.hidden) return; const cur = await api('/api/ideas/' + id).catch(() => null); if (!cur) return; if (cur.download_status !== i.download_status || cur.analysis_status !== i.analysis_status || cur.metadata_status !== i.metadata_status || (cur.jobs.download && i.jobs.download && cur.jobs.download.progress !== i.jobs.download.progress)) { if (document.activeElement && ['TEXTAREA', 'INPUT'].includes(document.activeElement.tagName) && document.activeElement.closest('#sheet')) return; openDetail(id); } }, 2500);
    if (wasHidden) $('#d-close').focus();
  }
  function renderAnalysis(i, ai, refresh) {
    const p = $('#d-analysis'); const a = i.analysis, b = a && a.brief; const inp = a && a.inputs;
    const running = ['queued', 'running'].includes(i.analysis_status);
    const inputLine = inp ? `Analyzed: ${['title', 'creator', 'caption', 'notes', 'transcript'].filter((k) => inp[k]).join(', ') || 'URL only'}${inp.frames ? `, ${inp.frames} sampled frame(s)${inp.frame_times && inp.frame_times.length ? ' at ' + inp.frame_times.map((t) => t + 's').join(', ') : ''}` : ''}${inp.screenshots ? `, ${inp.screenshots} screenshot(s)` : ''}${inp.transcript_source === 'local-whisper' ? ' (transcript from local speech-to-text)' : ''}. The full video and audio were not watched or heard.` : '';
    p.innerHTML = `<div class="row between"><b>AI analysis <span class="muted small">(${ai.local ? 'local, ' + esc(ai.model) : 'cloud, opt-in'})</span></b>
      <div class="row">${running ? `<span class="spinner"></span><span class="small muted">${esc((i.jobs.analysis && i.jobs.analysis.progress) || 'working')}</span><button class="btn small" id="a-cancel">Cancel</button>` : `<button class="btn small primary" id="a-run" ${!ai.configured ? 'disabled' : ''}>${b ? 'Re-analyze' : 'Analyze'}</button>`}${b ? `<a class="btn small" href="/api/ideas/${i.id}/analysis.md" download="brief.md">Export .md</a>` : ''}</div></div>
      ${!ai.configured ? `<div class="small muted">${esc(ai.how_to_configure)}</div>` : ''}
      ${i.analysis_status === 'failed' ? `<div class="small" style="color:var(--danger)">Last attempt failed: ${esc(i.analysis_error || '')}</div>` : ''}
      ${b ? `<div class="small muted" style="margin:6px 0">${esc(inputLine)} ${a.edited ? '· edited by you' : ''}</div><div class="brief" id="brief"></div>` : ''}`;
    const run = async () => { try { const r = await api(`/api/ideas/${i.id}/analyze?force=${b ? 'true' : 'false'}`, { method: 'POST' }); if (!r.ok) toast(r.error, 'err'); else { toast(r.cached ? r.note : 'Analysis started'); refresh(); } } catch (e) { toast(e.message, 'err'); } };
    const ar = $('#a-run'); if (ar) ar.onclick = run; const ac = $('#a-cancel'); if (ac) ac.onclick = async () => { await api(`/api/ideas/${i.id}/analyze/cancel`, { method: 'POST' }); toast('Cancel requested'); };
    if (!b) return;
    const tf = [['core_idea', 'Core idea'], ['opening_hook', 'Opening hook'], ['story_structure', 'Story structure'], ['camera_approach', 'Camera approach'], ['editing_approach', 'Editing approach'], ['sound_design', 'Sound design'], ['recreation_plan', 'Recreation plan'], ['personal_notes', 'Personal notes'], ['confidence_note', 'Confidence note']];
    const el = $('#brief');
    el.innerHTML = `<div class="field"><label>Observed facts (only what the inputs showed; one per line)</label><textarea id="b-observed_facts">${esc((b.observed_facts || []).join('\n'))}</textarea></div>
      <div class="field"><label>Uncertain interpretations (one per line)</label><textarea id="b-uncertain">${esc((b.uncertain_interpretations || []).join('\n'))}</textarea></div>
      ${tf.map(([k, l]) => `<div class="field"><label>${l} <span class="muted">(suggestion)</span></label><textarea id="b-${k}">${esc(b[k] || '')}</textarea></div>`).join('')}
      <div class="field"><label>Shot list (suggestion)</label><table class="shots" id="b-shots"><tr><th>#</th><th>Shot</th><th>Description</th><th>Sec</th><th>Camera</th><th></th></tr>${(b.shot_list || []).map((s, n) => shotRow(s, n)).join('')}</table><button class="btn small" id="b-add-shot">+ shot</button></div>
      <div class="field"><label>Production requirements (one per line)</label><textarea id="b-production_requirements">${esc((b.production_requirements || []).join('\n'))}</textarea></div>
      <button class="btn primary" id="b-save">Save brief</button>`;
    const bindDel = (tb) => { for (const d of tb.querySelectorAll('[data-del]')) d.onclick = () => d.closest('tr').remove(); };
    $('#b-add-shot').onclick = () => { const tb = $('#b-shots'); const tr = document.createElement('tr'); tr.innerHTML = shotRow({}, tb.rows.length - 1).replace(/^<tr>|<\/tr>$/g, ''); tb.appendChild(tr); bindDel(tb); };
    bindDel($('#b-shots'));
    $('#b-save').onclick = async () => {
      const lines = (id) => $(id).value.split('\n').map((s) => s.trim()).filter(Boolean);
      const brief = { observed_facts: lines('#b-observed_facts'), uncertain_interpretations: lines('#b-uncertain'), production_requirements: lines('#b-production_requirements'), shot_list: [] };
      for (const [k] of tf) brief[k] = $('#b-' + k).value;
      for (const tr of [...$('#b-shots').rows].slice(1)) { const c = tr.querySelectorAll('input'); if (!c[0].value.trim()) continue; brief.shot_list.push({ shot: c[0].value, description: c[1].value, duration_seconds: c[2].value ? Number(c[2].value) : null, camera: c[3].value }); }
      try { await api(`/api/ideas/${i.id}/analysis`, { method: 'PUT', body: { brief } }); toast('Brief saved', 'ok'); } catch (e) { toast(e.message, 'err'); }
    };
  }
  function shotRow(s, n) { return `<tr><td>${n + 1}</td><td><input value="${esc(s.shot || '')}"></td><td><input value="${esc(s.description || '')}"></td><td style="width:60px"><input value="${s.duration_seconds ?? ''}"></td><td><input value="${esc(s.camera || '')}"></td><td><button class="btn small" data-del>x</button></td></tr>`; }

  // ------------------------------------------------------------------ trips
  async function renderTrips() {
    const trips = state.trips;
    $('#view').innerHTML = `<div class="row between"><h1 style="margin:0">Trips</h1><button class="btn primary" id="btn-new-trip">+ New trip</button></div>
      <div class="muted small" style="margin:6px 0 16px">Lightweight collections. Ideas stay in the Inbox until you add them; nothing is assigned automatically.</div>
      ${trips.length ? `<table><tr><th>Name</th><th>Location</th><th>Dates</th><th>Ideas</th><th></th></tr>${trips.map((t) => `<tr style="${t.archived ? 'opacity:.55' : ''}"><td><a href="#/trip/${t.id}">${esc(t.name)}</a>${t.archived ? ' <span class="badge">archived</span>' : ''}</td><td>${esc(t.location)}</td><td class="small muted">${esc(t.start_date || '')}${t.end_date ? ' to ' + esc(t.end_date) : ''}</td><td>${t.idea_count}</td><td class="row"><button class="btn small" data-arch="${t.id}" data-val="${t.archived ? 0 : 1}">${t.archived ? 'Unarchive' : 'Archive'}</button><button class="btn small danger" data-del="${t.id}">Delete</button></td></tr>`).join('')}</table>` : '<div class="empty">No trips yet. Examples: Udaipur, Kedarnath, Tungnath, Future Travel Vlogs, General Reel Inspiration.</div>'}`;
    $('#btn-new-trip').onclick = () => tripForm();
    for (const b of document.querySelectorAll('[data-arch]')) b.onclick = async () => { await api('/api/trips/' + b.dataset.arch, { method: 'PUT', body: { fields: { archived: b.dataset.val === '1' } } }); currentRoute = ''; route(); };
    for (const b of document.querySelectorAll('[data-del]')) b.onclick = async () => { if (!confirm('Delete this trip? Ideas are kept; files are never touched.')) return; await api('/api/trips/' + b.dataset.del, { method: 'DELETE' }); currentRoute = ''; route(); };
  }
  function tripForm(t = {}) {
    const m = modal(`<h2 style="margin-top:0">${t.id ? 'Edit trip' : 'New trip'}</h2><div class="form">
      <label>Name</label><input id="t-name" value="${esc(t.name || '')}" placeholder="e.g. Udaipur"><label>Location</label><input id="t-location" value="${esc(t.location || '')}"><label>Description</label><input id="t-description" value="${esc(t.description || '')}">
      <label>Start date</label><input type="date" id="t-start_date" value="${esc(t.start_date || '')}"><label>End date</label><input type="date" id="t-end_date" value="${esc(t.end_date || '')}">
      <label></label><div class="row"><button class="btn primary" id="t-save">Save</button><button class="btn" id="t-cancel">Cancel</button></div></div>`);
    $('#t-cancel', m).onclick = closeModal;
    $('#t-save', m).onclick = async () => {
      const f = {}; for (const k of ['name', 'location', 'description', 'start_date', 'end_date']) f[k] = $('#t-' + k, m).value || null;
      try { if (t.id) { await api('/api/trips/' + t.id, { method: 'PUT', body: { fields: f } }); closeModal(); currentRoute = ''; route(); } else { f.description = f.description || ''; f.location = f.location || ''; const nt = await api('/api/trips', { method: 'POST', body: f }); closeModal(); location.hash = '#/trip/' + nt.id; } } catch (e) { toast(e.message, 'err'); }
    };
  }
  async function renderTrip(id) {
    const t = await api('/api/trips/' + id); const v = $('#view'); const high = t.ideas.filter((i) => i.priority === 'High'); const resolve = state.status.resolve;
    v.innerHTML = `<div class="row between"><h1 style="margin:0">${esc(t.name)} ${t.archived ? '<span class="badge">archived</span>' : ''}</h1>
      <div class="row"><button class="btn small" id="t-edit">Edit</button><button class="btn small" id="t-export">Export folder</button><button class="btn small" id="t-shotlist">Shot list</button><button class="btn small" id="t-suggest">Suggest ideas</button><button class="btn small primary" id="t-adapt">Adapt for my trip</button></div></div>
      <div class="muted small" style="margin:6px 0 14px">${esc(t.location || '')} ${t.start_date ? '· ' + esc(t.start_date) : ''}${t.end_date ? ' to ' + esc(t.end_date) : ''} ${t.description ? '· ' + esc(t.description) : ''}</div>
      <div id="t-plans"></div>
      <div class="feed-item" style="padding:0;border:0;background:transparent;grid-template-columns:1fr 300px">
        <div id="t-gallery"></div>
        <div class="side">
          <div class="panel"><h3 style="margin-top:0">Notes</h3><textarea id="t-notes">${esc(t.notes)}</textarea><button class="btn small" id="t-notes-save" style="margin-top:6px">Save notes</button></div>
          <div class="panel"><h3 style="margin-top:0">Checklist</h3><ul class="checklist" id="t-check" style="padding:0;margin:0">${t.checklist.map((c, n) => `<li style="list-style:none;display:flex;gap:8px;align-items:center"><input type="checkbox" data-n="${n}" ${c.done ? 'checked' : ''}><span class="grow" style="${c.done ? 'text-decoration:line-through;color:var(--muted)' : ''}">${esc(c.text)}</span><button class="btn small ghost" data-rm="${n}">x</button></li>`).join('')}</ul><div class="row" style="margin-top:6px"><input id="t-check-new" placeholder="Add item" class="grow"><button class="btn small" id="t-check-add">Add</button></div></div>
          <div class="panel"><h3 style="margin-top:0">High priority</h3>${high.length ? high.map((i) => `<div><a href="#" data-openidea="${i.id}">${esc(i.title || i.original_url)}</a></div>`).join('') : '<span class="muted small">none</span>'}</div>
          <div class="panel"><h3 style="margin-top:0">DaVinci Resolve</h3><div class="small muted">${esc(resolve.note)}</div><div class="row" style="margin-top:6px"><button class="btn small" id="t-media-folder">Open media folder</button><button class="btn small" id="t-resolve" ${resolve.detected ? '' : 'disabled'}>Import into Resolve bin</button></div></div>
        </div></div>`;
    await renderGallery({ title: t.name, key: 'trip:' + id, trip_id: id }, $('#t-gallery'));
    renderPlans(id);
    for (const a of v.querySelectorAll('[data-openidea]')) a.onclick = (e) => { e.preventDefault(); setQuery('idea', a.dataset.openidea); };
    $('#t-edit').onclick = () => tripForm(t);
    $('#t-export').onclick = async () => { try { const r = await api(`/api/trips/${id}/export`, { method: 'POST' }); toast('Exported to ' + r.folder, 'ok'); } catch (e) { toast(e.message, 'err'); } };
    $('#t-shotlist').onclick = () => shotListDialog(t.ideas, 'Shot list: ' + t.name);
    $('#t-adapt').onclick = () => adaptDialog(t);
    $('#t-suggest').onclick = async () => {
      const s = await api(`/api/trips/${id}/suggestions`);
      const m = modal(`<h2 style="margin-top:0">Suggested inbox ideas</h2><div class="small muted">Matched on the trip name/location. Nothing is assigned until you tick it.</div>${s.length ? s.map((x) => `<div class="row"><input type="checkbox" data-sug="${x.id}"><span>${esc(x.title || x.original_url)}</span></div>`).join('') : '<div class="empty">No matches.</div>'}<div class="row" style="margin-top:10px"><button class="btn primary" id="sug-assign">Assign selected</button><button class="btn" id="sug-close">Close</button></div>`);
      $('#sug-close', m).onclick = closeModal;
      $('#sug-assign', m).onclick = async () => { const ids = [...m.querySelectorAll('[data-sug]:checked')].map((c) => c.dataset.sug); if (ids.length) await api('/api/trips/add-ideas', { method: 'POST', body: { idea_ids: ids, trip_id: id } }); closeModal(); currentRoute = ''; route(); };
    };
    $('#t-notes-save').onclick = async () => { await api('/api/trips/' + id, { method: 'PUT', body: { fields: { notes: $('#t-notes').value } } }); toast('Saved', 'ok'); };
    const saveCheck = async (list) => { await api('/api/trips/' + id, { method: 'PUT', body: { fields: { checklist: list } } }); currentRoute = ''; route(); };
    $('#t-check-add').onclick = () => { const txt = $('#t-check-new').value.trim(); if (txt) saveCheck([...t.checklist, { text: txt, done: false }]); };
    for (const c of v.querySelectorAll('#t-check input[type=checkbox]')) c.onchange = () => { t.checklist[c.dataset.n].done = c.checked; saveCheck(t.checklist); };
    for (const b of v.querySelectorAll('[data-rm]')) b.onclick = () => { t.checklist.splice(Number(b.dataset.rm), 1); saveCheck(t.checklist); };
    $('#t-media-folder').onclick = () => api('/api/open-folder?which=media', { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    $('#t-resolve').onclick = async () => { try { const r = await api(`/api/trips/${id}/resolve-import`, { method: 'POST' }); toast(r.ok ? `Imported ${r.imported} file(s) into bin "${r.bin}"` : r.error, r.ok ? 'ok' : 'err'); } catch (e) { toast(e.message, 'err'); } };
  }
  async function renderPlans(tripId) {
    const plans = await api(`/api/trips/${tripId}/plans`).catch(() => []); const el = $('#t-plans'); if (!el) return;
    if (!plans.length) { el.innerHTML = ''; return; }
    const p = plans[0]; const plan = p.plan || {};
    el.innerHTML = `<div class="panel"><div class="row between"><b>Adapt for my trip <span class="muted small">(${esc(p.status)} · ${esc(p.model || '')})</span></b>${p.status === 'done' ? '<button class="btn small" id="pl-save">Save edits</button>' : ''}</div>
      ${p.status === 'failed' ? `<div class="small" style="color:var(--danger)">${esc(p.error)}</div>` : ''}${['queued', 'running'].includes(p.status) ? '<div class="small muted"><span class="spinner"></span> generating...</div>' : ''}
      ${p.plan ? `<div class="brief" style="margin-top:8px">
        <div class="field"><label>Observed in the references (facts from analyses)</label><textarea id="pl-obs">${esc((plan.observed_from_references || []).join('\n'))}</textarea></div>
        <div class="field"><label>Proposed shots (ideas, not facts)</label><table class="shots" id="pl-shots"><tr><th>#</th><th>Shot</th><th>Description</th><th>Where</th><th>Sec</th><th>Gear</th></tr>${(plan.proposed_shots || []).map((s, n) => `<tr><td>${n + 1}</td><td><input value="${esc(s.shot)}"></td><td><input value="${esc(s.description)}"></td><td><input value="${esc(s.location_hint)}"></td><td style="width:60px"><input value="${s.duration_seconds ?? ''}"></td><td><input value="${esc(s.gear)}"></td></tr>`).join('')}</table></div>
        <div class="field"><label>Schedule (one per line)</label><textarea id="pl-sched">${esc((plan.schedule || []).join('\n'))}</textarea></div>
        <div class="field"><label>Recreation plan</label><textarea id="pl-plan">${esc(plan.recreation_plan || '')}</textarea></div>
        <div class="field"><label>Gear checklist (one per line)</label><textarea id="pl-gear">${esc((plan.gear_checklist || []).join('\n'))}</textarea></div>
        <div class="field"><label>Risks (one per line)</label><textarea id="pl-risks">${esc((plan.risks || []).join('\n'))}</textarea></div></div>` : ''}</div>`;
    if (['queued', 'running'].includes(p.status)) setTimeout(() => renderPlans(tripId), 3000);
    const sv = $('#pl-save'); if (sv) sv.onclick = async () => {
      const lines = (id) => $(id).value.split('\n').map((s) => s.trim()).filter(Boolean);
      const body = { observed_from_references: lines('#pl-obs'), schedule: lines('#pl-sched'), recreation_plan: $('#pl-plan').value, gear_checklist: lines('#pl-gear'), risks: lines('#pl-risks'), notes: plan.notes || '', proposed_shots: [] };
      for (const tr of [...$('#pl-shots').rows].slice(1)) { const c = tr.querySelectorAll('input'); if (!c[0].value.trim()) continue; body.proposed_shots.push({ shot: c[0].value, description: c[1].value, location_hint: c[2].value, duration_seconds: c[3].value ? Number(c[3].value) : null, gear: c[4].value }); }
      try { await api('/api/plans/' + p.id, { method: 'PUT', body: { plan: body } }); toast('Plan saved', 'ok'); } catch (e) { toast(e.message, 'err'); }
    };
  }
  function adaptDialog(t) {
    const m = modal(`<h2 style="margin-top:0">Adapt for my trip: ${esc(t.name)}</h2><div class="small muted">Uses the selected references (their saved briefs, notes and tags) plus your details. Runs on the local AI; observed details stay separate from proposals.</div>
      <div class="form" style="margin-top:10px"><label>References</label><div style="max-height:30vh;overflow:auto">${t.ideas.map((i) => `<label class="row small"><input type="checkbox" data-ad="${i.id}" ${i.analysis ? 'checked' : ''}> ${esc(i.title || i.original_url)} ${i.analysis ? '<span class="badge ok">brief</span>' : ''}</label>`).join('') || '<span class="muted">No ideas in this trip yet.</span>'}</div>
      <label>Destination</label><input id="ad-dest" value="${esc(t.location || t.name)}"><label>Gear</label><input id="ad-gear" placeholder="e.g. iPhone 15, DJI Mini, tripod"><label>Time available</label><input id="ad-time" placeholder="e.g. 2 mornings, 1 sunset"><label>Preferences</label><input id="ad-pref" placeholder="e.g. no drone over crowds, calm pacing">
      <label></label><div class="row"><button class="btn primary" id="ad-go">Generate</button><button class="btn" id="ad-close">Cancel</button></div></div>`);
    $('#ad-close', m).onclick = closeModal;
    $('#ad-go', m).onclick = async () => { const ids = [...m.querySelectorAll('[data-ad]:checked')].map((c) => c.dataset.ad); try { const r = await api(`/api/trips/${t.id}/adapt`, { method: 'POST', body: { idea_ids: ids, destination: $('#ad-dest', m).value, gear: $('#ad-gear', m).value, time_available: $('#ad-time', m).value, preferences: $('#ad-pref', m).value } }); if (!r.ok) toast(r.error, 'err'); else { toast('Generating plan'); closeModal(); renderPlans(t.id); } } catch (e) { toast(e.message, 'err'); } };
  }
  function shotListDialog(ideas, heading) {
    const m = modal(`<h2 style="margin-top:0">Build shot list</h2><div class="small muted">Saved briefs are included; ideas without a brief contribute their notes.</div>
      <div style="max-height:40vh;overflow:auto;margin:8px 0">${ideas.map((i) => `<div class="row"><input type="checkbox" data-sl="${i.id}" ${i.analysis ? 'checked' : ''}><span>${esc(i.title || i.original_url)}</span>${i.analysis ? '<span class="badge ok">brief</span>' : ''}</div>`).join('') || '<div class="empty">No ideas.</div>'}</div>
      <div class="row"><select id="sl-fmt"><option value="md">Markdown</option><option value="txt">Plain text</option></select><button class="btn primary" id="sl-go">Download</button><button class="btn" id="sl-close">Close</button></div>`);
    $('#sl-close', m).onclick = closeModal;
    $('#sl-go', m).onclick = async () => { const ids = [...m.querySelectorAll('[data-sl]:checked')].map((c) => c.dataset.sl); if (!ids.length) return toast('Select at least one idea', 'err'); const fmt = $('#sl-fmt', m).value; const r = await fetch('/api/exports/shotlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idea_ids: ids, format: fmt, heading }) }); const blob = await r.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'shotlist.' + fmt; a.click(); closeModal(); };
  }

  // ------------------------------------------------------------------ repair
  async function renderRepair() {
    const r = await api('/api/repair'); const v = $('#view');
    const act = { redownload: 'Download again', verify: 'Verify', prepare: 'Prepare media', metadata: 'Retry metadata', test_ai: 'Test local AI' };
    v.innerHTML = `<h1>Repair centre</h1><div class="small muted" style="margin-bottom:12px">Targeted fixes for connection, sync, download, media and AI problems. Advanced diagnostics stay out of the creative views.</div>
      <div class="panel"><h3 style="margin-top:0">Phone connection</h3>
        <div class="small">${state.status.lan_enabled_running ? `LAN access on. Phones should use <span class="mono">${esc(r.lan.advertised_host || '?')}:${state.status.port}</span>.` : 'LAN access is OFF: phones cannot sync. Enable it in Settings and restart.'}</div>
        ${r.lan.candidates.length > 1 ? `<div class="small muted">Other addresses on this computer: ${r.lan.candidates.filter((c) => c.ip !== r.lan.advertised_host).map((c) => `${esc(c.ip)}${c.adapter ? ' (' + esc(c.adapter) + ')' : ''}${c.virtual ? ' virtual' : ''}`).join(', ')}. Pick the WiFi one in Settings if pairing fails.</div>` : ''}
        ${r.devices.length ? `<table class="small"><tr><th>Device</th><th>Last seen</th><th>Captures</th></tr>${r.devices.map((d) => `<tr><td>${esc(d.name || d.device_id.slice(0, 8))}</td><td>${fmtDate(d.last_seen_at)}</td><td>${d.captures_received}</td></tr>`).join('')}</table>` : '<div class="small muted">No phone has synced yet. Checklist: same WiFi, LAN access on, firewall allowed, QR scanned after enabling LAN, token not rotated.</div>'}
        <div class="small muted" style="margin-top:6px">Captures still "pending" on the phone mean the phone could not reach this computer; they are kept on the phone and sent when it can. Later download or analysis failures here never affect the capture itself.</div></div>
      <div class="panel"><h3 style="margin-top:0">Issues (${r.issues.length})</h3>${r.issues.length ? `<table><tr><th>Problem</th><th>Detail</th><th></th></tr>${r.issues.map((x, n) => `<tr><td>${esc(x.title)}</td><td class="small muted">${esc(x.detail || '')}</td><td>${x.action ? `<button class="btn small" data-fix="${n}">${act[x.action]}</button>` : ''}${x.kind !== 'tool' && x.kind !== 'ai' ? ` <button class="btn small ghost" data-openidea="${x.id}">Open</button>` : ''}</td></tr>`).join('')}</table>` : '<div class="small muted">Nothing to repair.</div>'}</div>
      <div class="panel"><h3 style="margin-top:0">Diagnostics</h3><div class="small muted">Redacted (no tokens, keys or file contents). Attach when asking for help.</div><a class="btn small" href="/api/diagnostics" download="reelvault-diagnostics.json">Download diagnostics</a> <button class="btn small" id="rp-backup">Backup database now</button></div>`;
    for (const b of v.querySelectorAll('[data-fix]')) b.onclick = async () => {
      const x = r.issues[Number(b.dataset.fix)]; b.disabled = true;
      try {
        if (x.action === 'redownload') { const res = await api(`/api/ideas/${x.id}/download`, { method: 'POST' }); toast(res.ok ? 'Download queued' : res.error, res.ok ? 'ok' : 'err'); }
        else if (x.action === 'verify') { await api(`/api/ideas/${x.id}/download/verify`, { method: 'POST' }); toast('Verified'); }
        else if (x.action === 'prepare') { const res = await api(`/api/ideas/${x.id}/prepare`, { method: 'POST' }); toast('Media: ' + res.status); }
        else if (x.action === 'metadata') { await api(`/api/ideas/${x.id}/metadata/retry`, { method: 'POST' }); toast('Retry queued'); }
        else if (x.action === 'test_ai') { const res = await api('/api/ai/local/test', { method: 'POST' }); toast(res.ok ? 'Local AI responded' : res.error, res.ok ? 'ok' : 'err'); }
      } catch (e) { toast(e.message, 'err'); }
      setTimeout(() => { currentRoute = ''; route(); }, 1500);
    };
    for (const a of v.querySelectorAll('[data-openidea]')) a.onclick = () => setQuery('idea', a.dataset.openidea);
    $('#rp-backup').onclick = async () => { const res = await api('/api/backup', { method: 'POST' }); toast('Backup written to ' + res.path, 'ok'); };
  }

  // --------------------------------------------------------------- settings
  async function renderSettings() {
    const [cfg, pair, local] = await Promise.all([api('/api/settings'), api('/api/pairing'), api('/api/ai/local')]);
    const s = cfg.settings, st = state.status, v = $('#view'); const hw = local.hardware;
    v.innerHTML = `<h1>Settings</h1>
    <div class="panel"><h2 style="margin-top:0">Pair your phone</h2>
      ${pair.warnings.map((w) => `<div class="banner small">${esc(w)}</div>`).join('')}
      <div class="row" style="align-items:flex-start;gap:24px"><div class="qr">${pair.qr_svg}</div>
        <div><div>1. Tick LAN access below, save, restart ReelVault.</div><div>2. On the phone: ReelVault > Settings > Scan pairing QR. The app fills host, port and token, then tests the connection.</div>
          <table style="width:auto;margin:8px 0"><tr><td>Host</td><td class="mono">${esc(pair.host)}</td></tr><tr><td>Port</td><td class="mono">${pair.port}</td></tr><tr><td>Token</td><td class="mono" id="tok" style="cursor:pointer" title="click to reveal">${'•'.repeat(12)}</td></tr></table>
          <div class="row"><button class="btn small" id="btn-copy-token">Copy token</button><button class="btn small danger" id="btn-rotate">Generate new token</button></div>
          <div class="form" style="margin-top:10px"><label>Advertised host</label><div><select id="s-advertised_host"><option value="">Auto (${esc(pair.candidates[0] ? pair.candidates[0].ip : 'none found')})</option>${pair.candidates.map((c) => `<option value="${esc(c.ip)}" ${s.advertised_host === c.ip ? 'selected' : ''}>${esc(c.ip)}${c.adapter ? ' · ' + esc(c.adapter) : ''}${c.virtual ? ' · virtual/VPN' : ''}</option>`).join('')}</select><div class="small muted">Choose the WiFi/Ethernet address the phone can reach. Virtual, VPN and CGNAT addresses are listed last.</div></div></div>
          <div class="small muted">Sync uses plain HTTP on your private network; every request is token-gated (docs/SECURITY.md).</div></div></div></div>
    <div class="panel"><h2 style="margin-top:0">Server</h2><div class="form">
      <label>LAN access</label><div><label><input type="checkbox" id="s-lan_enabled" ${s.lan_enabled ? 'checked' : ''}> Allow phones on the same private network (restart required)</label></div>
      <label>Port</label><input type="number" id="s-port" value="${s.port}" min="1024" max="65535" style="width:120px"><label>Server name</label><input id="s-server_name" value="${esc(s.server_name)}">
      <label>Media folder</label><div><input id="s-media_dir" value="${esc(s.media_dir)}" placeholder="${esc(st.media_dir)}"><div class="small muted">Downloads and imports, one subfolder per trip. Free: ${st.pipeline.free_gb} GB.</div></div>
      <label>Data folder</label><div class="mono small" style="padding-top:8px">${esc(st.data_dir)} <button class="btn small" id="btn-open-data">Open</button></div></div></div>
    <div class="panel"><h2 style="margin-top:0">Downloads and automation</h2><div class="form">
      <label>yt-dlp</label><div>${toolLine(st.tools.ytdlp)}<input id="s-ytdlp_path" value="${esc(s.ytdlp_path)}" placeholder="optional path to yt-dlp"></div>
      <label>ffmpeg</label><div>${toolLine(st.tools.ffmpeg)}<input id="s-ffmpeg_path" value="${esc(s.ffmpeg_path)}" placeholder="optional folder containing ffmpeg"></div>
      <label>Quality limit</label><select id="s-download_quality" style="width:140px">${['best', '1080p', '720p', '480p'].map((q) => `<option ${s.download_quality === q ? 'selected' : ''}>${q}</option>`).join('')}</select>
      <label>Keep free</label><div><input type="number" id="s-min_free_gb" value="${s.min_free_gb}" min="0" step="0.5" style="width:100px"> GB (downloads pause below this; originals are never deleted automatically)</div>
      <label>Auto-fetch metadata</label><div><label><input type="checkbox" id="s-metadata_auto" ${s.metadata_auto ? 'checked' : ''}> title, creator, thumbnail on arrival (documented endpoints only)</label></div>
      <label>Auto-download</label><div><label><input type="checkbox" id="s-auto_download" ${s.auto_download ? 'checked' : ''}> download the reference when a capture syncs</label></div>
      <label>Auto-analyze</label><div><label><input type="checkbox" id="s-auto_analyze" ${s.auto_analyze ? 'checked' : ''}> run local AI after each download (never cloud)</label></div>
      <label>Pipeline</label><div class="row"><span class="small">${st.pipeline.paused ? 'paused' : 'running'} · stages: ${esc(JSON.stringify(st.pipeline.stages))}</span><button class="btn small" id="s-pipe">${st.pipeline.paused ? 'Resume' : 'Pause'}</button></div>
      <label>Provider order</label><input id="s-metadata_providers" value="${esc((s.metadata_providers || []).join(','))}"><label>Instagram oEmbed token</label><input id="s-instagram_oembed_token" value="${esc(s.instagram_oembed_token)}" placeholder="optional Graph access token"></div></div>
    <div class="panel"><h2 style="margin-top:0">Local AI</h2>
      <div class="small muted">This machine: ${esc(hw.chip)} · ${hw.ram_gb ?? '?'} GB RAM · ${hw.disk_free_gb} GB free · ${esc(hw.os)}. Recommended model: <b>${esc(local.recommended.name)}</b> (${local.recommended.download_gb} GB download, ${esc(local.recommended.note)}). Models and the Ollama runtime are separate installs; inference uses disk, memory and power.</div>
      <div class="row" style="margin:8px 0"><span class="badge ${st.ai.configured ? 'ok' : 'warn'}">${st.ai.configured ? 'ready' : 'not ready'}</span><span class="small">${esc(st.ai.how_to_configure || '')}</span><button class="btn small" id="s-test-ai">Test local AI</button></div>
      <div class="form">
      <label>Provider</label><select id="s-ai_provider"><option value="ollama" ${s.ai_provider === 'ollama' ? 'selected' : ''}>Ollama (local)</option><option value="anthropic" ${s.ai_provider === 'anthropic' ? 'selected' : ''}>Anthropic cloud (opt-in)</option></select>
      <label>Ollama URL</label><input id="s-ollama_url" value="${esc(s.ollama_url)}"><label>Model</label><div><input id="s-ollama_model" value="${esc(s.ollama_model)}" list="models"><datalist id="models">${local.choices.map((c) => `<option value="${esc(c.name)}">`).join('')}${(st.ai.ollama ? st.ai.ollama.models : []).map((m) => `<option value="${esc(m)}">`).join('')}</datalist><div class="small muted">Installed: ${(st.ai.ollama && st.ai.ollama.models.length) ? esc(st.ai.ollama.models.join(', ')) : 'none detected'}</div></div>
      <label>Frames per video</label><input type="number" id="s-ai_max_frames" value="${s.ai_max_frames}" min="0" max="16" style="width:100px"><label>Timeout (s)</label><input type="number" id="s-ollama_timeout" value="${s.ollama_timeout}" min="30" style="width:100px"><label>Context tokens</label><input type="number" id="s-ollama_num_ctx" value="${s.ollama_num_ctx}" min="2048" step="1024" style="width:120px">
      <label>Local transcription</label><div><label><input type="checkbox" id="s-ai_transcribe" ${s.ai_transcribe ? 'checked' : ''}> use whisper when installed</label> ${toolLine(st.tools.whisper)}<input id="s-whisper_path" value="${esc(s.whisper_path)}" placeholder="optional path to whisper-cli"></div>
      <label>Cloud AI</label><div><label><input type="checkbox" id="s-cloud_ai_opt_in" ${s.cloud_ai_opt_in ? 'checked' : ''}> allow the Anthropic provider (needs REELVAULT_AI_API_KEY; costs money; never used automatically)</label> <input id="s-ai_model" value="${esc(s.ai_model)}" style="width:200px"></div></div></div>
    <div class="panel"><h2 style="margin-top:0">Reminders, priorities, categories</h2><div class="form">
      <label>Reminders</label><div><label><input type="checkbox" id="s-reminders_enabled" ${s.reminders_enabled ? 'checked' : ''}> remind about High-priority ideas on their follow-up date</label> quiet hours <input type="number" id="s-reminder_quiet_hours" value="${s.reminder_quiet_hours}" min="1" style="width:80px"> <button class="btn small" id="btn-notify-perm">Allow notifications</button></div>
      <label>Priorities</label><input id="s-priorities" value="${esc(s.priorities.join(','))}">
      <label>Categories</label><div id="cats">${state.categories.map((c) => `<div class="row small" style="margin-bottom:4px"><span style="min-width:140px">${esc(c.name)} <span class="muted">(${c.idea_count})</span></span><button class="btn small" data-ren="${c.id}">Rename</button><button class="btn small danger" data-delc="${c.id}">Delete</button></div>`).join('')}<div class="row"><input id="cat-new" placeholder="New category"><button class="btn small" id="cat-add">Add</button></div></div>
      <label>DaVinci Resolve</label><div><div class="small muted">${esc(st.resolve.note)}</div><input id="s-resolve_scripting_path" value="${esc(s.resolve_scripting_path)}" placeholder="optional Scripting/Modules folder"></div></div></div>
    <div class="row"><button class="btn primary" id="btn-save-settings">Save settings</button><span class="muted small">LAN access and port changes take effect after a restart.</span></div>`;
    $('#tok').onclick = () => { $('#tok').textContent = pair.token; };
    $('#btn-copy-token').onclick = () => navigator.clipboard.writeText(pair.token).then(() => toast('Token copied', 'ok'), () => { $('#tok').textContent = pair.token; });
    $('#btn-rotate').onclick = async () => { if (!confirm('Generate a new pairing token? The phone must be paired again.')) return; await api('/api/pairing/rotate', { method: 'POST' }); currentRoute = ''; route(); };
    $('#btn-open-data').onclick = () => api('/api/open-folder?which=data', { method: 'POST' }).catch((e) => toast(e.message, 'err'));
    $('#btn-notify-perm').onclick = () => { if (typeof Notification !== 'undefined') Notification.requestPermission(); };
    $('#s-pipe').onclick = async () => { await api(st.pipeline.paused ? '/api/pipeline/resume' : '/api/pipeline/pause', { method: 'POST' }); await refreshStatus(); currentRoute = ''; route(); };
    $('#s-test-ai').onclick = async () => { $('#s-test-ai').disabled = true; try { const r = await api('/api/ai/local/test', { method: 'POST' }); toast(r.ok ? `Local AI replied: ${JSON.stringify(r.reply)}` : r.error, r.ok ? 'ok' : 'err'); } catch (e) { toast(e.message, 'err'); } $('#s-test-ai').disabled = false; };
    $('#cat-add').onclick = async () => { try { await api('/api/categories', { method: 'POST', body: { name: $('#cat-new').value } }); currentRoute = ''; route(); } catch (e) { toast(e.message, 'err'); } };
    for (const b of v.querySelectorAll('[data-ren]')) b.onclick = async () => { const n = prompt('New name'); if (!n) return; try { await api('/api/categories/' + b.dataset.ren, { method: 'PUT', body: { name: n } }); currentRoute = ''; route(); } catch (e) { toast(e.message, 'err'); } };
    for (const b of v.querySelectorAll('[data-delc]')) b.onclick = async () => {
      const others = state.categories.filter((c) => c.id !== b.dataset.delc);
      const m = modal(`<h2 style="margin-top:0">Delete category</h2><div>Move its ideas to:</div><select id="dc-target" style="margin:8px 0"><option value="">No category</option>${others.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><div class="row"><button class="btn danger" id="dc-go">Delete</button><button class="btn" id="dc-close">Cancel</button></div>`);
      $('#dc-close', m).onclick = closeModal; $('#dc-go', m).onclick = async () => { const t = $('#dc-target', m).value; await api('/api/categories/' + b.dataset.delc + (t ? '?reassign_to=' + t : ''), { method: 'DELETE' }); closeModal(); currentRoute = ''; route(); };
    };
    $('#btn-save-settings').onclick = async () => {
      const g = (id) => $(id).value, c = (id) => $(id).checked, n = (id) => Number($(id).value);
      const values = { lan_enabled: c('#s-lan_enabled'), port: n('#s-port'), server_name: g('#s-server_name'), media_dir: g('#s-media_dir'), advertised_host: g('#s-advertised_host'),
        ytdlp_path: g('#s-ytdlp_path'), ffmpeg_path: g('#s-ffmpeg_path'), download_quality: g('#s-download_quality'), min_free_gb: n('#s-min_free_gb'), metadata_auto: c('#s-metadata_auto'), auto_download: c('#s-auto_download'), auto_analyze: c('#s-auto_analyze'),
        metadata_providers: g('#s-metadata_providers').split(',').map((x) => x.trim()).filter(Boolean), instagram_oembed_token: g('#s-instagram_oembed_token'),
        ai_provider: g('#s-ai_provider'), ollama_url: g('#s-ollama_url'), ollama_model: g('#s-ollama_model'), ai_max_frames: n('#s-ai_max_frames'), ollama_timeout: n('#s-ollama_timeout'), ollama_num_ctx: n('#s-ollama_num_ctx'), ai_transcribe: c('#s-ai_transcribe'), whisper_path: g('#s-whisper_path'), cloud_ai_opt_in: c('#s-cloud_ai_opt_in'), ai_model: g('#s-ai_model'),
        reminders_enabled: c('#s-reminders_enabled'), reminder_quiet_hours: n('#s-reminder_quiet_hours'), priorities: g('#s-priorities').split(',').map((x) => x.trim()).filter(Boolean), resolve_scripting_path: g('#s-resolve_scripting_path') };
      try { await api('/api/settings', { method: 'PUT', body: { values } }); toast('Settings saved', 'ok'); await refreshStatus(); currentRoute = ''; route(); } catch (e) { toast(e.message, 'err'); }
    };
  }
  function toolLine(t) { return t.found ? `<div class="small"><span class="badge ok">found</span> <span class="mono">${esc(t.path)}</span> ${esc(t.version || '')}</div>` : `<div class="small"><span class="badge warn">not found</span> ${esc(t.install_hint)}</div>`; }

  // ------------------------------------------------------------- add menu
  $('#btn-add').onclick = () => {
    const m = modal(`<h2 style="margin-top:0">Add to the library</h2>
      <h3>Paste links (one per line; Instagram, YouTube, Shorts)</h3><textarea id="ad-links" placeholder="https://www.instagram.com/reel/...\nhttps://youtube.com/shorts/..." style="min-height:110px"></textarea>
      <div class="row" style="margin-top:6px"><label class="small"><input type="checkbox" id="ad-dup"> save even if a link already exists</label><span class="grow"></span><button class="btn primary" id="ad-go">Add links</button></div><div id="ad-results" class="small" style="margin-top:6px"></div>
      <h3>Import a video file</h3><div class="small muted">Or drag files onto any gallery. The original is copied into the media folder, never modified.</div><input type="file" id="ad-file" accept=".mp4,.m4v,.webm,.mov,.mkv" multiple>
      <div class="row" style="margin-top:12px"><button class="btn" id="ad-close">Close</button></div>`);
    $('#ad-close', m).onclick = closeModal;
    $('#ad-go', m).onclick = async () => { try { const r = await api('/api/ideas/bulk', { method: 'POST', body: { text: $('#ad-links', m).value, allow_duplicate: $('#ad-dup', m).checked } }); $('#ad-results', m).innerHTML = r.results.map((x) => `<div><span class="badge ${x.result === 'created' ? 'ok' : x.result === 'invalid' ? 'bad' : ''}">${esc(x.result)}</span> ${esc(x.url || x.line)} ${esc(x.error || '')}</div>`).join(''); toast(`${r.created} added`, 'ok'); refreshStatus(); if (parseHash().name !== 'settings') { currentRoute = ''; route(); } } catch (e) { toast(e.message, 'err'); } };
    $('#ad-file', m).onchange = async (e) => { for (const f of e.target.files) await importFile(f); closeModal(); currentRoute = ''; route(); };
    $('#ad-links', m).focus();
  };

  // ------------------------------------------------------------- reminders
  async function checkReminders() {
    try { const r = await api('/api/reminders/due'); const b = $('#reminder-banner'); if (!r.enabled || !r.due.length) { b.classList.add('hidden'); return; }
      b.classList.remove('hidden'); b.innerHTML = `<b>Follow-up:</b> ${r.due.map((d) => `<a href="#" data-openidea="${d.id}">${esc(d.title || d.original_url)}</a>`).join(', ')} <button class="btn small" id="rem-ack" style="margin-left:10px">Dismiss</button>`;
      for (const a of b.querySelectorAll('[data-openidea]')) a.onclick = (e) => { e.preventDefault(); setQuery('idea', a.dataset.openidea); };
      $('#rem-ack').onclick = async () => { await api('/api/reminders/ack', { method: 'POST', body: { idea_ids: r.due.map((d) => d.id) } }); b.classList.add('hidden'); };
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && !sessionStorage.getItem('rv.notified')) { sessionStorage.setItem('rv.notified', '1'); new Notification('ReelVault', { body: `${r.due.length} high-priority idea(s) are due` }); }
    } catch { /* ignore */ }
  }

  (async () => { await refreshStatus(); await route(); checkReminders(); setInterval(checkReminders, 5 * 60 * 1000); setInterval(() => refreshStatus().catch(() => {}), 20000); })();
})();
