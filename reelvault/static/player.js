/* ReelVault player: seek, volume, speed, repeat, fullscreen, A-B loop, timestamped notes. No dependencies. */
(() => {
  'use strict';
  const fmt = (s) => { if (!isFinite(s)) return '0:00'; const m = Math.floor(s / 60), r = Math.floor(s % 60); return `${m}:${String(r).padStart(2, '0')}`; };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /** Mount a player into `root` for `idea`. opts: {api, onNotesChange, autoplay, preload} */
  function mount(root, idea, opts = {}) {
    const api = opts.api;
    root.innerHTML = '';
    root.className = 'player';
    if (!idea.playable) {
      const ms = idea.media_status;
      const msg = idea.source === 'local' ? 'The imported file could not be prepared for playback.'
        : ms === 'audio_only' ? 'This download is audio only (no video stream). Use Repair centre to re-download with ffmpeg installed.'
        : ms === 'missing' ? 'The local file is missing. Download again or Verify.'
        : ms === 'invalid' ? 'The local file is not a valid video.'
        : idea.download_status === 'downloading' ? 'Downloading...' : idea.download_status === 'queued' ? 'Queued for download'
        : idea.local_path && !idea.playback_path ? 'Needs ffmpeg to create a browser-playable copy.'
        : 'Not downloaded yet.';
      root.innerHTML = `<div class="state"${idea.has_thumbnail ? ` style="background:#0a0d12 url('/api/ideas/${idea.id}/cover?v=${encodeURIComponent(idea.updated_at)}') center/contain no-repeat"` : ''}><div style="background:rgba(0,0,0,.7);padding:10px 14px;border-radius:8px">${esc(msg)}<br><a class="btn small" style="margin-top:8px" href="${esc(idea.original_url)}" target="_blank" rel="noopener">Open original</a></div></div>`;
      return { destroy() {}, seek() {}, pause() {}, play() {}, video: null };
    }
    const v = document.createElement('video');
    v.src = `/api/media/${idea.id}`; v.preload = opts.preload || 'metadata'; v.playsInline = true; v.setAttribute('aria-label', idea.title || 'video');
    if (idea.has_thumbnail) v.poster = `/api/ideas/${idea.id}/cover?v=${encodeURIComponent(idea.updated_at)}`;
    root.appendChild(v);
    const c = document.createElement('div'); c.className = 'controls';
    c.innerHTML = `
      <div class="bar seek"><div class="ab" id="ab"></div><input type="range" min="0" max="1000" value="0" aria-label="Seek" id="seek"><span class="time" id="time">0:00 / 0:00</span></div>
      <div class="bar">
        <button class="btn small" id="pp" aria-label="Play or pause">Play</button>
        <button class="btn small" id="mute" aria-label="Mute">Mute</button><input type="range" min="0" max="1" step="0.05" value="1" style="width:70px" aria-label="Volume" id="vol">
        <select class="small" id="speed" aria-label="Playback speed"><option value="0.25">0.25x</option><option value="0.5">0.5x</option><option value="0.75">0.75x</option><option value="1" selected>1x</option><option value="1.25">1.25x</option><option value="1.5">1.5x</option><option value="2">2x</option></select>
        <button class="btn small" id="rep" aria-pressed="false">Repeat</button>
        <button class="btn small" id="setA" title="Set loop start (A)">A</button><button class="btn small" id="setB" title="Set loop end (B)">B</button><button class="btn small" id="clrAB" title="Clear A-B loop">A-B off</button>
        <span class="grow"></span>
        <button class="btn small" id="note" title="Add a note at the current time (N)">+ Note</button>
        <button class="btn small" id="fs" aria-label="Fullscreen">Full</button>
      </div>`;
    root.appendChild(c);
    const $ = (id) => c.querySelector('#' + id);
    let a = idea.loop_start ?? null, b = idea.loop_end ?? null, seeking = false;
    const drawAB = () => { const ab = $('ab'); if (a != null && b != null && v.duration) { ab.style.left = (a / v.duration * 100) + '%'; ab.style.width = ((b - a) / v.duration * 100) + '%'; $('clrAB').textContent = `A-B ${fmt(a)}-${fmt(b)}`; } else { ab.style.width = '0'; $('clrAB').textContent = 'A-B off'; } };
    v.addEventListener('loadedmetadata', drawAB);
    v.addEventListener('timeupdate', () => { if (!seeking && v.duration) { $('seek').value = Math.round(v.currentTime / v.duration * 1000); } $('time').textContent = `${fmt(v.currentTime)} / ${fmt(v.duration)}`; if (a != null && b != null && b > a && v.currentTime >= b) v.currentTime = a; });
    v.addEventListener('play', () => { $('pp').textContent = 'Pause'; }); v.addEventListener('pause', () => { $('pp').textContent = 'Play'; });
    v.addEventListener('error', () => { root.insertAdjacentHTML('beforeend', '<div class="state">Playback failed: the file may be corrupt or use an unsupported codec. Use Prepare in details.</div>'); });
    $('seek').addEventListener('input', () => { seeking = true; if (v.duration) $('time').textContent = `${fmt($('seek').value / 1000 * v.duration)} / ${fmt(v.duration)}`; });
    $('seek').addEventListener('change', () => { if (v.duration) v.currentTime = $('seek').value / 1000 * v.duration; seeking = false; });
    $('pp').onclick = () => v.paused ? v.play().catch(() => {}) : v.pause();
    v.onclick = $('pp').onclick;
    $('mute').onclick = () => { v.muted = !v.muted; $('mute').textContent = v.muted ? 'Unmute' : 'Mute'; };
    $('vol').oninput = () => { v.volume = Number($('vol').value); v.muted = v.volume === 0; };
    $('speed').onchange = () => { v.playbackRate = Number($('speed').value); };
    $('rep').onclick = () => { v.loop = !v.loop; $('rep').setAttribute('aria-pressed', String(v.loop)); };
    const saveAB = () => api && api(`/api/ideas/${idea.id}`, { method: 'PUT', body: { fields: { loop_start: a, loop_end: b } } }).catch(() => {});
    $('setA').onclick = () => { a = v.currentTime; if (b != null && b <= a) b = null; drawAB(); saveAB(); };
    $('setB').onclick = () => { b = v.currentTime; if (a == null || a >= b) a = 0; drawAB(); saveAB(); };
    $('clrAB').onclick = () => { a = b = null; drawAB(); saveAB(); };
    $('fs').onclick = () => { (root.requestFullscreen ? root.requestFullscreen() : v.webkitEnterFullscreen && v.webkitEnterFullscreen()); };
    $('note').onclick = () => { const text = prompt(`Note at ${fmt(v.currentTime)}:`); if (text && opts.onAddNote) opts.onAddNote(v.currentTime, text); };
    root.tabIndex = 0;
    root.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.key === ' ') { e.preventDefault(); $('pp').onclick(); } else if (e.key === 'ArrowLeft') v.currentTime = Math.max(0, v.currentTime - 5);
      else if (e.key === 'ArrowRight') v.currentTime = Math.min(v.duration || 0, v.currentTime + 5); else if (e.key === 'm') $('mute').onclick();
      else if (e.key === 'n') $('note').onclick(); else if (e.key === 'a') $('setA').onclick(); else if (e.key === 'b') $('setB').onclick(); else if (e.key === 'f') $('fs').onclick();
    });
    if (opts.autoplay) v.play().catch(() => {});
    return { video: v, seek(t) { v.currentTime = t; v.play().catch(() => {}); }, pause() { v.pause(); }, play() { v.play().catch(() => {}); },
      destroy() { v.pause(); v.removeAttribute('src'); v.load(); root.innerHTML = ''; } };
  }

  function notesList(root, idea, player, api, onChange) {
    root.className = 'notes';
    root.innerHTML = `<ul style="padding:0;margin:0">${(idea.timed_notes || []).map((n) => `<li><span class="t" data-t="${n.t}">${fmt(n.t)}</span><span class="grow">${esc(n.text)}</span><button class="btn small ghost" data-del="${n.id}" aria-label="Delete note">x</button></li>`).join('') || '<li class="muted small">No timestamped notes. Press + Note (or N) while playing.</li>'}</ul>`;
    for (const t of root.querySelectorAll('[data-t]')) t.onclick = () => player.seek(Number(t.dataset.t));
    for (const d of root.querySelectorAll('[data-del]')) d.onclick = async () => { await api('/api/notes/' + d.dataset.del, { method: 'DELETE' }); onChange && onChange(); };
  }

  window.RVPlayer = { mount, notesList, fmt };
})();
