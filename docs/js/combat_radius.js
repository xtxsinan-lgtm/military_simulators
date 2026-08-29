/**
 * 作战半径 Web 前端：选择战机加载预计算仪表盘；改参数后自动重算；下方三个按需查询走 Pyodide。
 */
const PYODIDE_VERSION = '0.26.4';
/** 与 combat-radius.html 中 ?v= 同步递增 */
const APP_VERSION = 9;

const COMBAT_RADIUS_PY_FILES = [
  'utils/__init__.py',
  'utils/paths.py',
  'utils/combat_radius/__init__.py',
  'utils/combat_radius/combat_radius_config.py',
  'utils/database_csv.py',
  'utils/combat_radius/lift_drag.py',
  'utils/combat_radius/military_thrust.py',
  'utils/combat_radius/engine_efficiency.py',
  'utils/combat_radius/cruise_load.py',
  'utils/combat_radius/breguet.py',
  'utils/combat_radius/cruise_search.py',
  'utils/combat_radius/max_speed_search.py',
  'utils/combat_radius/combat_radius_presets.py',
  'simulators/__init__.py',
  'simulators/combat_radius/__init__.py',
  'simulators/combat_radius/combat_radius.py',
  'apps/__init__.py',
  'apps/combat_radius_web.py',
];

const COMBAT_RADIUS_IMPORTS = [
  'utils.paths',
  'utils.combat_radius.combat_radius_config',
  'utils.database_csv',
  'utils.combat_radius.lift_drag',
  'utils.combat_radius.military_thrust',
  'utils.combat_radius.engine_efficiency',
  'utils.combat_radius.cruise_load',
  'utils.combat_radius.breguet',
  'utils.combat_radius.cruise_search',
  'utils.combat_radius.max_speed_search',
  'utils.combat_radius.combat_radius_presets',
  'simulators.combat_radius.combat_radius',
  'apps.combat_radius_web',
];

let data = null;
let pyodide = null;
let pyReady = false;
let runLock = false;
let dirty = false;
let dashTimer = 0;
let applyingPreset = false;

function $(id) {
  return document.getElementById(id);
}

function fmt(n, d = 4) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
}

function pct(n, d = 1) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `${fmt(100 * n, d)}%`;
}

function fillSelect(selectEl, presets, placeholder) {
  selectEl.innerHTML =
    `<option value="">${placeholder}</option>` +
    presets.map((p) => `<option value="${p.id}">${p.name}</option>`).join('');
}

function optionHtml(map) {
  return Object.entries(map || {})
    .map(([id, label]) => `<option value="${id}">${label}</option>`)
    .join('');
}

function renderAircraftFields() {
  const planforms = data.combat_radius_config?.planform_labels || {};
  const layouts = data.combat_radius_config?.layout_labels || {};
  $('tgtFields').innerHTML = `
    <div class="field"><label>名称</label><input id="tgt_name" type="text"></div>
    <div class="pair">
      <div class="field"><label>展弦比 AR</label><input id="tgt_AR" type="number" step="0.01" min="0.5"></div>
      <div class="field"><label>前缘后掠角 <span class="unit">°</span></label><input id="tgt_sweep" type="number" step="0.1"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼载荷 <span class="unit">t/m²</span></label><input id="tgt_wl" type="number" step="0.001" min="0.01"></div>
      <div class="field"><label>厚弦比 tc</label><input id="tgt_tc" type="number" step="0.001" min="0.01"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼面积 <span class="unit">m²</span></label><input id="tgt_area" type="number" step="0.01" min="0"></div>
      <div class="field"><label>马赫角 <span class="unit">°</span></label><input id="tgt_mach_angle" type="number" step="0.1" min="0"></div>
    </div>
    <div class="pair">
      <div class="field"><label>机身长度 <span class="unit">m</span></label><input id="tgt_len" type="number" step="0.01" min="0"></div>
      <div class="field"><label>翼展 <span class="unit">m</span></label><input id="tgt_span" type="number" step="0.01" min="0"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼型</label><select id="tgt_planform">${optionHtml(planforms)}</select></div>
      <div class="field"><label>布局</label><select id="tgt_layout">${optionHtml(layouts)}</select></div>
    </div>
    <div class="check-row">
      <label><input type="checkbox" id="tgt_bwb"> 翼身融合</label>
      <label><input type="checkbox" id="tgt_rough"> 表面不平整</label>
    </div>
  `;
}

