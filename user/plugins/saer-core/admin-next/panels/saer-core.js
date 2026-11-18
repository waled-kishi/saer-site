// "ملفات الصفحة" context panel in the page editor (tag grav-saer-core--panel, attribute "route").
// Lists the page's PDF / Word / EPUB / ZIP files and downloads them with the admin's token,
// so drafts (an unpublished booklet) can be reviewed before publishing.
(() => {
  const TAG = 'grav-saer-core--panel';
  if (customElements.get(TAG)) return;

  const api = (p) => `${window.__GRAV_API_SERVER_URL || ''}${window.__GRAV_API_PREFIX || '/api/v1'}${p}`;
  const headers = () => (window.__GRAV_API_TOKEN ? { Authorization: `Bearer ${window.__GRAV_API_TOKEN}` } : {});
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const size = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} ميغابايت` : `${Math.max(1, Math.round(b / 1024))} كيلوبايت`);
  const KIND = { pdf: 'PDF', docx: 'Word', doc: 'Word', odt: 'ODT', epub: 'EPUB', zip: 'ZIP', rtf: 'RTF', txt: 'نص' };

  class Panel extends HTMLElement {
    static get observedAttributes() { return ['route']; }
    connectedCallback() {
      this.root = this.root || this.attachShadow({ mode: 'open' });
      this.load();
    }
    attributeChangedCallback() { if (this.root) this.load(); }

    async load() {
      const route = this.getAttribute('route') || '';
      this.root.innerHTML = `${this.css()}<div class="p muted">جارٍ التحميل…</div>`;
      try {
        const r = await fetch(api(`/saer-core/files?route=${encodeURIComponent(route)}`), { headers: headers(), credentials: 'same-origin' });
        const body = await r.json();
        if (!r.ok) throw new Error(body?.message || r.status);
        this.render(body.data || body);
      } catch (e) {
        this.root.innerHTML = `${this.css()}<div class="p err">تعذّر جلب الملفات: ${esc(e.message)}</div>`;
      }
    }

    render(d) {
      const state = d.published
        ? (d.status === 'soon' ? 'منشورة، والحالة «قريباً» (الملفات مخفية عن الزوار)' : 'منشورة')
        : 'غير منشورة (الملفات مخفية عن الزوار)';
      const rows = (d.files || []).map((f) => `
        <li>
          <div><strong>${esc(f.name)}</strong><span class="muted">${KIND[f.ext] || f.ext} · ${size(f.size)} · ${new Date(f.modified * 1000).toLocaleDateString('ar-SY')}</span></div>
          <button type="button" data-name="${esc(f.name)}">تحميل</button>
        </li>`).join('');
      this.root.innerHTML = `${this.css()}<div class="p">
        <h2>ملفات الصفحة</h2>
        <p class="muted">${esc(d.title)} — ${state}</p>
        ${rows ? `<ul>${rows}</ul>` : '<p class="muted">لا توجد ملفات PDF أو Word في هذه الصفحة.</p>'}
        <p class="note">تُحمَّل الملفات هنا حتى لو كانت الصفحة غير منشورة، للمراجعة قبل النشر.</p>
      </div>`;
      this.root.querySelectorAll('button[data-name]').forEach((b) => b.addEventListener('click', () => this.download(d.route, b.dataset.name, b)));
    }

    async download(route, name, btn) {
      const label = btn.textContent;
      btn.disabled = true;
      btn.textContent = '…';
      try {
        const r = await fetch(api(`/saer-core/file?route=${encodeURIComponent(route)}&name=${encodeURIComponent(name)}`),
          { headers: headers(), credentials: 'same-origin' });
        if (!r.ok) throw new Error(r.status);
        const url = URL.createObjectURL(await r.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (e) {
        alert('تعذّر التحميل');
      } finally {
        btn.disabled = false;
        btn.textContent = label;
      }
    }

    css() {
      return `<style>
        :host{display:block;direction:rtl;font-family:inherit;color:inherit}
        .p{padding:20px;display:flex;flex-direction:column;gap:12px}
        h2{margin:0;font-size:18px}
        ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
        li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid rgba(127,127,127,.25);border-radius:10px}
        li div{display:flex;flex-direction:column;gap:2px;min-width:0}
        li strong{font-size:14px;word-break:break-all}
        .muted{opacity:.7;font-size:13px;margin:0}
        .note{font-size:12px;opacity:.6;margin:0}
        .err{color:#d9534f}
        button{flex:none;font:inherit;font-size:13px;padding:6px 14px;border-radius:8px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer}
        button:disabled{opacity:.5}
      </style>`;
    }
  }
  customElements.define(TAG, Panel);
})();
