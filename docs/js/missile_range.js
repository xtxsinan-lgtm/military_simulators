/**
 * 导弹射程 Web 前端：预设表来自 data.json，改参数后用 Pyodide 重算。
 */
const PYODIDE_VERSION = '0.26.4';
/** 与 missile-range.html 中 ?v= 同步递增 */
const APP_VERSION = 33;

const MISSILE_RANGE_PY_FILES = [
  'utils/__init__.py',
  'utils/paths.py',
  'utils/database_csv.py',
  'utils/missile_interception/__init__.py',
  'utils/missile_interception/missile_interception_config.py',
  'utils/missile_interception/missile_interception_radar.py',
  'utils/missile_range/__init__.py',
  'utils/missile_range/estimate.py',
  'utils/missile_range/classes.py',
  'utils/missile_range/dataset.py',
  'simulators/__init__.py',
  'simulators/missile_range/__init__.py',
  'simulators/missile_range/missile_range.py',
  'apps/__init__.py',
  'apps/missile_range_web.py',
];

const MISSILE_RANGE_DATA_FILES = [
  'data/missile_range_preset_database.csv',
];

const MISSILE_RANGE_IMPORTS = [
  'utils.paths',
  'utils.database_csv',
  'utils.missile_interception.missile_interception_radar',
  'utils.missile_range.estimate',
  'utils.missile_range.classes',
  'utils.missile_range.dataset',
  'simulators.missile_range.missile_range',
  'apps.missile_range_web',
];

let data = null;
let pyodide = null;
let pyReady = false;
let runLock = false;
let rows = [];
let activeId = null;

function $(id) {
  return document.getElementById(id);
}

function num(id, fallback) {
  const n = Number($(id).value);
  return Number.isFinite(n) ? n : fallback;
}

function fmt(n, d) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-US', {
    maximumFractionDigits: d,
    minimumFractionDigits: d,
  });
}

function readForm() {
  const params = {
    missile_class: $('missileClass').value || 'hgv_biconic',
    length_m: num('lengthM', 0),
    diameter_m: num('diameterM', 0),
    warhead_kg: num('warheadKg', 0),
    v_launch_mach: num('vMach', 0.85),
    h_launch_km: num('hKm', 13),
    isp_s: num('ispS', 264),
    propellant_density: num('density', 1760),
    ballistic_two_stage: $('ballisticTwoStage').checked,
    optimize_geometry: $('optimizeGeometry') ? $('optimizeGeometry').checked : true,
  };
  if (!$('ispAirField').hidden) params.isp_air_s = num('ispAir', 0);
  return params;
}

function classList() {
  return (data && data.missile_range && data.missile_range.classes) || [];
}

function syncClassUi() {
  const id = $('missileClass').value || 'hgv_biconic';
  const found = classList().find((item) => item.id === id);
  if (found && found.blurb) $('classBlurb').textContent = found.blurb;
  const air = $('ispAirField');
  const ballistic = $('ballisticTwoStageField');
  const optGeom = $('optimizeGeometryField');
  if (found && found.isp_cruise_s != null) {
    air.hidden = false;
    $('ispAir').value = found.isp_cruise_s;
  } else {
    air.hidden = true;
  }
  if (id === 'ballistic') {
    ballistic.hidden = false;
    $('ballisticTwoStage').checked = true;
  } else {
    ballistic.hidden = true;
  }
  if (optGeom) {
    optGeom.hidden = !id.startsWith('hgv');
  }
}

function ispLabel(row) {
  const boost = row.isp_boost_s;
  const cruise = row.isp_cruise_s;
  const rocket = row.isp_rocket_s;
  if (cruise != null && boost != null && rocket != null) {
    return `${fmt(boost, 0)}+${fmt(cruise, 0)}/${fmt(rocket, 0)}`;
  }
  if (cruise != null && boost != null) return `${fmt(boost, 0)}+${fmt(cruise, 0)}`;
  if (cruise != null && rocket != null) return `${fmt(cruise, 0)}/${fmt(rocket, 0)}`;
  if (cruise != null) return fmt(cruise, 0);
  if (rocket != null) return fmt(rocket, 0);
  if (boost != null) return fmt(boost, 0);
  return '—';
}