function applyPresetToFields(preset) {
  if (!preset) return;
  applyingPreset = true;
  $('tgt_name').value = preset.name || '';
  $('tgt_AR').value = preset.AR;
  $('tgt_sweep').value = preset.sweep_deg;
  $('tgt_wl').value = preset.wing_loading;
  $('tgt_tc').value = preset.tc;
  $('tgt_planform').value = preset.planform;
  $('tgt_layout').value = preset.layout;
  $('tgt_bwb').checked = !!preset.bwb;
  $('tgt_rough').checked = !!preset.rough;
  $('tgt_area').value = preset.wing_area_m2 != null ? preset.wing_area_m2 : '';
  $('tgt_mach_angle').value = preset.mach_angle_deg != null ? preset.mach_angle_deg : '';
  $('tgt_len').value = preset.length_m != null ? preset.length_m : '';
  $('tgt_span').value = preset.wingspan_m != null ? preset.wingspan_m : '';
  applyWeightFromPreset(preset);
  applyingPreset = false;
}

function applyWeightFromPreset(p) {
  if (!p) return;
  if (p.empty_kg != null) $('wtEmpty').value = p.empty_kg;
  if (p.internal_fuel_kg != null) $('wtFuel').value = p.internal_fuel_kg;
  if (p.n_pilots != null) $('wtPilots').value = p.n_pilots;
  if (p.missile_mass_kg != null) $('wtMissile').value = p.missile_mass_kg;
  $('wtNMissiles').value = 4;
  if (p.n_engines != null) $('wtEngines').value = p.n_engines;
  $('wtCarrier').checked = !!p.carrier;
  if (p.engine_id) {
    const engines = data.combat_radius_engine_presets || [];
    const eng = engines.find((x) => x.id === p.engine_id);
    if (eng) {
      $('engPreset').value = eng.id;
      applyEnginePreset(eng);
    }
  }
}

function applyEnginePreset(p) {
  if (!p) return;
  $('engBpr').value = p.bpr;
  $('engOpr').value = p.opr;
  $('engT4').value = p.t4_K;
  $('engTsl').value = p.tsl_kN != null ? p.tsl_kN : '';
  $('engMaxTsl').value = p.max_tsl_kN != null ? p.max_tsl_kN : '';
}

function readAircraft() {
  return {
    name: $('tgt_name').value || '未命名',
    AR: Number($('tgt_AR').value),
    sweep_deg: Number($('tgt_sweep').value),
    wing_loading: Number($('tgt_wl').value),
    tc: Number($('tgt_tc').value),
    mach: 0.8,
    alt_m: 12000,
    planform: $('tgt_planform').value,
    layout: $('tgt_layout').value,
    bwb: $('tgt_bwb').checked,
    rough: $('tgt_rough').checked,
    length_m: Number($('tgt_len').value),
    wingspan_m: Number($('tgt_span').value),
    mach_angle_deg: Number($('tgt_mach_angle').value),
    wing_area_m2: Number($('tgt_area').value),
  };
}

function readDashboardParams() {
  const params = {
    name: $('tgt_name').value || '',
    target: readAircraft(),
    empty_kg: Number($('wtEmpty').value),
    internal_fuel_kg: Number($('wtFuel').value),
    n_pilots: Number($('wtPilots').value),
    missile_mass_kg: Number($('wtMissile').value),
    n_missiles: Number($('wtNMissiles').value),
    n_engines: Number($('wtEngines').value),
    carrier: $('wtCarrier').checked,
    bpr: Number($('engBpr').value),
    opr: Number($('engOpr').value),
    t4_K: Number($('engT4').value),
    tsl_kN: Number($('engTsl').value),
    eta_c: Number($('engEta').value),
    eps: Number($('effEps').value),
    etan: Number($('effEtan').value),
    acc_frac: Number($('effAcc').value),
  };
  if ($('engMaxTsl').value !== '') params.max_tsl_kN = Number($('engMaxTsl').value);
  return params;
}

