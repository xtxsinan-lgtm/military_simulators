const api = require('../../utils/api.js');

function num(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function kindOf(row) {
  return row.class_label || row.missile_class;
}

function ispTextOf(row) {
  const boost = row.isp_boost_s;
  const cruise = row.isp_cruise_s;
  const rocket = row.isp_rocket_s;
  const n = (v) => String(Math.round(Number(v)));
  if (cruise != null && boost != null && rocket != null) return `${n(boost)}+${n(cruise)}/${n(rocket)}`;
  if (cruise != null && boost != null) return `${n(boost)}+${n(cruise)}`;
  if (cruise != null && rocket != null) return `${n(cruise)}/${n(rocket)}`;
  if (cruise != null) return n(cruise);
  if (rocket != null) return n(rocket);
  if (boost != null) return n(boost);
  return '—';
}

function stageTextOf(row) {
  if (!row || row.n_stages == null) return '—';
  const names = { 1: '单级', 2: '两级', 3: '三级' };
  const name = names[row.n_stages] || `${row.n_stages}级`;
  if (row.n_stages === 1) return name;
  return `${name} ${row.stage_split || ''}`;
}
function formatRangeKm(n) {
  if (n == null || n === '' || Number.isNaN(Number(n))) return '—';
  return String(Math.round(Number(n)));
}

function integerRangeLabel(text) {
  return String(text).replace(/\d+\.\d+/g, (token) => String(Math.round(Number(token))));
}

function profileTextOf(row) {
  if (!row) return '—';
  if (row.profile_text) return integerRangeLabel(row.profile_text);
  if (row.range_high_km == null || row.range_sea_km == null) return '';
  const mixed = row.range_mixed_km == null ? '—' : formatRangeKm(row.range_mixed_km);
  return `${formatRangeKm(row.range_high_km)}/${mixed}/${formatRangeKm(row.range_sea_km)}`;
}

function decorate(row) {
  return {
    ...row,
    kind: kindOf(row),
    profileText: profileTextOf(row),
    rangeText: formatRangeKm(row.range_km),
    altText: row.alt_range_text ? integerRangeLabel(row.alt_range_text) : '—',
    ispText: ispTextOf(row),
    stageText: stageTextOf(row),
  };
}

function takeoverPctOf(row) {
  if (!row || row.mach_takeover == null) return 0;
  const frac = row.takeover_progress != null
    ? Number(row.takeover_progress)
    : Number(row.mach_boost || row.v_burnout_mach) / Number(row.mach_takeover);
  return Math.round(Math.max(0, Math.min(1, frac)) * 100);
}

Page({
  data: {
    classes: [],
    classNames: [],
    classIndex: 0,
    classBlurb: '选择弹种后估算射程。固体比冲用于火箭级，吸气巡航用更高的比冲。',
    cases: [],
    rows: [],
    caseNames: [],
    caseIndex: 0,
    lengthM: '',
    diameterM: '',
    warheadKg: '',
    vMach: '0.85',
    hKm: '13',
    ispS: '264',
    ispAir: '',
    showAirIsp: false,
    ballisticSingleStage: false,
    showBallisticSingleStage: false,
    optimizeGeometry: true,
    showOptimizeGeometry: true,
    density: '1760',
    activeId: null,
    result: null,
    takeoverPct: 0,
    failOnly: false,
    failCount: 0,
    okCount: 0,
    statusText: '加载中…',
    running: false,
  },

  onShow() {
    if (this.data.cases.length) return;
    api.loadSimulatorData()
      .then((catalog) => {
        const block = catalog.missile_range || {};
        const cases = (block.cases || []).map(decorate);
        if (!cases.length) {
          this.setData({ statusText: 'data.json 缺少 missile_range，请运行 build_all.py' });
          return;
        }
        const classes = block.classes || [];
        const defaults = block.defaults || {};
        this.tableIsp = defaults.isp_s != null ? Number(defaults.isp_s) : 264;
        this.tableDensity = defaults.propellant_density != null ? Number(defaults.propellant_density) : 1760;
        this.setData({
          classes,
          classNames: classes.map((item) => item.label),
          cases,
          rows: cases,
          caseNames: cases.map((row) => row.name),
          ispS: defaults.isp_s != null ? String(defaults.isp_s) : '264',
          density: defaults.propellant_density != null ? String(defaults.propellant_density) : '1760',
          ballisticSingleStage: defaults.ballistic_single_stage === true,
          failCount: cases.filter((row) => row.reached_takeover === false).length,
          okCount: cases.filter((row) => row.reached_takeover === true).length,
          statusText: 'STANDBY',
        });
        this.applyCase(cases[0]);
      })
      .catch((err) => {
        this.setData({ statusText: String(err.message || err) });
      });
  },

  syncClass(missileClass) {
    const classes = this.data.classes;
    const classIndex = Math.max(0, classes.findIndex((item) => item.id === missileClass));
    const found = classes[classIndex];
    const showAir = !!(found && found.isp_cruise_s != null);
    const showBallistic = missileClass === 'ballistic';
    this.setData({
      classIndex: found ? classIndex : 0,
      classBlurb: (found && found.blurb) || this.data.classBlurb,
      showAirIsp: showAir,
      ispAir: showAir ? String(found.isp_cruise_s) : '',
      showBallisticSingleStage: showBallistic,
      ballisticSingleStage: false,
      showOptimizeGeometry: String(missileClass).indexOf('hgv') === 0,
    });
  },

  applyCase(row) {
    if (!row) return;
    const caseIndex = Math.max(0, this.data.cases.findIndex((item) => item.id === row.id));
    this.syncClass(row.missile_class || 'hgv_biconic');
    this.setData({
      caseIndex,
      lengthM: String(row.length_m),
      diameterM: String(row.diameter_m),
      warheadKg: String(row.warhead_kg),
      vMach: String(row.v_mach),
      hKm: String(row.h_km),
      activeId: row.id,
      ballisticSingleStage: false,
      result: {
        range_km: row.range_km,
        rangeText: formatRangeKm(row.range_km),
        range_high_km: row.range_high_km,
        range_sea_km: row.range_sea_km,
        range_mixed_km: row.range_mixed_km,
        profileText: row.profileText,
        alt_range_text: row.alt_range_text ? integerRangeLabel(row.alt_range_text) : row.alt_range_text,
        range_terminal_km: row.range_terminal_km,
        v_burnout_mach: row.v_burnout_mach,
        ld_ratio: row.ld_ratio,
        m_0_t: row.m_0_t,
        l_head_m: row.l_head_m,
        d_head_m: row.d_head_m,
        fineness: row.fineness,
        range_gain_km: row.range_gain_km,
        rangeGainText: row.range_gain_km == null ? '—' : formatRangeKm(row.range_gain_km),
        l_booster_m: row.l_booster_m,
        m_p_total_kg: row.m_p_total_kg,
        note: row.note,
        n_stages: row.n_stages,
        stage_split: row.stage_split,
        stage_locked: row.stage_locked,
        missile_class: row.missile_class,
        isp_boost_s: row.isp_boost_s,
        isp_cruise_s: row.isp_cruise_s,
        isp_rocket_s: row.isp_rocket_s,
        reached_takeover: row.reached_takeover,
        mach_takeover: row.mach_takeover,
        mach_boost: row.mach_boost,
        m_booster_kg: row.m_booster_kg,
        m_fuel_kg: row.m_fuel_kg,
        takeover_progress: row.takeover_progress,
      },
      takeoverPct: takeoverPctOf(row),
      statusText: row.reached_takeover === false ? '⚠️ 未达工作速度' : 'PRESET',
    });
  },

  onPickCase(e) {
    const index = Number(e.detail.value);
    this.applyCase(this.data.cases[index]);
  },

  onPickClass(e) {
    const index = Number(e.detail.value);
    const found = this.data.classes[index];
    if (!found) return;
    this.syncClass(found.id);
  },

  onInput(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: e.detail.value });
  },

  onBallisticSingleStageChange(e) {
    this.setData({ ballisticSingleStage: !!e.detail.value });
  },

  onOptimizeGeometryChange(e) {
    this.setData({ optimizeGeometry: !!e.detail.value });
  },

  onFailOnlyChange(e) {
    const failOnly = !!e.detail.value;
    const source = this.data.cases;
    const rows = failOnly
      ? source.filter((row) => row.reached_takeover === false)
      : source;
    this.setData({ failOnly, rows });
    if (failOnly && rows.length && !rows.some((row) => row.id === this.data.activeId)) {
      this.applyCase(rows[0]);
    }
  },

  onTapRow(e) {
    const id = Number(e.currentTarget.dataset.id);
    const row = this.data.rows.find((item) => item.id === id)
      || this.data.cases.find((item) => item.id === id);
    this.applyCase(row);
  },

  onRun() {
    if (this.data.running) return;
    const missileClass = (this.data.classes[this.data.classIndex] || {}).id || 'hgv_biconic';
    const payload = {
      action: 'estimate',
      params: {
        missile_class: missileClass,
        length_m: num(this.data.lengthM, 0),
        diameter_m: num(this.data.diameterM, 0),
        warhead_kg: num(this.data.warheadKg, 0),
        v_launch_mach: num(this.data.vMach, 0.85),
        h_launch_km: num(this.data.hKm, 13),
        isp_s: num(this.data.ispS, 264),
        propellant_density: num(this.data.density, 1760),
        ballistic_single_stage: !!this.data.ballisticSingleStage,
        optimize_geometry: !!this.data.optimizeGeometry,
      },
    };
    if (this.data.showAirIsp) payload.params.isp_air_s = num(this.data.ispAir, 0);
    const isp = payload.params.isp_s;
    const density = payload.params.propellant_density;
    const refreshRows = Math.abs(isp - (this.tableIsp ?? 264)) > 1e-4
      || Math.abs(density - (this.tableDensity ?? 1760)) > 1e-4;
    payload.params.include_rows = refreshRows;
    this.setData({ running: true, statusText: 'RUNNING' });
    api.runMissileRangeSimulation(payload)
      .then((res) => {
        if (!res.success) throw new Error(res.error || '估算失败');
        const result = res.result || {};
        if (result.range_sea_km === undefined) result.range_sea_km = null;
        if (result.range_high_km === undefined) result.range_high_km = null;
        if (result.range_mixed_km === undefined) result.range_mixed_km = null;
        result.profileText = profileTextOf(result);
        result.rangeText = formatRangeKm(result.range_km);
        result.rangeGainText = result.range_gain_km == null ? '—' : formatRangeKm(result.range_gain_km);
        if (result.range_terminal_km === undefined) result.range_terminal_km = null;
        if (refreshRows && res.rows && res.rows.length) {
          this.tableIsp = isp;
          this.tableDensity = density;
        }
        const rows = (refreshRows && res.rows && res.rows.length ? res.rows : this.data.cases).map(decorate);
        const visible = this.data.failOnly
          ? rows.filter((row) => row.reached_takeover === false)
          : rows;
        const isFailed = res.result && res.result.reached_takeover === false;
        this.setData({
          result: res.result,
          cases: rows,
          caseNames: rows.map((row) => row.name),
          rows: visible,
          failCount: rows.filter((row) => row.reached_takeover === false).length,
          okCount: rows.filter((row) => row.reached_takeover === true).length,
          takeoverPct: takeoverPctOf(res.result),
          activeId: null,
          statusText: isFailed ? '⚠️ 未达工作速度' : 'DONE',
          running: false,
        });
      })
      .catch((err) => {
        this.setData({ statusText: String(err.message || err), running: false });
      });
  },
});
