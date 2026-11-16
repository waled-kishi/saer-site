// saer-core statistics page for Admin2 (component page). Reads /api/v1/saer-core/*.
(() => {
  const TAG = window.__GRAV_PAGE_TAG || 'saer-core-page';
  if (customElements.get(TAG)) return;

  const api = (path) => `${window.__GRAV_API_SERVER_URL || ''}${window.__GRAV_API_PREFIX || '/api/v1'}${path}`;
  const headers = () => {
    const h = { Accept: 'application/json' };
    if (window.__GRAV_API_TOKEN) h.Authorization = `Bearer ${window.__GRAV_API_TOKEN}`;
    return h;
  };
  const nf = new Intl.NumberFormat('ar-SY-u-nu-latn');
  const n = (x) => nf.format(+x || 0);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const DEVICES = { mobile: 'موبايل', desktop: 'كمبيوتر', tablet: 'تابلت' };
  const RANGES = [[1, 'اليوم'], [7, '7 أيام'], [30, '30 يوماً'], [90, '3 أشهر'], [365, 'سنة']];

  const CSS = `
  :host{display:block;direction:rtl;font-family:inherit;color:inherit}
  *{box-sizing:border-box}
  .wrap{display:flex;flex-direction:column;gap:20px;padding:4px 0 40px}
  .bar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}
  .ranges{display:flex;flex-wrap:wrap;gap:6px}
  button,.btn{font:inherit;cursor:pointer;border:1px solid rgba(127,127,127,.35);background:transparent;color:inherit;border-radius:8px;padding:6px 12px;font-size:14px}
  button[aria-pressed=true]{background:#7B3FE4;border-color:#7B3FE4;color:#fff}
  button:focus-visible{outline:2px solid #C99A45;outline-offset:2px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
  .card{border:1px solid rgba(127,127,127,.25);border-radius:12px;padding:16px;background:rgba(127,127,127,.06)}
  .kpi b{display:block;font-size:30px;font-weight:700;line-height:1.2;margin-top:4px}
  .kpi span{font-size:13px;opacity:.75}
  .kpi small{display:block;font-size:12px;opacity:.65;margin-top:4px}
  h2{font-size:16px;margin:0 0 12px}
  .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th,td{text-align:right;padding:7px 6px;border-bottom:1px solid rgba(127,127,127,.18);vertical-align:top}
  th{font-weight:600;opacity:.75;font-size:12px}
  td.num,th.num{text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}
  .rows{display:flex;flex-direction:column;gap:8px}
  .row{display:grid;grid-template-columns:minmax(90px,38%) 1fr auto;align-items:center;gap:10px;font-size:14px}
  .track{height:10px;border-radius:6px;background:rgba(127,127,127,.15);overflow:hidden}
  .fill{height:100%;background:#7B3FE4;border-radius:6px}
  .fill.gold{background:#C99A45}
  .muted{opacity:.65;font-size:13px}
  .chart svg{width:100%;height:180px;display:block}
  .legend{display:flex;gap:16px;font-size:12px;margin-top:6px}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-left:6px;vertical-align:middle}
  .file{border-top:1px solid rgba(127,127,127,.2);padding-top:12px;margin-top:12px}
  .file:first-of-type{border-top:0;margin-top:0;padding-top:0}
  .file h3{font-size:15px;margin:0 0 4px}
  .mini{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:10px}
  .mini h4{font-size:12px;margin:0 0 6px;opacity:.75;font-weight:600}
  .err{color:#d9534f}
  a{color:inherit}
  .scroll{overflow-x:auto}
  .note{font-size:12px;opacity:.65;line-height:1.7}
  `;

  class SaerStats extends HTMLElement {
    constructor() { super(); this.days = 30; this.root = this.attachShadow({ mode: 'open' }); }
    connectedCallback() { this.load(); }

    async load() {
      this.render('<p class="muted">جارٍ التحميل…</p>');
      try {
        const r = await fetch(api(`/saer-core/stats?days=${this.days}`), { headers: headers(), credentials: 'same-origin' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        this.data = (await r.json()).data;
        this.render(this.view());
      } catch (e) {
        this.render(`<p class="err">تعذّر جلب الإحصائيات (${esc(e.message)}).</p>`);
      }
    }

    async exportCsv(type) {
      const r = await fetch(api(`/saer-core/export?type=${type}&days=${this.days}`), { headers: headers(), credentials: 'same-origin' });
      if (!r.ok) { alert('تعذّر التصدير'); return; }
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `saer-${type}-${this.days}d.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }

    render(body) {
      const ranges = RANGES.map(([d, l]) => `<button type="button" data-days="${d}" aria-pressed="${d === this.days}">${l}</button>`).join('');
      this.root.innerHTML = `<style>${CSS}</style><div class="wrap">
        <div class="bar"><div class="ranges" role="group" aria-label="المدة">${ranges}</div>
          <div class="ranges"><button type="button" data-export="people">تصدير بيانات المحمّلين</button>
          <button type="button" data-export="downloads">تصدير التحميلات</button>
          <button type="button" data-export="views">تصدير الزيارات</button></div></div>
        ${body}</div>`;
      this.root.querySelectorAll('[data-days]').forEach((b) => b.addEventListener('click', () => { this.days = +b.dataset.days; this.load(); }));
      this.root.querySelectorAll('[data-export]').forEach((b) => b.addEventListener('click', () => this.exportCsv(b.dataset.export)));
    }

    bars(rows, key = 'n', label = 'label', gold = false) {
      if (!rows || !rows.length) return '<p class="muted">لا بيانات بعد.</p>';
      const max = Math.max(...rows.map((r) => +r[key] || 0), 1);
      return `<div class="rows">${rows.map((r) => `<div class="row"><span>${esc(r[label] || '—')}</span>
        <div class="track"><div class="fill${gold ? ' gold' : ''}" style="width:${Math.round(((+r[key] || 0) / max) * 100)}%"></div></div>
        <b class="num">${n(r[key])}</b></div>`).join('')}</div>`;
    }

    chart(series) {
      if (!series.length) return '';
      const W = 800, H = 170, pad = 4;
      const max = Math.max(...series.map((s) => Math.max(s.visitors, s.downloads)), 1);
      const bw = (W - pad * 2) / series.length;
      const bars = series.map((s, i) => {
        const h = (s.visitors / max) * (H - 20);
        const dh = (s.downloads / max) * (H - 20);
        const x = W - pad - (i + 1) * bw; // right-to-left
        return `<g><title>${s.day}: ${n(s.visitors)} زائر، ${n(s.views)} زيارة، ${n(s.downloads)} تحميل</title>
          <rect x="${x + bw * 0.12}" y="${H - h}" width="${bw * 0.5}" height="${h}" rx="2" fill="#7B3FE4"/>
          <rect x="${x + bw * 0.62}" y="${H - dh}" width="${bw * 0.26}" height="${dh}" rx="2" fill="#C99A45"/></g>`;
      }).join('');
      return `<div class="card chart"><h2>الزوار والتحميلات يومياً</h2>
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="الزوار والتحميلات يومياً">${bars}</svg>
        <div class="legend"><span><i style="background:#7B3FE4"></i>زوار</span><span><i style="background:#C99A45"></i>تحميلات</span>
        <span class="muted">${esc(series[0].day)} ← ${esc(series[series.length - 1].day)}</span></div></div>`;
    }

    view() {
      const d = this.data, t = d.totals;
      const kpi = (label, val, sub = '') => `<div class="card kpi"><span>${label}</span><b>${n(val)}</b>${sub ? `<small>${sub}</small>` : ''}</div>`;
      const pages = d.pages.map((p) => `<tr><td><a href="${esc(p.route)}" target="_blank" rel="noopener">${esc(p.title || p.route)}</a>
        <div class="muted" dir="ltr" style="text-align:right">${esc(p.route)}</div></td><td class="num">${n(p.visitors)}</td><td class="num">${n(p.views)}</td></tr>`).join('');
      const SECTION = { '/': 'الرئيسية', '/programs': 'البرامج', '/lectures': 'الدروس والخطب', '/books': 'الكتب', '/about': 'عن الشيخ', '/articles': 'المقالات', '/courses': 'الدورات' };
      const sections = d.sections.map((s) => ({ ...s, label: SECTION[s.section] || s.section }));
      const files = d.files.length ? d.files.map((f) => `<div class="file">
          <h3>${esc(f.book)}${f.label && f.label !== 'تحميل الكتاب' ? ` · <span class="muted">${esc(f.label)}</span>` : ''}</h3>
          <div class="muted">${n(f.downloads)} تحميل · ${n(f.unique_downloads)} بدون تكرار باليوم · ${n(f.people)} شخص عبّأ النموذج</div>
          <div class="mini"><div><h4>العمر</h4>${this.bars(f.ages, 'n', 'label', true)}</div>
            <div><h4>الجنس</h4>${this.bars(f.genders, 'n', 'label', true)}</div>
            <div><h4>البلد</h4>${this.bars(f.countries.slice(0, 8), 'n', 'label', true)}</div></div></div>`).join('')
        : '<p class="muted">لا تحميلات في هذه المدة بعد.</p>';
      const recent = d.people.recent.length ? `<div class="scroll"><table><thead><tr><th>الوقت</th><th>الاسم</th><th>العمر</th><th>البلد</th><th>الجنس</th><th>الكتاب</th></tr></thead><tbody>
        ${d.people.recent.map((r) => `<tr><td class="num">${esc(r.when)}</td><td>${esc(r.name)}</td><td>${esc(r.age)}</td><td>${esc(r.country)}</td><td>${esc(r.gender)}</td>
        <td>${esc(r.book)}${r.label && r.label !== 'تحميل الكتاب' ? ` · ${esc(r.label)}` : ''}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="muted">لم يعبّئ أحد النموذج في هذه المدة بعد.</p>';
      return `
        <div class="kpis">${kpi('الزوار', t.visitors, 'كل زائر مرة واحدة في اليوم')}${kpi('الزيارات', t.views, 'كل فتح لصفحة')}
          ${kpi('التحميلات', t.downloads, `${n(t.unique_downloads)} بدون تكرار`)}${kpi('نماذج معبّأة', t.forms, 'أشخاص جدد')}</div>
        ${this.chart(d.series)}
        <div class="grid2">
          <div class="card"><h2>الأقسام</h2>${this.bars(sections, 'visitors')}</div>
          <div class="card"><h2>الدول</h2>${this.bars(d.countries.slice(0, 12), 'visitors', 'name')}</div>
          <div class="card"><h2>الأجهزة</h2>${this.bars(d.devices.map((x) => ({ ...x, label: DEVICES[x.device] || x.device })), 'visitors')}</div>
          <div class="card"><h2>من أين جاء الزوار</h2>${this.bars(d.referrers.map((x) => ({ ...x, label: x.ref || 'مباشرة أو غير معروف' })), 'visitors')}</div>
        </div>
        <div class="card"><h2>الصفحات الأكثر زيارة</h2>${d.pages.length ? `<div class="scroll"><table><thead><tr><th>الصفحة</th><th class="num">زوار</th><th class="num">زيارات</th></tr></thead><tbody>${pages}</tbody></table></div>` : '<p class="muted">لا بيانات بعد.</p>'}</div>
        <div class="card"><h2>التحميلات حسب الكتاب</h2>${files}</div>
        <div class="grid2">
          <div class="card"><h2>المحمّلون: العمر</h2>${this.bars(d.people.ages, 'n', 'label', true)}</div>
          <div class="card"><h2>المحمّلون: الجنس</h2>${this.bars(d.people.genders, 'n', 'label', true)}</div>
          <div class="card"><h2>المحمّلون: البلد</h2>${this.bars(d.people.countries.slice(0, 12), 'n', 'label', true)}</div>
        </div>
        <div class="card"><h2>آخر من حمّل</h2>${recent}</div>
        <p class="note">لا يحفظ الموقع عناوين IP ولا يضع كوكيز للعدّ. "الزائر" يُحسب مرة واحدة في اليوم. البلد في الزيارات من قاعدة DB-IP Lite (IP Geolocation by DB-IP)، وفي النموذج من اختيار الشخص. الروبوتات ومحركات البحث لا تُحسب.</p>`;
    }
  }
  customElements.define(TAG, SaerStats);
})();
