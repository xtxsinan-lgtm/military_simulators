import {
  a2aMassKg,
  computeAircraftAero,
  computeSkiJumpArc,
  defaultDeckWindKt,
  filterAircraftForMode,
  filterCarriersForMode,
  fmtInt,
  fmtNum,
  maxPayloadKg,
  resolveCarrierSkiJump,
} from './physics.js';

const PYODIDE_VERSION = '0.26.4';
/** 与 takeoff.html 中 app.js?v= 及 data.json?v= 同步递增，避免 CDN/浏览器缓存旧资源 */
const APP_VERSION = 23;
let data = null;
let pyodide = null;
let pyReady = false;
let currentMode = 'ski_jump';
let currentStrategy = 'A';
let skiGeom = null;

const els = {};

function $(id) {
  return document.getElementById(id);
}

async function loadData() {
  const resp = await fetch(`data.json?v=${APP_VERSION}`);
  if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
  data = await resp.json();
  if (!data.py_sources) {
    throw new Error('data.json 缺少 py_sources，请运行 python3 scripts/build_docs.py');
  }
}

async function loadPythonModules() {
  pyodide.runPython(`
import sys
from pathlib import Path
Path('/py').mkdir(parents=True, exist_ok=True)
if '/py' not in sys.path:
    sys.path.insert(0, '/py')
`);

  for (const name of data.py_load_order) {
    const code = data.py_sources[name];
    if (code === undefined || code === null) {
      throw new Error(`缺少 Python 模块: ${name}`);
    }
    const parts = name.split('/');
    if (parts.length > 1) {
      let dir = '/py';
      for (let i = 0; i < parts.length - 1; i++) {
        dir += `/${parts[i]}`;
        try {
          pyodide.FS.mkdir(dir);
        } catch {
          /* already exists */
        }
      }
    }
    pyodide.FS.writeFile(`/py/${name}`, code);
  }

  pyodide.globals.set('_takeoff_cfg', JSON.stringify(data.takeoff_config || {}));
  await pyodide.runPythonAsync(`
import json
from utils.takeoff.takeoff_config import inject_takeoff_config
inject_takeoff_config(json.loads(_takeoff_cfg))
`);

  const importOrder = (data.py_import_order || data.py_load_order.map((n) => n.replace(/\.py$/, '').replace(/\//g, '.')))
    .filter((name) => !name.includes('missile_interception'));
  for (const moduleName of importOrder) {
    try {
      await pyodide.runPythonAsync(
        `import importlib\nimportlib.import_module(${JSON.stringify(moduleName)})`
      );
    } catch (error) {
      throw new Error(`Python 模块加载失败 (${moduleName}): ${error.message || error}`);
    }
  }
}

function setStatus(text, cls = '') {
  els.status.textContent = text;
  els.status.className = cls;
}

/** 仿真输出卡片标题右侧：优先用 API output_summary，否则本地拼装 */
function formatOutputSummary(result) {
  if (result?.output_summary) return result.output_summary;
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

function setOutputSummary(text) {
  if (!els.outputSummary) return;
  els.outputSummary.textContent = text || '';
}

function modeNeedsSkiJump(mode) {
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}

function modeNeedsStovlStrategy(mode) {
  return (
    mode === 'short_takeoff' ||
    mode === 'short_ski_jump' ||
    mode === 'tiltrotor_short_takeoff'
  );
}

function modeAllowsStrategyC(mode) {
  return mode === 'short_takeoff' || mode === 'short_ski_jump';
}

function strategyDescriptionMap(mode) {
  const cfg = data?.takeoff_config;
  if (!cfg) return {};
  return mode === 'tiltrotor_short_takeoff'
    ? cfg.tiltrotor_strategy_descriptions || {}
    : cfg.stovl_strategy_descriptions || {};
}

function currentStrategyDescription() {
  const descs = strategyDescriptionMap(currentMode);
  return descs[currentStrategy] || '';
}

function refreshStrategySection() {
  const show = modeNeedsStovlStrategy(currentMode);
  els.strategySection.classList.toggle('hidden', !show);
  const allowC = modeAllowsStrategyC(currentMode);
  if (els.strategyBtnC) {
    els.strategyBtnC.classList.toggle('hidden', !allowC);
  }
  if (els.strategyTitle) {
    els.strategyTitle.textContent =
      currentMode === 'tiltrotor_short_takeoff' ? '短舱倾转策略' : '喷口策略';
  }
  if (!allowC && currentStrategy === 'C') {
    currentStrategy = 'A';
  }
  els.strategyBtns.forEach((btn) => {
    if (btn.dataset.strategy === 'C' && !allowC) {
      btn.classList.remove('active');
      return;
    }
    btn.classList.toggle('active', btn.dataset.strategy === currentStrategy);
  });
  if (els.strategyDesc) {
    const text = show ? currentStrategyDescription() : '';
    els.strategyDesc.textContent = text;
    els.strategyDesc.classList.toggle('hidden', !text);
  }
}

function populateModeButtons() {
  /** 模式按钮由 data.modes 生成，与小程序 / catalog 同源，避免硬编码漏同步。 */
  const modes = data.modes || {};
  const ids = Object.keys(modes);
  if (!ids.length) {
    throw new Error('data.json 缺少 modes，请运行 python3 scripts/build_all.py');
  }
  if (!modes[currentMode]) {
    currentMode = ids[0];
  }
  els.modeGroup.innerHTML = ids
    .map(
      (id) =>
        `<button type="button" class="mode-btn" data-mode="${id}">${modes[id]}</button>`
    )
    .join('');
  els.modeBtns = [...els.modeGroup.querySelectorAll('.mode-btn')];
}

function refreshModeButtons() {
  els.modeBtns.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === currentMode);
  });
  els.skiJumpSection.classList.toggle('hidden', !modeNeedsSkiJump(currentMode));
  refreshStrategySection();
}

function populateCarriers() {
  const list = filterCarriersForMode(currentMode, data.carriers);
  els.carrierSelect.innerHTML =
    list.length === 0
      ? '<option value="">（无可用航母）</option>'
      : list.map((c) => `<option value="${c.id}">${c.name}（${c.nation}）</option>`).join('');
  updateCarrierInfo();
}

function populateAircraft() {
  const list = filterAircraftForMode(currentMode, data.aircraft);
  els.aircraftSelect.innerHTML =
    list.length === 0
      ? '<option value="">（无可用战斗机）</option>'
      : list.map((a) => `<option value="${a.id}">${a.name}</option>`).join('');
  updateAircraftInfo();
}

function getSelectedCarrier() {
  const id = els.carrierSelect.value;
  return data.carriers.find((c) => c.id === id) || null;
}

function getSelectedAircraft() {
  const id = els.aircraftSelect.value;
  return data.aircraft.find((a) => a.id === id) || null;
}

function updateSkiJumpFromInputs() {
  const carrier = getSelectedCarrier();
  if (!carrier || !carrier.ski_jump) {
    skiGeom = null;
    return;
  }
  const angle = parseFloat(els.skiAngle.value);
  const arcLen = parseFloat(els.skiArcLength.value);
  if (Number.isNaN(angle) || angle <= 0) return;
  try {
    skiGeom = computeSkiJumpArc(
      angle,
      null,
      Number.isNaN(arcLen) || arcLen <= 0 ? null : arcLen
    );
    els.skiHeight.value = skiGeom.lip_height_m.toFixed(2);
    els.skiHorizontal.textContent = fmtNum(skiGeom.horizontal_m, 1);
  } catch (e) {
    skiGeom = null;
  }
}

function updateCarrierInfo() {
  const c = getSelectedCarrier();
  if (!c) {
    els.carrierSpecs.innerHTML = '<tr><td colspan="2">请选择航母</td></tr>';
    return;
  }

  if (c.ski_jump) {
    const base = resolveCarrierSkiJump(c);
    els.skiAngle.value = base.angle_deg;
    els.skiArcLength.value = base.arc_length_m.toFixed(1);
    updateSkiJumpFromInputs();
  }

  els.carrierSpecs.innerHTML = `
    <tr><th>最大航速</th><td>${fmtInt(c.max_speed_kt)} kt</td></tr>
    <tr><th>甲板总长度</th><td>${fmtNum(c.total_deck_length_m, 1)} m</td></tr>
    ${c.ski_jump ? '<tr><th>滑跃甲板</th><td>是 <span class="badge">参数可编辑</span></td></tr>' : '<tr><th>滑跃甲板</th><td>否（平直甲板）</td></tr>'}
  `;

  els.skiJumpSection.classList.toggle(
    'hidden',
    !modeNeedsSkiJump(currentMode) || !c.ski_jump
  );

  if (!els.windInput.dataset.userEdited) {
    const wind = defaultDeckWindKt(c);
    if (wind != null) els.windInput.value = wind;
  }
}

function updateAircraftInfo() {
  const ac = getSelectedAircraft();
  if (!ac) {
    els.aircraftSpecs.innerHTML = '<tr><td colspan="2">请选择战斗机</td></tr>';
    return;
  }

  const aero = computeAircraftAero(ac);
  const isVtol = ac.type_label === 'v/stol';
  const isTilt = ac.type_label === 'tiltrotor';

  let thrustRows = '';
  if (isVtol) {
    thrustRows = `
      <tr><th>主喷管推力 (15°C SL)</th><td>${fmtNum(ac.t_main_stovl_sl_n / 1000, 1)} kN</td></tr>
      <tr><th>升力风扇推力</th><td>${fmtNum(ac.t_liftfan_sl_n / 1000, 1)} kN</td></tr>
      <tr><th>滚转喷管推力</th><td>${fmtNum(ac.t_rollposts_sl_n / 1000, 1)} kN</td></tr>
    `;
  } else if (isTilt) {
    thrustRows = `
      <tr><th>总轴功率 (15°C SL)</th><td>${fmtNum(ac.shaft_power_sl_w / 1e6, 2)} MW</td></tr>
      <tr><th>桨盘直径</th><td>${fmtNum(ac.prop_diameter_m, 2)} m</td></tr>
      <tr><th>短舱遮挡比</th><td>${fmtNum((ac.nacelle_blockage_frac ?? 0.1) * 100, 0)} %</td></tr>
    `;
  } else {
    thrustRows = `<tr><th>最大加力推力 (15°C SL)</th><td>${fmtNum(ac.t_max_sl_n / 1000, 1)} kN</td></tr>`;
  }

  const massLabel = isTilt
    ? '默认起飞重量（空重+内油+机组）'
    : '4枚中距弹满内油空战起飞重量';

  els.aircraftSpecs.innerHTML = `
    <tr><th>最大起飞重量 (MTOW)</th><td>${fmtInt(ac.mtow_kg)} kg</td></tr>
    <tr><th>最大内油</th><td>${fmtInt(ac.internal_fuel_kg)} kg</td></tr>
    <tr><th>中距弹型号</th><td>${ac.bvr_missile}</td></tr>
    <tr><th>中距弹重量</th><td>${fmtNum(ac.missile_mass_kg, 1)} kg/枚</td></tr>
    <tr><th>最大载弹量</th><td>${fmtInt(maxPayloadKg(ac))} kg</td></tr>
    <tr><th>${massLabel}</th><td>${fmtInt(a2aMassKg(ac))} kg</td></tr>
    <tr><th>翼展</th><td>${fmtNum(ac.wingspan_m, 2)} m</td></tr>
    <tr><th>翼面积</th><td>${fmtNum(ac.wing_area_m2, 2)} m²</td></tr>
    ${thrustRows}
    <tr><th>前缘后掠角</th><td>${fmtNum(ac.sweep_le_deg, 1)}°</td></tr>
    <tr><th>展弦比</th><td>${fmtNum(aero.aspect_ratio, 3)}</td></tr>
    <tr><th>升力线斜率 C_Lα</th><td>${fmtNum(aero.cl_alpha_per_rad, 4)} /rad</td></tr>
    <tr><th>滑行升力系数 Cl_taxi</th><td>${fmtNum(aero.cl_taxi, 4)}（迎角 ${fmtNum(aero.taxi_alpha_deg, 1)}°）</td></tr>
    <tr><th>20° 攻角升力系数</th><td>${fmtNum(aero.cl_20deg, 4)}</td></tr>
    <tr><th>零升阻力系数 Cd0</th><td>${fmtNum(aero.cd0, 4)}</td></tr>
  `;

  if (!els.massInput.dataset.userEdited) {
    els.massInput.value = Math.round(a2aMassKg(ac));
  }
}

async function initPyodide() {
  if (pyReady) return;
  setStatus('正在加载 Python 仿真引擎（首次约需 20–40 秒）…', 'loading');
  els.runBtn.disabled = true;

  const { loadPyodide } = await import(
    `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.mjs`
  );
  pyodide = await loadPyodide();
  await pyodide.loadPackage('numpy');

  try {
    await loadPythonModules();
  } catch (e) {
    throw new Error(`Python 模块加载失败: ${e.message}`);
  }

  pyReady = true;
  els.runBtn.disabled = false;
  setStatus('仿真引擎已就绪', 'ok');
}

function modeHasTrajectory(mode) {
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}

function hideTrajectory() {
  els.trajectorySection.classList.add('hidden');
  if (els.trajectoryMeta) els.trajectoryMeta.textContent = '';
}

function xAxisStepM(maxX) {
  if (maxX <= 80) return 10;
  if (maxX <= 200) return 20;
  if (maxX <= 400) return 50;
  return 100;
}

function resolveTakeoffX(result, deckPts, traj) {
  const deckExit = traj.find((p) => p.phase === 'deck_exit');
  if (deckExit) return deckExit.x;
  if (result.deck_profile?.takeoff_distance_m != null) {
    return result.deck_profile.takeoff_distance_m;
  }
  if (result.distance_m != null) return result.distance_m;
  return deckPts[deckPts.length - 1][0];
}

function paintTrajectoryCanvas(result) {
  const canvas = els.trajectoryCanvas;
  const ctx = canvas.getContext('2d');
  // 从 hidden 恢复后首帧 getBoundingClientRect 可能为 0，回退到父级/属性宽度
  const rect = canvas.getBoundingClientRect();
  const parent = canvas.parentElement;
  const parentW = parent ? parent.clientWidth : 0;
  const cssW = Math.max(rect.width || parentW || Number(canvas.getAttribute('width')) || 1060, 320);
  const cssH = Math.max(rect.height || Number(canvas.getAttribute('height')) || 320, 200);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const deckPts = result.deck_profile.points;
  const traj = result.trajectory;
  const takeoffX = resolveTakeoffX(result, deckPts, traj);
  const takeoffLabelM = result.distance_m ?? result.deck_profile?.takeoff_distance_m ?? takeoffX;
  const carrierDeckM = result.deck_profile.total_deck_length_m;

  const xs = [...deckPts.map((p) => p[0]), ...traj.map((p) => p.x), takeoffX];
  if (carrierDeckM) xs.push(carrierDeckM);
  const ys = [...deckPts.map((p) => p[1]), ...traj.map((p) => p.y)];
  const minX = 0;
  const maxX = Math.max(...xs, 1) * 1.08;
  const minY = Math.min(0, ...ys) - 2;
  const maxY = Math.max(...ys, result.deck_profile.lip_height_m || 0, 1) + 8;

  const pad = { l: 48, r: 16, t: 28, b: 44 };
  const plotW = cssW - pad.l - pad.r;
  const plotH = cssH - pad.t - pad.b;

  const toX = (x) => pad.l + ((x - minX) / (maxX - minX)) * plotW;
  const toY = (y) => pad.t + plotH - ((y - minY) / (maxY - minY)) * plotH;

  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = '#1a2332';
  ctx.fillRect(0, 0, cssW, cssH);

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.15)';
  ctx.lineWidth = 1;
  const xStep = xAxisStepM(maxX);
  for (let gx = 0; gx <= maxX; gx += xStep) {
    ctx.beginPath();
    ctx.moveTo(toX(gx), pad.t);
    ctx.lineTo(toX(gx), pad.t + plotH);
    ctx.stroke();
  }
  for (let gy = Math.ceil(minY / 5) * 5; gy <= maxY; gy += 5) {
    ctx.beginPath();
    ctx.moveTo(pad.l, toY(gy));
    ctx.lineTo(pad.l + plotW, toY(gy));
    ctx.stroke();
  }

  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let gx = 0; gx <= maxX; gx += xStep) {
    ctx.fillText(String(Math.round(gx)), toX(gx), pad.t + plotH + 6);
  }
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText('水平距离 (m)', pad.l + plotW / 2, cssH - 6);
  ctx.save();
  ctx.translate(14, pad.t + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('高度 (m)', 0, 0);
  ctx.restore();

  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let gy = Math.ceil(minY / 5) * 5; gy <= maxY; gy += 10) {
    ctx.fillText(String(gy), pad.l - 6, toY(gy));
  }

  ctx.strokeStyle = '#f87171';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(toX(takeoffX), pad.t);
  ctx.lineTo(toX(takeoffX), pad.t + plotH);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = '#f87171';
  ctx.font = '600 11px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText(`滑跑 ${fmtNum(takeoffLabelM, 1)} m`, toX(takeoffX), pad.t - 6);

  ctx.strokeStyle = '#64748b';
  ctx.lineWidth = 3;
  ctx.beginPath();
  deckPts.forEach(([x, y], i) => {
    if (i === 0) ctx.moveTo(toX(x), toY(y));
    else ctx.lineTo(toX(x), toY(y));
  });
  ctx.stroke();

  ctx.fillStyle = 'rgba(100, 116, 139, 0.25)';
  ctx.beginPath();
  deckPts.forEach(([x, y], i) => {
    if (i === 0) ctx.moveTo(toX(x), toY(y));
    else ctx.lineTo(toX(x), toY(y));
  });
  ctx.lineTo(toX(deckPts[deckPts.length - 1][0]), toY(minY));
  ctx.lineTo(toX(deckPts[0][0]), toY(minY));
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  traj.forEach((p, i) => {
    if (i === 0) ctx.moveTo(toX(p.x), toY(p.y));
    else ctx.lineTo(toX(p.x), toY(p.y));
  });
  ctx.stroke();

  const first = traj[0];
  const deckExit = traj.find((p) => p.phase === 'deck_exit');
  const last = traj[traj.length - 1];
  for (const [pt, color] of [
    [first, '#4ade80'],
    ...(deckExit ? [[deckExit, '#fb923c']] : []),
    [last, '#fbbf24'],
  ]) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(toX(pt.x), toY(pt.y), 5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawTrajectory(result) {
  if (!modeHasTrajectory(currentMode)) {
    hideTrajectory();
    return;
  }
  if (!result?.trajectory?.length || !result?.deck_profile?.points?.length) {
    hideTrajectory();
    return;
  }

  els.trajectorySection.classList.remove('hidden');
  const deckPts = result.deck_profile.points;
  const takeoffX = resolveTakeoffX(result, deckPts, result.trajectory);
  const takeoffLabelM = result.distance_m ?? result.deck_profile?.takeoff_distance_m ?? takeoffX;
  if (els.trajectoryMeta) {
    els.trajectoryMeta.textContent =
      `滑跑距离 ${fmtNum(takeoffLabelM, 1)} m · ` +
      `${result.trajectory.length} 个采样点 · ` +
      `最大高度 ${fmtNum(Math.max(...result.trajectory.map((p) => p.y)), 1)} m`;
  }

  // 双 rAF：先完成取消 hidden 的布局，再测量 canvas 尺寸绘制
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      paintTrajectoryCanvas(result);
      els.trajectorySection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });
}

