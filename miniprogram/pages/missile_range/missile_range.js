const api = require('../../utils/api.js');

const TYPE_IDS = ['biconic', 'waverider'];
const TYPE_NAMES = ['双锥体', '乘波体'];

function num(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

Page({
  data: {
    cases: [],
    rows: [],
    caseNames: [],
    caseIndex: 0,
    typeNames: TYPE_NAMES,
    typeIndex: 0,
    lengthM: '',
    diameterM: '',
    warheadKg: '',
    vMach: '0.85',
    hKm: '13',
    ispS: '264',
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
        const cases = block.cases || [];
        if (!cases.length) {
          this.setData({ statusText: 'data.json 缺少 missile_range，请运行 build_all.py' });
          return;
        }
        const defaults = block.defaults || {};
        this.setData({
          cases,
          rows: cases,
          caseNames: cases.map((row) => row.name),
          ispS: defaults.isp_s != null ? String(defaults.isp_s) : '264',
          density: defaults.propellant_density != null ? String(defaults.propellant_density) : '1760',
          statusText: 'STANDBY',
        });
        this.applyCase(cases[0]);
      })
      .catch((err) => {
        this.setData({ statusText: String(err.message || err) });
      });
  },

  applyCase(row) {
    if (!row) return;
    const typeIndex = Math.max(0, TYPE_IDS.indexOf(row.hgv_type));
    const caseIndex = Math.max(0, this.data.cases.findIndex((item) => item.id === row.id));
    this.setData({
      caseIndex,
      typeIndex,
      lengthM: String(row.length_m),
      diameterM: String(row.diameter_m),
      warheadKg: String(row.warhead_kg),
      vMach: String(row.v_mach),
      hKm: String(row.h_km),
      activeId: row.id,
      result: {
        range_km: row.range_km,
        v_burnout_mach: row.v_burnout_mach,
        ld_ratio: row.ld_ratio,
        m_0_t: row.m_0_t,
        l_head_m: row.l_head_m,
        l_booster_m: row.l_booster_m,
        m_p_total_kg: row.m_p_total_kg,
      },
      statusText: 'PRESET',
    });
  },

  onPickCase(e) {
    const index = Number(e.detail.value);
    this.applyCase(this.data.cases[index]);
  },

  onPickType(e) {
    this.setData({ typeIndex: Number(e.detail.value) });
  },

  onInput(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: e.detail.value });
  },

  onTapRow(e) {
    const id = Number(e.currentTarget.dataset.id);
    const row = this.data.rows.find((item) => item.id === id)
      || this.data.cases.find((item) => item.id === id);
    this.applyCase(row);
  },

  onRun() {
    if (this.data.running) return;
    const payload = {
      action: 'estimate',
      params: {
        length_m: num(this.data.lengthM, 0),
        diameter_m: num(this.data.diameterM, 0),
        warhead_kg: num(this.data.warheadKg, 0),
        hgv_type: TYPE_IDS[this.data.typeIndex] || 'biconic',
        v_launch_mach: num(this.data.vMach, 0.85),
        h_launch_km: num(this.data.hKm, 13),
        isp_s: num(this.data.ispS, 264),
        propellant_density: num(this.data.density, 1760),
      },
    };
    this.setData({ running: true, statusText: 'RUNNING' });
    api.runMissileRangeSimulation(payload)
      .then((res) => {
        if (!res.success) throw new Error(res.error || '估算失败');
        this.setData({
          result: res.result,
          rows: res.rows && res.rows.length ? res.rows : this.data.rows,
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
