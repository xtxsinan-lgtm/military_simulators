const api = require('../../utils/api.js');

const EMPTY_AC = {
  name: '',
  AR: '',
  sweep_deg: '',
  wing_loading: '',
  tc: '',
  mach: '',
  alt_m: '',
  planform: 'trapezoidal',
  layout: 'conventional',
  bwb: false,
  rough: false,
};

function num(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function fmt(n, d) {
  return Number(n).toFixed(d);
}

function cloneAc(src) {
  return Object.assign({}, EMPTY_AC, src || {});
}

function weightFromPreset(p) {
  if (!p) return {};
  const patch = { wtNMissiles: '4' };
  if (p.empty_kg != null) patch.wtEmpty = String(p.empty_kg);
  if (p.internal_fuel_kg != null) patch.wtFuel = String(p.internal_fuel_kg);
  if (p.n_pilots != null) patch.wtPilots = String(p.n_pilots);
  if (p.missile_mass_kg != null) patch.wtMissile = String(p.missile_mass_kg);
  if (p.n_engines != null) patch.wtEngines = String(p.n_engines);
  return patch;
}

function planformIndex(ids, id) {
  const i = ids.indexOf(id);
  return i >= 0 ? i : 0;
}

Page({
  data: {
    presets: [],
    presetNames: ['— 自定义 —'],
    planformIds: ['trapezoidal'],
    planformNames: ['梯形翼'],
    layoutIds: ['conventional'],
    layoutNames: ['常规'],
    a1: cloneAc(),
    a2: cloneAc(),
    tgt: cloneAc(),
    a1Ld: '8.8',
    a2Ld: '8.0',
    a1PresetIndex: 0,
    a2PresetIndex: 0,
    tgtPresetIndex: 0,
    a1PlanformIndex: 0,
    a2PlanformIndex: 0,
    tgtPlanformIndex: 0,
    a1LayoutIndex: 0,
    a2LayoutIndex: 0,
    tgtLayoutIndex: 0,
    statusText: '加载预设…',
    result: null,
    resultLd: '',
    resultCf0: '',
    resultKe: '',
    resultRows: [],
    running: false,
    enginePresets: [],
    engineNames: ['— 自定义 —'],
    enginePresetIndex: 0,
    engBpr: '',
    engOpr: '',
    engT4: '',
    engTsl: '',
    engAlt: '11000',
    engMach: '1.5',
    engEta: '0.87',
    engFanPr: '',
    thrustStatusText: 'STANDBY',
    thrustResult: null,
    thrustKN: '',
    thrustTf: '',
    thrustAlpha: '',
    thrustMdot: '',
    thrustFanPr: '',
    thrustNote: '',
    wtEmpty: '',
    wtFuel: '',
    wtPilots: '1',
    wtMissile: '',
    wtNMissiles: '4',
    wtEngines: '1',
    effEps: '0.83',
    effEtan: '0.95',
    effAcc: '0.16',
    effStatusText: 'STANDBY',
    effResult: null,
    effLoadPct: '',
    effLoadRawPct: '',
    effEtaO: '',
    effEtaTh: '',
    effEtaP: '',
    effTsfc: '',
    effTsfcLb: '',
    effT4: '',
    effNote: '',
  },

  onShow() {
    api.loadSimulatorData()
      .then((data) => {
        const presets = data.combat_radius_presets || [];
        const cfg = data.combat_radius_config || {};
        const planformMap = cfg.planform_labels || { trapezoidal: '梯形翼' };
        const layoutMap = cfg.layout_labels || { conventional: '常规' };
        const planformIds = Object.keys(planformMap);
        const layoutIds = Object.keys(layoutMap);
        const ui = cfg.ui || {};
        const presetNames = ['— 自定义 —'].concat(presets.map((p) => p.name));
        const findIdx = (id) => {
          const i = presets.findIndex((p) => p.id === id);
          return i >= 0 ? i + 1 : 0;
        };
        const a1p = presets.find((p) => p.id === ui.default_anchor1_id) || presets[0];
        const a2p = presets.find((p) => p.id === ui.default_anchor2_id) || presets[1];
        const tgtp = presets.find((p) => p.id === ui.default_target_id) || presets[2];
        const engines = data.combat_radius_engine_presets || [];
        const engineNames = ['— 自定义 —'].concat(engines.map((p) => p.name));
        const findEngIdx = (id) => {
          const i = engines.findIndex((p) => p.id === id);
          return i >= 0 ? i + 1 : 0;
        };
        const eng = engines.find((p) => p.id === ui.default_engine_id)
          || engines.find((p) => p.tsl_kN != null)
          || engines[0];
        this.setData({
          presets,
          presetNames,
          planformIds,
          planformNames: planformIds.map((k) => planformMap[k]),
          layoutIds,
          layoutNames: layoutIds.map((k) => layoutMap[k]),
          a1: cloneAc(a1p),
          a2: cloneAc(a2p),
          tgt: cloneAc(tgtp),
          a1Ld: String(ui.default_ld1 ?? (a1p && a1p.ld_known) ?? 8.8),
          a2Ld: String(ui.default_ld2 ?? (a2p && a2p.ld_known) ?? 8.0),
          a1PresetIndex: findIdx(ui.default_anchor1_id),
          a2PresetIndex: findIdx(ui.default_anchor2_id),
          tgtPresetIndex: findIdx(ui.default_target_id),
          a1PlanformIndex: planformIndex(planformIds, a1p && a1p.planform),
          a2PlanformIndex: planformIndex(planformIds, a2p && a2p.planform),
          tgtPlanformIndex: planformIndex(planformIds, tgtp && tgtp.planform),
          a1LayoutIndex: planformIndex(layoutIds, a1p && a1p.layout),
          a2LayoutIndex: planformIndex(layoutIds, a2p && a2p.layout),
          tgtLayoutIndex: planformIndex(layoutIds, tgtp && tgtp.layout),
          enginePresets: engines,
          engineNames,
          enginePresetIndex: findEngIdx(eng && eng.id),
          engBpr: eng ? String(eng.bpr) : '',
          engOpr: eng ? String(eng.opr) : '',
          engT4: eng ? String(eng.t4_K) : '',
          engTsl: eng && eng.tsl_kN != null ? String(eng.tsl_kN) : '',
          engAlt: String(ui.default_thrust_alt_m ?? 11000),
          engMach: String(ui.default_thrust_mach ?? 1.5),
          engEta: String(ui.default_eta_c ?? 0.87),
          effEps: String(ui.default_eps ?? 0.83),
          effEtan: String(ui.default_etan ?? 0.95),
          effAcc: String(ui.default_acc_frac ?? 0.16),
          ...weightFromPreset(tgtp),
          statusText: presets.length ? '预设已加载' : '缺少 combat_radius_presets，请运行 build_all.py',
        });
      })
      .catch((e) => {
        this.setData({ statusText: String(e.message || e) });
      });
  },

  onField(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: e.detail.value });
  },

  onAcField(e) {
    const slot = e.currentTarget.dataset.slot;
    const key = e.currentTarget.dataset.key;
    this.setData({ [`${slot}.${key}`]: e.detail.value });
  },

  onSwitch(e) {
    const slot = e.currentTarget.dataset.slot;
    const key = e.currentTarget.dataset.key;
    this.setData({ [`${slot}.${key}`]: !!e.detail.value });
  },

  onPreset(e) {
    const slot = e.currentTarget.dataset.slot;
    const idx = Number(e.detail.value);
    const patch = { [`${slot}PresetIndex`]: idx };
    if (idx > 0) {
      const p = this.data.presets[idx - 1];
      patch[slot] = cloneAc(p);
      patch[`${slot}PlanformIndex`] = planformIndex(this.data.planformIds, p.planform);
      patch[`${slot}LayoutIndex`] = planformIndex(this.data.layoutIds, p.layout);
      if (slot === 'a1' && p.ld_known != null) patch.a1Ld = String(p.ld_known);
      if (slot === 'a2' && p.ld_known != null) patch.a2Ld = String(p.ld_known);
      if (slot === 'tgt') Object.assign(patch, weightFromPreset(p));
    }
    this.setData(patch);
  },

  onEnginePreset(e) {
    const idx = Number(e.detail.value);
    const patch = { enginePresetIndex: idx };
    if (idx > 0) {
      const p = this.data.enginePresets[idx - 1];
      patch.engBpr = String(p.bpr);
      patch.engOpr = String(p.opr);
      patch.engT4 = String(p.t4_K);
      if (p.tsl_kN != null) patch.engTsl = String(p.tsl_kN);
    }
    this.setData(patch);
  },

  onPlanform(e) {
    const slot = e.currentTarget.dataset.slot;
    const idx = Number(e.detail.value);
    this.setData({
      [`${slot}PlanformIndex`]: idx,
      [`${slot}.planform`]: this.data.planformIds[idx],
    });
  },

  onLayout(e) {
    const slot = e.currentTarget.dataset.slot;
    const idx = Number(e.detail.value);
    this.setData({
      [`${slot}LayoutIndex`]: idx,
      [`${slot}.layout`]: this.data.layoutIds[idx],
    });
  },

  toAircraft(slot) {
    const ac = this.data[slot];
    return {
      name: ac.name || '未命名',
      AR: num(ac.AR, 0),
      sweep_deg: num(ac.sweep_deg, 0),
      wing_loading: num(ac.wing_loading, 0),
      tc: num(ac.tc, 0),
      mach: num(ac.mach, 0.8),
      alt_m: num(ac.alt_m, 12000),
      planform: ac.planform,
      layout: ac.layout,
      bwb: !!ac.bwb,
      rough: !!ac.rough,
    };
  },

  onRun() {
    if (this.data.running) return;
    this.setData({ running: true, statusText: '计算中…' });
    api.runCombatRadiusSimulation({
      action: 'predict_ld',
      params: {
        anchor1: this.toAircraft('a1'),
        ld1_target: num(this.data.a1Ld, 8.8),
        anchor2: this.toAircraft('a2'),
        ld2_target: num(this.data.a2Ld, 8.0),
        target: this.toAircraft('tgt'),
      },
    })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '估算失败');
        const rows = (r.anchors || []).map((row) => ({
          name: row.name,
          ld: fmt(row.ld, 4),
          CD0: fmt(row.CD0, 5),
          CDi: fmt(row.CDi, 5),
          target: false,
        }));
        rows.push({
          name: r.target.name,
          ld: fmt(r.target.ld, 4),
          CD0: fmt(r.target.CD0, 5),
          CDi: fmt(r.target.CDi, 5),
          target: true,
        });
        this.setData({
          result: r,
          resultLd: fmt(r.target.ld, 4),
          resultCf0: fmt(r.Cf0, 6),
          resultKe: fmt(r.k_e, 6),
          resultRows: rows,
          statusText: 'READY',
          running: false,
        });
      })
      .catch((e) => {
        this.setData({ statusText: String(e.message || e), running: false, result: null });
      });
  },

  onRunThrust() {
    if (this.data.running) return;
    this.setData({ running: true, thrustStatusText: '计算中…' });
    const params = {
      name: this.data.engineNames[this.data.enginePresetIndex] || '',
      bpr: num(this.data.engBpr, 0),
      opr: num(this.data.engOpr, 0),
      t4_K: num(this.data.engT4, 0),
      tsl_kN: num(this.data.engTsl, 0),
      alt_m: num(this.data.engAlt, 11000),
      mach: num(this.data.engMach, 1.5),
      eta_c: num(this.data.engEta, 0.87),
    };
    if (this.data.engFanPr !== '') params.fan_pr_override = num(this.data.engFanPr, 0);
    api.runCombatRadiusSimulation({
      action: 'estimate_thrust',
      params,
    })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '估算失败');
        this.setData({
          thrustResult: r,
          thrustKN: fmt(r.thrust_kN, 1),
          thrustTf: fmt(r.thrust_tf, 2),
          thrustAlpha: fmt(r.alpha, 3),
          thrustMdot: fmt(r.mdot_ratio, 3),
          thrustFanPr: fmt(r.fan_pr, 2),
          thrustNote: `来流总温比 τr=${fmt(r.tau_r, 3)} · 大气 ${fmt(r.T0, 1)} K / ${fmt(r.P0 / 1000, 1)} kPa。α = T_flight / T_SL。`,
          thrustStatusText: 'READY',
          running: false,
        });
      })
      .catch((e) => {
        this.setData({
          thrustStatusText: String(e.message || e),
          running: false,
          thrustResult: null,
        });
      });
  },

  onRunEfficiency() {
    if (this.data.running) return;
    this.setData({ running: true, effStatusText: '计算中…' });
    const params = {
      name: this.data.engineNames[this.data.enginePresetIndex] || '',
      bpr: num(this.data.engBpr, 0),
      opr: num(this.data.engOpr, 0),
      t4_K: num(this.data.engT4, 0),
      tsl_kN: num(this.data.engTsl, 0),
      alt_m: num(this.data.engAlt, 11000),
      mach: num(this.data.engMach, 1.5),
      eta_c: num(this.data.engEta, 0.87),
      anchor1: this.toAircraft('a1'),
      ld1_target: num(this.data.a1Ld, 8.8),
      anchor2: this.toAircraft('a2'),
      ld2_target: num(this.data.a2Ld, 8.0),
      target: this.toAircraft('tgt'),
      empty_kg: num(this.data.wtEmpty, 0),
      internal_fuel_kg: num(this.data.wtFuel, 0),
      n_pilots: num(this.data.wtPilots, 1),
      missile_mass_kg: num(this.data.wtMissile, 0),
      n_missiles: num(this.data.wtNMissiles, 4),
      n_engines: num(this.data.wtEngines, 1),
      eps: num(this.data.effEps, 0.83),
      etan: num(this.data.effEtan, 0.95),
      acc_frac: num(this.data.effAcc, 0.16),
    };
    if (this.data.engFanPr !== '') params.fan_pr_override = num(this.data.engFanPr, 0);
    api.runCombatRadiusSimulation({
      action: 'estimate_efficiency',
      params,
    })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '估算失败');
        const tsfc = r.tsfc_mg_n_s != null ? `${fmt(r.tsfc_mg_n_s, 2)} mg/(N·s)` : '—';
        const tsfcLb = r.tsfc_lb_lbf_h != null ? `${fmt(r.tsfc_lb_lbf_h, 3)} lb/(lbf·h)` : '';
        this.setData({
          effResult: r,
          effLoadPct: fmt(100 * (r.load || 0), 1),
          effLoadRawPct: fmt(100 * (r.load_raw || 0), 1),
          effEtaO: fmt(100 * (r.eta_o || 0), 1),
          effEtaTh: fmt(100 * (r.eta_th || 0), 1),
          effEtaP: fmt(100 * (r.eta_p || 0), 1),
          effTsfc: tsfc,
          effTsfcLb: tsfcLb,
          effT4: fmt(r.T4_solved, 0),
          effNote: `空战重量 ${fmt(r.mass_kg, 0)} kg · 阻力 ${fmt(r.drag_kN, 2)} kN · 可用军推 ${fmt(r.thrust_avail_kN, 1)} kN（${r.n_engines} 发）· L/D ${fmt(r.ld, 3)}。`,
          effStatusText: r.warning ? String(r.warning) : 'READY',
          running: false,
        });
      })
      .catch((e) => {
        this.setData({
          effStatusText: String(e.message || e),
          running: false,
          effResult: null,
        });
      });
  },
});
