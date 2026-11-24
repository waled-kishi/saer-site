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
   The deadline countdowns, the bar that appears once the hero is away, and the
   special offer. The offer's window is real: it starts at the visitor's first
   view, it lives in their browser, and while it runs the special price replaces
   the usual one everywhere on the page — the buttons, the WhatsApp message and
   the registration form — so what they were promised is what they are asked for.
   When it runs out, everything returns to the usual price. */
(function () {
  var pad = function (n) { return n < 10 ? '0' + n : String(n); };

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

  var topBar = document.getElementById('lp-top');
  if (topBar) {
    topBar.hidden = false;
    var onScroll = function () { topBar.classList.toggle('on', window.scrollY > 560); };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  var goRegister = function () {
    var t = document.getElementById('register');
    if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  var pop = document.getElementById('lp-pop');
  if (!pop) return;
  var key = pop.dataset.key;
  var hours = parseFloat(pop.dataset.hours) || 1;
  var special = (pop.dataset.offerPrice || '').trim();   // never data-price: that is what the swap writes into
  var store = {
    get: function (k) { try { return localStorage.getItem(key + ':' + k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(key + ':' + k, v); } catch (e) {} }
  };

  /* The page as it stands at the usual price, so it can be put back. */
  var prices = [].slice.call(document.querySelectorAll('[data-price]'));
  var offs = [].slice.call(document.querySelectorAll('[data-off]'));
  var was = [].slice.call(document.querySelectorAll('[data-wa]'));
  var wases = [].slice.call(document.querySelectorAll('[data-was]'));
  var field = document.querySelector('[data-offer-field]');
  var offerClocks = [].slice.call(document.querySelectorAll('[data-offer-count]'));
  var barNotes = [].slice.call(document.querySelectorAll('[data-bar-note]'));
  var barWas = barNotes.map(function (el) { return el.textContent; });
  var usual = prices.length ? prices[0].textContent.trim() : '';
  var waHrefs = was.map(function (a) { return a.href; });
  var num = function (t) { var m = String(t).replace(/[^\d.]/g, ''); return m ? parseFloat(m) : 0; };
  wases.forEach(function (el) { if (!el.dataset.orig) el.dataset.orig = el.textContent.trim(); });

  var applyOffer = function (on) {
    if (!special) return;
    prices.forEach(function (el) { el.textContent = on ? special : usual; });
    var base = wases.length ? num(wases[0].dataset.orig) : 0;
    offs.forEach(function (el) {
      var to = on ? num(special) : num(usual);
      el.textContent = base && to ? 'خصم ' + Math.round((1 - to / base) * 100) + '%' : el.textContent;
      el.classList.toggle('lp-off--hot', on);
    });
    was.forEach(function (a, i) {
      var u = waHrefs[i];
      a.href = on ? u.replace(/(\?text=)(.*)$/, function (_, p, t) {
        return p + encodeURIComponent(decodeURIComponent(t) + ' (بالسعر الخاص ' + special + ')');
      }) : u;
    });
    if (field) field.value = on ? special : '';
    offerClocks.forEach(function (el) { el.hidden = !on; });
    barNotes.forEach(function (el, i) { el.textContent = on ? 'سعرك الخاص ينتهي قريباً' : barWas[i]; });
    document.querySelectorAll('[data-offer-note]').forEach(function (el) { el.hidden = !on; });
  };

  var started = parseInt(store.get('start') || '0', 10);   // set when the offer is first shown
  var ends = started ? started + hours * 3600 * 1000 : 0;
  var timer = null;

  var stop = function () {
    applyOffer(false);
    document.body.style.overflow = '';
    if (pop.parentNode) pop.remove();
    if (timer) clearInterval(timer);
  };

  var tick = function () {
    var left = ends - Date.now();
    if (left <= 0) { stop(); return; }
    var s = Math.floor(left / 1000);
    var hh = pad(Math.floor(s / 3600)), mm = pad(Math.floor(s % 3600 / 60)), ss = pad(s % 60);
    var boxes = [pop.querySelector('[data-pop-count]')].concat(offerClocks);
    boxes.forEach(function (box) {
      if (!box) return;
      box.querySelector('[data-h]').textContent = hh;
      box.querySelector('[data-m]').textContent = mm;
      box.querySelector('[data-s]').textContent = ss;
    });
    barNotes.forEach(function (el) { el.textContent = 'سعرك الخاص: ' + hh + ':' + mm + ':' + ss; });
  };

  var close = function () { pop.classList.remove('on'); document.body.style.overflow = ''; };
  pop.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', close); });
  pop.addEventListener('click', function (e) { if (e.target === pop) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pop.classList.contains('on')) close(); });
  var go = pop.querySelector('[data-go]');
  if (go) {
    go.addEventListener('click', function (e) {
      if ((go.getAttribute('href') || '').charAt(0) === '#') { e.preventDefault(); close(); setTimeout(goRegister, 60); }
      else { close(); }
    });
  }

  var runWindow = function () {
    tick();
    timer = setInterval(tick, 1000);
    applyOffer(true);
  };

  if (started) {                       // the offer was already revealed on this device
    if (Date.now() >= ends) { stop(); return; }
    runWindow();                       // still running: the page keeps the special price
    return;
  }

  /* Not revealed yet: the page stays at the usual price until the offer shows itself —
     once the reader has gone a little way down, or after two minutes on the page. */
  var opened = false;
  var reveal = function () {
    if (opened) return;
    opened = true;
    window.removeEventListener('scroll', onScrollReveal);
    started = Date.now();
    store.set('start', String(started));
    ends = started + hours * 3600 * 1000;
    runWindow();
    pop.classList.add('on');
    document.body.style.overflow = 'hidden';
    var box = pop.querySelector('.lp-pop__box');
    if (box) box.scrollTop = 0;
  };
  var onScrollReveal = function () {
    var seen = window.scrollY + window.innerHeight;
    if (seen > document.documentElement.scrollHeight * 0.3) reveal();
  };
  window.addEventListener('scroll', onScrollReveal, { passive: true });
  setTimeout(reveal, 120000);
})();
