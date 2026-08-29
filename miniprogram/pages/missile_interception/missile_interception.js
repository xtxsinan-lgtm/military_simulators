const api = require('../../utils/api.js');

const RADAR_TYPES = ['mechanical', 'pesa', 'aesa', 'gan_aesa'];
const RADAR_TYPE_NAMES = ['机械扫描', 'PESA', 'AESA', 'GaN AESA'];
const DEFAULT_TRAJ_TYPES = {
  high: '高空 / 常规弹道',
  sea: '掠海 / 海面杂波环境',
  glide: '滑翔体弹道（鹰击-17 等）',
  ballistic: '弹道导弹弹道（鹰击-20/21 等）',
};
const SEEKERS = ['active_aesa', 'active_mech', 'semi_active'];
const SEEKER_NAMES = ['主动 AESA', '主动机械', '半主动'];

/** 「国别」选择器首项：不限国别 */
const ALL_NATIONS = '— 全部国别 —';

function trajFromConfig(cfg) {
  const types = (cfg && cfg.traj_types) || DEFAULT_TRAJ_TYPES;
  const keys = Object.keys(types);
  return { keys, names: keys.map((k) => types[k]) };
}

function trajIndexForId(keys, id) {
  const i = keys.indexOf(id);
  return i >= 0 ? i : 0;
}