function fillForm(row) {
  $('missileClass').value = row.missile_class || 'hgv_biconic';
  $('lengthM').value = row.length_m;
  $('diameterM').value = row.diameter_m;
  $('warheadKg').value = row.warhead_kg;
  $('vMach').value = row.v_mach;
  $('hKm').value = row.h_km;
  $('ballisticTwoStage').checked = row.missile_class === 'ballistic';
  activeId = row.id;
  syncClassUi();
}

function visibleRows() {
  const failOnly = $('failOnly') && $('failOnly').checked;
  if (!failOnly) return rows;
  return rows.filter((row) => row.reached_takeover === false);
}

function takeoverMeterHtml(result) {
  if (result.mach_takeover == null) return '';
  const boost = result.mach_boost ?? result.v_burnout_mach;
  const frac = result.takeover_progress != null
    ? result.takeover_progress
    : (result.mach_takeover > 0 ? Math.max(0, boost / result.mach_takeover) : 0);
  const pct = Math.round(Math.max(0, Math.min(1, frac)) * 100);
  const failed = result.reached_takeover === false;
  return `<div class="takeover-meter">
    <div class="takeover-meter-head">
      <span>助推接力进度</span>
      <span>Ma ${fmt(boost, 2)} / ${fmt(result.mach_takeover, 2)}</span>
    </div>
    <div class="bar-wrap">
      <div class="bar-bg"><div class="bar-fill ${failed ? 'w' : ''}" style="width:${pct}%"></div></div>
      <span class="bar-cap">${pct}%</span>
    </div>
    <div class="takeover-meter-cap">${failed ? '未达接力速度，冲压未启动' : '已接入冲压巡航'}</div>
  </div>`;
}

function takeoverSummaryHtml() {
  const failed = rows.filter((row) => row.reached_takeover === false).length;
  const ok = rows.filter((row) => row.reached_takeover === true).length;
  if (!failed && !ok) return '';
  return `冲压接力：已接入 ${ok} 发 · <span class="sum-fail">未达工作速度 ${failed} 发</span>。勾选筛选或点红色标签，查看只计弹道弧的短射程。`;
}

function speedLabel(result) {
  const id = result.missile_class || '';
  if (result.reached_takeover === false) return '助推关机马赫';
  if (id === 'ballistic' || id.indexOf('hgv') === 0) return '关机马赫数';
  return '巡航马赫数';
}

