/**
 * 作战半径 Web 前端：升阻比标定 + 军推包线 + 巡航效率/TSFC + 布雷盖半径，计算走 Pyodide Python 核心。
 */
const PYODIDE_VERSION = '0.26.4';
/** 与 combat-radius.html 中 ?v= 同步递增 */
const APP_VERSION = 7;

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

function $(id) {
  return document.getElementById(id);
}

function fmt(n, d = 4) {
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
}

function fillSelect(selectEl, presets) {
  selectEl.innerHTML =
    '<option value="">— 自定义 / 手动输入 —</option>' +
    presets.map((p) => `<option value="${p.id}">${p.name}</option>`).join('');
}

function optionHtml(map) {
  return Object.entries(map || {})
    .map(([id, label]) => `<option value="${id}">${label}</option>`)
    .join('');
}

function renderAircraftFields(containerId, prefix) {
  const planforms = data.combat_radius_config?.planform_labels || {};
  const layouts = data.combat_radius_config?.layout_labels || {};
  $(containerId).innerHTML = `
    <div class="field"><label>名称</label><input id="${prefix}_name" type="text"></div>
    <div class="pair">
      <div class="field"><label>展弦比 AR</label><input id="${prefix}_AR" type="number" step="0.01" min="0.5"></div>
      <div class="field"><label>前缘后掠角 <span class="unit">°</span></label><input id="${prefix}_sweep" type="number" step="0.1"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼载荷 <span class="unit">t/m²</span></label><input id="${prefix}_wl" type="number" step="0.001" min="0.01"></div>
      <div class="field"><label>厚弦比 tc</label><input id="${prefix}_tc" type="number" step="0.001" min="0.01"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼面积 <span class="unit">m²</span></label><input id="${prefix}_area" type="number" step="0.01" min="0"></div>
      <div class="field"><label>马赫角 <span class="unit">°</span></label><input id="${prefix}_mach_angle" type="number" step="0.1" min="0"></div>
    </div>
    <div class="pair">
      <div class="field"><label>机身长度 <span class="unit">m</span></label><input id="${prefix}_len" type="number" step="0.01" min="0"></div>
      <div class="field"><label>翼展 <span class="unit">m</span></label><input id="${prefix}_span" type="number" step="0.01" min="0"></div>
    </div>
    <div class="pair">
      <div class="field"><label>马赫数</label><input id="${prefix}_mach" type="number" step="0.01" min="0.1"></div>
      <div class="field"><label>高度 <span class="unit">m</span></label><input id="${prefix}_alt" type="number" step="100" min="11000"></div>
    </div>
    <div class="pair">
      <div class="field"><label>翼型</label><select id="${prefix}_planform">${optionHtml(planforms)}</select></div>
      <div class="field"><label>布局</label><select id="${prefix}_layout">${optionHtml(layouts)}</select></div>
    </div>
    <div class="check-row">
      <label><input type="checkbox" id="${prefix}_bwb"> 翼身融合</label>
      <label><input type="checkbox" id="${prefix}_rough"> 表面不平整</label>
    </div>
  `;
}

