/**
 * 导弹射程计算线程。Pyodide 和估算都在这里跑，页面主线程保持可点。
 */
let pyodide = null;

function writeTree(files) {
  pyodide.runPython(`
import sys
from pathlib import Path
Path('/py').mkdir(parents=True, exist_ok=True)
if '/py' not in sys.path:
    sys.path.insert(0, '/py')
`);
  Object.entries(files).forEach(([name, code]) => {
    const parts = name.split('/');
    let dir = '/py';
    for (let i = 0; i < parts.length - 1; i += 1) {
      dir += `/${parts[i]}`;
      try { pyodide.FS.mkdir(dir); } catch { /* 目录已存在 */ }
    }
    pyodide.FS.writeFile(`/py/${name}`, code);
  });
}

self.onmessage = async (event) => {
  const msg = event.data || {};
  try {
    if (msg.type === 'init') {
      const { loadPyodide } = await import(
        `https://cdn.jsdelivr.net/pyodide/v${msg.pyodideVersion}/full/pyodide.mjs`
      );
      pyodide = await loadPyodide();
      writeTree(msg.files || {});
      pyodide.globals.set('_py_import_order', msg.imports || []);
      await pyodide.runPythonAsync(`
import importlib
for _name in _py_import_order:
    importlib.import_module(_name)
`);
      self.postMessage({ type: 'ready' });
      return;
    }
    if (msg.type === 'run') {
      if (!pyodide) throw new Error('计算引擎尚未就绪');
      pyodide.globals.set('_missile_range_payload', msg.payload);
      const raw = await pyodide.runPythonAsync(msg.runSnippet);
      self.postMessage({ type: 'result', id: msg.id, raw });
    }
  } catch (err) {
    self.postMessage({
      type: 'error',
      id: msg.id,
      error: String(err && err.message ? err.message : err),
    });
  }
};