function renderResult(result, title) {
  if (!result) {
    $('resultBox').className = 'placeholder';
    $('resultBox').textContent = '无结果';
    return;
  }
  const isFailedTakeover = result.reached_takeover === false;
  const alertHtml = isFailedTakeover
    ? `<div class="takeover-alert">
        <div class="takeover-badge">⚠️ 未达工作速度 (TAKEOVER FAILED)</div>
        <div class="takeover-desc">
          助推级实际仅加速至 <strong>Ma ${fmt(result.mach_boost ?? result.v_burnout_mach, 2)}</strong>，
          低于冲压发动机设计接力速度 <strong>Ma ${fmt(result.mach_takeover, 2)}</strong>。<br>
          冲压发动机无法启动，巡航段有效射程为 <strong>0.0 km</strong>，当前射程仅计助推关机后的纯惯性弹道滑行弧。
        </div>
      </div>`
    : '';

  const dual = result.range_high_km != null && result.range_sea_km != null;
  const lead = dual
    ? `<div class="stat"><div class="k">全高空射程</div><div class="v">${fmt(result.range_high_km, 1)}</div><div class="sub">km</div></div>
       <div class="stat"><div class="k">全掠海射程</div><div class="v amber">${fmt(result.range_sea_km, 1)}</div><div class="sub">km</div></div>`
    : `<div class="stat"><div class="k">${isFailedTakeover ? '弹道滑行射程' : '估算射程'}</div><div class="v ${isFailedTakeover ? 'amber' : ''}">${fmt(result.range_km, 1)}</div><div class="sub">${isFailedTakeover ? 'km (冲压未启动)' : 'km'}</div></div>`;
  const wing = result.m_wing_kg != null
    ? `<div class="stat"><div class="k">折叠弹翼</div><div class="v">${fmt(result.m_wing_kg, 0)}</div><div class="sub">kg</div></div>
       <div class="stat"><div class="k">死重</div><div class="v amber">${fmt(result.m_dead_kg, 0)}</div><div class="sub">kg</div></div>`
    : '';
  const gain = (result.range_gain_km != null && result.range_gain_km > 0)
    ? `<div class="stat"><div class="k">几何增程</div><div class="v cyan">+${fmt(result.range_gain_km, 1)}</div><div class="sub">km</div></div>`
    : '';
  const dHead = result.d_head_m != null
    ? `<div class="stat"><div class="k">滑翔体直径</div><div class="v">${fmt(result.d_head_m, 3)}</div><div class="sub">m</div></div>`
    : '';
  const fineness = result.fineness != null
    ? `<div class="stat"><div class="k">滑翔长细比</div><div class="v">${fmt(result.fineness, 2)}</div><div class="sub">L/D_geom</div></div>`
    : '';

  const takeoverRow = result.mach_takeover != null
    ? `<div class="stat-row">
        <div class="stat"><div class="k">接力设计速度</div><div class="v">${fmt(result.mach_takeover, 2)}</div><div class="sub">Ma (要求)</div></div>
        <div class="stat"><div class="k">助推实际速度</div><div class="v ${isFailedTakeover ? 'red' : 'amber'}">${fmt(result.mach_boost ?? result.v_burnout_mach, 2)}</div><div class="sub">Ma (达成)</div></div>
        <div class="stat"><div class="k">冲压工作状态</div><div class="v ${isFailedTakeover ? 'red' : 'green'}">${isFailedTakeover ? '未启动' : '已接入'}</div><div class="sub">${isFailedTakeover ? '有效巡航 0 km' : '吸气巡航'}</div></div>
        ${result.m_booster_kg != null ? `<div class="stat"><div class="k">助推器全重</div><div class="v amber">${fmt(result.m_booster_kg, 1)}</div><div class="sub">kg</div></div>` : ''}
        ${result.m_fuel_kg != null ? `<div class="stat"><div class="k">巡航燃料</div><div class="v">${fmt(result.m_fuel_kg, 1)}</div><div class="sub">kg</div></div>` : ''}
      </div>`
    : '';

  $('resultBox').className = '';
  $('resultBox').innerHTML = `
    ${alertHtml}
    ${takeoverMeterHtml(result)}
    ${takeoverRow}
    <div class="stat-row">
      ${lead}
      ${gain}
      ${wing}
      <div class="stat"><div class="k">${speedLabel(result)}</div><div class="v ${isFailedTakeover ? 'red' : 'amber'}">${fmt(result.v_burnout_mach, 2)}</div><div class="sub">Ma</div></div>
      <div class="stat"><div class="k">升阻比</div><div class="v">${fmt(result.ld_ratio, 2)}</div><div class="sub">L/D</div></div>
      <div class="stat"><div class="k">起飞质量</div><div class="v amber">${fmt(result.m_0_t, 2)}</div><div class="sub">t</div></div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="k">弹头长度</div><div class="v">${fmt(result.l_head_m, 2)}</div><div class="sub">m</div></div>
      ${dHead}
      ${fineness}
      <div class="stat"><div class="k">助推/弹体</div><div class="v">${fmt(result.l_booster_m, 2)}</div><div class="sub">m</div></div>
      <div class="stat"><div class="k">燃料或推进剂</div><div class="v">${fmt(result.m_p_total_kg, 1)}</div><div class="sub">kg</div></div>
      ${result.isp_boost_s != null ? `<div class="stat"><div class="k">助推比冲</div><div class="v">${fmt(result.isp_boost_s, 0)}</div><div class="sub">s</div></div>` : ''}
      ${result.isp_cruise_s != null ? `<div class="stat"><div class="k">吸气比冲</div><div class="v amber">${fmt(result.isp_cruise_s, 0)}</div><div class="sub">s</div></div>` : ''}
      ${result.isp_rocket_s != null ? `<div class="stat"><div class="k">固体比冲</div><div class="v">${fmt(result.isp_rocket_s, 0)}</div><div class="sub">s</div></div>` : ''}
    </div>
    <p class="note">${result.note || title || ''}</p>
  `;
}

