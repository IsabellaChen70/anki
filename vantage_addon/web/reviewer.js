/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Vantage in-dashboard reviewer. The host (the desktop add-on) drives this
   through Anki's real scheduler: it calls window.vreview.card / .answer / .done,
   and the buttons call back through vpy. Cards render in an isolated iframe so
   the note's own styling never fights the dashboard's. */
(function () {
  // Render into a full-page layer over the dashboard (not into #app), so the
  // dashboard stays mounted exactly where you left it and shows instantly on close.
  const stage = () => {
    let el = document.getElementById('reviewOverlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'reviewOverlay';
      el.className = 'reviewoverlay';
      document.body.appendChild(el);
      document.body.style.overflow = 'hidden';
    }
    return el;
  };
  const close = () => {
    const el = document.getElementById('reviewOverlay');
    if (el) el.remove();
    document.body.style.overflow = '';
  };
  let state = 'idle';
  let meta = { deck: 'Studying', counts: { new: 0, lrn: 0, rev: 0 } };

  const escHtml = (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const escAttr = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;');

  function topBar() {
    const c = meta.counts || { new: 0, lrn: 0, rev: 0 };
    return `<div class="review__top">
      <div class="review__deck">${escHtml(meta.deck || 'Studying')}</div>
      <div class="review__topright">
        <div class="review__counts">
          <span class="rc rc--new">${c.new} new</span>
          <span class="rc rc--lrn">${c.lrn} learning</span>
          <span class="rc rc--rev">${c.rev} to review</span>
        </div>
        <button class="review__back" onclick="vreview._close()">Back to dashboard</button>
      </div></div>`;
  }

  function frame(css, html) {
    const base =
      "html,body{margin:0;background:#fff}body{font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,sans-serif;" +
      "padding:1.6rem;color:#1f2937;line-height:1.55;font-size:17px}";
    // Vantage overrides, injected AFTER the note's own CSS so they win: neutralize
    // an imported deck's theming (parchment backgrounds, oversized fonts, its own
    // font family, source/Khan-Academy links, huge images) so every card reads
    // like the rest of the app instead of like the source deck.
    const overrides =
      ".card{background:transparent!important;color:#1f2937!important;font-size:17px!important}" +
      "*{font-family:inherit!important;background-image:none!important;max-width:100%!important}" +
      // Equation/prompt images (in the card's Text field) stay small; explanation
      // diagrams (MileDown puts them in the Extra field, wrapped in #extra) get a
      // bigger box so their small labels stay readable.
      "img{max-width:min(100%,200px)!important;max-height:150px!important;height:auto!important;width:auto!important}" +
      "#extra img{max-width:min(100%,480px)!important;max-height:460px!important}" +
      'a[href*="khan"],a[href*="youtu"]{display:none!important}' +
      ".cloze{color:#2563eb!important;font-weight:700}";
    const doc = "<style>" + base + (css || '') + overrides + "</style>" + (html || '');
    return `<div class="cardframe"><iframe id="cardframe" sandbox="allow-same-origin" srcdoc="${escAttr(doc)}"></iframe></div>`;
  }

  function sizeFrame() {
    const f = document.getElementById('cardframe');
    if (!f) return;
    const fit = () => {
      try {
        // Cap the card to roughly one screen; taller cards scroll inside the frame
        // so the answer/rate buttons stay visible ("fits on one page").
        const h = f.contentWindow.document.body.scrollHeight + 8;
        const cap = Math.max(200, Math.round(window.innerHeight * 0.62));
        f.style.height = Math.min(Math.max(140, h), cap) + 'px';
      } catch (e) { f.style.height = '240px'; }
    };
    f.onload = fit;
    setTimeout(fit, 60);
  }

  window.vreview = {
    enter() {
      state = 'loading';
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage"><p style="color:var(--gray-500);font-weight:600">Loading your next card</p></div></div>`;
    },
    card(p) {
      state = 'question';
      meta = { deck: p.deck, counts: p.counts };
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage">${frame(p.css, p.html)}
          <div class="review__controls"><button class="showbtn" onclick="vreview._show()">Show answer</button></div>
        </div></div>`;
      sizeFrame();
    },
    answer(p) {
      state = 'answer';
      const rates = (p.buttons || [])
        .map((b) => `<button class="rate rate--${b.cls}" onclick="vreview._rate(${b.ease})">${escHtml(b.label)}<span class="rate__ivl">${escHtml(b.ivl)}</span></button>`)
        .join('');
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage">${frame(p.css, p.html)}
          <div class="review__controls"><div class="rates">${rates}</div></div>
        </div></div>`;
      sizeFrame();
    },
    done() {
      state = 'done';
      meta = { deck: 'Studying', counts: { new: 0, lrn: 0, rev: 0 } };
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage"><div class="review__done">
          <h2>No cards due right now</h2>
          <p>Nice work. Close this to head back to your dashboard.</p>
          <button class="showbtn" onclick="vreview._close()">Back to dashboard</button>
        </div></div></div>`;
    },
    _show() { vpy('review:show'); },
    _rate(e) { vpy('review:answer:' + e); },
    // Drop the overlay instantly, then ask the host to recompute so the dashboard
    // reflects the cards you just studied (memory score, ranges, counts).
    _close() { close(); vpy('studydone'); },
  };

  document.addEventListener('keydown', (ev) => {
    if (state === 'question' && (ev.key === ' ' || ev.key === 'Enter')) { ev.preventDefault(); vreview._show(); }
    else if (state === 'answer' && ['1', '2', '3', '4'].includes(ev.key)) { ev.preventDefault(); vreview._rate(parseInt(ev.key, 10)); }
  });

  // Bridge fallback if the dashboard script did not define it (standalone preview).
  window.vpy = window.vpy || function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };
})();
