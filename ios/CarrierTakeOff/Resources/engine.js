/**
 * iOS 本地仿真桥：在 WKWebView 内用 Pyodide 运行与 Web 相同的 Python 模块。
 * 由 Swift LocalSimulatorEngine 调用 window.__carrierSim。
 */
const PYODIDE_VERSION = '0.26.4';

let pyodide = null;
let ready = false;
let catalog = null;

function post(msg) {
  try {
    window.webkit?.messageHandlers?.simBridge?.postMessage(msg);
  } catch (_) {
    /* 非 WKWebView 环境忽略 */
  }
}

async function loadCatalog() {
  // 优先使用 Swift 注入的 Bundle 数据（file:// 下 fetch 常返回 status 0）
  if (window.__BUNDLED_CATALOG__) {
    catalog = window.__BUNDLED_CATALOG__;
  } else {
    const resp = await fetch('data.json');
    if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
    catalog = await resp.json();
  }
  if (!catalog.py_sources || !catalog.py_load_order) {
    throw new Error('data.json 缺少 py_sources，请运行 python3 scripts/build_all.py');
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

  for (const name of catalog.py_load_order) {
    const code = catalog.py_sources[name];
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

  const importOrder =
    catalog.py_import_order ||
    catalog.py_load_order.map((n) => n.replace(/\.py$/, '').replace(/\//g, '.'));
  pyodide.globals.set('_py_import_order', importOrder);
  await pyodide.runPythonAsync(`
import importlib
for _name in _py_import_order:
    importlib.import_module(_name)
`);
}

async function initEngine() {
  post({ type: 'status', text: '正在加载本地 Python 仿真引擎…' });
  await loadCatalog();
  const { loadPyodide } = await import(
    `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.mjs`
  );
  pyodide = await loadPyodide();
  await pyodide.loadPackage('numpy');
  await loadPythonModules();
  ready = true;
  post({ type: 'ready' });
}

/**
 * 运行起飞仿真：payload 为普通对象，返回 JSON 可序列化结果。
 */
async function runSimulation(payload) {
  if (!ready || !pyodide) {
    throw new Error('仿真引擎尚未就绪');
  }
  pyodide.globals.set('_payload_json', JSON.stringify(payload));
  const raw = pyodide.runPython(`
import json
from apps.web_simulator import run_simulation_json
json.dumps(run_simulation_json(_payload_json), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

/**
 * 运行饱和打击仿真 / 估算：payload 含 action 与 params。
 */
async function runMissileInterception(payload) {
  if (!ready || !pyodide) {
    throw new Error('仿真引擎尚未就绪');
  }
  pyodide.globals.set('_missile_interception_payload_json', JSON.stringify(payload));
  const raw = pyodide.runPython(`
import json
from apps.missile_interception_strike_web import run_missile_interception_json
json.dumps(run_missile_interception_json(_missile_interception_payload_json), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

/**
 * 运行作战半径 / 升阻比估算：payload 含 action 与 params。
 */
async function runCombatRadius(payload) {
  if (!ready || !pyodide) {
    throw new Error('仿真引擎尚未就绪');
  }
  pyodide.globals.set('_combat_radius_payload_json', JSON.stringify(payload));
  const raw = pyodide.runPython(`
import json
from apps.combat_radius_web import run_combat_radius_json
json.dumps(run_combat_radius_json(_combat_radius_payload_json), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

window.__carrierSim = {
  init: initEngine,
  run: runSimulation,
  isReady: () => ready,
};

window.__missileInterceptionSim = {
  run: runMissileInterception,
  isReady: () => ready,
};

window.__combatRadiusSim = {
  run: runCombatRadius,
  isReady: () => ready,
};

initEngine().catch((e) => {
  post({ type: 'error', text: String(e && e.message ? e.message : e) });
});
