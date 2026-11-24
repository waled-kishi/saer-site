/* Back-to-top button: hidden at the top of the page, shown after scrolling down. */
(function () {
  var btn = document.getElementById('to-top');
  if (!btn) return;
  btn.hidden = false;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var ticking = false;
  function update() {
    btn.classList.toggle('is-on', window.scrollY > Math.max(400, window.innerHeight * 0.6));
    ticking = false;
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
  }, { passive: true });
  btn.addEventListener('click', function (e) {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
    var first = document.querySelector('.skip');
    if (first) first.focus({ preventScroll: true });
  });
  update();
})();

/* ── Course landing page ──────────────────────────────────────────────
   Three small things: the deadline countdowns, the bar that appears once the
   hero is out of sight, and the special offer. The offer's window is real: it
   starts at the visitor's first view, it is kept in their browser, and when it
   runs out the popup and its chip are gone for good on this device. */
(function () {
  var pad = function (n) { return n < 10 ? '0' + n : String(n); };

  /* Deadline countdowns (days/hours/minutes/seconds). */
  var counts = document.querySelectorAll('.lp-count[data-ends]');
  if (counts.length) {
    var tickEnds = function () {
      counts.forEach(function (el) {
        var left = new Date(el.dataset.ends).getTime() - Date.now();
        if (left <= 0) { el.textContent = 'انتهى موعد التسجيل'; return; }
        var s = Math.floor(left / 1000);
        var set = function (k, v) { var b = el.querySelector('[data-' + k + ']'); if (b) b.textContent = v; };
        set('d', Math.floor(s / 86400));
        set('h', pad(Math.floor(s % 86400 / 3600)));
        set('m', pad(Math.floor(s % 3600 / 60)));
        set('s', pad(s % 60));
      });
    };
    tickEnds();
    setInterval(tickEnds, 1000);
  }

  /* The top bar shows itself once the hero has scrolled away. */
  var top = document.getElementById('lp-top');
  if (top) {
    top.hidden = false;
    var onScroll = function () { top.classList.toggle('on', window.scrollY > 520); };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* The special offer. */
  var pop = document.getElementById('lp-pop');
  if (!pop) return;
  var chip = document.getElementById('lp-chip');
  var key = pop.dataset.key;
  var hours = parseFloat(pop.dataset.hours) || 3;
  var store = {
    get: function (k) { try { return localStorage.getItem(key + ':' + k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(key + ':' + k, v); } catch (e) {} }
  };
  var started = parseInt(store.get('start') || '0', 10);
  if (!started) { started = Date.now(); store.set('start', String(started)); }
  var ends = started + hours * 3600 * 1000;
  if (Date.now() >= ends) return;   // the window is over: nothing is shown again

  var open = function () { pop.classList.add('on'); document.body.style.overflow = 'hidden'; };
  var close = function () {
    pop.classList.remove('on');
    document.body.style.overflow = '';
    store.set('seen', '1');
    if (chip) chip.hidden = false;
  };
  pop.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', close); });
  pop.addEventListener('click', function (e) { if (e.target === pop) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pop.classList.contains('on')) close(); });
  var go = pop.querySelector('[data-go]');
  if (go) go.addEventListener('click', close);
  if (chip) chip.addEventListener('click', open);

  var tickPop = function () {
    var left = ends - Date.now();
    if (left <= 0) {                 // honoured to the second: it disappears
      pop.classList.remove('on');
      document.body.style.overflow = '';
      pop.remove();
      if (chip) chip.remove();
      clearInterval(timer);
      return;
    }
    var s = Math.floor(left / 1000);
    var hh = pad(Math.floor(s / 3600)), mm = pad(Math.floor(s % 3600 / 60)), ss = pad(s % 60);
    var box = pop.querySelector('[data-pop-count]');
    if (box) {
      box.querySelector('[data-h]').textContent = hh;
      box.querySelector('[data-m]').textContent = mm;
      box.querySelector('[data-s]').textContent = ss;
    }
    if (chip) chip.querySelector('[data-chip]').textContent = hh + ':' + mm + ':' + ss;
  };
  tickPop();
  var timer = setInterval(tickPop, 1000);

  if (store.get('seen')) {
    if (chip) chip.hidden = false;            // seen already: only the chip stays
  } else {
    var shown = false;
    var maybe = function () {
      if (shown) return;
      if (window.scrollY > document.documentElement.scrollHeight * 0.25 || Date.now() - started > 25000) {
        shown = true;
        open();
        window.removeEventListener('scroll', maybe);
      }
    };
    window.addEventListener('scroll', maybe, { passive: true });
    setTimeout(maybe, 25000);
  }
})();
