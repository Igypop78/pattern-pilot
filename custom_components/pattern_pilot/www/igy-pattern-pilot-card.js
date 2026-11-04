/*
 * Igy Pattern Pilot Card – priebeh učenia a čo Pattern Pilot vidí v dome.
 * Súčasť integrácie Pattern Pilot (registruje sa sama), dáta cez WebSocket pattern_pilot/overview.
 *
 *   type: custom:igy-pattern-pilot-card
 *   title: Pattern Pilot        # voliteľné
 *   rhythm: true                # rytmus dňa (ručné akcie po hodinách)
 *   actors: true                # kto ovláda dom
 *   top: true                   # najčastejšie ručne
 *   recent: true                # práve sa stalo
 */
(function () {
  'use strict';
  let LANG = String((typeof document !== 'undefined' && document.documentElement && document.documentElement.lang) || (typeof navigator !== 'undefined' && navigator.language) || 'en').slice(0, 2).toLowerCase();
  const setLang = (h) => { const l = h && ((h.locale && h.locale.language) || h.language); if (l) LANG = String(l).slice(0, 2).toLowerCase(); };
  const _ = (s, ...a) => { let r = LANG === 'sk' ? s : (EN[s] != null ? EN[s] : s); a.forEach((v, i) => { r = r.split('{' + i + '}').join(v); }); return r; };
  const EN = {
    'Zbiera dáta': 'Collecting data',
    'Pripravený': 'Ready',
    'Deň': 'Day',
    'z {0}': 'of {0}',
    'Návrhy od {0}': 'Suggestions from {0}',
    'Dosť dát na analýzu': 'Enough data for analysis',
    'Návrhy automatizácií prídu v ďalšej verzii.': 'Automation suggestions arrive in the next version.',
    '{0} udalostí': '{0} events',
    '{0} z {1} senzorov naučených': '{0} of {1} sensors learned',
    '{0} počítadiel z Energy panelu': '{0} Energy dashboard meters',
    'Udalosti dnes': 'Events today',
    'Ručne dnes': 'Manual today',
    'Zmeny senzorov': 'Sensor changes',
    'za 7 dní': 'last 7 days',
    'Rytmus dňa': 'Daily rhythm',
    'ručné akcie po hodinách': 'manual actions per hour',
    'dnes': 'today',
    'priemer {0} dní': '{0}-day average',
    'Kto ovláda dom': 'Who runs the house',
    'za 7 dní, zmeny zariadení': 'last 7 days, device changes',
    'ty (aplikácia, hlas)': 'you (app, voice)',
    'vypínače': 'switches',
    'automatizácie': 'automations',
    'iné integrácie': 'other integrations',
    'vylúčení': 'excluded',
    'Najčastejšie ručne': 'Most often by hand',
    'kandidáti na automatizáciu': 'candidates for automation',
    'Práve sa stalo': 'Just happened',
    'Zatiaľ nič.': 'Nothing yet.',
    'zapnuté': 'on', 'vypnuté': 'off', 'otvorené': 'open', 'zatvorené': 'closed', 'doma': 'home', 'preč': 'away',
    'zamknuté': 'locked', 'odomknuté': 'unlocked',
    'aktivované': 'activated',
    'jas': 'brightness',
    'stúpa': 'rising', 'klesá': 'falling', 'spotreba začala': 'consumption started', 'spotreba klesla': 'consumption dropped',
    'spustená': 'triggered',
    'zrušené': 'overridden',
    'Pattern Pilot nie je nainštalovaný alebo nebeží.': 'Pattern Pilot is not installed or not running.',
    'Načítavam…': 'Loading…',
    'Nadpis': 'Title',
    'Zobraziť': 'Show',
    'Priebeh učenia a čo Pattern Pilot vidí v dome.': 'Learning progress and what Pattern Pilot sees in your home.',
    'teraz': 'now',
    'pred {0} min': '{0} min ago'
  };

  const VERSION = '0.1.2';
  const C = { human: '#0a84ff', physical: '#ff9f0a', automation: '#30d158', system: '#8e8e93', external: '#bf5af2' };
  const ACTOR_ORDER = ['human', 'physical', 'automation', 'system', 'external'];
  const ACTOR_T = { human: 'ty (aplikácia, hlas)', physical: 'vypínače', automation: 'automatizácie', system: 'iné integrácie', external: 'vylúčení' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 17l4-4.5 3.5 2.5 4-5.5 3 2"/><circle cx="3.5" cy="17" r="1.4" fill="currentColor"/><circle cx="7.5" cy="12.5" r="1.4" fill="currentColor"/><circle cx="11" cy="15" r="1.4" fill="currentColor"/><circle cx="15" cy="9.5" r="1.4" fill="currentColor"/><path d="M18 6.5l3-1-1 3"/></svg>';
  const ACT_ICON = {
    human: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-3.3 0-8 1.7-8 5v1h16v-1c0-3.3-4.7-5-8-5z"/></svg>',
    physical: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm3 5v6h4V7h-4z"/></svg>',
    automation: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>',
    system: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M4 6h16v10H4zM2 18h20v2H2z"/></svg>',
    external: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M5 5h6v2H7v10h10v-4h2v6H5zM13 3h8v8l-3-3-5 5-2-2 5-5z"/></svg>',
    device: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4l4 6H8z"/></svg>'
  };

  const CSS = `
    ha-card { padding: 12px 16px 16px; overflow: hidden; }
    .hl { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--secondary-text-color); letter-spacing: .02em; margin-bottom: 10px; }
    .hl svg { width: 18px; height: 18px; }
    .chip { margin-left: auto; font-size: 11.5px; font-weight: 600; padding: 3px 9px; border-radius: 99px; letter-spacing: 0; }
    .chip.collecting { color: #0a84ff; background: rgba(10,132,255,.14); }
    .chip.ready { color: #30d158; background: rgba(48,209,88,.15); }
    .box { border-radius: 16px; background: var(--hc-surface, rgba(127,127,127,.1)); box-shadow: inset 0 0 0 1px var(--hc-surface-line, transparent); padding: 12px 14px; }
    .box + .box, .tiles + .box, .box + .tiles { margin-top: 8px; }
    .st { display: flex; align-items: baseline; gap: 8px; font-size: 13px; font-weight: 600; color: var(--primary-text-color); margin-bottom: 10px; }
    .st small { font-weight: 400; color: var(--secondary-text-color); font-size: 12px; }
    /* priebeh */
    .p1 { display: flex; align-items: flex-end; gap: 12px; }
    .big { font-size: 34px; font-weight: 600; line-height: 1; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
    .big small { font-size: 15px; font-weight: 500; color: var(--secondary-text-color); margin-left: 4px; }
    .p1 .rt { margin-left: auto; text-align: right; font-size: 12.5px; color: var(--secondary-text-color); line-height: 1.35; }
    .p1 .rt b { display: block; font-size: 15px; font-weight: 600; color: var(--primary-text-color); }
    .bar { position: relative; height: 10px; border-radius: 99px; background: rgba(127,127,127,.2); overflow: hidden; margin: 12px 0 10px; }
    .bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px; background: linear-gradient(90deg, #0a84ff, #30d158); transition: width .6s ease; }
    .bar i::after { content: ''; position: absolute; inset: 0; background-image: repeating-linear-gradient(-45deg, rgba(255,255,255,.18) 0 6px, transparent 6px 12px); background-size: 34px 34px; animation: flow 1.6s linear infinite; }
    .bar.done i::after { display: none; }
    @keyframes flow { to { background-position: 34px 0; } }
    @media (prefers-reduced-motion: reduce) { .bar i::after { animation: none; } }
    .facts { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
    .facts b { color: var(--primary-text-color); font-weight: 500; }
    /* dlaždice */
    .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .tile { border-radius: 16px; background: var(--hc-surface, rgba(127,127,127,.1)); box-shadow: inset 0 0 0 1px var(--hc-surface-line, transparent); padding: 10px 12px; min-width: 0; }
    .tile b { display: block; font-size: 22px; font-weight: 600; color: var(--primary-text-color); font-variant-numeric: tabular-nums; line-height: 1.15; }
    .tile span { display: block; font-size: 11.5px; color: var(--secondary-text-color); line-height: 1.3; }
    /* rytmus */
    .rh { position: relative; height: 92px; display: grid; grid-template-columns: repeat(24, 1fr); gap: 3px; align-items: end; }
    .rh .h { position: relative; height: 100%; display: flex; align-items: flex-end; justify-content: center; }
    .rh .avg { position: absolute; left: 0; right: 0; bottom: 0; border-radius: 4px 4px 2px 2px; background: rgba(127,127,127,.22); }
    .rh .tod { position: relative; width: 62%; border-radius: 3px 3px 1px 1px; background: #0a84ff; min-height: 0; }
    .rh .h.now .tod { background: #30d158; }
    .rh .h.now::after { content: ''; position: absolute; left: 50%; bottom: -6px; width: 4px; height: 4px; margin-left: -2px; border-radius: 50%; background: #30d158; }
    .ax { display: grid; grid-template-columns: repeat(4, 1fr) auto; font-size: 10.5px; color: var(--secondary-text-color); margin-top: 8px; font-variant-numeric: tabular-nums; }
    .lg { display: flex; gap: 14px; font-size: 11.5px; color: var(--secondary-text-color); margin-top: 8px; }
    .lg i { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
    /* kto */
    .seg { display: flex; height: 12px; border-radius: 99px; overflow: hidden; background: rgba(127,127,127,.2); gap: 2px; }
    .seg i { display: block; height: 100%; }
    .who { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px 12px; margin-top: 10px; font-size: 12.5px; color: var(--secondary-text-color); }
    .who div { display: flex; align-items: center; gap: 6px; min-width: 0; }
    .who svg { width: 15px; height: 15px; flex: none; }
    .who b { margin-left: auto; color: var(--primary-text-color); font-weight: 500; font-variant-numeric: tabular-nums; }
    /* top */
    .tr { display: grid; grid-template-columns: 1fr 70px 30px; gap: 10px; align-items: center; min-height: 34px; border-top: 1px solid rgba(127,127,127,.14); font-size: 13.5px; cursor: pointer; }
    .tr:first-of-type { border-top: 0; }
    .tr .n { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--primary-text-color); }
    .tr .n small { color: var(--secondary-text-color); font-size: 11.5px; margin-left: 4px; }
    .tr .mb { height: 5px; border-radius: 9px; background: rgba(127,127,127,.18); overflow: hidden; }
    .tr .mb i { display: block; height: 100%; border-radius: 9px; background: #ff9f0a; }
    .tr .c { text-align: right; font-variant-numeric: tabular-nums; color: var(--primary-text-color); font-weight: 500; }
    /* feed */
    .ev { display: grid; grid-template-columns: 40px 22px 1fr; gap: 8px; align-items: center; min-height: 32px; font-size: 13px; cursor: pointer; }
    .ev + .ev { border-top: 1px solid rgba(127,127,127,.12); }
    .ev .t { font-size: 11.5px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
    .ev .a { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
    .ev .a svg { width: 13px; height: 13px; color: #fff; }
    .ev .x { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--primary-text-color); }
    .ev .x small { color: var(--secondary-text-color); margin-left: 4px; }
    .ev .x .ov { color: #ff6961; font-size: 11px; margin-left: 4px; }
    .empty, .err { font-size: 13px; color: var(--secondary-text-color); padding: 6px 2px; }
  `;

  class IgyPatternPilotCard extends HTMLElement {
    static getConfigElement() { return document.createElement('igy-pattern-pilot-card-editor'); }
    static getStubConfig() { return {}; }
    setConfig(c) { this._cfg = Object.assign({ rhythm: true, actors: true, top: true, recent: true }, c || {}); if (this._data) this._render(); }
    set hass(h) {
      setLang(h); const first = !this._hass; this._hass = h;
      if (first) this._load(); else if (this._data) this._render();
    }
    connectedCallback() { if (!this._t) this._t = setInterval(() => this._load(), 60000); if (this._hass && !this._data) this._load(); }
    disconnectedCallback() { clearInterval(this._t); this._t = null; }
    getCardSize() { return 8; }
    getGridOptions() { return { columns: 12, min_columns: 6 }; }

    async _load() {
      if (!this._hass || this._busy) return;
      this._busy = true;
      try { this._data = await this._hass.callWS({ type: 'pattern_pilot/overview' }); this._err = null; }
      catch (e) { this._err = e; }
      this._busy = false; this._render();
    }

    _loc() { return (this._hass.locale && this._hass.locale.language) || LANG; }
    _n(v, d = 0) { return Number(v || 0).toLocaleString(this._loc(), { minimumFractionDigits: d, maximumFractionDigits: d }); }
    _name(id) {
      const s = this._hass.states[id];
      let n = (s && s.attributes.friendly_name) || id;
      return n;
    }
    _area(id) {
      const e = this._hass.entities && this._hass.entities[id]; if (!e) return '';
      let a = e.area_id; if (!a && e.device_id && this._hass.devices && this._hass.devices[e.device_id]) a = this._hass.devices[e.device_id].area_id;
      return (a && this._hass.areas && this._hass.areas[a] && this._hass.areas[a].name) || '';
    }
    _time(ts) { return new Date(ts * 1000).toLocaleTimeString(this._loc(), { hour: '2-digit', minute: '2-digit' }); }
    _date(iso) { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d).toLocaleDateString(this._loc(), { day: 'numeric', month: 'numeric' }); }
    _stateText(v) {
      const map = { on: 'zapnuté', off: 'vypnuté', open: 'otvorené', closed: 'zatvorené', home: 'doma', not_home: 'preč', locked: 'zamknuté', unlocked: 'odomknuté', activated: 'aktivované' };
      return map[v] ? _(map[v]) : v;
    }
    _evText(e) {
      const name = esc(this._name(e.entity_id));
      if (e.kind === 'run') return `${name} <small>${_('spustená')}</small>`;
      if (e.kind === 'signal') {
        const s = this._hass.states[e.entity_id], u = (s && s.attributes.unit_of_measurement) || '';
        const counter = e.old === 'counter';
        const what = e.new === 'rise' ? (counter ? _('spotreba začala') : _('stúpa')) : (counter ? _('spotreba klesla') : _('klesá'));
        const arrow = e.new === 'rise' ? '↑' : '↓';
        const val = !counter && e.value != null ? ` ${arrow} ${this._n(e.value, e.value < 10 ? 1 : 0)}${e.old === 'power' ? ' W' : u ? ' ' + esc(u) : ''}` : '';
        return `${name} <small>${what}${val}</small>`;
      }
      if (e.kind === 'attr') {
        const [k, v] = String(e.new || '').split(':');
        if (k === 'brightness' && !isNaN(+v)) return `${name} <small>${_('jas')} ${Math.round(+v / 2.55)} %</small>`;
        return `${name} <small>${esc(k)} → ${esc(v)}</small>`;
      }
      return `${name} <small>→ ${esc(this._stateText(e.new))}</small>${e.override ? `<span class="ov">${_('zrušené')}</span>` : ''}`;
    }

    _render() {
      if (!this._hass || !this._cfg) return;
      if (!this.shadowRoot) {
        this.attachShadow({ mode: 'open' });
        this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card><div id="c"></div></ha-card>`;
        this.shadowRoot.querySelector('ha-card').addEventListener('click', (ev) => {
          const el = ev.target.closest('[data-more]'); if (el && el.dataset.more) this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId: el.dataset.more }, bubbles: true, composed: true }));
        });
      }
      const c = this._cfg, d = this._data;
      let h = `<div class="hl">${ICON}<span>${esc(c.title || 'Pattern Pilot')}</span>`;
      if (!d) {
        h += `</div><div class="${this._err ? 'err' : 'empty'}">${this._err ? _('Pattern Pilot nie je nainštalovaný alebo nebeží.') : _('Načítavam…')}</div>`;
        return this._set(h);
      }
      const ready = d.status === 'ready';
      h += `<span class="chip ${ready ? 'ready' : 'collecting'}">${ready ? _('Pripravený') : _('Zbiera dáta')}</span></div>`;

      // priebeh učenia
      const day = Math.min(d.days + 1, d.days_needed), pct = ready ? 100 : Math.max(3, (d.days + 0.5) / d.days_needed * 100);
      h += `<div class="box"><div class="p1"><div class="big">${ready ? this._n(d.days) : `${_('Deň')} ${day}`}<small>${ready ? '' : _('z {0}', d.days_needed)}</small></div>`
        + `<div class="rt">${ready ? `<b>${_('Dosť dát na analýzu')}</b>${_('Návrhy automatizácií prídu v ďalšej verzii.')}` : d.ready_from ? `<b>${_('Návrhy od {0}', this._date(d.ready_from))}</b>` : ''}</div></div>`
        + `<div class="bar${ready ? ' done' : ''}"><i style="width:${pct.toFixed(1)}%"></i></div>`
        + `<div class="facts"><span>${_('{0} udalostí', `<b>${this._n(d.events_total)}</b>`)}</span>`
        + `<span>${_('{0} z {1} senzorov naučených', `<b>${this._n(d.sensors_ready)}</b>`, this._n(d.sensors_watched))}</span>`
        + (d.energy_counters ? `<span>${_('{0} počítadiel z Energy panelu', `<b>${d.energy_counters}</b>`)}</span>` : '')
        + `<span><b>${this._n(d.db_mb, 1)}</b> MB</span></div></div>`;

      // dlaždice
      h += `<div class="tiles"><div class="tile"><b>${this._n(d.events_today)}</b><span>${_('Udalosti dnes')}</span></div>`
        + `<div class="tile"><b>${this._n(d.manual_today)}</b><span>${_('Ručne dnes')}</span></div>`
        + `<div class="tile"><b>${this._n(d.signals_week)}</b><span>${_('Zmeny senzorov')}<br>${_('za 7 dní')}</span></div></div>`;

      // rytmus dňa
      if (c.rhythm) {
        const t = d.hourly_today || [], a = d.hourly_avg || [], mx = Math.max(1, ...t, ...a), now = new Date().getHours();
        h += `<div class="box"><div class="st">${_('Rytmus dňa')}<small>${_('ručné akcie po hodinách')}</small></div><div class="rh">`
          + t.map((v, i) => `<div class="h${i === now ? ' now' : ''}" title="${i}:00 · ${v}${a.length ? ' / ⌀ ' + this._n(a[i], 1) : ''}">${a.length ? `<div class="avg" style="height:${(a[i] / mx * 100).toFixed(1)}%"></div>` : ''}<div class="tod" style="height:${(v / mx * 100).toFixed(1)}%"></div></div>`).join('')
          + `</div><div class="ax"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>`
          + `<div class="lg"><span><i style="background:#0a84ff"></i>${_('dnes')}</span>${a.length ? `<span><i style="background:rgba(127,127,127,.35)"></i>${_('priemer {0} dní', d.hourly_days)}</span>` : ''}</div></div>`;
      }

      // kto ovláda dom
      if (c.actors) {
        const acts = d.actors || {}, tot = ACTOR_ORDER.reduce((s, k) => s + (acts[k] || 0), 0);
        if (tot) {
          h += `<div class="box"><div class="st">${_('Kto ovláda dom')}<small>${_('za 7 dní, zmeny zariadení')}</small></div><div class="seg">`
            + ACTOR_ORDER.filter((k) => acts[k]).map((k) => `<i style="width:${(acts[k] / tot * 100).toFixed(2)}%;background:${C[k]}"></i>`).join('') + `</div><div class="who">`
            + ACTOR_ORDER.filter((k) => acts[k]).map((k) => `<div><span style="color:${C[k]}">${ACT_ICON[k]}</span>${_(ACTOR_T[k])}<b>${Math.round(acts[k] / tot * 100)} %</b></div>`).join('') + `</div></div>`;
        }
      }

      // najčastejšie ručne
      if (c.top && d.top && d.top.length) {
        const mx = Math.max(...d.top.map((x) => x.count));
        h += `<div class="box"><div class="st">${_('Najčastejšie ručne')}<small>${_('kandidáti na automatizáciu')}</small></div>`
          + d.top.map((x) => { const ar = this._area(x.entity_id); return `<div class="tr" data-more="${esc(x.entity_id)}"><div class="n">${esc(this._name(x.entity_id))}${ar ? `<small>${esc(ar)}</small>` : ''}</div><div class="mb"><i style="width:${(x.count / mx * 100).toFixed(0)}%"></i></div><div class="c">${x.count}×</div></div>`; }).join('') + `</div>`;
      }

      // práve sa stalo
      if (c.recent) {
        const ev = (d.recent || []).slice(0, 8);
        h += `<div class="box"><div class="st">${_('Práve sa stalo')}</div>`
          + (ev.length ? ev.map((e) => { const k = e.kind === 'signal' ? 'device' : e.actor; const col = C[e.actor] || '#8e8e93';
            return `<div class="ev" data-more="${esc(e.entity_id)}"><span class="t">${this._time(e.ts)}</span><span class="a" style="background:${e.kind === 'signal' ? '#64d2ff' : col}">${ACT_ICON[k] || ACT_ICON.device}</span><span class="x">${this._evText(e)}</span></div>`; }).join('')
            : `<div class="empty">${_('Zatiaľ nič.')}</div>`) + `</div>`;
      }
      this._set(h);
    }
    _set(h) { const box = this.shadowRoot.getElementById('c'); if (box.__h !== h) { box.__h = h; box.innerHTML = h; } }
  }

  class IgyPatternPilotCardEditor extends HTMLElement {
    setConfig(c) { this._cfg = Object.assign({}, c); if (this._hass) this._build(); }
    set hass(h) { setLang(h); const f = !this._hass; this._hass = h; if (f && this._cfg) this._build(); if (this._form) this._form.hass = h; }
    _build() {
      const c = this._cfg, f = document.createElement('ha-form'); this._form = f;
      f.hass = this._hass;
      f.data = { title: c.title || '', rhythm: c.rhythm !== false, actors: c.actors !== false, top: c.top !== false, recent: c.recent !== false };
      f.schema = [{ name: 'title', selector: { text: {} } },
        { name: 'rhythm', selector: { boolean: {} } }, { name: 'actors', selector: { boolean: {} } },
        { name: 'top', selector: { boolean: {} } }, { name: 'recent', selector: { boolean: {} } }];
      const L = { title: _('Nadpis'), rhythm: _('Rytmus dňa'), actors: _('Kto ovláda dom'), top: _('Najčastejšie ručne'), recent: _('Práve sa stalo') };
      f.computeLabel = (x) => L[x.name] || x.name;
      f.addEventListener('value-changed', (e) => {
        e.stopPropagation(); const v = e.detail.value, out = { type: 'custom:igy-pattern-pilot-card' };
        if (v.title) out.title = v.title;
        ['rhythm', 'actors', 'top', 'recent'].forEach((k) => { if (v[k] === false) out[k] = false; });
        this._cfg = out; this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: out }, bubbles: true, composed: true }));
      });
      this.innerHTML = ''; this.appendChild(f);
    }
  }

  // Karta sa načítava cez extra_module_url; definujeme ju až keď je HA pripravený
  // (inak „Custom element not found“ a nekonečné koliesko – rovnaké riešenie ako v AI Energy).
  const register = () => {
    const reg = window.customElements;
    if (!reg.get('igy-pattern-pilot-card-editor')) reg.define('igy-pattern-pilot-card-editor', IgyPatternPilotCardEditor);
    if (!reg.get('igy-pattern-pilot-card')) reg.define('igy-pattern-pilot-card', IgyPatternPilotCard);
  };
  if (window.__haScopedRegistryReady || customElements.get('home-assistant') || !document.querySelector('home-assistant')) {
    register();
  } else {
    let done = false;
    const once = () => { if (!done) { done = true; register(); } };
    customElements.whenDefined('home-assistant').then(() => setTimeout(once, 0));
    setTimeout(once, 10000);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === 'igy-pattern-pilot-card'))
    window.customCards.push({ type: 'igy-pattern-pilot-card', name: 'Igy Pattern Pilot Card', description: _('Priebeh učenia a čo Pattern Pilot vidí v dome.'), preview: false, documentationURL: 'https://github.com/Igypop78/pattern-pilot' });
  console.info('%c IGY-PATTERN-PILOT-CARD %c ' + VERSION + ' ', 'background:#30d158;color:#000;border-radius:3px 0 0 3px', 'background:#333;color:#fff;border-radius:0 3px 3px 0');
})();
