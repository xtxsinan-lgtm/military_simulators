const { loadSimulatorData, runSimulation, modesToList } = require('../../utils/api.js');
const {
  computeSkiJumpArc,
  resolveCarrierSkiJump,
  computeAircraftAero,
  a2aMassKg,
  maxPayloadKg,
  filterCarriersForMode,
  filterAircraftForMode,
  fmtNum,
  fmtInt,
  modeNeedsSkiJump,
  modeHasTrajectory,
  defaultDeckWindKt,
} = require('../../utils/physics.js');
const { trajectoryCanvasHeightRpx } = require('../../utils/responsive.js');
const config = require('../../config.js');

/** 仿真输出卡片标题右侧：优先用 API output_summary，否则本地拼装 */
function formatOutputSummary(result) {
  if (result && result.output_summary) return result.output_summary;
  if (!result || result.distance_m == null) return '';
  const dist = `起飞 ${fmtNum(result.distance_m, 1)} m`;
  if (result.deck_margin_m == null) return dist;
  const margin = Number(result.deck_margin_m);
  const deck =
    margin >= 0
      ? `余量 ${fmtNum(margin, 1)} m`
      : `超出 ${fmtNum(-margin, 1)} m`;
  return `${dist} · ${deck}`;
}

Page({
  data: {
    modeList: [],
    strategyList: [],
    currentMode: 'ski_jump',
    currentStrategy: 'A',
    showStrategy: false,
    strategyTitle: '喷口策略',
    strategyDescription: '',
    carriers: [],
    aircraft: [],
    carrierNames: [],
    aircraftNames: [],
    carrierIndex: 0,
    aircraftIndex: 0,
    carrierLabel: '',
    aircraftLabel: '',
    carrierSpecs: [],
    aircraftSpecs: [],
    showSkiJump: false,
    skiAngle: '',
    skiArcLength: '',
    skiHeight: '',
    skiHorizontal: '—',
    windKt: '',
    tempC: '30',
    massKg: '',
    statusText: '',
    statusClass: '',
    outputText: '选择参数后点击「开始仿真」，结果将显示在此处。',
    outputEmpty: true,
    outputSummary: '',
    highlights: [],
    resultStale: false,
    outputDetailsOpen: true,
    massRangeHint: '',
    massError: '',
    massInvalid: false,
    showBackToTop: false,
    running: false,
    simResult: null,
    showTrajectory: false,
    trajHeightRpx: 380,
    hasApi: false,
  },

  /** 页面级缓存：完整数据库与滑跃几何 */
  _data: null,
  _skiGeom: null,
  _windUserEdited: false,
  _massUserEdited: false,
  _resultFresh: false,

  onLoad() {
    this.setData({
      trajHeightRpx: trajectoryCanvasHeightRpx(),
      hasApi: Boolean(config.apiBaseUrl),
    });
    this.bootstrap();
  },

  async bootstrap() {
    this.setStatus('正在加载数据…', 'loading');
    try {
      const data = await loadSimulatorData();
      if (!data || !Array.isArray(data.carriers) || !Array.isArray(data.aircraft)) {
        throw new Error('数据格式无效：缺少 carriers / aircraft');
      }
      this._data = data;
      const ui = data.takeoff_config?.ui || {};
      this._stovlStrategies = data.stovl_strategies || {
        A: '策略 A — 延迟偏转喷口',
        B: '策略 B — 全程固定喷口',
        C: '策略 C — 尾流约束最优偏转',
      };
      this._tiltrotorStrategies = data.tiltrotor_strategies || {
        A: '策略 A — 延迟倾转短舱',
        B: '策略 B — 全程固定短舱角',
      };
      const takeoffCfg = data.takeoff_config || {};
      this._stovlStrategyDesc = takeoffCfg.stovl_strategy_descriptions || {};
      this._tiltrotorStrategyDesc = takeoffCfg.tiltrotor_strategy_descriptions || {};
      this.setData({
        modeList: modesToList(data.modes),
        strategyList: modesToList(this._stovlStrategies),
        tempC: ui.default_temp_c != null ? String(ui.default_temp_c) : '30',
      });
      this.applyMode(ui.default_mode || 'ski_jump');
      const hint = config.apiBaseUrl
        ? '本地数据已加载。仿真将请求后端 API。'
        : '数据已加载。仿真需配置 config.js 中的 apiBaseUrl 并启动 python3 apps/miniprogram_api.py';
      this.setStatus(hint, 'ok');
    } catch (e) {
      this.setStatus(e.message || '加载失败', 'error');
    }
  },

  onPageScroll(e) {
    const show = (e.scrollTop || 0) > 360;
    if (show !== this.data.showBackToTop) this.setData({ showBackToTop: show });
  },

  onBackToTop() {
    wx.pageScrollTo({ scrollTop: 0, duration: 300 });
  },

  onToggleOutputDetails() {
    this.setData({ outputDetailsOpen: !this.data.outputDetailsOpen });
  },

  markResultsStale() {
    if (!this._resultFresh) return;
    this._resultFresh = false;
    this.setData({ resultStale: true });
    this.setStatus('参数已更改 — 结果已过期，请重新仿真', '');
  },

  /** 与 Python validate_takeoff_mass 对齐。 */
  validateTakeoffMass(massKg, mtowKg, emptyKg) {
    const mass = Number(massKg);
    if (!Number.isFinite(mass)) return '请填写有效的起飞重量';
    if (mass <= 0) return '起飞重量必须为正数';
    if (Number.isFinite(mtowKg) && mass > mtowKg + 1e-6) {
      return `起飞重量 ${Math.round(mass)} kg 超出最大起飞重量 ${Math.round(mtowKg)} kg`;
    }
    if (Number.isFinite(emptyKg) && mass + 1e-6 < emptyKg) {
      return `起飞重量 ${Math.round(mass)} kg 低于空重 ${Math.round(emptyKg)} kg`;
    }
    return '';
  },

  refreshMassHint() {
    const ac = this.getSelectedAircraft();
    const massRangeHint = ac
      ? `范围：空重 ${Math.round(ac.empty_kg)} – MTOW ${Math.round(ac.mtow_kg)} kg`
      : '';
    const massError = ac
      ? this.validateTakeoffMass(parseFloat(this.data.massKg), ac.mtow_kg, ac.empty_kg)
      : '';
    this.setData({ massRangeHint, massError, massInvalid: Boolean(massError) });
    return massError;
  },

  setStatus(text, cls = '') {
    this.setData({ statusText: text, statusClass: cls });
  },

  resolveStrategyDescription(mode, strategy) {
    const descs =
      mode === 'tiltrotor_short_takeoff'
        ? this._tiltrotorStrategyDesc
        : this._stovlStrategyDesc;
    return (descs && descs[strategy]) || '';
  },

  applyMode(mode) {
    if (!this._data) return;
    const carriers = filterCarriersForMode(mode, this._data.carriers);
    const aircraft = filterAircraftForMode(mode, this._data.aircraft);
    const showStrategy =
      mode === 'short_takeoff' ||
      mode === 'short_ski_jump' ||
      mode === 'tiltrotor_short_takeoff';
    const isTilt = mode === 'tiltrotor_short_takeoff';
    const strategyMap = isTilt ? this._tiltrotorStrategies : this._stovlStrategies;
    let currentStrategy = this.data.currentStrategy;
    if (isTilt && currentStrategy === 'C') currentStrategy = 'A';
    this._windUserEdited = false;
    this._massUserEdited = false;
    this.setData({
      currentMode: mode,
      showStrategy,
      strategyTitle: isTilt ? '短舱倾转策略' : '喷口策略',
      strategyList: modesToList(strategyMap || {}),
      currentStrategy,
      strategyDescription: this.resolveStrategyDescription(mode, currentStrategy),
      carriers,
      aircraft,
      carrierNames: carriers.map((c) => `${c.name}（${c.nation}）`),
      aircraftNames: aircraft.map((a) => a.name),
      carrierIndex: 0,
      aircraftIndex: 0,
      showTrajectory: false,
      simResult: null,
    });
    this.refreshSelections();
    this.markResultsStale();
  },

  getSelectedCarrier() {
    const list = this.data.carriers;
    const idx = this.data.carrierIndex;
    return list[idx] || null;
  },

  getSelectedAircraft() {
    const list = this.data.aircraft;
    const idx = this.data.aircraftIndex;
    return list[idx] || null;
  },

  refreshSelections() {
    this.updateCarrierInfo();
    this.updateAircraftInfo();
  },

  updateSkiJumpFromInputs() {
    const carrier = this.getSelectedCarrier();
    if (!carrier || !carrier.ski_jump) {
      this._skiGeom = null;
      return;
    }
    const angle = parseFloat(this.data.skiAngle);
    const arcLen = parseFloat(this.data.skiArcLength);
    if (Number.isNaN(angle) || angle <= 0) return;
    try {
      this._skiGeom = computeSkiJumpArc(
        angle,
        null,
        Number.isNaN(arcLen) || arcLen <= 0 ? null : arcLen
      );
      this.setData({
        skiHeight: this._skiGeom.lip_height_m.toFixed(2),
        skiHorizontal: fmtNum(this._skiGeom.horizontal_m, 1),
      });
    } catch (e) {
      this._skiGeom = null;
    }
  },

  updateCarrierInfo() {
    const c = this.getSelectedCarrier();
    if (!c) {
      this.setData({
        carrierLabel: '（无可用航母）',
        carrierSpecs: [],
        showSkiJump: false,
      });
      return;
    }

    let skiPatch = {};
    if (c.ski_jump) {
      const base = resolveCarrierSkiJump(c);
      skiPatch = {
        skiAngle: String(base.angle_deg),
        skiArcLength: base.arc_length_m.toFixed(1),
      };
    }

    const specs = [
      { label: '最大航速', value: `${fmtInt(c.max_speed_kt)} kt` },
      { label: '甲板总长度', value: `${fmtNum(c.total_deck_length_m, 1)} m` },
      {
        label: '滑跃甲板',
        value: c.ski_jump ? '是（参数可编辑）' : '否（平直甲板）',
      },
    ];

    const showSki = modeNeedsSkiJump(this.data.currentMode) && c.ski_jump;
    const patch = {
      carrierLabel: `${c.name}（${c.nation}）`,
      carrierSpecs: specs,
      showSkiJump: showSki,
      ...skiPatch,
    };

    if (!this._windUserEdited) {
      const wind = defaultDeckWindKt(c);
      if (wind != null) patch.windKt = String(wind);
    }

    this.setData(patch, () => {
      if (c.ski_jump) this.updateSkiJumpFromInputs();
    });
  },

  updateAircraftInfo() {
    const ac = this.getSelectedAircraft();
    if (!ac) {
      this.setData({
        aircraftLabel: '（无可用战斗机）',
        aircraftSpecs: [],
      });
      return;
    }

    const aero = computeAircraftAero(ac);
    const isVtol = ac.type_label === 'v/stol';
    const isTilt = ac.type_label === 'tiltrotor';
    const specs = [
      { label: '最大起飞重量 (MTOW)', value: `${fmtInt(ac.mtow_kg)} kg` },
      { label: '最大内油', value: `${fmtInt(ac.internal_fuel_kg)} kg` },
      { label: '中距弹型号', value: ac.bvr_missile },
      { label: '中距弹重量', value: `${fmtNum(ac.missile_mass_kg, 1)} kg/枚` },
      { label: '最大载弹量', value: `${fmtInt(maxPayloadKg(ac))} kg` },
      {
        label: isTilt ? '默认起飞重量（空重+内油+机组）' : '4枚中距弹满内油空战起飞重量',
        value: `${fmtInt(a2aMassKg(ac))} kg`,
      },
      { label: '翼展', value: `${fmtNum(ac.wingspan_m, 2)} m` },
      { label: '翼面积', value: `${fmtNum(ac.wing_area_m2, 2)} m²` },
    ];

    if (isVtol) {
      specs.push(
        { label: '主喷管推力 (15°C SL)', value: `${fmtNum(ac.t_main_stovl_sl_n / 1000, 1)} kN` },
        { label: '升力风扇推力', value: `${fmtNum(ac.t_liftfan_sl_n / 1000, 1)} kN` },
        { label: '滚转喷管推力', value: `${fmtNum(ac.t_rollposts_sl_n / 1000, 1)} kN` }
      );
    } else if (isTilt) {
      specs.push(
        { label: '总轴功率 (15°C SL)', value: `${fmtNum(ac.shaft_power_sl_w / 1e6, 2)} MW` },
        { label: '桨盘直径', value: `${fmtNum(ac.prop_diameter_m, 2)} m` },
        {
          label: '短舱遮挡比',
          value: `${fmtNum((ac.nacelle_blockage_frac != null ? ac.nacelle_blockage_frac : 0.1) * 100, 0)} %`,
        }
      );
    } else {
      specs.push({
        label: '最大加力推力 (15°C SL)',
        value: `${fmtNum(ac.t_max_sl_n / 1000, 1)} kN`,
      });
    }

    specs.push(
      { label: '前缘后掠角', value: `${fmtNum(ac.sweep_le_deg, 1)}°` },
      { label: '展弦比', value: fmtNum(aero.aspect_ratio, 3) },
      { label: '升力线斜率 C_Lα', value: `${fmtNum(aero.cl_alpha_per_rad, 4)} /rad` },
      {
        label: '滑行升力系数 Cl_taxi',
        value: `${fmtNum(aero.cl_taxi, 4)}（迎角 ${fmtNum(aero.taxi_alpha_deg, 1)}°）`,
      },
      { label: '20° 攻角升力系数', value: fmtNum(aero.cl_20deg, 4) },
      { label: '零升阻力系数 Cd0', value: fmtNum(aero.cd0, 4) }
    );

    const patch = {
      aircraftLabel: ac.name,
      aircraftSpecs: specs,
    };
    if (!this._massUserEdited) {
      patch.massKg = String(Math.round(a2aMassKg(ac)));
    }
    this.setData(patch, () => this.refreshMassHint());
  },

  onModeChange(e) {
    this.applyMode(e.detail.mode);
  },

  onStrategyChange(e) {
    const strategy = e.detail.mode;
    if (!strategy) return;
    this.setData({
      currentStrategy: strategy,
      strategyDescription: this.resolveStrategyDescription(this.data.currentMode, strategy),
    });
    this.markResultsStale();
  },

  onCarrierChange(e) {
    this._windUserEdited = false;
    this.setData({ carrierIndex: Number(e.detail.value) }, () => {
      this.updateCarrierInfo();
      this.markResultsStale();
    });
  },

  onAircraftChange(e) {
    this._massUserEdited = false;
    this.setData({ aircraftIndex: Number(e.detail.value) }, () => {
      this.updateAircraftInfo();
      this.markResultsStale();
    });
  },

  onSkiAngleInput(e) {
    this.setData({ skiAngle: e.detail.value }, () => this.updateSkiJumpFromInputs());
    this.markResultsStale();
  },

  onSkiArcInput(e) {
    this.setData({ skiArcLength: e.detail.value }, () => this.updateSkiJumpFromInputs());
    this.markResultsStale();
  },

  onWindInput(e) {
    this._windUserEdited = true;
    this.setData({ windKt: e.detail.value });
    this.markResultsStale();
  },

  onTempInput(e) {
    this.setData({ tempC: e.detail.value });
    this.markResultsStale();
  },

  onMassInput(e) {
    this._massUserEdited = true;
    this.setData({ massKg: e.detail.value }, () => this.refreshMassHint());
    this.markResultsStale();
  },

  async onRunSimulation() {
    const carrier = this.getSelectedCarrier();
    const aircraft = this.getSelectedAircraft();
    if (!carrier || !aircraft) {
      this.setStatus('请选择航母和战斗机', 'error');
      return;
    }

    const mass = parseFloat(this.data.massKg);
    const temp = parseFloat(this.data.tempC);
    const wind = parseFloat(this.data.windKt);
    if ([mass, temp, wind].some((v) => Number.isNaN(v))) {
      this.setStatus('请填写有效的重量、温度和甲板风', 'error');
      return;
    }
    const massErr = this.refreshMassHint();
    if (massErr) {
      this.setStatus(massErr, 'error');
      return;
    }

      this.setData({
        running: true,
        outputEmpty: false,
        outputText: '计算中…',
        outputSummary: '',
        highlights: [],
        resultStale: false,
        outputDetailsOpen: true,
        showTrajectory: false,
        simResult: null,
      });
    this.setStatus('仿真计算中（可能需要数秒至数十秒）…', 'loading');

    const payload = {
      mode: this.data.currentMode,
      aircraft,
      carrier,
      mass_kg: mass,
      temp_c: temp,
      wind_kt: wind,
      total_deck_length_m: carrier.total_deck_length_m,
    };

    if (this.data.showStrategy) {
      payload.strategy = this.data.currentStrategy;
    }

    if (modeNeedsSkiJump(this.data.currentMode) && carrier.ski_jump) {
      this.updateSkiJumpFromInputs();
      payload.ski_jump_angle_deg = parseFloat(this.data.skiAngle);
      payload.ski_jump_arc_length_m = parseFloat(this.data.skiArcLength);
      payload.ski_jump_height_m = parseFloat(this.data.skiHeight);
    }

    try {
      const result = await runSimulation(payload);
      const traj = result && result.trajectory;
      const deck = result && result.deck_profile;
      const showTraj = Boolean(
        modeHasTrajectory(this.data.currentMode) &&
          result.success &&
          Array.isArray(traj) &&
          traj.length > 0 &&
          deck &&
          Array.isArray(deck.points) &&
          deck.points.length > 0
      );

      // 只把绘图所需字段传给组件，避免整包 output 过大导致 observer/渲染异常
      const chartResult = showTraj
        ? {
            trajectory: traj,
            deck_profile: deck,
            distance_m: result.distance_m,
          }
        : null;

      this.setData({
        outputText: result.output || '(无输出)',
        outputSummary: result.success ? formatOutputSummary(result) : '',
        highlights: result.success ? (result.highlights || []) : [],
        resultStale: false,
        outputDetailsOpen: !result.success,
        simResult: chartResult,
        showTrajectory: showTraj,
      });

      if (result.success) {
        this._resultFresh = true;
        const trajNote = showTraj ? ` · 轨迹 ${traj.length} 点` : '';
        const missingTrajNote =
          modeHasTrajectory(this.data.currentMode) && !showTraj
            ? ' · 未返回轨迹数据'
            : '';
        const msg = result.deck_launch_ok
          ? `仿真完成 — 甲板可用${trajNote}${missingTrajNote}`
          : `仿真完成 — 甲板不足${trajNote}${missingTrajNote}`;
        this.setStatus(msg, result.deck_launch_ok ? 'ok' : 'error');
      } else {
        this.setStatus(result.error || '仿真失败', 'error');
      }
    } catch (e) {
      this.setData({
        outputText: String(e.message || e),
        outputSummary: '',
        highlights: [],
        resultStale: false,
        outputDetailsOpen: true,
        showTrajectory: false,
        simResult: null,
      });
      this.setStatus(`仿真出错: ${e.message}`, 'error');
    } finally {
      this.setData({ running: false });
    }
  },
});
