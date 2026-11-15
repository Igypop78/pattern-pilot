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
    'mimo HA': 'outside HA',
    'programy zariadení': 'device programs',
    'v aplikácii, na dashboarde alebo hlasom': 'in the app, on a dashboard or by voice',
    'vypínač, ovládač, appka výrobcu – zmena bez príkazu z HA': 'wall switch, remote, vendor app – a change without a command from HA',
    'automatizácie a skripty': 'automations and scripts',
    'zariadenie samo (termostat, vysávač …)': 'the device on its own (thermostat, vacuum …)',
    'iná integrácia poslala príkaz': 'another integration sent a command',
    'vylúčení používatelia (Node-RED …)': 'excluded users (Node-RED …)',
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
    'Návrhy automatizácií, priebeh učenia a čo Pattern Pilot vidí v dome.': 'Automation suggestions, learning progress and what Pattern Pilot sees in your home.',
    'teraz': 'now',
    'Návrhy': 'Suggestions', 'Prehľad': 'Overview', 'Prijaté': 'Accepted', 'Odmietnuté': 'Dismissed',
    '{0} nové návrhy': '{0} new suggestions', '1 nový návrh': '1 new suggestion',
    'Časový návyk': 'Time habit', 'Po A nasleduje B': 'A then B', 'Vylepšenie automatizácie': 'Improve automation',
    'zapnúť': 'turn on', 'vypnúť': 'turn off', 'otvoriť': 'open', 'zatvoriť': 'close', 'aktivovať': 'activate',
    'okolo {0}': 'around {0}', 'v pracovné dni': 'on workdays', 'cez víkend': 'at weekends', ', keď je tma': ' when it is dark',
    'pri „{0}“': 'on “{0}”', 'príchod domov': 'arrives home', 'odchod': 'leaves',
    'Robíš to ručne medzi {0} a {1}': 'You do it by hand between {0} and {1}',
    '{0} z {1} dní': '{0} of {1} days',
    'v spätnom teste 0 zbytočných spustení': 'backtest: 0 needless runs',
    'v spätnom teste {0}× týždenne zbytočne': 'backtest: {0}× a week for nothing',
    'Do 90 s po „{0}“ to urobíš ručne': 'Within 90 s after “{0}” you do it by hand',
    '{0} z {1}×': '{0} of {1}×', 'po {0} % udalostí': 'after {0} % of them',
    'často ju rušíš': 'you often revert it',
    'Po jej zásahu si do 2 min prepol {0} na „{1}“': 'Within 2 min after it ran you switched {0} to “{1}”',
    '{0}× za 14 dní': '{0}× in 14 days',
    'Prijať': 'Accept', 'Upraviť': 'Edit', 'Teraz nie': 'Not now', 'Nikdy': 'Never', 'Otvoriť automatizáciu': 'Open automation',
    'Vyriešené': 'Done', 'Otvoriť': 'Open', 'Vrátiť': 'Undo', 'Obnoviť': 'Restore', 'odložené': 'snoozed', 'nikdy': 'never',
    'Analyzovať teraz': 'Analyse now', 'Analyzujem…': 'Analysing…',
    'Predbežné návrhy – zatiaľ {0} z {1} dní dát, budú presnejšie.': 'Preliminary – {0} of {1} days of data so far, they will get more accurate.',
    'Zatiaľ žiadne návrhy': 'No suggestions yet',
    'Analýza beží každú noc. Môžeš ju spustiť aj teraz.': 'The analysis runs every night. You can also run it now.',
    'Posledná analýza {0}': 'Last analysis {0}',
    'Posledných 14 dní: vzor sa stal · deň bez vzoru · nesledovaný deň': 'Last 14 days: pattern happened · day without it · day not counted',
    'Automatizácia vytvorená': 'Automation created', 'Nepodarilo sa: {0}': 'Failed: {0}',
    'Upraviť vytvorí automatizáciu a otvorí ju v editore': 'Edit creates the automation and opens it in the editor',
    'Zatiaľ nič.': 'Nothing yet.',
    'pred {0} min': '{0} min ago'
  };

  const VERSION = '0.2.0';
  const C = { human: '#0a84ff', physical: '#ff9f0a', automation: '#30d158', system: '#8e8e93', external: '#bf5af2', device: '#64d2ff' };
  const ACTOR_ORDER = ['human', 'physical', 'automation', 'device', 'system', 'external'];
  const ACTOR_T = { human: 'ty (aplikácia, hlas)', physical: 'mimo HA', automation: 'automatizácie', device: 'programy zariadení', system: 'iné integrácie', external: 'vylúčení' };
  const ACTOR_H = { human: 'v aplikácii, na dashboarde alebo hlasom', physical: 'vypínač, ovládač, appka výrobcu – zmena bez príkazu z HA', automation: 'automatizácie a skripty', device: 'zariadenie samo (termostat, vysávač …)', system: 'iná integrácia poslala príkaz', external: 'vylúčení používatelia (Node-RED …)' };
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
    .who { display: grid; grid-template-columns: repeat(auto-fill, minmax(165px, 1fr)); gap: 6px 16px; margin-top: 10px; font-size: 12.5px; color: var(--secondary-text-color); }
    .who div { display: flex; align-items: center; gap: 6px; min-width: 0; }
    .who .l { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .who svg { width: 15px; height: 15px; flex: none; }
    .who b { margin-left: auto; color: var(--primary-text-color); font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
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
    .tabs { display: flex; gap: 6px; flex-wrap: wrap; margin: -2px 0 10px; }
    .tab { font: inherit; font-size: 12.5px; padding: 5px 12px; border-radius: 99px; border: 1px solid rgba(127,127,127,.25); background: none; color: var(--secondary-text-color); cursor: pointer; }
    .tab.on { background: rgba(10,132,255,.14); border-color: rgba(10,132,255,.45); color: #0a84ff; }
    .tab b { font-weight: 600; margin-left: 3px; }
    .chip.new { color: #30d158; background: rgba(48,209,88,.15); }
    .sg { border-radius: 16px; background: var(--hc-surface, rgba(127,127,127,.1)); box-shadow: inset 0 0 0 1px var(--hc-surface-line, transparent); padding: 12px 14px; }
    .sg + .sg { margin-top: 8px; }
    .sg .top { display: flex; gap: 10px; align-items: flex-start; }
    .sg .ic { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; flex: none; }
    .sg .ic svg { width: 18px; height: 18px; }
    .sg .ti { font-size: 14px; font-weight: 500; line-height: 1.4; color: var(--primary-text-color); }
    .sg .tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 99px; margin-top: 4px; }
    .sg .evi { font-size: 12px; color: var(--secondary-text-color); margin: 8px 0 7px; line-height: 1.5; }
    .strip { display: flex; gap: 4px; margin-bottom: 10px; }
    .strip i { width: 14px; height: 14px; border-radius: 4px; background: rgba(127,127,127,.18); }
    .strip i.h { background: #0a84ff; } .strip i.e { background: rgba(10,132,255,.2); }
    .acts { display: flex; gap: 6px; flex-wrap: wrap; }
    .btn { font: inherit; font-size: 12.5px; padding: 5px 12px; border-radius: 99px; border: 1px solid rgba(127,127,127,.3); background: none; color: var(--primary-text-color); cursor: pointer; }
    .btn.pri { background: #0a84ff; border-color: #0a84ff; color: #fff; }
    .btn:disabled { opacity: .5; cursor: default; }
    .note { font-size: 12px; color: var(--secondary-text-color); padding: 8px 12px; border-radius: 12px; background: rgba(255,159,10,.12); margin-bottom: 8px; line-height: 1.45; }
    .foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11.5px; color: var(--secondary-text-color); margin-top: 10px; }
    .foot .btn { margin-left: auto; font-size: 12px; padding: 4px 10px; }
    .lst { display: flex; align-items: center; gap: 10px; min-height: 40px; border-top: 1px solid rgba(127,127,127,.14); font-size: 13px; }
    .lst:first-of-type { border-top: 0; }
    .lst .n { flex: 1; min-width: 0; color: var(--primary-text-color); line-height: 1.35; padding: 6px 0; }
    .lst .n small { display: block; color: var(--secondary-text-color); font-size: 11.5px; }
    .lst .btn { font-size: 12px; padding: 4px 10px; flex: none; }
    .emptybox { text-align: center; padding: 18px 10px; }
    .emptybox b { display: block; font-size: 15px; font-weight: 600; color: var(--primary-text-color); margin-bottom: 4px; }
    .emptybox span { display: block; font-size: 12.5px; color: var(--secondary-text-color); margin-bottom: 12px; }
  `;
  const KIND = {
    time: { t: 'Časový návyk', c: '#ff9f0a', bg: 'rgba(255,159,10,.16)', i: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>' },
    trigger: { t: 'Po A nasleduje B', c: '#bf5af2', bg: 'rgba(191,90,242,.16)', i: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15M13 6l6 6-6 6"/></svg>' },
    improve: { t: 'Vylepšenie automatizácie', c: '#ff453a', bg: 'rgba(255,69,58,.15)', i: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 7h9M18 7h1M5 17h3M12 17h7"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>' }
  };
  const VERB = { on: 'zapnúť', off: 'vypnúť', open: 'otvoriť', closed: 'zatvoriť', activated: 'aktivovať' };

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
      try {
        const [ov, sg] = await Promise.all([
          this._hass.callWS({ type: 'pattern_pilot/overview' }),
          this._hass.callWS({ type: 'pattern_pilot/suggestions' }).catch(() => null)
        ]);
        this._data = ov; this._sug = sg; this._err = null;
      } catch (e) { this._err = e; }
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
          const tb = ev.target.closest('[data-tab]'); if (tb) { this._tab = tb.dataset.tab; this._render(); return; }
          const ac = ev.target.closest('[data-act]'); if (ac) { if (!ac.disabled) this._act(ac.dataset.act, ac.dataset.id); return; }
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
      const items = (this._sug && this._sug.suggestions) || [];
      const fresh = items.filter((x) => x.status === 'new');
      if (!this._tab) this._tab = fresh.length ? 'sug' : 'ov';
      const chip = fresh.length ? `<span class="chip new">${fresh.length === 1 ? _('1 nový návrh') : _('{0} nové návrhy', fresh.length)}</span>`
        : `<span class="chip ${ready ? 'ready' : 'collecting'}">${ready ? _('Pripravený') : _('Zbiera dáta')}</span>`;
      h += chip + `</div>`;
      const acc = items.filter((x) => x.status === 'accepted'), rej = items.filter((x) => x.status === 'rejected' || x.status === 'snoozed');
      const tab = (k, label, n) => `<button class="tab${this._tab === k ? ' on' : ''}" data-tab="${k}">${label}${n ? `<b>${n}</b>` : ''}</button>`;
      h += `<div class="tabs">${tab('sug', _('Návrhy'), fresh.length)}${tab('ov', _('Prehľad'))}${acc.length ? tab('acc', _('Prijaté'), acc.length) : ''}${rej.length ? tab('rej', _('Odmietnuté'), rej.length) : ''}</div>`;
      if (this._tab === 'sug') h += this._renderSuggestions(fresh);
      else if (this._tab === 'acc') h += this._renderList(acc, 'acc');
      else if (this._tab === 'rej') h += this._renderList(rej, 'rej');
      else h += this._renderOverview(d);
      this._set(h);
    }
    _renderOverview(d) {
      const c = this._cfg;
      const ready = d.status === 'ready';
      let h = '';

      // priebeh učenia
      const day = Math.min(d.days + 1, d.days_needed), pct = ready ? 100 : Math.max(3, (d.days + 0.5) / d.days_needed * 100);
      h += `<div class="box"><div class="p1"><div class="big">${ready ? this._n(d.days) : `${_('Deň')} ${day}`}<small>${ready ? '' : _('z {0}', d.days_needed)}</small></div>`
        + `<div class="rt">${ready ? `<b>${_('Dosť dát na analýzu')}</b>` : d.ready_from ? `<b>${_('Návrhy od {0}', this._date(d.ready_from))}</b>` : ''}</div></div>`
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
            + ACTOR_ORDER.filter((k) => acts[k]).map((k) => `<div title="${esc(_(ACTOR_H[k]))}"><span style="color:${C[k]}">${ACT_ICON[k]}</span><span class="l">${_(ACTOR_T[k])}</span><b>${Math.round(acts[k] / tot * 100)} %</b></div>`).join('') + `</div></div>`;
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
      return h;
    }

    _short(id) {
      const n = this._name(id), a = this._area(id);
      return a && n.toLowerCase().startsWith(a.toLowerCase() + ' ') ? n.slice(a.length + 1) : n;
    }
    _sugText(s) {
      const a = this._area(s.entity_id), pre = a ? `${esc(a)} – ` : '';
      const verb = _(VERB[s.action] || s.action), what = esc(this._short(s.entity_id));
      const strip = (s.strip || []).map((v) => `<i class="${v === 2 ? 'h' : v === 1 ? 'e' : ''}"></i>`).join('');
      if (s.kind === 'time') {
        const days = s.days === 'workday' ? ' ' + _('v pracovné dni') : s.days === 'weekend' ? ' ' + _('cez víkend') : '';
        return { title: `${pre}${verb} ${what} ${_('okolo {0}', s.at)}${days}${s.dark ? _(', keď je tma') : ''}`,
          evi: [_('Robíš to ručne medzi {0} a {1}', s.window[0], s.window[1]), _('{0} z {1} dní', s.hits, s.eligible),
            s.false_per_week ? _('v spätnom teste {0}× týždenne zbytočne', this._n(s.false_per_week, 1)) : _('v spätnom teste 0 zbytočných spustení')].join(' · '), strip };
      }
      if (s.kind === 'trigger') {
        let tn = esc(this._name(s.trigger_entity));
        if (s.trigger_entity.startsWith('person.')) tn = `${tn}: ${s.trigger_state === 'home' ? _('príchod domov') : _('odchod')}`;
        const win = s.window ? ` ${s.window[0]}–${s.window[1]}` : '';
        return { title: `${pre}${verb} ${what} ${_('pri „{0}“', tn)}${win}`,
          evi: [_('Do 90 s po „{0}“ to urobíš ručne', tn), _('{0} z {1}×', s.hits, s.total), _('po {0} % udalostí', Math.round(s.precision * 100))].join(' · '), strip };
      }
      return { title: `${esc(this._name(s.automation))}: ${_('často ju rušíš')}`,
        evi: [_('Po jej zásahu si do 2 min prepol {0} na „{1}“', esc(this._name(s.entity_id)), esc(this._stateText(s.action))), _('{0}× za 14 dní', s.hits)].join(' · '), strip };
    }
    _renderSuggestions(list) {
      const sg = this._sug || {}, busy = this._busyId;
      let h = '';
      if (sg.preliminary && list.length) h += `<div class="note">${_('Predbežné návrhy – zatiaľ {0} z {1} dní dát, budú presnejšie.', sg.days, sg.days_needed)}</div>`;
      if (!list.length) {
        h += `<div class="box emptybox"><b>${_('Zatiaľ žiadne návrhy')}</b><span>${_('Analýza beží každú noc. Môžeš ju spustiť aj teraz.')}</span>`
          + `<button class="btn" data-act="analyze"${this._analyzing ? ' disabled' : ''}>${this._analyzing ? _('Analyzujem…') : _('Analyzovať teraz')}</button></div>`;
      }
      h += list.map((s) => {
        const k = KIND[s.kind] || KIND.time, t = this._sugText(s), dis = busy === s.id ? ' disabled' : '';
        const btns = s.kind === 'improve'
          ? `<button class="btn pri" data-act="open" data-id="${s.id}"${dis}>${_('Otvoriť automatizáciu')}</button><button class="btn" data-act="done" data-id="${s.id}"${dis}>${_('Vyriešené')}</button>`
          : `<button class="btn pri" data-act="accept" data-id="${s.id}"${dis}>${_('Prijať')}</button><button class="btn" data-act="edit" data-id="${s.id}" title="${esc(_('Upraviť vytvorí automatizáciu a otvorí ju v editore'))}"${dis}>${_('Upraviť')}</button>`;
        return `<div class="sg"><div class="top"><div class="ic" style="background:${k.bg};color:${k.c}">${k.i}</div><div><div class="ti">${t.title}</div>`
          + `<span class="tag" style="background:${k.bg};color:${k.c}">${_(k.t)}</span></div></div><div class="evi">${t.evi}</div><div class="strip">${t.strip}</div>`
          + `<div class="acts">${btns}<button class="btn" data-act="snooze" data-id="${s.id}"${dis}>${_('Teraz nie')}</button><button class="btn" data-act="reject" data-id="${s.id}"${dis}>${_('Nikdy')}</button></div></div>`;
      }).join('');
      if (list.length || sg.last_analysis) {
        h += `<div class="foot">${list.length ? `<span>${_('Posledných 14 dní: vzor sa stal · deň bez vzoru · nesledovaný deň')}</span>` : ''}`
          + (sg.last_analysis ? `<span>${_('Posledná analýza {0}', new Date(sg.last_analysis).toLocaleString(this._loc(), { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }))}</span>` : '')
          + (list.length ? `<button class="btn" data-act="analyze"${this._analyzing ? ' disabled' : ''}>${this._analyzing ? _('Analyzujem…') : _('Analyzovať teraz')}</button>` : '') + `</div>`;
      }
      return h;
    }
    _renderList(list, mode) {
      return `<div class="box">` + list.map((s) => {
        const t = this._sugText(s), k = KIND[s.kind] || KIND.time;
        const sub = mode === 'rej' ? (s.status === 'snoozed' ? _('odložené') : _('nikdy')) : _(k.t);
        const btn = mode === 'acc'
          ? (s.automation_id ? `<button class="btn" data-act="openid" data-id="${s.id}">${_('Otvoriť')}</button>` : '') + `<button class="btn" data-act="restore" data-id="${s.id}">${_('Vrátiť')}</button>`
          : `<button class="btn" data-act="restore" data-id="${s.id}">${_('Obnoviť')}</button>`;
        return `<div class="lst"><div class="n">${t.title}<small>${sub}</small></div>${btn}</div>`;
      }).join('') + `</div>`;
    }

    _nav(path) { history.pushState(null, '', path); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }
    _toast(msg) { this.dispatchEvent(new CustomEvent('hass-notification', { detail: { message: msg }, bubbles: true, composed: true })); }
    async _status(id, status, automation_id) {
      const msg = { type: 'pattern_pilot/suggestion/update', suggestion_id: id, status };
      if (automation_id) msg.automation_id = automation_id;
      this._sug = await this._hass.callWS(msg);
    }
    async _act(act, id) {
      if (act === 'analyze') {
        this._analyzing = true; this._render();
        try { this._sug = await this._hass.callWS({ type: 'pattern_pilot/analyze' }); } catch (e) { this._toast(_('Nepodarilo sa: {0}', e.message || e)); }
        this._analyzing = false; this._render(); return;
      }
      const s = ((this._sug && this._sug.suggestions) || []).find((x) => x.id === id); if (!s) return;
      this._busyId = id; this._render();
      try {
        if (act === 'accept' || act === 'edit') {
          const newId = String(Date.now());
          await this._hass.callApi('POST', `config/automation/config/${newId}`, s.automation);
          await this._status(id, 'accepted', newId);
          this._toast(_('Automatizácia vytvorená'));
          if (act === 'edit') this._nav(`/config/automation/edit/${newId}`);
        } else if (act === 'open') {
          if (s.automation_config_id) this._nav(`/config/automation/edit/${s.automation_config_id}`);
        } else if (act === 'openid') {
          this._nav(`/config/automation/edit/${s.automation_id}`);
        } else if (act === 'done') await this._status(id, 'accepted');
        else if (act === 'snooze') await this._status(id, 'snoozed');
        else if (act === 'reject') await this._status(id, 'rejected');
        else if (act === 'restore') await this._status(id, 'new');
      } catch (e) { this._toast(_('Nepodarilo sa: {0}', (e && (e.body && e.body.message || e.message)) || e)); }
      this._busyId = null; this._render();
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
    window.customCards.push({ type: 'igy-pattern-pilot-card', name: 'Igy Pattern Pilot Card', description: _('Návrhy automatizácií, priebeh učenia a čo Pattern Pilot vidí v dome.'), preview: false, documentationURL: 'https://github.com/Igypop78/pattern-pilot' });
  console.info('%c IGY-PATTERN-PILOT-CARD %c ' + VERSION + ' ', 'background:#30d158;color:#000;border-radius:3px 0 0 3px', 'background:#333;color:#fff;border-radius:0 3px 3px 0');
})();