function num(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

/** 从预设列表提取去重国别（按首次出现顺序，与 Python nations_sorted 一致）。 */
function nationsSorted(presets) {
  const seen = [];
  (presets || []).forEach((p) => {
    const nation = (p.nation || '').trim();
    if (nation && seen.indexOf(nation) < 0) seen.push(nation);
  });
  return seen;
}

/** 合并多组预设国别（与 Python nations_union 一致）。 */
function nationsUnion() {
  const seen = [];
  for (let i = 0; i < arguments.length; i++) {
    nationsSorted(arguments[i]).forEach((n) => {
      if (seen.indexOf(n) < 0) seen.push(n);
    });
  }
  return seen;
}

/** 按国别过滤预设；国别为空时返回全部。 */
function filterPresetsByNation(presets, nation) {
  const key = (nation || '').trim();
  if (!key) return (presets || []).slice();
  return (presets || []).filter((p) => (p.nation || '').trim() === key);
}

/** 型号选择器名称列表：首项固定为「— 自定义 —」。 */
function modelNames(presets) {
  return ['— 自定义 —'].concat((presets || []).map((x) => x.name));
}

function fmt(n, d) {
  return Number(n).toFixed(d);
}

function formatDiveEntryDisplay(dist) {
  if (dist.dive_entry_km != null && dist.dive_entry_km > 0) {
    return `${fmt(dist.dive_entry_km, 1)} km（俯冲 ${fmt(dist.dive_angle_deg, 0)}°）`;
  }
  const h = fmt(dist.h_target_m ?? 0, 0);
  const alt = fmt(dist.sam_max_alt_km ?? 0, 0);
  return `全程在有效射高包线内（巡航 ${h}m ≤ 最大射高 ${alt}km）`;
}

Page({
  data: {
    asmList: [], aewList: [], shipList: [], samList: [],
    // 反舰为两级选择；驱护+防空共用「防御方国别」，*Filtered 为当前国别下的型号列表
    asmFiltered: [], shipFiltered: [], samFiltered: [],
    asmNationNames: [ALL_NATIONS], defenderNationNames: [ALL_NATIONS],
    asmNationIndex: 0, defenderNationIndex: 0,
    // 预警机预设下标 0 固定为「无预警机」，1 为「— 自定义 —」，>=2 为 aewList 预设
    asmNames: ['— 自定义 —'], aewNames: ['无预警机', '— 自定义 —'],
    shipNames: ['— 自定义 —'], samNames: ['— 自定义 —'],
    asmIndex: 0, aewIndex: 1, shipIndex: 0, samIndex: 0,
    hasAwacs: true,
    trajNames: trajFromConfig().names, trajIndex: 0,
    radarTypeNames: RADAR_TYPE_NAMES,
    awacsTypeIndex: 2, shipTypeIndex: 2, seekerIndex: 0,
    seekerNames: SEEKER_NAMES,
    nm: '24', vm: '2.6', rcs: '0.5', asmId: '', maneuverClass: '',
    awacsArea: '8', standoff: '150',
    shipArea: '12', samRange: '40', samMaxAlt: '33',
    discoveryKm: '120', ni: '16', vi: '3.8',
    interceptorDia: '0.35', pk: '0.7', tlock: '6', minr: '3',
    awacsDetectKm: '待估算', shipDetectKm: '待估算', diveEntryDisplay: '—',
    distNote: '', pkNote: '', statusText: '', statusTag: 'STANDBY',
    running: false, hasResult: false, resultStale: false, showBackToTop: false,
    fieldHints: {}, ranges: {},
    windows: [], planRows: [], strategies: [],
    statRounds: '–', statLeak: '–', statRate: '–',
    statRoundsSub: '', statLeakSub: '', statRateSub: '',
    finalNote: '', avgSurvivors: [],
  },

  onLoad() {
    api.loadSimulatorData().then((data) => {
      const p = data.missile_interception_presets || {};
      const ui = data.missile_interception_config?.ui || {};
      const trajCfg = trajFromConfig(data.missile_interception_config);
      this._trajKeys = trajCfg.keys;
      const asmList = p.asm || [];
      const aewList = p.aew || [];
      const shipList = p.ship || [];
      const samList = p.sam || [];
      const cfg = data.missile_interception_config || {};
      this.setData({
        asmList, aewList, shipList, samList,
        asmFiltered: asmList, shipFiltered: shipList, samFiltered: samList,
        asmNationNames: [ALL_NATIONS].concat(nationsSorted(asmList)),
        defenderNationNames: [ALL_NATIONS].concat(nationsUnion(shipList, samList)),
        asmNames: modelNames(asmList),
        aewNames: ['无预警机', '— 自定义 —'].concat(aewList.map((x) => x.name)),
        shipNames: modelNames(shipList),
        samNames: modelNames(samList),
        nm: String(ui.nm ?? '24'),
        vm: String(ui.vm ?? '2.6'),
        rcs: String(ui.rcs ?? '0.5'),
        awacsArea: String(ui.awacs_area ?? '8'),
        standoff: String(ui.standoff ?? '150'),
        shipArea: String(ui.ship_area ?? '12'),
        samRange: String(ui.sam_range ?? '40'),
        samMaxAlt: String(ui.sam_max_alt ?? '33'),
        discoveryKm: String(ui.discovery_km ?? '120'),
        ni: String(ui.ni ?? '16'),
        vi: String(ui.vi ?? '3.8'),
        interceptorDia: String(ui.interceptor_dia ?? '0.35'),
        pk: String(ui.pk ?? '0.7'),
        tlock: String(ui.tlock ?? '6'),
        minr: String(ui.minr ?? '3'),
        trajNames: trajCfg.names,
        trajIndex: trajIndexForId(trajCfg.keys, ui.traj || 'high'),
        awacsTypeIndex: ['mechanical', 'pesa', 'aesa', 'gan_aesa'].indexOf(ui.awacs_type || 'aesa'),
        shipTypeIndex: ['mechanical', 'pesa', 'aesa', 'gan_aesa'].indexOf(ui.ship_type || 'aesa'),
        seekerIndex: ['active_aesa', 'active_mech', 'semi_active'].indexOf(ui.seeker_type || 'active_aesa'),
        aewIndex: ui.has_awacs === false ? 0 : 1,
        hasAwacs: ui.has_awacs !== false,
        fieldHints: cfg.field_hints || {},
        ranges: cfg.field_ranges || {},
        statusText: '预设已加载。引擎就绪后将自动估算探测距离。',
      }, () => {
        const cfgJs = require('../../config.js');
        if (cfgJs.apiBaseUrl) this.onEstimateDistanceAndPk();
      });
    }).catch((e) => {
      this.setData({ statusText: String(e.message || e) });
    });
  },

  onPageScroll(e) {
    const show = (e.scrollTop || 0) > 360;
    if (show !== this.data.showBackToTop) this.setData({ showBackToTop: show });
  },

  onBackToTop() {
    wx.pageScrollTo({ scrollTop: 0, duration: 300 });
  },

  onHint(e) {
    const key = e.currentTarget.dataset.key;
    const text = (this.data.fieldHints || {})[key];
    if (!text) return;
    wx.showModal({ title: '术语说明', content: text, showCancel: false });
  },

  markResultsStale() {
    if (!this._resultFresh) return;
    this._resultFresh = false;
    this.setData({ resultStale: true, statusTag: 'STALE' });
  },

  onField(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: e.detail.value });
    this.markResultsStale();
  },

  onTraj(e) { this.setData({ trajIndex: Number(e.detail.value) }); this.markResultsStale(); },
  onAwacsType(e) { this.setData({ awacsTypeIndex: Number(e.detail.value) }); this.markResultsStale(); },
  onShipType(e) { this.setData({ shipTypeIndex: Number(e.detail.value) }); this.markResultsStale(); },
  onSeeker(e) { this.setData({ seekerIndex: Number(e.detail.value) }); this.markResultsStale(); },

  /** 切换国别：重建该国别下的型号列表并复位为「— 自定义 —」。 */
  onNation(e, listKey, nationNamesKey, indexKey, filteredKey, namesKey, modelIndexKey) {
    const idx = Number(e.detail.value);
    const nation = idx <= 0 ? '' : this.data[nationNamesKey][idx];
    const filtered = filterPresetsByNation(this.data[listKey], nation);
    this.setData({
      [indexKey]: idx,
      [filteredKey]: filtered,
      [namesKey]: modelNames(filtered),
      [modelIndexKey]: 0,
    });
  },

  onAsmNation(e) {
    this.onNation(e, 'asmList', 'asmNationNames', 'asmNationIndex', 'asmFiltered', 'asmNames', 'asmIndex');
    this.markResultsStale();
  },
  /** 切换防御方国别：同时过滤驱护舰艇与防空导弹型号列表并复位为自定义。 */
  onDefenderNation(e) {
    const idx = Number(e.detail.value);
    const nation = idx <= 0 ? '' : this.data.defenderNationNames[idx];
    const shipFiltered = filterPresetsByNation(this.data.shipList, nation);
    const samFiltered = filterPresetsByNation(this.data.samList, nation);
    this.setData({
      defenderNationIndex: idx,
      shipFiltered,
      samFiltered,
      shipNames: modelNames(shipFiltered),
      samNames: modelNames(samFiltered),
      shipIndex: 0,
      samIndex: 0,
    });
  },

  onAsmPreset(e) {
    const idx = Number(e.detail.value);
    this.setData({ asmIndex: idx });
    if (idx <= 0) return;
    const p = this.data.asmFiltered[idx - 1];
    if (!p) return;
    this.setData({
      vm: String(p.vm), rcs: String(p.rcs),
      trajIndex: trajIndexForId(this._trajKeys || trajFromConfig().keys, p.traj),
      asmId: p.id || '',
      maneuverClass: p.maneuver_class || '',
    });
    this.markResultsStale();
  },
  onAewPreset(e) {
    // 0=无预警机 1=自定义 >=2=aewList[idx-2] 预设
    const idx = Number(e.detail.value);
    this.setData({ aewIndex: idx, hasAwacs: idx !== 0 });
    if (idx <= 1) return;
    const p = this.data.aewList[idx - 2];
    this.setData({
      awacsArea: String(p.area), standoff: String(p.standoff),
      awacsTypeIndex: Math.max(0, RADAR_TYPES.indexOf(p.type)),
    });
    this.markResultsStale();
  },
  onShipPreset(e) {
    const idx = Number(e.detail.value);
    this.setData({ shipIndex: idx });
    if (idx <= 0) return;
    const p = this.data.shipFiltered[idx - 1];
    if (!p) return;
    this.setData({
      shipArea: String(p.area),
      shipTypeIndex: Math.max(0, RADAR_TYPES.indexOf(p.type)),
    });
    this.markResultsStale();
  },
  onSamPreset(e) {
    const idx = Number(e.detail.value);
    this.setData({ samIndex: idx });
    if (idx <= 0) return;
    const p = this.data.samFiltered[idx - 1];
    if (!p) return;
    this.setData({
      vi: String(p.vi), interceptorDia: String(p.dia), samRange: String(p.range),
      samMaxAlt: p.max_alt != null ? String(p.max_alt) : this.data.samMaxAlt,
      seekerIndex: Math.max(0, SEEKERS.indexOf(p.guidance)),
    });
    this.markResultsStale();
  },

  estimateParams() {
    const d = this.data;
    return {
      rcs: num(d.rcs, 0.5),
      traj: (this._trajKeys || trajFromConfig().keys)[d.trajIndex] || 'high',
      awacs_area: num(d.awacsArea, 8),
      awacs_type: RADAR_TYPES[d.awacsTypeIndex] || 'aesa',
      standoff: num(d.standoff, 150),
      ship_area: num(d.shipArea, 12),
      ship_type: RADAR_TYPES[d.shipTypeIndex] || 'aesa',
      sam_range: num(d.samRange, 40),
      sam_max_alt: num(d.samMaxAlt, 33),
      vm: num(d.vm, 2.6),
      vi: num(d.vi, 3.8),
      interceptor_dia: num(d.interceptorDia, 0.35),
      seeker_type: SEEKERS[d.seekerIndex] || 'active_aesa',
      has_awacs: d.aewIndex !== 0,
      asm_id: d.asmId || '',
      maneuver_class: d.maneuverClass || '',
    };
  },

  /** 一次估算交战距离与单发拦截成功概率，填入预警机/舰载探测距离与交战距离等字段。 */
  onEstimateDistanceAndPk() {
    const params = this.estimateParams();
    api.runMissileInterceptionSimulation({ action: 'estimate_distance', params })
      .then((dist) => {
        if (!dist.success) throw new Error(dist.error || '交战距离估算失败');
        return api.runMissileInterceptionSimulation({ action: 'estimate_pk', params }).then((pkR) => {
          if (!pkR.success) throw new Error(pkR.error || '拦截率估算失败');
          const diveSuffix = dist.dive_entry_km != null && dist.dive_entry_km > 0
            ? `，俯冲进入(${fmt(dist.dive_angle_deg, 0)}°/射高${fmt(dist.sam_max_alt_km, 0)}km)≈${fmt(dist.dive_entry_km, 1)}km`
            : '';
          const distNote = dist.has_awacs
            ? `预警机探测 ${fmt(dist.awacs_detect_km, 0)}km ｜ 舰载探测 ${fmt(dist.ship_detect_km, 0)}km（射高${fmt(dist.h_engage_m, 0)}m）→ 交战距离=${fmt(dist.engage_dist, 1)} km${diveSuffix}（受限于：${dist.binding}）`
            : `无预警机：巡航${fmt(dist.h_target_m, 0)}m/射高${fmt(dist.h_engage_m, 0)}m，舰载探测=${fmt(dist.ship_detect_km, 0)}km，交战距离 ${fmt(dist.engage_dist, 1)} km${diveSuffix}（受限于：${dist.binding}）`;
          this.setData({
            awacsDetectKm: dist.has_awacs ? fmt(dist.awacs_detect_km, 1) : '0',
            shipDetectKm: fmt(dist.ship_detect_km, 1),
            diveEntryDisplay: formatDiveEntryDisplay(dist),
            discoveryKm: fmt(dist.engage_dist, 1),
            distNote,
            pk: fmt(pkR.pk, 2),
            pkNote: `估算拦截率（单发）= ${fmt(pkR.pk, 2)}（含机动性×${fmt(pkR.maneuver_factor, 2)}[${pkR.maneuver_class || 'cruise'}]）`,
          });
        });
      })
      .catch((e) => this.setData({ distNote: String(e.message || e), pkNote: '' }));
  },

  onRun() {
    if (this.data.running) {
      this._rerunRequested = true;
      this.setData({ statusTag: 'QUEUED', statusText: '已排队，当前轮结束后用新参数重算…' });
      return;
    }
    this._rerunRequested = false;
    const d = this.data;
    this.setData({ running: true, statusText: '计算中…', statusTag: 'COMPUTING' });
    const payload = {
      action: 'simulate',
      params: {
        nm: num(d.nm, 24),
        vm: num(d.vm, 2.6),
        D: num(d.discoveryKm, 120),
        ni: num(d.ni, 16),
        vi: num(d.vi, 3.8),
        pk: num(d.pk, 0.7),
        tlock: num(d.tlock, 6),
        minr: num(d.minr, 3),
      },
    };
    api.runMissileInterceptionSimulation(payload)
      .then((r) => {
        if (!r.success) throw new Error(r.error || '仿真失败');
        this.applyResult(r);
        if (this._rerunRequested) {
          this._rerunRequested = false;
          this.onRun();
        }
      })
      .catch((e) => {
        this.setData({
          running: false,
          statusTag: 'ERROR',
          statusText: String(e.message || e),
          hasResult: false,
        });
        if (this._rerunRequested) {
          this._rerunRequested = false;
          this.onRun();
        }
      });
  },

  applyResult(r) {
    const windows = (r.windows || []).map((w) => ({
      round: w.round,
      dist_start_km: fmt(w.dist_start_km, 1),
      t_fly_s: fmt(w.t_fly_s, 1),
      total_t_s: fmt(w.total_t_s, 1),
      dist_end_km: fmt(w.dist_end_km, 1),
    }));
    const avg = r.avg_survivors || [];
    const plan = (r.best && r.best.plan) || [];
    const apiRows = r.plan_rows || [];
    const planRows = (apiRows.length ? apiRows : plan.map((budget, i) => {
      const surv = avg[i] || 0;
      const per = surv > 0 ? budget / surv : 0;
      return { round: i + 1, budget, survivors: surv, per_target: per, kill_prob: 0 };
    })).map((row, i) => ({
      round: row.round || i + 1,
      budget: `${row.budget} 枚`,
      surv: fmt(row.survivors, 2),
      per: `≈${fmt(row.per_target, 2)}`,
      kill: `${fmt((row.kill_prob || 0) * 100, 1)}%`,
    }));
    const bestKey = plan.join(',');
    const strategies = (r.all_candidates || []).map((c) => {
      const best = c.is_best || (c.name === (r.best && r.best.name) && (c.plan || []).join(',') === bestKey);
      return {
        name: c.name,
        plan: `[${(c.plan || []).join(', ')}]`,
        leak: fmt(c.expected_leak, 2),
        best,
        relative: c.relative_label || (best ? '最优' : ''),
      };
    });
    this._resultFresh = true;
    this.setData({
      running: false,
      hasResult: true,
      resultStale: false,
      statusTag: 'DONE',
      statusText: `MC N=${r.final_trials}`,
      windows,
      planRows,
      strategies,
      avgSurvivors: avg,
      statRounds: String(r.n_rounds),
      statRoundsSub: `锁定 ${r.t_lock_s}s/轮`,
      statLeak: fmt(r.expected_leak, 2),
      statLeakSub: `/ 共 ${r.nm} 枚`,
      statRate: `${fmt((r.intercept_rate || 0) * 100, 1)}%`,
      statRateSub: `弹药 ≤ ${r.ni}`,
      finalNote: r.note || '',
    }, () => this.drawChart(avg));
  },

  drawChart(avgSurvivors) {
    const query = wx.createSelectorQuery();
    query.select('#survivorCanvas').fields({ node: true, size: true }).exec((res) => {
      if (!res || !res[0] || !res[0].node) return;
      const canvas = res[0].node;
      const width = res[0].width;
      const height = res[0].height;
      const ctx = canvas.getContext('2d');
      const dpr = wx.getSystemInfoSync().pixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
      ctx.fillStyle = '#0e161b';
      ctx.fillRect(0, 0, width, height);
      const pts = avgSurvivors || [];
      if (pts.length < 2) return;
      const maxY = Math.max(...pts, 1);
      const pad = 16;
      ctx.strokeStyle = '#1c2b30';
      ctx.beginPath();
      ctx.moveTo(pad, pad);
      ctx.lineTo(pad, height - pad);
      ctx.lineTo(width - pad, height - pad);
      ctx.stroke();
      ctx.strokeStyle = '#ff4d4f';
      ctx.lineWidth = 2;
      ctx.beginPath();
      pts.forEach((y, i) => {
        const x = pad + (i / (pts.length - 1)) * (width - 2 * pad);
        const yy = height - pad - (y / maxY) * (height - 2 * pad);
        if (i === 0) ctx.moveTo(x, yy);
        else ctx.lineTo(x, yy);
      });
      ctx.stroke();
    });
  },
});