function applyPresetToFields(prefix, preset) {
  if (!preset) return;
  $(`${prefix}_name`).value = preset.name || '';
  $(`${prefix}_AR`).value = preset.AR;
  $(`${prefix}_sweep`).value = preset.sweep_deg;
  $(`${prefix}_wl`).value = preset.wing_loading;
  $(`${prefix}_tc`).value = preset.tc;
  $(`${prefix}_mach`).value = preset.mach;
  $(`${prefix}_alt`).value = preset.alt_m;
  $(`${prefix}_planform`).value = preset.planform;
  $(`${prefix}_layout`).value = preset.layout;
  $(`${prefix}_bwb`).checked = !!preset.bwb;
  $(`${prefix}_rough`).checked = !!preset.rough;
  $(`${prefix}_area`).value = preset.wing_area_m2 != null ? preset.wing_area_m2 : '';
  $(`${prefix}_mach_angle`).value = preset.mach_angle_deg != null ? preset.mach_angle_deg : '';
  $(`${prefix}_len`).value = preset.length_m != null ? preset.length_m : '';
  $(`${prefix}_span`).value = preset.wingspan_m != null ? preset.wingspan_m : '';
  if (prefix === 'tgt') applyWeightFromPreset(preset);
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

function readAircraft(prefix) {
  return {
    name: $(`${prefix}_name`).value || '未命名',
    AR: Number($(`${prefix}_AR`).value),
    sweep_deg: Number($(`${prefix}_sweep`).value),
    wing_loading: Number($(`${prefix}_wl`).value),
    tc: Number($(`${prefix}_tc`).value),
    mach: Number($(`${prefix}_mach`).value),
    alt_m: Number($(`${prefix}_alt`).value),
    planform: $(`${prefix}_planform`).value,
    layout: $(`${prefix}_layout`).value,
    bwb: $(`${prefix}_bwb`).checked,
    rough: $(`${prefix}_rough`).checked,
    length_m: Number($(`${prefix}_len`).value),
    wingspan_m: Number($(`${prefix}_span`).value),
    mach_angle_deg: Number($(`${prefix}_mach_angle`).value),
    wing_area_m2: Number($(`${prefix}_area`).value),
  };
}

function bindPresetSelect(selectId, prefix, ldInputId) {
  const presets = data.combat_radius_presets || [];
  fillSelect($(selectId), presets);
  $(selectId).addEventListener('change', () => {
    const p = presets.find((x) => x.id === $(selectId).value);
    applyPresetToFields(prefix, p);
    if (ldInputId && p && p.ld_known != null) {
      $(ldInputId).value = p.ld_known;
    }
  });
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
  if (!data.combat_radius_engine_presets) {
    throw new Error('data.json 缺少 combat_radius_engine_presets，请运行 python3 scripts/build_all.py');
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
  await pyodide.runPythonAsync(`
import json
from utils.combat_radius.combat_radius_config import inject_combat_radius_config
inject_combat_radius_config(json.loads(_combat_radius_cfg))
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

function dragBar(cd0, cdi, cdw) {
  const total = cd0 + cdi + cdw;
  if (!(total > 0)) return '';
  const p0 = (100 * cd0) / total;
  const pi = (100 * cdi) / total;
  const pw = (100 * cdw) / total;
  return `<div class="bar-wrap"><div class="bar-bg">
    <div class="bar-fill" style="width:${p0}%;display:inline-block"></div>
    <div class="bar-fill i" style="width:${pi}%;display:inline-block"></div>
    <div class="bar-fill w" style="width:${pw}%;display:inline-block"></div>
  </div></div>`;
}

function renderResult(r) {
  const rows = [...(r.anchors || []), r.target].filter(Boolean);
  const tgt = r.target || {};
  const table = rows.map((row, i) => {
    const cls = i === rows.length - 1 ? 'target' : '';
    const tgtLd = row.target_ld != null ? fmt(row.target_ld, 2) : '—';
    const err = row.error != null ? fmt(row.error, 2) : '—';
    return `<tr class="${cls}">
      <td>${row.name}</td>
      <td>${fmt(row.ld, 4)}</td>
      <td>${tgtLd}</td>
      <td>${err}</td>
      <td>${fmt(row.CL, 4)}</td>
      <td>${fmt(row.CD0, 5)}</td>
      <td>${fmt(row.CDi, 5)}</td>
      <td>${fmt(row.CDw, 5)}</td>
      <td>${fmt(row.CD, 5)}</td>
    </tr>`;
  }).join('');
  $('resultBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">待估 L/D</div><div class="v">${fmt(tgt.ld, 4)}</div><div class="sub">${tgt.name || ''}</div></div>
      <div class="stat"><div class="k">Cf0</div><div class="v amber">${fmt(r.Cf0, 6)}</div></div>
      <div class="stat"><div class="k">k_e</div><div class="v amber">${fmt(r.k_e, 6)}</div></div>
      <div class="stat"><div class="k">κ_A</div><div class="v">${fmt(r.kappa_A, 2)}</div><div class="sub">Korn 固定</div></div>
    </div>
    <div class="scroll-x">
      <table>
        <thead><tr>
          <th>机型</th><th>L/D</th><th>目标</th><th>误差</th>
          <th>CL</th><th>CD0</th><th>CDi</th><th>CDw</th><th>CD</th>
        </tr></thead>
        <tbody>${table}</tbody>
      </table>
    </div>
    ${dragBar(tgt.CD0 || 0, tgt.CDi || 0, tgt.CDw || 0)}
    <p class="note">阻力分解条：青=摩擦/寄生 CD0，琥珀=诱导 CDi，红=波阻 CDw。锚点误差应接近 0（闭式标定）。</p>
  `;
}

function renderThrustResult(r) {
  $('thrustBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">可用军推</div><div class="v">${fmt(r.thrust_kN, 1)} kN</div><div class="sub">${fmt(r.thrust_tf, 2)} 吨力</div></div>
      <div class="stat"><div class="k">推力衰减 α</div><div class="v amber">${fmt(r.alpha, 3)}</div></div>
      <div class="stat"><div class="k">质量流比</div><div class="v">${fmt(r.mdot_ratio, 3)}</div></div>
      <div class="stat"><div class="k">风扇压比</div><div class="v">${fmt(r.fan_pr, 2)}</div></div>
    </div>
    <p class="note">来流总温比 τr=${fmt(r.tau_r, 3)} · 大气 ${fmt(r.T0, 1)} K / ${fmt(r.P0 / 1000, 1)} kPa。α = T_flight / T_SL。</p>
  `;
}

function renderEffResult(r) {
  const loadPct = 100 * (r.load || 0);
  const warn = r.warning
    ? `<p class="note">告警：${r.warning === 'load_exceeds_thrust' || String(r.warning).includes('load_exceeds_thrust') ? '阻力超过可用军推，负载已截断到 100%。' : r.warning}</p>`
    : '';
  const tsfc = r.tsfc_mg_n_s != null
    ? `${fmt(r.tsfc_mg_n_s, 2)} mg/(N·s)`
    : '—';
  const tsfcLb = r.tsfc_lb_lbf_h != null ? `${fmt(r.tsfc_lb_lbf_h, 3)} lb/(lbf·h)` : '';
  $('effBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">负载比</div><div class="v amber">${fmt(loadPct, 1)}%</div><div class="sub">原始 ${fmt(100 * (r.load_raw || 0), 1)}%</div></div>
      <div class="stat"><div class="k">总效率 η_o</div><div class="v">${fmt(100 * (r.eta_o || 0), 1)}%</div><div class="sub">热 ${fmt(100 * (r.eta_th || 0), 1)}% · 推进 ${fmt(100 * (r.eta_p || 0), 1)}%</div></div>
      <div class="stat"><div class="k">TSFC</div><div class="v">${tsfc}</div><div class="sub">${tsfcLb}</div></div>
      <div class="stat"><div class="k">反解 T4</div><div class="v">${fmt(r.T4_solved, 0)} K</div></div>
    </div>
    <p class="note">空战重量 ${fmt(r.mass_kg, 0)} kg · 阻力 ${fmt(r.drag_kN, 2)} kN · 可用军推 ${fmt(r.thrust_avail_kN, 1)} kN（${r.n_engines} 发）· L/D ${fmt(r.ld, 3)} · V0 ${fmt(r.V0, 1)} m/s。</p>
    ${warn}
  `;
}

function renderMaxSpeedResult(r) {
  if (!r.feasible) {
    $('maxSpeedBox').innerHTML = `<p class="placeholder">${r.fail_reason || '无法满足加力推力裕度'}</p>`;
    return;
  }
  const rows = (r.profile || []).map((p) => `<tr>
    <td>${fmt(p.alt_m / 1000, 1)}</td>
    <td>${fmt(p.mach, 3)}</td>
    <td>${fmt(p.v_kmh, 0)}</td>
    <td>${fmt(100 * p.load_raw, 1)}%</td>
  </tr>`).join('');
  $('maxSpeedBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">最大速度</div><div class="v amber">${fmt(r.max_speed_kmh, 0)} km/h</div><div class="sub">${fmt(r.max_speed_kts, 0)} kt · Ma ${fmt(r.max_speed_mach, 3)}</div></div>
      <div class="stat"><div class="k">最佳高度</div><div class="v">${fmt(r.alt_m / 1000, 1)} km</div></div>
      <div class="stat"><div class="k">加力海推</div><div class="v">${fmt(r.max_tsl_kN, 0)} kN</div><div class="sub">${r.n_engines} 发 · 空战 ${fmt(r.mass_kg, 0)} kg</div></div>
      <div class="stat"><div class="k">负载</div><div class="v">${fmt(100 * r.load, 1)}%</div><div class="sub">D ${fmt(r.drag_kN, 1)} kN / T ${fmt(r.thrust_avail_kN, 1)} kN</div></div>
    </div>
    <div class="scroll-x">
      <table>
        <thead><tr><th>高度 km</th><th>Ma</th><th>km/h</th><th>负载</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="note">${r.note || ''}</p>
  `;
}

function renderRadiusResult(r) {
  const angle = r.mach_angle_deg != null
    ? `${fmt(r.mach_angle_deg, 1)}° · 锥限 Ma ${fmt(r.mach_cone_limit, 2)}`
    : '未提供机身长度/翼展';
  const mf = r.mission_fuel || {};
  const rows = (r.points || []).map((p) => {
    if (!p.feasible) {
      return `<tr>
        <td>${p.label}</td>
        <td>${p.mach != null ? fmt(p.mach, 3) : '—'}</td>
        <td colspan="8">${p.fail_reason || '无满足 92% 推力裕度的高度'}</td>
      </tr>`;
    }
    return `<tr class="target">
      <td>${p.label}</td>
      <td>${fmt(p.mach, 3)}</td>
      <td>${fmt(p.alt_m / 1000, 1)}</td>
      <td>${fmt(p.ld, 2)}</td>
      <td>${fmt(100 * p.eta_o, 1)}%</td>
      <td>${p.tsfc_mg_n_s != null ? fmt(p.tsfc_mg_n_s, 2) : '—'}</td>
      <td>${fmt(p.thrust_avail_kN, 1)}</td>
      <td>${fmt(100 * p.load, 1)}%</td>
      <td>${fmt(p.radius_km, 0)}</td>
      <td>${fmt(p.fuel_kg_per_km, 2)}</td>
    </tr>`;
  }).join('');
  const reserveKind = r.carrier ? '舰载 40 min' : '陆基 30 min';
  $('radiusBox').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="k">马赫角</div><div class="v">${angle}</div></div>
      <div class="stat"><div class="k">最大巡航 Ma</div><div class="v amber">${r.max_cruise_mach != null ? fmt(r.max_cruise_mach, 3) : '—'}</div></div>
      <div class="stat"><div class="k">布雷盖质量</div><div class="v">${fmt(r.mass_initial_kg, 0)} kg</div><div class="sub">终了 ${fmt(r.mass_final_kg, 0)} kg</div></div>
      <div class="stat"><div class="k">可用油</div><div class="v">${r.fuel_usable_kg != null ? fmt(r.fuel_usable_kg, 0) : '—'} kg</div><div class="sub">内油 ${fmt(r.fuel_kg, 0)} · ${r.n_missiles} 枚弹</div></div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="k">降落冗余</div><div class="v">${mf.reserve_fuel_kg != null ? fmt(mf.reserve_fuel_kg, 0) : '—'} kg</div><div class="sub">${reserveKind} · ${mf.reserve_loiter_km != null ? fmt(mf.reserve_loiter_km, 0) : '—'} km</div></div>
      <div class="stat"><div class="k">爬升额外</div><div class="v amber">${mf.climb_extra_kg != null ? fmt(mf.climb_extra_kg, 0) : '—'} kg</div><div class="sub">起飞 ${mf.takeoff_kg_per_km != null ? fmt(mf.takeoff_kg_per_km, 2) : '—'} kg/km × ${mf.climb_extra_km != null ? fmt(mf.climb_extra_km, 1) : '120'} km</div></div>
      <div class="stat"><div class="k">降落节省</div><div class="v">${mf.descent_save_kg != null ? fmt(mf.descent_save_kg, 0) : '—'} kg</div><div class="sub">余油 ${mf.landing_kg_per_km != null ? fmt(mf.landing_kg_per_km, 2) : '—'} kg/km × ${mf.descent_save_km != null ? fmt(mf.descent_save_km, 1) : '87.5'} km</div></div>
    </div>
    <div class="scroll-x">
      <table>
        <thead><tr>
          <th>点</th><th>Ma</th><th>高度 km</th><th>L/D</th><th>η_o</th>
          <th>TSFC</th><th>军推 kN</th><th>负载</th><th>半径 km</th><th>kg/km</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="note">${r.note || ''} TSFC 单位 mg/(N·s)；kg/km 为往返航程均摊油耗。</p>
  `;
}

function readMaxSpeedParams() {
  const params = readEfficiencyParams();
  params.max_tsl_kN = Number($('engMaxTsl').value);
  delete params.tsl_kN;
  return params;
}

function readEfficiencyParams() {
  const params = {
    ...readThrustParams(),
    anchor1: readAircraft('a1'),
    ld1_target: Number($('a1Ld').value),
    anchor2: readAircraft('a2'),
    ld2_target: Number($('a2Ld').value),
    target: readAircraft('tgt'),
    empty_kg: Number($('wtEmpty').value),
    internal_fuel_kg: Number($('wtFuel').value),
    n_pilots: Number($('wtPilots').value),
    missile_mass_kg: Number($('wtMissile').value),
    n_missiles: Number($('wtNMissiles').value),
    n_engines: Number($('wtEngines').value),
    carrier: $('wtCarrier').checked,
    eps: Number($('effEps').value),
    etan: Number($('effEtan').value),
    acc_frac: Number($('effAcc').value),
  };
  return params;
}

function readThrustParams() {
  const fanRaw = $('engFanPr').value;
  const params = {
    name: ($('engPreset').selectedOptions[0] || {}).text || '',
    bpr: Number($('engBpr').value),
    opr: Number($('engOpr').value),
    t4_K: Number($('engT4').value),
    tsl_kN: Number($('engTsl').value),
    alt_m: Number($('engAlt').value),
    mach: Number($('engMach').value),
    eta_c: Number($('engEta').value),
  };
  if (fanRaw !== '') params.fan_pr_override = Number(fanRaw);
  return params;
}

function applyEnginePreset(p) {
  if (!p) return;
  $('engBpr').value = p.bpr;
  $('engOpr').value = p.opr;
  $('engT4').value = p.t4_K;
  if (p.tsl_kN != null) $('engTsl').value = p.tsl_kN;
  if (p.max_tsl_kN != null) $('engMaxTsl').value = p.max_tsl_kN;
  else $('engMaxTsl').value = '';
}

function bindEnginePreset() {
  const presets = data.combat_radius_engine_presets || [];
  fillSelect($('engPreset'), presets);
  $('engPreset').addEventListener('change', () => {
    const p = presets.find((x) => x.id === $('engPreset').value);
    applyEnginePreset(p);
  });
}

async function runEstimate() {
  if (runLock) return;
  runLock = true;
  const btn = $('runBtn');
  btn.disabled = true;
  $('statusTag').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('predict_ld', {
      anchor1: readAircraft('a1'),
      ld1_target: Number($('a1Ld').value),
      anchor2: readAircraft('a2'),
      ld2_target: Number($('a2Ld').value),
      target: readAircraft('tgt'),
    });
    if (!result.success) throw new Error(result.error || '估算失败');
    renderResult(result);
    $('statusTag').textContent = 'READY';
  } catch (e) {
    $('resultBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('statusTag').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
    runLock = false;
  }
}

async function runThrust() {
  if (runLock) return;
  runLock = true;
  const btn = $('thrustBtn');
  btn.disabled = true;
  $('thrustStatus').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('estimate_thrust', readThrustParams());
    if (!result.success) throw new Error(result.error || '估算失败');
    renderThrustResult(result);
    $('thrustStatus').textContent = 'READY';
  } catch (e) {
    $('thrustBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('thrustStatus').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
    runLock = false;
  }
}

async function runEfficiency() {
  if (runLock) return;
  runLock = true;
  const btn = $('effBtn');
  btn.disabled = true;
  $('effStatus').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('estimate_efficiency', readEfficiencyParams());
    if (!result.success) throw new Error(result.error || '估算失败');
    renderEffResult(result);
    $('effStatus').textContent = 'READY';
  } catch (e) {
    $('effBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('effStatus').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
    runLock = false;
  }
}

async function runMaxSpeed() {
  if (runLock) return;
  runLock = true;
  const btn = $('maxSpeedBtn');
  btn.disabled = true;
  $('maxSpeedStatus').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('estimate_max_speed', readMaxSpeedParams());
    if (!result.success) throw new Error(result.error || '估算失败');
    renderMaxSpeedResult(result);
    $('maxSpeedStatus').textContent = 'READY';
  } catch (e) {
    $('maxSpeedBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('maxSpeedStatus').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
    runLock = false;
  }
}

async function runRadius() {
  if (runLock) return;
  runLock = true;
  const btn = $('radiusBtn');
  btn.disabled = true;
  $('radiusStatus').textContent = 'RUNNING';
  try {
    await initPyodide();
    const result = await callPythonAsync('estimate_radius', readEfficiencyParams());
    if (!result.success) throw new Error(result.error || '估算失败');
    renderRadiusResult(result);
    $('radiusStatus').textContent = 'READY';
  } catch (e) {
    $('radiusBox').innerHTML = `<p class="placeholder">${String(e.message || e)}</p>`;
    $('radiusStatus').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
    runLock = false;
  }
}

function applyUiDefaults() {
  const ui = data.combat_radius_config?.ui || {};
  const presets = data.combat_radius_presets || [];
  const a1 = presets.find((p) => p.id === ui.default_anchor1_id) || presets[0];
  const a2 = presets.find((p) => p.id === ui.default_anchor2_id) || presets[1];
  const tgt = presets.find((p) => p.id === ui.default_target_id) || presets[2];
  if (a1) {
    $('a1Preset').value = a1.id;
    applyPresetToFields('a1', a1);
    $('a1Ld').value = ui.default_ld1 ?? a1.ld_known ?? 8.8;
  }
  if (a2) {
    $('a2Preset').value = a2.id;
    applyPresetToFields('a2', a2);
    $('a2Ld').value = ui.default_ld2 ?? a2.ld_known ?? 8.0;
  }
  if (tgt) {
    $('tgtPreset').value = tgt.id;
    applyPresetToFields('tgt', tgt);
  }
  const engines = data.combat_radius_engine_presets || [];
  const eng = engines.find((p) => p.id === ui.default_engine_id) || engines.find((p) => p.tsl_kN != null) || engines[0];
  if (eng) {
    $('engPreset').value = eng.id;
    applyEnginePreset(eng);
  }
  $('engAlt').value = ui.default_thrust_alt_m ?? 11000;
  $('engMach').value = ui.default_thrust_mach ?? 1.5;
  $('engEta').value = ui.default_eta_c ?? 0.87;
  $('effEps').value = ui.default_eps ?? 0.83;
  $('effEtan').value = ui.default_etan ?? 0.95;
  $('effAcc').value = ui.default_acc_frac ?? 0.16;
}

async function main() {
  try {
    await loadData();
    renderAircraftFields('a1Fields', 'a1');
    renderAircraftFields('a2Fields', 'a2');
    renderAircraftFields('tgtFields', 'tgt');
    bindPresetSelect('a1Preset', 'a1', 'a1Ld');
    bindPresetSelect('a2Preset', 'a2', 'a2Ld');
    bindPresetSelect('tgtPreset', 'tgt', null);
    bindEnginePreset();
    applyUiDefaults();
    $('runBtn').addEventListener('click', runEstimate);
    $('thrustBtn').addEventListener('click', runThrust);
    $('effBtn').addEventListener('click', runEfficiency);
    $('radiusBtn').addEventListener('click', runRadius);
    $('maxSpeedBtn').addEventListener('click', runMaxSpeed);
    initPyodide().catch((e) => {
      $('clock').textContent = 'ENGINE ERR';
      $('resultBox').textContent = String(e.message || e);
    });
  } catch (e) {
    $('clock').textContent = 'ERROR';
    $('resultBox').textContent = String(e.message || e);
  }
}

main();
