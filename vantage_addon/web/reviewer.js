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
  // Count answers this session so we can gently mark today's recommended flashcard
  // goal once, without ending the session (you usually have time for more).
  let answered = 0;
  let goalShown = false;
  // Feature 3: absolute epoch-ms deadline for a time-capped session (0 = no limit).
  // Set by the host in enter(); the host also enforces the stop, so this is display
  // only (the countdown pill), never the thing that actually ends the session.
  let deadlineMs = 0;
  let timerId = null;
  function fmtLeft(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }
  function timerPill() {
    if (!deadlineMs) return '';
    const left = deadlineMs - Date.now();
    const up = left <= 0;
    return `<span class="review__timer${up ? ' review__timer--up' : ''}" id="vrtimer">${up ? "time's up" : fmtLeft(left)}</span>`;
  }
  function tickTimer() {
    if (timerId) { clearInterval(timerId); timerId = null; }
    if (!deadlineMs) return;
    timerId = setInterval(() => {
      const el = document.getElementById('vrtimer');
      if (!el) return;
      const left = deadlineMs - Date.now();
      if (left <= 0) { el.textContent = "time's up"; el.classList.add('review__timer--up'); }
      else el.textContent = fmtLeft(left);
    }, 1000);
  }

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
        ${timerPill()}
        ${meta.hasCard ? `<button class="review__flag${meta.flag ? ' review__flag--on' : ''}" aria-pressed="${meta.flag ? 'true' : 'false'}" title="Flag to revisit (F)" onclick="vreview._flag()"><span class="review__flagstar">${meta.flag ? '\u2605' : '\u2606'}</span> Flag</button>` : ''}
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
      // Imported decks color their DEFAULT/secondary card text a light gray/blue-gray
      // for their original dark surface (e.g. #extra{color:#D7DEE9}, .tags{color:#A6ABB9}),
      // which is near-invisible on our white card. This frame has no `.card` wrapper, so
      // those id/class rules win over the dark body text and leak through. Force the gray
      // CONTAINERS to the readable body color: plain text inherits it, while bold/italic/
      // underline/cloze accents inside keep their own color rule (highlighted terms like
      // the teal "Paramagnetic" / "unpaired" stay colored).
      "#extra,.tags{color:#1f2937!important}" +
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

  // Today's recommended flashcard count, taken from the dashboard's study plan (the
  // same "X flashcards to study today" number). 0 when there is no plan yet.
  function dailyGoal() {
    const v = (typeof window !== 'undefined' && window.__VANTAGE__) || null;
    const sp = v && v.study_pace;
    if (!sp) return 0;
    const n = sp.flashcards_per_day || sp.reviews_due || 0;
    return n > 0 ? n : 0;
  }
  // A quiet, one-time nudge when you reach today's recommended number: happy, but it
  // does NOT stop the session, so you keep going if you have the time. Lives on the
  // body (not the review stage) so pushing the next card doesn't wipe it.
  function goalToast(goal) {
    let el = document.getElementById('revgoal');
    if (!el) {
      el = document.createElement('div');
      el.id = 'revgoal';
      el.className = 'revgoal';
      document.body.appendChild(el);
    }
    el.innerHTML =
      '<span class="revgoal__dot"></span><span>Nice work, that\u2019s today\u2019s ' +
      goal + ' flashcard' + (goal === 1 ? '' : 's') + '. Keep going while you have time.</span>';
    void el.offsetWidth; // reflow so re-adding the class re-animates
    el.classList.add('revgoal--show');
    clearTimeout(window.__revgoalT);
    window.__revgoalT = setTimeout(function () { el.classList.remove('revgoal--show'); }, 5200);
  }
  function maybeGoalToast() {
    if (goalShown) return;
    const goal = dailyGoal();
    if (goal > 0 && answered >= goal) {
      goalShown = true;
      goalToast(goal);
    }
  }

  window.vreview = {
    enter(p) {
      state = 'loading';
      answered = 0;
      goalShown = false;
      deadlineMs = (p && p.endMs) ? p.endMs : 0;   // Feature 3: host-provided cap
      meta = { deck: 'Studying', counts: { new: 0, lrn: 0, rev: 0 } };  // no card yet -> no flag star
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage"><p style="color:var(--gray-500);font-weight:600">Loading your next card</p></div></div>`;
      tickTimer();
    },
    card(p) {
      state = 'question';
      meta = { deck: p.deck, counts: p.counts, flag: p.flag || 0, hasCard: true };
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage">${frame(p.css, p.html)}
          <div class="review__controls"><button class="showbtn" onclick="vreview._show()">Show answer</button></div>
        </div></div>`;
      sizeFrame();
      tickTimer();
    },
    answer(p) {
      state = 'answer';
      meta.flag = p.flag || 0; meta.hasCard = true;  // Feature 4: keep the star correct across show-answer
      const rates = (p.buttons || [])
        .map((b) => `<button class="rate rate--${b.cls}" onclick="vreview._rate(${b.ease})">${escHtml(b.label)}<span class="rate__ivl">${escHtml(b.ivl)}</span></button>`)
        .join('');
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage">${frame(p.css, p.html)}
          <div class="review__controls"><div class="rates">${rates}</div></div>
        </div></div>`;
      sizeFrame();
      tickTimer();
    },
    // End of the due queue. `p.section` names the section just finished (omitted for
    // the mixed queue); `p.canContinue` offers more of that pool's non-due cards.
    done(p) {
      p = p || {};
      state = 'done';
      if (timerId) { clearInterval(timerId); timerId = null; }  // Feature 3: stop the ticker
      deadlineMs = 0;
      meta = { deck: 'Studying', counts: { new: 0, lrn: 0, rev: 0 } };
      const sec = p.section ? ' for ' + escHtml(p.section) : '';
      const keep = p.canContinue
        ? `<button class="showbtn" onclick="vreview._more()">Keep studying${p.section ? ' ' + escHtml(p.section) : ''}</button>`
        : '';
      // Feature 3: at time-up the session ended because the clock ran out, so the
      // heading says so and there is no "keep going".
      const heading = p.timeup ? "Time's up. Nice work." : 'Nice work';
      const lead = p.canContinue
        ? `You finished today's reviews${sec}. Want to keep going with more cards?`
        : (p.timeup
          ? `You studied right up to time${sec}. Head back to your dashboard when you are ready.`
          : `You finished today's reviews${sec}. Close this to head back to your dashboard.`);
      // Real count of cards graded this session (from `answered`, incremented on
      // each rate). Flashcards have no right/wrong grade, so we show only the count,
      // never an accuracy. Omitted entirely if nothing was reviewed this session.
      const recap = answered > 0
        ? `<div class="review__recap">You reviewed <b>${answered}</b> card${answered === 1 ? '' : 's'} this session</div>`
        : '';
      stage().innerHTML = `<div class="review">${topBar()}
        <div class="review__stage"><div class="review__done">
          <h2>${escHtml(heading)}</h2>
          ${recap}
          <p>${lead}</p>
          <div class="review__donebtns">
            ${keep}
            <button class="showbtn ${p.canContinue ? 'showbtn--ghost' : ''}" onclick="vreview._close()">Back to dashboard</button>
          </div>
        </div></div></div>`;
      // Light celebration only when real work happened; reuses practice.js's burst.
      if (answered > 0) { try { window.__vConfetti && window.__vConfetti(); } catch (e) { /* no-op */ } }
    },
    _show() { vpy('review:show'); },
    _rate(e) { answered += 1; vpy('review:answer:' + e); maybeGoalToast(); },
    _more() { vpy('review:more'); },
    // Feature 4: flag/unflag the card on screen. Optimistic UI, then tell the host
    // to write the native Anki flag. Never advances the card (metadata only).
    _flag() {
      meta.flag = meta.flag ? 0 : 1;
      const btn = document.querySelector('.review__flag');
      if (btn) {
        btn.classList.toggle('review__flag--on', !!meta.flag);
        btn.setAttribute('aria-pressed', meta.flag ? 'true' : 'false');
        const star = btn.querySelector('.review__flagstar');
        if (star) star.textContent = meta.flag ? '\u2605' : '\u2606';
      }
      vpy('review:flag:' + (meta.flag ? 1 : 0));
    },
    // Drop the overlay instantly, then ask the host to recompute so the dashboard
    // reflects the cards you just studied (memory score, ranges, counts).
    _close() { if (timerId) { clearInterval(timerId); timerId = null; } close(); vpy('studydone'); },
  };

  document.addEventListener('keydown', (ev) => {
    if (state === 'question' && (ev.key === ' ' || ev.key === 'Enter')) { ev.preventDefault(); vreview._show(); }
    else if (state === 'answer' && ['1', '2', '3', '4'].includes(ev.key)) { ev.preventDefault(); vreview._rate(parseInt(ev.key, 10)); }
    else if ((state === 'question' || state === 'answer') && (ev.key === 'f' || ev.key === 'F')) { ev.preventDefault(); vreview._flag(); }
  });

  // Bridge fallback if the dashboard script did not define it (standalone preview).
  window.vpy = window.vpy || function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };
})();
