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
});
