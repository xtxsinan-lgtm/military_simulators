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

function decorate(row) {
  return {
    ...row,
    kind: kindOf(row),
    seaText: row.range_sea_km == null ? '—' : String(row.range_sea_km),
    ispText: ispTextOf(row),
  };
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
    ballisticTwoStage: true,
    showBallisticTwoStage: false,
    density: '1760',
    activeId: null,
    result: null,
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
        this.setData({
          classes,
          classNames: classes.map((item) => item.label),
          cases,
          rows: cases,
          caseNames: cases.map((row) => row.name),
          ispS: defaults.isp_s != null ? String(defaults.isp_s) : '264',
          density: defaults.propellant_density != null ? String(defaults.propellant_density) : '1760',
          ballisticTwoStage: defaults.ballistic_two_stage !== false,
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
      showBallisticTwoStage: showBallistic,
      ballisticTwoStage: showBallistic ? true : this.data.ballisticTwoStage,
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
      ballisticTwoStage: row.missile_class === 'ballistic',
      result: {
        range_km: row.range_km,
        range_high_km: row.range_high_km,
        range_sea_km: row.range_sea_km,
        range_terminal_km: row.range_terminal_km,
        v_burnout_mach: row.v_burnout_mach,
        ld_ratio: row.ld_ratio,
        m_0_t: row.m_0_t,
        l_head_m: row.l_head_m,
        l_booster_m: row.l_booster_m,
        m_p_total_kg: row.m_p_total_kg,
        note: row.note,
        missile_class: row.missile_class,
        isp_boost_s: row.isp_boost_s,
        isp_cruise_s: row.isp_cruise_s,
        isp_rocket_s: row.isp_rocket_s,
      },
      statusText: 'PRESET',
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

  onBallisticTwoStageChange(e) {
    this.setData({ ballisticTwoStage: !!e.detail.value });
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
        ballistic_two_stage: !!this.data.ballisticTwoStage,
      },
    };
    if (this.data.showAirIsp) payload.params.isp_air_s = num(this.data.ispAir, 0);
    this.setData({ running: true, statusText: 'RUNNING' });
    api.runMissileRangeSimulation(payload)
      .then((res) => {
        if (!res.success) throw new Error(res.error || '估算失败');
        const result = res.result || {};
        if (result.range_sea_km === undefined) result.range_sea_km = null;
        if (result.range_high_km === undefined) result.range_high_km = null;
        if (result.range_terminal_km === undefined) result.range_terminal_km = null;
        const rows = (res.rows && res.rows.length ? res.rows : this.data.rows).map(decorate);
        this.setData({
          result: res.result,
          rows,
          activeId: null,
          statusText: 'DONE',
          running: false,
        });
      })
      .catch((err) => {
        this.setData({ statusText: String(err.message || err), running: false });
      });
  },
});