async function runSimulation() {
  const carrier = getSelectedCarrier();
  const aircraft = getSelectedAircraft();
  if (!carrier || !aircraft) {
    setStatus('请选择航母和战斗机', 'error');
    return;
  }

  const mass = parseFloat(els.massInput.value);
  const temp = parseFloat(els.tempInput.value);
  const wind = parseFloat(els.windInput.value);
  if ([mass, temp, wind].some((v) => Number.isNaN(v))) {
    setStatus('请填写有效的重量、温度和甲板风', 'error');
    return;
  }

  try {
    if (!pyReady) await initPyodide();
  } catch (e) {
    setStatus(`引擎加载失败: ${e.message}`, 'error');
    return;
  }

  els.runBtn.disabled = true;
  setStatus('仿真计算中（可能需要数秒至数十秒）…', 'loading');
  els.output.classList.remove('empty');
  els.output.textContent = '计算中…';
  setOutputSummary('');
  hideTrajectory();

  const payload = {
    mode: currentMode,
    aircraft,
    carrier,
    mass_kg: mass,
    temp_c: temp,
    wind_kt: wind,
    total_deck_length_m: carrier.total_deck_length_m,
  };

  if (modeNeedsStovlStrategy(currentMode)) {
    payload.strategy = currentStrategy;
  }

  if (modeNeedsSkiJump(currentMode) && carrier.ski_jump) {
    updateSkiJumpFromInputs();
    payload.ski_jump_angle_deg = parseFloat(els.skiAngle.value);
    payload.ski_jump_arc_length_m = parseFloat(els.skiArcLength.value);
    payload.ski_jump_height_m = parseFloat(els.skiHeight.value);
  }

  try {
    pyodide.globals.set('_payload_json', JSON.stringify(payload));
    const raw = pyodide.runPython(`
import json
from apps.web_simulator import run_simulation_json
json.dumps(run_simulation_json(_payload_json), ensure_ascii=False)
`);
    const result = JSON.parse(raw);
    els.output.textContent = result.output || '(无输出)';
    if (result.success) {
      drawTrajectory(result);
      setOutputSummary(formatOutputSummary(result));
      const trajNote =
        modeHasTrajectory(currentMode) && result.trajectory?.length
          ? ` · 轨迹 ${result.trajectory.length} 点`
          : '';
      setStatus(
        (result.deck_launch_ok ? '仿真完成 — 甲板可用' : '仿真完成 — 甲板不足') + trajNote,
        result.deck_launch_ok ? 'ok' : 'error'
      );
    } else {
      hideTrajectory();
      setOutputSummary('');
      setStatus(result.error || '仿真失败', 'error');
    }
  } catch (e) {
    hideTrajectory();
    els.output.textContent = String(e);
    setOutputSummary('');
    setStatus(`仿真出错: ${e.message}`, 'error');
  } finally {
    els.runBtn.disabled = false;
  }
}

