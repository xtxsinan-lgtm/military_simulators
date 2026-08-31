const api = require('../../utils/api.js');

const EMPTY_AC = {
  name: '',
  AR: '',
  sweep_deg: '',
  sweep_inner_deg: '',
  sweep_outer_deg: '',
  wing_loading: '',
  tc: '',
  mach: '0.8',
  alt_m: '12000',
  planform: 'trapezoidal',
  layout: 'conventional',
  bwb: false,
  rough: false,
  length_m: '',
  wingspan_m: '',
  mach_angle_deg: '',
  wing_area_m2: '',
};

function num(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function fmt(n, d) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toFixed(d);
}

function resolveTslKN(engine, ratio) {
  if (!engine) return '';
  const tsl = Number(engine.tsl_kN);
  if (Number.isFinite(tsl) && tsl > 0) return String(tsl);
  const maxTsl = Number(engine.max_tsl_kN);
  const r = Number(ratio);
  const use = r > 0 && r <= 1 ? r : 0.7;
  if (Number.isFinite(maxTsl) && maxTsl > 0) {
    return String(Math.round(maxTsl * use * 10) / 10);
  }
  return '';
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
  patch.wtCarrier = !!p.carrier;
  return patch;
}

/** 分速表第一列：固定马赫只写数字，表尾两行写中文名称加马赫。 */
function cruiseSpeedLabel(p) {
  const name = p.label || (p.mach != null ? `Ma ${fmt(p.mach, 3)}` : '—');
  if ((p.id === 'max_cruise' || p.id === 'floor_max_cruise') && p.mach != null) {
    return `${name} ${fmt(p.mach, 3)}`;
  }
  return p.mach != null ? fmt(p.mach, 3) : name;
}

function dashRowsFrom(r) {
  return (r.points || []).map((p) => {
    const maxLd = p.max_ld != null ? fmt(p.max_ld, 2) : '—';
    const speed = cruiseSpeedLabel(p);
    if (!p.feasible) {
      return {
        label: p.label,
        mach: speed,
        maxLd,
        radius: p.fail_reason || '不可行',
        mixed: '—',
        ok: false,
      };
    }
    const mixed = p.mach != null && p.mach > 1
      ? (p.mixed_radius_km != null ? fmt(p.mixed_radius_km, 0) : '—')
      : '不适用';
    return {
      label: p.label,
      mach: speed,
      maxLd,
      radius: fmt(p.radius_km, 0),
      mixed,
      ok: true,
    };
  });
}

