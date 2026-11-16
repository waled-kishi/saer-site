// saer-core dashboard widget: today / last 7 days and a 14-day sparkline of visitors.
(() => {
  const TAG = window.__GRAV_WIDGET_TAG || 'grav-widget-saer-core-summary';
  if (customElements.get(TAG)) return;
  const api = (p) => `${window.__GRAV_API_SERVER_URL || ''}${window.__GRAV_API_PREFIX || '/api/v1'}${p}`;
  const nf = new Intl.NumberFormat('ar-SY-u-nu-latn');
  const n = (x) => nf.format(+x || 0);

  class SaerWidget extends HTMLElement {
    constructor() { super(); this.root = this.attachShadow({ mode: 'open' }); }
    async connectedCallback() {
      this.root.innerHTML = `<style>
        :host{display:block;direction:rtl;color:inherit}
        .g{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
        .k span{display:block;font-size:12px;opacity:.7}.k b{font-size:22px}.k small{display:block;font-size:11px;opacity:.6}
        svg{width:100%;height:46px;margin-top:10px;display:block}
        a{color:inherit;font-size:12px;opacity:.8}
        .m{opacity:.65;font-size:13px}
      </style><div class="m">جارٍ التحميل…</div>`;
      try {
        const h = { Accept: 'application/json' };
        if (window.__GRAV_API_TOKEN) h.Authorization = `Bearer ${window.__GRAV_API_TOKEN}`;
        const r = await fetch(api('/saer-core/summary'), { headers: h, credentials: 'same-origin' });
        if (!r.ok) throw new Error(r.status);
        const d = (await r.json()).data;
        const s = d.series, max = Math.max(...s.map((x) => x.visitors), 1), W = 280, H = 46;
        const pts = s.map((x, i) => `${W - (i * W) / Math.max(s.length - 1, 1)},${H - 4 - (x.visitors / max) * (H - 8)}`).join(' ');
        const k = (l, t, w) => `<div class="k"><span>${l}</span><b>${n(t)}</b><small>7 أيام: ${n(w)}</small></div>`;
        this.root.querySelector('.m').outerHTML = `<div class="g">${k('زوار اليوم', d.today.visitors, d.week.visitors)}
          ${k('زيارات اليوم', d.today.views, d.week.views)}${k('تحميلات اليوم', d.today.downloads, d.week.downloads)}</div>
          <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="الزوار في آخر 14 يوماً"><polyline points="${pts}" fill="none" stroke="#7B3FE4" stroke-width="2"/></svg>
          <a href="${(window.__GRAV_CONFIG__ && window.__GRAV_CONFIG__.basePath) || '/admin'}/plugin/saer-core">كل الإحصائيات ←</a>`;
      } catch (e) {
        this.root.querySelector('.m').textContent = 'تعذّر جلب الإحصائيات.';
      }
    }
  }
  customElements.define(TAG, SaerWidget);
})();