function bindEvents() {
  // 事件委托：模式按钮可能在 populateModeButtons 后重建
  els.modeGroup.addEventListener('click', (e) => {
    const btn = e.target.closest('.mode-btn');
    if (!btn || !els.modeGroup.contains(btn)) return;
    currentMode = btn.dataset.mode;
    refreshModeButtons();
    populateCarriers();
    populateAircraft();
    els.massInput.dataset.userEdited = '';
    els.windInput.dataset.userEdited = '';
  });

  els.strategyBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      currentStrategy = btn.dataset.strategy;
      refreshStrategySection();
    });
  });

  els.carrierSelect.addEventListener('change', () => {
    els.windInput.dataset.userEdited = '';
    updateCarrierInfo();
  });

  els.aircraftSelect.addEventListener('change', () => {
    els.massInput.dataset.userEdited = '';
    updateAircraftInfo();
  });

  els.skiAngle.addEventListener('input', updateSkiJumpFromInputs);
  els.skiArcLength.addEventListener('input', updateSkiJumpFromInputs);

  els.windInput.addEventListener('input', () => {
    els.windInput.dataset.userEdited = '1';
  });
  els.massInput.addEventListener('input', () => {
    els.massInput.dataset.userEdited = '1';
  });

  els.runBtn.addEventListener('click', runSimulation);

  els.preloadBtn.addEventListener('click', () => initPyodide().catch((e) => setStatus(e.message, 'error')));
}