Page({
  data: {
    presets: [],
    presetNames: ['— 选择战机 —'],
    tgt: cloneAc(),
    tgtPresetIndex: 0,
    statusText: '加载预设…',
    enginePresets: [],
    engineNames: ['— 自定义 —'],
    enginePresetIndex: 0,
    engBpr: '',
    engOpr: '',
    engT4: '',
    engTsl: '',
    engMaxTsl: '',
    engEta: '0.87',
    wtEmpty: '',
    wtFuel: '',
    wtPilots: '1',
    wtMissile: '',
    wtNMissiles: '4',
    wtEngines: '1',
    wtCarrier: false,
    dashStatusText: 'STANDBY',
    dashOk: false,
    dashMaxCruise: '—',
    dashFloorCruise: '—',
    dashVmax: '—',
    dashRows: [],
    resultsMap: {},
    q1Mach: '0.9',
    q1Text: '',
    q2Mach: '0.8',
    q2Alt: '12000',
    q2Text: '',
    q3Mach: '0.8',
    q3Alt: '12000',
    q3Load: '0.45',
    q3Text: '',
    running: false,
    dryToMaxRatio: 0.7,
  },

  onShow() {
    api.loadSimulatorData()
      .then((data) => {
        const presets = data.combat_radius_presets || [];
        const cfg = data.combat_radius_config || {};
        const ui = cfg.ui || {};
        const presetNames = ['— 选择战机 —'].concat(presets.map((p) => p.name));
        const engines = data.combat_radius_engine_presets || [];
        const engineNames = ['— 自定义 —'].concat(engines.map((p) => p.name));
        const tgtp = presets.find((p) => p.id === ui.default_target_id) || presets[0];
        const findIdx = (id) => {
          const i = presets.findIndex((p) => p.id === id);
          return i >= 0 ? i + 1 : 0;
        };
        const findEngIdx = (id) => {
          const i = engines.findIndex((p) => p.id === id);
          return i >= 0 ? i + 1 : 0;
        };
        const ratioRaw = Number((cfg.engine || {}).dry_to_max_thrust_ratio);
        const dryToMaxRatio = ratioRaw > 0 && ratioRaw <= 1 ? ratioRaw : 0.7;
        const eng = (tgtp && tgtp.engine_id && engines.find((p) => p.id === tgtp.engine_id))
          || engines.find((p) => p.id === ui.default_engine_id)
          || engines[0];
        this.setData({
          presets,
          presetNames,
          tgt: cloneAc(tgtp),
          tgtPresetIndex: findIdx(ui.default_target_id),
          enginePresets: engines,
          engineNames,
          enginePresetIndex: findEngIdx(eng && eng.id),
          engBpr: eng ? String(eng.bpr) : '',
          engOpr: eng ? String(eng.opr) : '',
          engT4: eng ? String(eng.t4_K) : '',
          engTsl: resolveTslKN(eng, dryToMaxRatio),
          engMaxTsl: eng && eng.max_tsl_kN != null ? String(eng.max_tsl_kN) : '',
          engEta: String(ui.default_eta_c ?? 0.87),
          dryToMaxRatio,
          resultsMap: (data.combat_radius_results && data.combat_radius_results.aircraft) || {},
          ...weightFromPreset(tgtp),
          statusText: presets.length ? '预设已加载' : '缺少 combat_radius_presets，请运行 build_all.py',
        });
        this.showSnapshot(tgtp && tgtp.id);
      })
      .catch((e) => {
        this.setData({ statusText: String(e.message || e) });
      });
  },

  showSnapshot(id) {
    const snap = id ? this.data.resultsMap[id] : null;
    if (!snap || !snap.success) {
      this.setData({
        dashOk: false,
        dashStatusText: (snap && snap.error) || '无预计算快照。填写军推后将自动重算。',
        dashRows: [],
      });
      return;
    }
    const ms = snap.max_speed || {};
    this.setData({
      dashOk: true,
      dashStatusText: '预计算快照',
      dashMaxCruise: snap.max_cruise_mach != null ? fmt(snap.max_cruise_mach, 3) : '—',
      dashFloorCruise: snap.max_cruise_floor_mach != null ? fmt(snap.max_cruise_floor_mach, 3) : '—',
      dashVmax: ms.feasible ? `${fmt(ms.max_speed_kmh, 0)} km/h` : (ms.fail_reason || '—'),
      dashRows: dashRowsFrom(snap),
    });
  },

  applyEngine(p) {
    if (!p) return {};
    const patch = {
      engBpr: String(p.bpr),
      engOpr: String(p.opr),
      engT4: String(p.t4_K),
    };
    patch.engTsl = resolveTslKN(p, this.data.dryToMaxRatio);
    patch.engMaxTsl = p.max_tsl_kN != null ? String(p.max_tsl_kN) : '';
    return patch;
  },

  onField(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: e.detail.value });
    if (!['q1Mach', 'q2Mach', 'q2Alt', 'q3Mach', 'q3Alt', 'q3Load'].includes(key)) {
      this.scheduleLiveDash();
    }
  },

  onAcField(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [`tgt.${key}`]: e.detail.value });
    this.scheduleLiveDash();
  },

  onCarrierSwitch(e) {
    this.setData({ wtCarrier: !!e.detail.value });
    this.scheduleLiveDash();
  },

  onAircraftPreset(e) {
    const idx = Number(e.detail.value);
    const patch = { tgtPresetIndex: idx };
    if (idx > 0) {
      const p = this.data.presets[idx - 1];
      patch.tgt = cloneAc(p);
      Object.assign(patch, weightFromPreset(p));
      if (p.engine_id) {
        const ei = this.data.enginePresets.findIndex((x) => x.id === p.engine_id);
        if (ei >= 0) {
          patch.enginePresetIndex = ei + 1;
          Object.assign(patch, this.applyEngine(this.data.enginePresets[ei]));
        }
      }
      this.setData(patch);
      this.showSnapshot(p.id);
    } else {
      this.setData(patch);
    }
  },

  onEnginePreset(e) {
    const idx = Number(e.detail.value);
    const patch = { enginePresetIndex: idx };
    if (idx > 0) Object.assign(patch, this.applyEngine(this.data.enginePresets[idx - 1]));
    this.setData(patch);
    this.scheduleLiveDash();
  },

  scheduleLiveDash() {
    if (this._dashTimer) clearTimeout(this._dashTimer);
    this._dashTimer = setTimeout(() => this.runLiveDash(), 600);
  },

  toAircraft() {
    const ac = this.data.tgt;
    return {
      name: ac.name || '未命名',
      AR: num(ac.AR, 0),
      sweep_deg: num(ac.sweep_deg, 0),
      sweep_inner_deg: num(ac.sweep_inner_deg, 0),
      sweep_outer_deg: num(ac.sweep_outer_deg, 0),
      wing_loading: num(ac.wing_loading, 0),
      tc: num(ac.tc, 0),
      mach: 0.8,
      alt_m: 12000,
      planform: ac.planform,
      layout: ac.layout,
      bwb: !!ac.bwb,
      rough: !!ac.rough,
      length_m: num(ac.length_m, 0),
      wingspan_m: num(ac.wingspan_m, 0),
      mach_angle_deg: num(ac.mach_angle_deg, 0),
      wing_area_m2: num(ac.wing_area_m2, 0),
    };
  },

  dashboardParams() {
    const params = {
      name: this.data.tgt.name || '',
      target: this.toAircraft(),
      empty_kg: num(this.data.wtEmpty, 0),
      internal_fuel_kg: num(this.data.wtFuel, 0),
      n_pilots: num(this.data.wtPilots, 1),
      missile_mass_kg: num(this.data.wtMissile, 0),
      n_missiles: num(this.data.wtNMissiles, 4),
      n_engines: num(this.data.wtEngines, 1),
      carrier: !!this.data.wtCarrier,
      bpr: num(this.data.engBpr, 0),
      opr: num(this.data.engOpr, 0),
      t4_K: num(this.data.engT4, 0),
      eta_c: num(this.data.engEta, 0.87),
    };
    const tsl = num(this.data.engTsl, 0);
    if (tsl > 0) params.tsl_kN = tsl;
    if (this.data.engMaxTsl !== '') params.max_tsl_kN = num(this.data.engMaxTsl, 0);
    return params;
  },

  runLiveDash() {
    if (this.data.running) return;
    this.setData({ running: true, dashStatusText: '重算中…' });
    api.runCombatRadiusSimulation({ action: 'aircraft_dashboard', params: this.dashboardParams() })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '仪表盘失败');
        const ms = r.max_speed || {};
        this.setData({
          dashOk: true,
          dashStatusText: '现场重算',
          dashMaxCruise: r.max_cruise_mach != null ? fmt(r.max_cruise_mach, 3) : '—',
          dashFloorCruise: r.max_cruise_floor_mach != null ? fmt(r.max_cruise_floor_mach, 3) : '—',
          dashVmax: ms.feasible ? `${fmt(ms.max_speed_kmh, 0)} km/h` : (ms.fail_reason || '—'),
          dashRows: dashRowsFrom(r),
          running: false,
        });
      })
      .catch((e) => {
        this.setData({
          dashOk: false,
          dashStatusText: String(e.message || e),
          running: false,
        });
      });
  },

  onRunSearchCruise() {
    if (this.data.running) return;
    this.setData({ running: true, q1Text: '搜索中…' });
    const params = this.dashboardParams();
    params.mach = num(this.data.q1Mach, 0.9);
    api.runCombatRadiusSimulation({ action: 'search_best_cruise', params })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '搜索失败');
        if (!r.feasible) {
          const maxLd = r.max_ld != null
            ? `最大 L/D ${fmt(r.max_ld, 2)} · ${fmt((r.max_ld_alt_m || 0) / 1000, 1)} km · ${r.max_ld_thrust_mode === 'afterburner' ? '加力' : '军推'}。`
            : '';
          this.setData({
            q1Text: `${r.fail_reason || '无可行高度'}${maxLd ? ' ' + maxLd : ''}`,
            running: false,
          });
          return;
        }
        this.setData({
          q1Text: `L/D ${fmt(r.ld, 2)} · 最大 L/D ${fmt(r.max_ld, 2)} · ${fmt(r.alt_m / 1000, 1)} km · 推力 ${fmt(r.thrust_avail_kN, 1)} kN · 负载 ${fmt(100 * r.load, 1)}% · 热效率 ${fmt(100 * r.eta_th, 1)}% · 推进效率 ${fmt(100 * r.eta_p, 1)}%`,
          running: false,
        });
      })
      .catch((e) => this.setData({ q1Text: String(e.message || e), running: false }));
  },

  onRunPoint() {
    if (this.data.running) return;
    this.setData({ running: true, q2Text: '计算中…' });
    const params = this.dashboardParams();
    params.mach = num(this.data.q2Mach, 0.8);
    params.alt_m = num(this.data.q2Alt, 12000);
    api.runCombatRadiusSimulation({ action: 'estimate_efficiency', params })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '计算失败');
        this.setData({
          q2Text: `L/D ${fmt(r.ld, 2)} · 推力 ${fmt(r.thrust_avail_kN, 1)} kN · 负载 ${fmt(100 * r.load, 1)}% · 热效率 ${fmt(100 * r.eta_th, 1)}% · 推进效率 ${fmt(100 * r.eta_p, 1)}% · 总效率 ${fmt(100 * r.eta_o, 1)}%`,
          running: false,
        });
      })
      .catch((e) => this.setData({ q2Text: String(e.message || e), running: false }));
  },

  onRunEngineCycle() {
    if (this.data.running) return;
    this.setData({ running: true, q3Text: '计算中…' });
    api.runCombatRadiusSimulation({
      action: 'estimate_engine_cycle',
      params: {
        bpr: num(this.data.engBpr, 0),
        opr: num(this.data.engOpr, 0),
        t4_K: num(this.data.engT4, 0),
        mach: num(this.data.q3Mach, 0.8),
        alt_m: num(this.data.q3Alt, 12000),
        load: num(this.data.q3Load, 0.45),
      },
    })
      .then((r) => {
        if (!r.success) throw new Error(r.error || '计算失败');
        this.setData({
          q3Text: `热效率 ${fmt(100 * r.eta_th, 1)}% · 推进效率 ${fmt(100 * r.eta_p, 1)}% · 总效率 ${fmt(100 * r.eta_o, 1)}%`,
          running: false,
        });
      })
      .catch((e) => this.setData({ q3Text: String(e.message || e), running: false }));
  },
});
