/**
 * 导弹射程 Web 前端：预设表来自 data.json，改参数后用 Pyodide 重算。
 */
const PYODIDE_VERSION = '0.26.4';
/** 与 missile-range.html 中 ?v= 同步递增 */
const APP_VERSION = 13;

const MISSILE_RANGE_PY_FILES = [
  'utils/__init__.py',
  'utils/paths.py',
  'utils/database_csv.py',
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
  if (found && found.isp_cruise_s != null) {
    air.hidden = false;
    $('ispAir').value = found.isp_cruise_s;
  } else {
    air.hidden = true;
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
  activeId = row.id;
  syncClassUi();
}

function speedLabel(result) {
  const id = result.missile_class || '';
  if (id === 'ballistic' || id.indexOf('hgv') === 0) return '关机马赫数';
  return '巡航马赫数';
}

function renderResult(result, title) {
  if (!result) {
    $('resultBox').className = 'placeholder';
    $('resultBox').textContent = '无结果';
    return;
  }
  const dual = result.range_high_km != null && result.range_sea_km != null;
  const lead = dual
    ? `<div class="stat"><div class="k">全高空射程</div><div class="v">${fmt(result.range_high_km, 1)}</div><div class="sub">km</div></div>
       <div class="stat"><div class="k">全掠海射程</div><div class="v amber">${fmt(result.range_sea_km, 1)}</div><div class="sub">km</div></div>`
    : `<div class="stat"><div class="k">估算射程</div><div class="v">${fmt(result.range_km, 1)}</div><div class="sub">km</div></div>`;
  const wing = result.m_wing_kg != null
    ? `<div class="stat"><div class="k">折叠弹翼</div><div class="v">${fmt(result.m_wing_kg, 0)}</div><div class="sub">kg</div></div>
       <div class="stat"><div class="k">死重</div><div class="v amber">${fmt(result.m_dead_kg, 0)}</div><div class="sub">kg</div></div>`
    : '';
  const terminal = result.range_terminal_km != null
    ? `<div class="stat"><div class="k">末端冲刺</div><div class="v">${fmt(result.range_terminal_km, 1)}</div><div class="sub">km</div></div>`
    : '';
  $('resultBox').className = '';
  $('resultBox').innerHTML = `
    <div class="stat-row">
      ${lead}
      ${terminal}
      ${wing}
      <div class="stat"><div class="k">${speedLabel(result)}</div><div class="v amber">${fmt(result.v_burnout_mach, 2)}</div><div class="sub">Ma</div></div>
      <div class="stat"><div class="k">升阻比</div><div class="v">${fmt(result.ld_ratio, 2)}</div><div class="sub">L/D</div></div>
      <div class="stat"><div class="k">起飞质量</div><div class="v amber">${fmt(result.m_0_t, 2)}</div><div class="sub">t</div></div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="k">弹头长度</div><div class="v">${fmt(result.l_head_m, 2)}</div><div class="sub">m</div></div>
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
  const body = rows.map((row) => `
    <tr data-id="${row.id}" class="${row.id === activeId ? 'on' : ''}">
      <td>${row.id}</td>
      <td>${row.size_m}</td>
      <td>${row.bay || '—'}</td>
      <td>${row.warhead_kg}</td>
      <td>${kindLabel(row)}</td>
      <td>${row.launch}</td>
      <td>${fmt(row.m_0_t, 2)}</td>
      <td>${fmt(row.v_burnout_mach, 2)}</td>
          <td>${ispLabel(row)}</td>
          <td>${fmt(row.range_km, 1)}</td>
          <td>${row.range_sea_km == null ? '—' : fmt(row.range_sea_km, 1)}</td>
    </tr>
  `).join('');
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
  $('status').textContent = 'PRESET';
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
    $('status').textContent = 'DONE';
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
}

main().catch((err) => {
  $('status').textContent = 'ERROR';
  $('resultBox').className = 'placeholder';
  $('resultBox').textContent = String(err.message || err);
});
