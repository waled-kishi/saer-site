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