function applyTakeoffUiDefaults() {
  const ui = data?.takeoff_config?.ui;
  if (!ui) return;
  if (ui.default_temp_c != null && els.tempInput) {
    els.tempInput.value = ui.default_temp_c;
  }
  if (ui.default_mode) currentMode = ui.default_mode;
  if (ui.default_strategy) currentStrategy = ui.default_strategy;
}

async function main() {
  els.modeGroup = $('modeGroup');
  els.headerSubtitle = $('headerSubtitle');
  els.modeBtns = [];
  els.strategyBtns = [...document.querySelectorAll('.strategy-btn')];
  els.strategySection = $('strategySection');
  els.strategyDesc = $('strategyDesc');
  els.strategyBtnC = $('strategyBtnC');
  els.strategyTitle = $('strategyTitle');
  els.carrierSelect = $('carrierSelect');
  els.aircraftSelect = $('aircraftSelect');
  els.carrierSpecs = $('carrierSpecs');
  els.aircraftSpecs = $('aircraftSpecs');
  els.skiJumpSection = $('skiJumpSection');
  els.skiAngle = $('skiAngle');
  els.skiArcLength = $('skiArcLength');
  els.skiHeight = $('skiHeight');
  els.skiHorizontal = $('skiHorizontal');
  els.windInput = $('windInput');
  els.tempInput = $('tempInput');
  els.massInput = $('massInput');
  els.runBtn = $('runBtn');
  els.preloadBtn = $('preloadBtn');
  els.output = $('output');
  els.outputSummary = $('outputSummary');
  els.status = $('status');
  els.trajectorySection = $('trajectorySection');
  els.trajectoryCanvas = $('trajectoryCanvas');
  els.trajectoryMeta = $('trajectoryMeta');

  try {
    await loadData();
    applyTakeoffUiDefaults();
    populateModeButtons();
  } catch (e) {
    setStatus(e.message, 'error');
    return;
  }

  refreshModeButtons();
  populateCarriers();
  populateAircraft();
  bindEvents();

  applyTakeoffUiDefaults();
  setStatus('页面已加载。点击「预加载引擎」或「开始仿真」时将加载 Python 引擎。', '');

  const clockEl = $('takeoffClock');
  function tickClock() {
    if (!clockEl) return;
    clockEl.textContent = new Date().toTimeString().slice(0, 8) + ' · SIM CLOCK';
  }
  tickClock();
  setInterval(tickClock, 1000);
}

main();