function kindLabel(row) {
  return row.class_label || row.missile_class;
}

function renderTable() {
  const shown = visibleRows();
  const summary = $('takeoverSummary');
  if (summary) summary.innerHTML = takeoverSummaryHtml();
  if (!shown.length) {
    $('tableBox').innerHTML = '<p class="note">当前筛选下没有未达工作速度的样本。</p>';
    return;
  }
  const body = shown.map((row) => {
    const isFailed = row.reached_takeover === false;
    const kindBadge = isFailed
      ? `<span class="tag-alert" title="助推未达接力工作速度，仅弹道弧">未达工作速度</span>`
      : '';
    const rangeSub = isFailed
      ? `<br><span style="color:var(--red);font-size:9.5px">(未达工作速度)</span>`
      : '';
    const rowClass = [
      row.id === activeId ? 'on' : '',
      isFailed ? 'fail-takeover' : '',
    ].filter(Boolean).join(' ');
    return `
    <tr data-id="${row.id}" class="${rowClass}">
      <td>${row.id}</td>
      <td>${row.size_m}</td>
      <td>${row.bay || '—'}</td>
      <td>${row.warhead_kg}</td>
      <td>${kindLabel(row)}${kindBadge}</td>
      <td>${row.launch}</td>
      <td>${fmt(row.m_0_t, 2)}</td>
      <td>${fmt(row.v_burnout_mach, 2)}</td>
      <td>${ispLabel(row)}</td>
      <td>${fmt(row.range_km, 1)}${rangeSub}</td>
      <td>${row.range_sea_km == null ? '—' : fmt(row.range_sea_km, 1)}</td>
    </tr>
  `;
  }).join('');
  $('tableBox').innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th><th>尺寸 m</th><th>载机</th><th>弹头 kg</th><th>弹种</th><th>发射条件</th>
          <th>起飞 t</th><th>Ma</th><th>比冲 s</th><th>射程 km</th><th>掠海 km</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function fillClassSelect() {
  const options = classList();
  $('missileClass').innerHTML = options.map((item) => (
    `<option value="${item.id}">${item.label}</option>`
  )).join('');
}

function fillPresetSelect() {
  const classes = classList();
  if (!classes.length) {
    $('preset').innerHTML = rows.map((row) => (
      `<option value="${row.id}">${row.name}</option>`
    )).join('');
    return;
  }
  $('preset').innerHTML = classes.map((item) => {
    const opts = rows
      .filter((row) => row.missile_class === item.id)
      .map((row) => `<option value="${row.id}">${row.name}</option>`)
      .join('');
    return opts ? `<optgroup label="${item.label}">${opts}</optgroup>` : '';
  }).join('');
}

function selectPreset(id) {
  const row = rows.find((item) => String(item.id) === String(id));
  if (!row) return;
  $('preset').value = String(row.id);
  fillForm(row);
  renderResult(row, row.name);
  renderTable();
  const isFailed = row.reached_takeover === false;
  $('status').innerHTML = isFailed
    ? '<span style="color:var(--red);font-weight:bold">⚠️ 未达工作速度</span>'
    : 'PRESET';
}

async function loadPythonModules() {
  pyodide.runPython(`
import sys
from pathlib import Path
Path('/py').mkdir(parents=True, exist_ok=True)
if '/py' not in sys.path:
    sys.path.insert(0, '/py')
`);
  for (const name of MISSILE_RANGE_PY_FILES) {
    const code = data.py_sources[name];
    if (!code) throw new Error(`缺少 Python 模块: ${name}`);
    const parts = name.split('/');
    let dir = '/py';
    for (let i = 0; i < parts.length - 1; i += 1) {
      dir += `/${parts[i]}`;
      try { pyodide.FS.mkdir(dir); } catch { /* 目录已存在 */ }
    }
    pyodide.FS.writeFile(`/py/${name}`, code);
  }
  for (const name of (data.py_data_files || MISSILE_RANGE_DATA_FILES)) {
    const code = data.py_sources[name];
    if (!code) throw new Error(`缺少数据文件: ${name}`);
    const parts = name.split('/');
    let dir = '/py';
    for (let i = 0; i < parts.length - 1; i += 1) {
      dir += `/${parts[i]}`;
      try { pyodide.FS.mkdir(dir); } catch { /* 目录已存在 */ }
    }
    pyodide.FS.writeFile(`/py/${name}`, code);
  }
  pyodide.globals.set(
    '_missile_interception_cfg',
    JSON.stringify(data.missile_interception_config || {}),
  );
  await pyodide.runPythonAsync(`
import json
from utils.missile_interception.missile_interception_config import inject_missile_interception_config
inject_missile_interception_config(json.loads(_missile_interception_cfg))
`);
  pyodide.globals.set('_py_import_order', MISSILE_RANGE_IMPORTS);
  await pyodide.runPythonAsync(`
import importlib
for _name in _py_import_order:
    importlib.import_module(_name)
`);
}

async function initPyodide() {
  if (pyReady) return;
  $('clock').textContent = 'LOADING';
  const { loadPyodide } = await import(
    `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.mjs`
  );
  pyodide = await loadPyodide();
  await loadPythonModules();
  pyReady = true;
  $('clock').textContent = 'READY';
}

async function callPython(action, params) {
  const payload = JSON.stringify({ action, params });
  pyodide.globals.set('_missile_range_payload', payload);
  const raw = await pyodide.runPythonAsync(`
import json
from apps.missile_range_web import run_missile_range_json
json.dumps(run_missile_range_json(_missile_range_payload), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

async function runEstimate() {
  if (runLock) return;
  runLock = true;
  $('runBtn').disabled = true;
  $('status').textContent = 'RUNNING';
  try {
    await initPyodide();
    const res = await callPython('estimate', readForm());
    if (!res.success) throw new Error(res.error || '估算失败');
    if (Array.isArray(res.rows) && res.rows.length) rows = res.rows;
    activeId = null;
    renderResult(res.result, '当前参数');
    renderTable();
    const isFailed = res.result && res.result.reached_takeover === false;
    $('status').innerHTML = isFailed
      ? '<span style="color:var(--red);font-weight:bold">⚠️ 未达工作速度</span>'
      : 'DONE';
  } catch (err) {
    $('status').textContent = 'ERROR';
    $('resultBox').className = 'placeholder';
    $('resultBox').textContent = String(err.message || err);
  } finally {
    runLock = false;
    $('runBtn').disabled = false;
  }
}

async function main() {
  const resp = await fetch(`data.json?v=${APP_VERSION}`);
  if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
  data = await resp.json();
  const block = data.missile_range;
  if (!block || !Array.isArray(block.cases) || !block.cases.length) {
    throw new Error('data.json 缺少 missile_range，请运行 python3 scripts/build_all.py');
  }
  rows = block.cases;
  const defaults = block.defaults || {};
  if (defaults.isp_s != null) $('ispS').value = defaults.isp_s;
  if (defaults.propellant_density != null) $('density').value = defaults.propellant_density;
  if (defaults.ballistic_two_stage != null) $('ballisticTwoStage').checked = !!defaults.ballistic_two_stage;
  fillClassSelect();
  fillPresetSelect();
  renderTable();
  selectPreset(rows[0].id);
  $('missileClass').addEventListener('change', () => syncClassUi());
  $('preset').addEventListener('change', () => selectPreset($('preset').value));
  $('tableBox').addEventListener('click', (event) => {
    const tr = event.target.closest('tr[data-id]');
    if (tr) selectPreset(tr.dataset.id);
  });
  $('runBtn').addEventListener('click', () => { runEstimate(); });
  $('failOnly').addEventListener('change', () => {
    const shown = visibleRows();
    renderTable();
    if ($('failOnly').checked && shown.length && !shown.some((row) => row.id === activeId)) {
      selectPreset(shown[0].id);
    }
  });
}

main().catch((err) => {
  $('status').textContent = 'ERROR';
  $('resultBox').className = 'placeholder';
  $('resultBox').textContent = String(err.message || err);
});