async function loadData() {
  const resp = await fetch(`data.json?v=${APP_VERSION}`);
  if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
  data = await resp.json();
  if (!data.py_sources) {
    throw new Error('data.json 缺少 py_sources，请运行 python3 scripts/build_all.py');
  }
  if (!data.combat_radius_presets) {
    throw new Error('data.json 缺少 combat_radius_presets，请运行 python3 scripts/build_all.py');
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

  for (const name of COMBAT_RADIUS_PY_FILES) {
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

  pyodide.globals.set('_combat_radius_cfg', JSON.stringify(data.combat_radius_config || {}));
  pyodide.globals.set('_cr_ac', JSON.stringify(data.combat_radius_presets || []));
  pyodide.globals.set('_cr_eng', JSON.stringify(data.combat_radius_engine_presets || []));
  await pyodide.runPythonAsync(`
import json
from utils.combat_radius.combat_radius_config import inject_combat_radius_config
from utils.combat_radius.combat_radius_presets import inject_combat_radius_presets
inject_combat_radius_config(json.loads(_combat_radius_cfg))
inject_combat_radius_presets(json.loads(_cr_ac), json.loads(_cr_eng))
`);

  pyodide.globals.set('_py_import_order', COMBAT_RADIUS_IMPORTS);
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

async function callPythonAsync(action, params) {
  const payload = JSON.stringify({ action, params });
  pyodide.globals.set('_combat_radius_payload', payload);
  const raw = await pyodide.runPythonAsync(`
import json
from apps.combat_radius_web import run_combat_radius_json
json.dumps(run_combat_radius_json(_combat_radius_payload), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

function snapshotFor(id) {
  return (data.combat_radius_results && data.combat_radius_results.aircraft)
    ? data.combat_radius_results.aircraft[id]
    : null;
}

function renderDash(r, sourceLabel) {
  if (!r || !r.success) {
    $('dashBox').innerHTML = `<p class="placeholder">${(r && r.error) || '无法计算该机型仪表盘（例如缺少海平面军推）。填写参数后将自动重算。'}</p>`;
    $('dashStatus').textContent = 'UNAVAILABLE';
    return;
  }
  const ms = r.max_speed || {};
  const vmax = ms.feasible
    ? `${fmt(ms.max_speed_kmh, 0)} km/h · Ma ${fmt(ms.max_speed_mach, 3)}`
    : (ms.fail_reason || '不可用');
  const rows = (r.points || []).map((p) => {
    if (!p.feasible) {
      return `<tr>
        <td>${p.label || ''}</td>
        <td>${p.mach != null ? fmt(p.mach, 3) : '—'}</td>
        <td colspan="10">${p.fail_reason || '无满足 92% 推力裕度的高度'}</td>
      </tr>`;
    }
    const mixed = p.mach != null && p.mach > 1
      ? (p.mixed_radius_km != null ? fmt(p.mixed_radius_km, 0) : '—')
      : '不适用';
    return `<tr class="target">
      <td>${p.label || ''}</td>
      <td>${fmt(p.mach, 3)}</td>
      <td>${fmt((p.alt_m || 0) / 1000, 1)}</td>
      <td>${fmt(p.ld, 2)}</td>
      <td>${fmt(p.thrust_avail_kN, 1)}</td>
      <td>${pct(p.load)}</td>
      <td>${pct(p.eta_th)}</td>
      <td>${pct(p.eta_p)}</td>
      <td>${pct(p.eta_o)}</td>
      <td>${fmt(p.radius_km, 0)}</td>
      <td>${mixed}</td>
      <td>${fmt(p.fuel_kg_per_km, 2)}</td>
    </tr>`;
  }).join('');
  $('dashBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">最大巡航 Ma</div><div class="v amber">${r.max_cruise_mach != null ? fmt(r.max_cruise_mach, 3) : '—'}</div></div>
      <div class="stat"><div class="k">极速</div><div class="v">${vmax}</div><div class="sub">${ms.alt_m != null ? `${fmt(ms.alt_m / 1000, 1)} km` : ''}</div></div>
      <div class="stat"><div class="k">可用油</div><div class="v">${fmt(r.fuel_usable_kg, 0)} kg</div><div class="sub">内油 ${fmt(r.fuel_kg, 0)} · ${r.carrier ? '舰载' : '陆基'}</div></div>
    </div>
    <div class="scroll-x">
      <table>
        <thead><tr>
          <th>点</th><th>Ma</th><th>高度 km</th><th>最佳 L/D</th><th>军推 kN</th><th>负载</th>
          <th>η_th</th><th>η_p</th><th>η_o</th><th>半径 km</th><th>混合作战半径</th><th>kg/km</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="note">${sourceLabel} 最佳 L/D 指该马赫下使升阻比×总效率最大的高度。混合作战半径仅超音速：去程该马赫、返程 Ma 0.8。</p>
  `;
  $('dashStatus').textContent = 'READY';
}

function showSnapshot() {
  dirty = false;
  const id = $('tgtPreset').value;
  const snap = id ? snapshotFor(id) : null;
  if (!snap) {
    $('dashBox').innerHTML = '<p class="placeholder">无预计算快照。填写海平面军推后将自动计算。</p>';
    $('dashStatus').textContent = 'NO SNAPSHOT';
    return;
  }
  renderDash(snap, '预计算快照 ·');
}

function scheduleLiveDash() {
  if (applyingPreset) return;
  dirty = true;
  $('dashStatus').textContent = 'PARAMS CHANGED';
  clearTimeout(dashTimer);
  dashTimer = setTimeout(() => {
    runLiveDash();
  }, 600);
}

async function runLiveDash() {
  if (runLock) return;
  runLock = true;
  $('dashStatus').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('aircraft_dashboard', readDashboardParams());
    if (!result.success) throw new Error(result.error || '仪表盘失败');
    renderDash(result, '现场重算 ·');
  } catch (e) {
    $('dashBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('dashStatus').textContent = 'ERROR';
  } finally {
    runLock = false;
  }
}

function renderQueryBox(id, html) {
  $(id).innerHTML = html;
}

async function withLock(fn) {
  if (runLock) return;
  runLock = true;
  try {
    await initPyodide();
    await fn();
  } finally {
    runLock = false;
  }
}

async function runSearchCruise() {
  try {
    await withLock(async () => {
      renderQueryBox('q1Box', '<p class="placeholder">搜索中…</p>');
      const params = readDashboardParams();
      params.mach = Number($('q1Mach').value);
      const r = await callPythonAsync('search_best_cruise', params);
      if (!r.success) throw new Error(r.error || '搜索失败');
      if (!r.feasible) {
        renderQueryBox('q1Box', `<p class="placeholder">${r.fail_reason || '无可行高度'}</p>`);
        return;
      }
      renderQueryBox('q1Box', `
        <div class="stat-row">
          <div class="stat"><div class="k">最佳 L/D</div><div class="v">${fmt(r.ld, 3)}</div></div>
          <div class="stat"><div class="k">巡航高度</div><div class="v amber">${fmt(r.alt_m / 1000, 1)} km</div></div>
          <div class="stat"><div class="k">最大可用推力</div><div class="v">${fmt(r.thrust_avail_kN, 1)} kN</div></div>
          <div class="stat"><div class="k">负载</div><div class="v">${pct(r.load)}</div></div>
          <div class="stat"><div class="k">热效率</div><div class="v">${pct(r.eta_th)}</div></div>
          <div class="stat"><div class="k">推进效率</div><div class="v">${pct(r.eta_p)}</div></div>
        </div>
      `);
    });
  } catch (e) {
    renderQueryBox('q1Box', `<p class="placeholder">${String(e.message || e)}</p>`);
  }
}

async function runPoint() {
  try {
    await withLock(async () => {
      renderQueryBox('q2Box', '<p class="placeholder">计算中…</p>');
      const params = readDashboardParams();
      params.mach = Number($('q2Mach').value);
      params.alt_m = Number($('q2Alt').value);
      const r = await callPythonAsync('estimate_efficiency', params);
      if (!r.success) throw new Error(r.error || '计算失败');
      renderQueryBox('q2Box', `
        <div class="stat-row">
          <div class="stat"><div class="k">升阻比</div><div class="v">${fmt(r.ld, 3)}</div></div>
          <div class="stat"><div class="k">最大可用推力</div><div class="v amber">${fmt(r.thrust_avail_kN, 1)} kN</div></div>
          <div class="stat"><div class="k">负载</div><div class="v">${pct(r.load)}</div></div>
          <div class="stat"><div class="k">热效率</div><div class="v">${pct(r.eta_th)}</div></div>
          <div class="stat"><div class="k">推进效率</div><div class="v">${pct(r.eta_p)}</div></div>
          <div class="stat"><div class="k">总效率</div><div class="v">${pct(r.eta_o)}</div></div>
        </div>
      `);
    });
  } catch (e) {
    renderQueryBox('q2Box', `<p class="placeholder">${String(e.message || e)}</p>`);
  }
}

async function runEngineCycle() {
  try {
    await withLock(async () => {
      renderQueryBox('q3Box', '<p class="placeholder">计算中…</p>');
      const r = await callPythonAsync('estimate_engine_cycle', {
        name: $('engPreset').selectedOptions[0]?.text || '',
        bpr: Number($('engBpr').value),
        opr: Number($('engOpr').value),
        t4_K: Number($('engT4').value),
        mach: Number($('q3Mach').value),
        alt_m: Number($('q3Alt').value),
        load: Number($('q3Load').value),
        eps: Number($('effEps').value),
        etan: Number($('effEtan').value),
        acc_frac: Number($('effAcc').value),
      });
      if (!r.success) throw new Error(r.error || '计算失败');
      renderQueryBox('q3Box', `
        <div class="stat-row">
          <div class="stat"><div class="k">热效率</div><div class="v">${pct(r.eta_th)}</div></div>
          <div class="stat"><div class="k">推进效率</div><div class="v amber">${pct(r.eta_p)}</div></div>
          <div class="stat"><div class="k">总效率</div><div class="v">${pct(r.eta_o)}</div></div>
        </div>
      `);
    });
  } catch (e) {
    renderQueryBox('q3Box', `<p class="placeholder">${String(e.message || e)}</p>`);
  }
}

function bindLiveInputs() {
  const root = document.querySelector('.grid');
  root.addEventListener('input', (e) => {
    if (e.target && e.target.closest && e.target.closest('.panel')) scheduleLiveDash();
  });
  root.addEventListener('change', (e) => {
    if (e.target && (e.target.id === 'tgtPreset' || e.target.id === 'engPreset')) return;
    if (e.target && e.target.closest && e.target.closest('.panel')) scheduleLiveDash();
  });
}

function applyUiDefaults() {
  const ui = data.combat_radius_config?.ui || {};
  const presets = data.combat_radius_presets || [];
  const tgt = presets.find((p) => p.id === ui.default_target_id) || presets[0];
  $('engEta').value = ui.default_eta_c ?? 0.87;
  $('effEps').value = ui.default_eps ?? 0.83;
  $('effEtan').value = ui.default_etan ?? 0.95;
  $('effAcc').value = ui.default_acc_frac ?? 0.16;
  if (tgt) {
    $('tgtPreset').value = tgt.id;
    applyPresetToFields(tgt);
    showSnapshot();
  }
}

async function main() {
  try {
    await loadData();
    renderAircraftFields();
    const presets = data.combat_radius_presets || [];
    const engines = data.combat_radius_engine_presets || [];
    fillSelect($('tgtPreset'), presets, '— 选择战机 —');
    fillSelect($('engPreset'), engines, '— 自定义 / 手动输入 —');
    $('tgtPreset').addEventListener('change', () => {
      const p = presets.find((x) => x.id === $('tgtPreset').value);
      applyPresetToFields(p);
      showSnapshot();
    });
    $('engPreset').addEventListener('change', () => {
      const p = engines.find((x) => x.id === $('engPreset').value);
      applyEnginePreset(p);
      scheduleLiveDash();
    });
    applyUiDefaults();
    bindLiveInputs();
    $('q1Btn').addEventListener('click', () => runSearchCruise());
    $('q2Btn').addEventListener('click', () => runPoint());
    $('q3Btn').addEventListener('click', () => runEngineCycle());
    initPyodide().catch((e) => {
      $('clock').textContent = 'ENGINE ERR';
      console.error(e);
    });
  } catch (e) {
    $('clock').textContent = 'ERROR';
    $('dashBox').textContent = String(e.message || e);
  }
}

main();
