/**
 * 饱和打击 Web 前端：GUI 保留战术终端风格，计算走 Pyodide Python 核心。
 */
const PYODIDE_VERSION = '0.26.4';
/** 与 missile-interception-strike.html 中 ?v= 同步递增 */
const APP_VERSION = 17;

/** 预警机预设中「无预警机」的特殊 value */
const AEW_NONE_VALUE = '__none__';

/** 仅加载饱和打击相关 Python 模块（无需 numpy） */
const MISSILE_INTERCEPTION_PY_FILES = [
  'utils/__init__.py',
  'utils/paths.py',
  'utils/missile_interception/__init__.py',
  'utils/missile_interception/missile_interception_config.py',
  'utils/database_csv.py',
  'utils/missile_interception/missile_interception_presets.py',
  'utils/missile_interception/missile_interception_radar.py',
  'utils/missile_interception/missile_interception_windows.py',
  'utils/missile_interception/missile_interception_monte_carlo.py',
  'utils/missile_interception/missile_interception_display.py',
  'simulators/__init__.py',
  'simulators/missile_interception/__init__.py',
  'simulators/missile_interception/missile_interception_strike.py',
  'apps/__init__.py',
  'apps/missile_interception_strike_web.py',
];

const MISSILE_INTERCEPTION_IMPORTS = [
  'utils.paths',
  'utils.missile_interception.missile_interception_config',
  'utils.database_csv',
  'utils.missile_interception.missile_interception_presets',
  'utils.missile_interception.missile_interception_radar',
  'utils.missile_interception.missile_interception_windows',
  'utils.missile_interception.missile_interception_monte_carlo',
  'utils.missile_interception.missile_interception_display',
  'simulators.missile_interception.missile_interception_strike',
  'apps.missile_interception_strike_web',
];

let data = null;
let pyodide = null;
let pyReady = false;
let chartRef = null;
/** 防止重入；计算中再次点击则排队用最新参数再跑一轮 */
let runLock = false;
let rerunRequested = false;
/** 当前结果是否对应当前参数 */
let resultFresh = false;

function $(id) {
  return document.getElementById(id);
}

function fmt(n, d = 2) {
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
}

function fillSelect(selectEl, presets) {
  selectEl.innerHTML =
    '<option value="">— 自定义 / 手动输入 —</option>' +
    presets.map((p) => `<option value="${p.id}">${p.name}</option>`).join('');
}

/** 从预设列表提取去重国别（按首次出现顺序，与 Python nations_sorted 一致）。 */
function nationsSorted(presets) {
  const seen = [];
  (presets || []).forEach((p) => {
    const nation = (p.nation || '').trim();
    if (nation && !seen.includes(nation)) seen.push(nation);
  });
  return seen;
}

/** 合并多组预设国别（与 Python nations_union 一致）。 */
function nationsUnion(...presetLists) {
  const seen = [];
  presetLists.forEach((presets) => {
    nationsSorted(presets).forEach((n) => {
      if (!seen.includes(n)) seen.push(n);
    });
  });
  return seen;
}

/** 按国别过滤预设；国别为空时返回全部。 */
function filterPresetsByNation(presets, nation) {
  const key = (nation || '').trim();
  if (!key) return (presets || []).slice();
  return (presets || []).filter((p) => (p.nation || '').trim() === key);
}

/**
 * 绑定「国别 → 型号」两级选择器：选国别后重建型号列表并复位为自定义，
 * 选型号后调用 apply 回填参数。
 */
function bindNationModelSelects(nationEl, modelEl, presets, apply) {
  nationEl.innerHTML =
    '<option value="">— 全部国别 —</option>' +
    nationsSorted(presets).map((n) => `<option value="${n}">${n}</option>`).join('');
  fillSelect(modelEl, presets);
  nationEl.addEventListener('change', () => {
    fillSelect(modelEl, filterPresetsByNation(presets, nationEl.value));
    modelEl.value = '';
  });
  modelEl.addEventListener('change', () => {
    const p = (presets || []).find((x) => x.id === modelEl.value);
    if (p) apply(p);
  });
}

/**
 * 绑定「一国别 → 多型号」：选国别后同时过滤多组型号列表并复位为自定义。
 * bindings: [{ el, presets, apply }, ...]
 */
function bindSharedNationModelSelects(nationEl, bindings) {
  const lists = bindings.map((b) => b.presets || []);
  nationEl.innerHTML =
    '<option value="">— 全部国别 —</option>' +
    nationsUnion(...lists).map((n) => `<option value="${n}">${n}</option>`).join('');
  bindings.forEach(({ el, presets }) => fillSelect(el, presets || []));
  nationEl.addEventListener('change', () => {
    const nation = nationEl.value;
    bindings.forEach(({ el, presets }) => {
      fillSelect(el, filterPresetsByNation(presets || [], nation));
      el.value = '';
    });
  });
  bindings.forEach(({ el, presets, apply }) => {
    el.addEventListener('change', () => {
      const p = (presets || []).find((x) => x.id === el.value);
      if (p) apply(p);
    });
  });
}

/** 在预警机预设下拉框中插入「无预警机」选项（紧跟自定义选项之后）。 */
function insertNoAewOption(selectEl) {
  const noneOpt = document.createElement('option');
  noneOpt.value = AEW_NONE_VALUE;
  noneOpt.textContent = '无预警机';
  selectEl.insertBefore(noneOpt, selectEl.options[1] || null);
}

/** 选择「无预警机」时置灰预警机相关输入，提示这些字段此时不参与计算。 */
function setAwacsFieldsDisabled(disabled) {
  ['awacsArea', 'awacsType', 'standoff'].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = disabled;
  });
}

function applyPresetsFromData() {
  const presets = data.missile_interception_presets || {};
  bindNationModelSelects($('asmNation'), $('asmPreset'), presets.asm || [], (p) => {
    $('vm').value = p.vm;
    $('rcs').value = p.rcs;
    $('traj').value = p.traj;
  });
  $('samMaxAlt').value = (data.missile_interception_config?.ui?.sam_max_alt ?? 33);
  // 驱护舰艇与舰载防空弹共用一个「防御方国别」，选择后同时限制两侧型号
  bindSharedNationModelSelects($('defenderNation'), [
    {
      el: $('shipPreset'),
      presets: presets.ship || [],
      apply: (p) => {
        $('shipArea').value = p.area;
        $('shipType').value = p.type;
      },
    },
    {
      el: $('samPreset'),
      presets: presets.sam || [],
      apply: (p) => {
        $('vi').value = p.vi;
        $('interceptorDia').value = p.dia;
        $('seekerType').value = p.guidance;
        $('samRange').value = p.range;
        if (p.max_alt != null) $('samMaxAlt').value = p.max_alt;
      },
    },
  ]);

  fillSelect($('aewPreset'), presets.aew || []);
  insertNoAewOption($('aewPreset'));
  $('aewPreset').addEventListener('change', (e) => {
    const isNone = e.target.value === AEW_NONE_VALUE;
    setAwacsFieldsDisabled(isNone);
    if (isNone) return;
    const p = (presets.aew || []).find((x) => x.id === e.target.value);
    if (!p) return;
    $('awacsArea').value = p.area;
    $('awacsType').value = p.type;
    $('standoff').value = p.standoff;
  });
}

async function loadData() {
  const resp = await fetch(`data.json?v=${APP_VERSION}`);
  if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
  data = await resp.json();
  if (!data.py_sources) {
    throw new Error('data.json 缺少 py_sources，请运行 python3 scripts/build_all.py');
  }
  if (!data.missile_interception_presets) {
    throw new Error('data.json 缺少 missile_interception_presets，请运行 python3 scripts/build_all.py');
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

  for (const name of MISSILE_INTERCEPTION_PY_FILES) {
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

  pyodide.globals.set('_missile_interception_cfg', JSON.stringify(data.missile_interception_config || {}));
  await pyodide.runPythonAsync(`
import json
from utils.missile_interception.missile_interception_config import inject_missile_interception_config
inject_missile_interception_config(json.loads(_missile_interception_cfg))
`);

  pyodide.globals.set('_py_import_order', MISSILE_INTERCEPTION_IMPORTS);
  await pyodide.runPythonAsync(`
import importlib
for _name in _py_import_order:
    importlib.import_module(_name)
`);
}

async function initPyodide() {
  if (pyReady) return;
  $('statusTag').textContent = 'LOADING';
  const { loadPyodide } = await import(
    `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.mjs`
  );
  pyodide = await loadPyodide();
  await loadPythonModules();
  pyReady = true;
  $('statusTag').textContent = 'READY';
}

function callPython(action, params) {
  const payload = JSON.stringify({ action, params });
  pyodide.globals.set('_missile_interception_payload', payload);
  const raw = pyodide.runPython(`
import json
from apps.missile_interception_strike_web import run_missile_interception_json
json.dumps(run_missile_interception_json(_missile_interception_payload), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

/** 异步调用 Python，便于在计算前刷新「计算中」UI */
async function callPythonAsync(action, params) {
  const payload = JSON.stringify({ action, params });
  pyodide.globals.set('_missile_interception_payload', payload);
  const raw = await pyodide.runPythonAsync(`
import json
from apps.missile_interception_strike_web import run_missile_interception_json
json.dumps(run_missile_interception_json(_missile_interception_payload), ensure_ascii=False)
`);
  return JSON.parse(raw);
}

function engageFormulaLabel(dist) {
  const diveLimited = dist.dive_entry_km != null && dist.dive_entry_km > 0;
  return diveLimited ? 'min(max(预警机,舰载),射程,俯冲进入)' : 'min(max(预警机,舰载),射程)';
}

function formatDiveEntryDisplay(dist) {
  if (dist.dive_entry_km != null && dist.dive_entry_km > 0) {
    return `${Number(dist.dive_entry_km).toFixed(1)} km（俯冲 ${Number(dist.dive_angle_deg).toFixed(0)}°）`;
  }
  const h = Number(dist.h_target_m ?? 0).toFixed(0);
  const alt = Number(dist.sam_max_alt_km ?? 0).toFixed(0);
  return `全程在有效射高包线内（巡航 ${h}m ≤ 最大射高 ${alt}km）`;
}

function diveEntrySuffix(dist) {
  if (dist.dive_entry_km != null && dist.dive_entry_km > 0) {
    return `，俯冲进入(${Number(dist.dive_angle_deg).toFixed(0)}°/射高${Number(dist.sam_max_alt_km).toFixed(0)}km)≈${Number(dist.dive_entry_km).toFixed(1)}km`;
  }
  return '';
}

function collectEstimateParams() {
  const asmId = $('asmPreset').value || '';
  const asmPreset = (data?.missile_interception_presets?.asm || []).find((x) => x.id === asmId);
  return {
    rcs: +$('rcs').value,
    traj: $('traj').value,
    awacs_area: +$('awacsArea').value,
    awacs_type: $('awacsType').value,
    standoff: +$('standoff').value,
    ship_area: +$('shipArea').value,
    ship_type: $('shipType').value,
    sam_range: +$('samRange').value,
    sam_max_alt: +$('samMaxAlt').value,
    vm: +$('vm').value,
    vi: +$('vi').value,
    interceptor_dia: +$('interceptorDia').value,
    seeker_type: $('seekerType').value,
    has_awacs: $('aewPreset').value !== AEW_NONE_VALUE,
    asm_id: asmId,
    maneuver_class: asmPreset?.maneuver_class || '',
  };
}

function collectSimParams() {
  return {
    nm: +$('Nm').value,
    vm: +$('vm').value,
    D: +$('D').value,
    ni: +$('Ni').value,
    vi: +$('vi').value,
    pk: +$('pk').value,
    tlock: +$('tlock').value,
    minr: +$('minr').value,
  };
}

function renderResults(r) {
  $('placeholder').style.display = 'none';
  $('resultsBody').style.display = 'block';
  $('statusTag').textContent = 'DONE';

  const windows = r.windows || [];
  const nRounds = r.n_rounds || 0;
  const theadW = document.querySelector('#windowTable thead');
  const tbodyW = document.querySelector('#windowTable tbody');
  theadW.innerHTML =
    '<tr><th>窗口</th><th>轮次起始距离 (km)</th><th>拦截弹飞行时间 (s)</th><th>本轮耗时 (s)</th><th>轮末剩余距离 (km)</th></tr>';
  tbodyW.innerHTML =
    windows
      .map(
        (w) => `<tr>
      <td>#${w.round}</td><td>${fmt(w.dist_start_km, 2)}</td><td>${fmt(w.t_fly_s, 1)}</td>
      <td>${fmt(w.total_t_s, 1)}</td><td>${fmt(w.dist_end_km, 2)}</td>
    </tr>`
      )
      .join('') ||
    '<tr><td colspan="5">发现距离不足以形成任何拦截窗口 — 检查参数（发现距离/速度/锁定时间）</td></tr>';

  if (nRounds === 0) {
    $('statRounds').textContent = '0';
    $('statLeak').textContent = r.nm;
    $('statRate').textContent = '0%';
    $('statRoundsSub').textContent = '';
    $('statLeakSub').textContent = '';
    $('statRateSub').textContent = '';
    $('finalNote').textContent = r.note || '';
    document.querySelector('#planTable thead').innerHTML = '';
    document.querySelector('#planTable tbody').innerHTML = '';
    document.querySelector('#strategyTable thead').innerHTML = '';
    document.querySelector('#strategyTable tbody').innerHTML = '';
    if (chartRef) chartRef.destroy();
    $('mcN').textContent = r.final_trials || '–';
    return;
  }

  const best = r.best;
  const avgSurvivors = r.avg_survivors || [];
  const allCandidates = r.all_candidates || [];
  const expectedLeak = r.expected_leak;
  const interceptRate = r.intercept_rate;
  const pk = r.pk;
  const ni = r.ni;
  const nm = r.nm;
  const tlock = r.t_lock_s;

  $('mcN').textContent = r.final_trials;
  $('statRounds').textContent = nRounds;
  $('statRoundsSub').textContent = `火控锁定 ${tlock}s / 轮`;
  $('statLeak').textContent = fmt(expectedLeak, 2);
  $('statLeakSub').textContent = `/ 共 ${nm} 枚来袭`;
  $('statRate').textContent = fmt(interceptRate * 100, 1) + '%';
  $('statRateSub').textContent = `弹药消耗 ≤ ${ni} 枚`;

  const theadP = document.querySelector('#planTable thead');
  const tbodyP = document.querySelector('#planTable tbody');
  theadP.innerHTML =
    '<tr><th>窗口</th><th>本轮弹药预算</th><th>预期存活目标数(轮初)</th><th>每目标约分配</th><th>单目标本轮杀伤概率</th></tr>';
  const planRows = r.plan_rows || [];
  let maxPer = 1;
  if (planRows.length) {
    planRows.forEach((row) => {
      maxPer = Math.max(maxPer, row.per_target || 0);
    });
  } else {
    for (let i = 0; i < nRounds; i++) {
      const surv = avgSurvivors[i];
      if (surv > 0) maxPer = Math.max(maxPer, best.plan[i] / surv);
    }
  }
  let rows = '';
  const nPlan = planRows.length || nRounds;
  for (let ri = 0; ri < nPlan; ri++) {
    const row = planRows[ri];
    const survBefore = row ? row.survivors : avgSurvivors[ri];
    const perTarget = row ? row.per_target : (survBefore > 0 ? best.plan[ri] / survBefore : 0);
    const budget = row ? row.budget : best.plan[ri];
    const pkill = row ? row.kill_prob : roundKillProbability(pk, perTarget);
    rows += `<tr>
      <td>#${ri + 1}</td>
      <td>${budget} 枚</td>
      <td>${fmt(survBefore, 2)}</td>
      <td>≈${fmt(perTarget, 2)} 枚/目标
        <div class="bar-wrap"><div class="bar-bg"><div class="bar-fill i" style="width:${Math.min(100, (perTarget / maxPer) * 100)}%"></div></div></div>
      </td>
      <td>${fmt(pkill * 100, 1)}%</td>
    </tr>`;
  }
  tbodyP.innerHTML = rows;

  const canvas = $('survivorChart');
  if (chartRef) {
    chartRef.destroy();
    chartRef = null;
  }
  if (canvas && typeof Chart !== 'undefined' && avgSurvivors.length) {
    const ctx = canvas.getContext('2d');
    const labels = ['发现'].concat(windows.map((w) => '窗口#' + w.round + '后'));
    chartRef = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: '预期剩余来袭导弹数',
            data: avgSurvivors,
            borderColor: '#ff4d4f',
            backgroundColor: 'rgba(255,77,79,0.12)',
            fill: true,
            tension: 0.25,
            pointRadius: 3,
            pointBackgroundColor: '#ff4d4f',
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: '#7b8e92', font: { family: 'monospace', size: 10 } } } },
        scales: {
          x: { ticks: { color: '#7b8e92', font: { family: 'monospace', size: 9 } }, grid: { color: '#1c2b30' } },
          y: {
            beginAtZero: true,
            ticks: { color: '#7b8e92', font: { family: 'monospace', size: 9 } },
            grid: { color: '#1c2b30' },
          },
        },
      },
    });
  }

  const theadS = document.querySelector('#strategyTable thead');
  const tbodyS = document.querySelector('#strategyTable tbody');
  theadS.innerHTML = '<tr><th>策略</th><th>各轮弹药分配</th><th>期望突防导弹数</th><th>相对最优方案</th></tr>';
  if (!allCandidates.length) {
    tbodyS.innerHTML = '';
  } else {
    const minScore = allCandidates[0].expected_leak;
    const bestKey = best.plan.join(',');
    tbodyS.innerHTML = allCandidates
      .map((c) => {
        const isBest = c.is_best || (c.name === best.name && c.plan.join(',') === bestKey);
        const relLabel = c.relative_label || (isBest ? '最优' : '+' + fmt(c.expected_leak - minScore, 2));
        const relClass = c.relative_tone === 'worse' ? 'worse' : (isBest ? 'best-label' : '');
        return `<tr class="${isBest ? 'best' : ''}">
        <td>${isBest ? '★ ' : ''}${c.name}</td>
        <td>[${c.plan.join(', ')}]</td>
        <td>${fmt(c.expected_leak, 2)}</td>
        <td class="${relClass}">${isBest ? '最优' : relLabel}</td>
      </tr>`;
      })
      .join('');
  }

  $('finalNote').textContent = r.note || '';
}

async function ensureEngine() {
  if (!pyReady) await initPyodide();
}

/** 一次估算交战距离与单发拦截成功概率（拦截率输入），填入按钮下方两字段。 */
async function onEstimateDistanceAndPk() {
  const btn = $('estimateBtn');
  btn.disabled = true;
  try {
    await ensureEngine();
    const params = collectEstimateParams();
    const dist = callPython('estimate_distance', params);
    if (!dist.success) throw new Error(dist.error || '交战距离估算失败');
    $('awacsDetectKm').value = dist.has_awacs ? Number(dist.awacs_detect_km).toFixed(1) : '0';
    $('shipDetectKm').value = Number(dist.ship_detect_km).toFixed(1);
    $('diveEntryDisplay').value = formatDiveEntryDisplay(dist);
    $('D').value = Number(dist.engage_dist).toFixed(1);
    const diveSuffix = diveEntrySuffix(dist);
    const formula = engageFormulaLabel(dist);
    const noAwacsFormula = dist.dive_entry_km != null && dist.dive_entry_km > 0
      ? 'min(舰载探测,射程,俯冲进入)' : 'min(舰载探测,射程)';
    $('distBreakdown').textContent = dist.has_awacs
      ? `预警机雷达探测: ${dist.awacs_detect.toFixed(0)}km(功率限${dist.awacs_power.toFixed(0)}/视距限${dist.awacs_horizon.toFixed(0)}) + 前出${dist.standoff.toFixed(0)}km = ${dist.awacs_detect_km.toFixed(0)}km ｜ 舰载雷达探测: ${dist.ship_detect_km.toFixed(0)}km(功率限${dist.ship_power.toFixed(0)}/视距限${dist.ship_horizon.toFixed(0)}km，交战高度${Number(dist.h_engage_m).toFixed(0)}m) ｜ 拦截弹射程: ${dist.sam_range.toFixed(0)}km / 最大射高: ${Number(dist.sam_max_alt_km).toFixed(1)}km → 交战距离＝${formula}${diveSuffix}＝${dist.engage_dist.toFixed(1)}km（受限于：${dist.binding}）— 已填入下方字段，可手动修改。`
      : `无预警机：巡航高度 ${dist.h_target_m.toFixed(0)}m，交战高度 ${Number(dist.h_engage_m).toFixed(0)}m ｜ 舰载雷达探测＝min(功率限${dist.ship_power.toFixed(0)}km, 视距限${dist.ship_horizon.toFixed(0)}km)＝${dist.ship_detect_km.toFixed(0)}km ｜ 拦截弹射程: ${dist.sam_range.toFixed(0)}km / 最大射高: ${Number(dist.sam_max_alt_km).toFixed(1)}km → 交战距离＝${noAwacsFormula}${diveSuffix}＝${dist.engage_dist.toFixed(1)}km（受限于：${dist.binding}）— 已填入下方字段，可手动修改。`;

    const pkR = callPython('estimate_pk', params);
    if (!pkR.success) throw new Error(pkR.error || '拦截率估算失败');
    $('pk').value = Number(pkR.pk).toFixed(2);
    $('pkEstBreakdown').textContent =
      `估算拦截率（单发）= ${pkR.pk.toFixed(2)}（基线0.75 × 速度系数${pkR.speed_factor.toFixed(2)} × 舰载雷达增益${pkR.ship_radar_factor.toFixed(2)} × 导引头增益${pkR.seeker_factor.toFixed(2)} × RCS系数${pkR.rcs_factor.toFixed(2)} × 弹道系数${pkR.traj_factor.toFixed(2)} × 机动性系数${Number(pkR.maneuver_factor).toFixed(2)}[${pkR.maneuver_class}]）— 已填入下方「单发拦截成功概率」，可手动修改。`;
  } catch (e) {
    const msg = String(e.message || e);
    $('distBreakdown').textContent = msg;
    $('pkEstBreakdown').textContent = '';
    $('statusTag').textContent = 'ERROR';
  } finally {
    btn.disabled = false;
  }
}

async function onRun() {
  const btn = $('runBtn');
  // 计算进行中再次点击：排队，结束后用最新表单参数再跑
  if (runLock) {
    rerunRequested = true;
    $('statusTag').textContent = 'QUEUED';
    btn.textContent = '▶ 已排队，稍后重算…';
    return;
  }
  runLock = true;
  rerunRequested = false;
  btn.disabled = true;
  try {
    if (!pyReady) {
      btn.textContent = '▶ 加载引擎中…';
      $('statusTag').textContent = 'LOADING';
      await ensureEngine();
    }
    btn.textContent = '▶ 计算中…';
    $('statusTag').textContent = 'COMPUTING';
    // 让浏览器先绘制按钮/状态，再进入阻塞式蒙特卡洛
    await new Promise((r) => setTimeout(r, 40));
    const r = await callPythonAsync('simulate', collectSimParams());
    if (!r.success) throw new Error(r.error || '仿真失败');
    renderResults(r);
    markResultFresh();
  } catch (e) {
    $('statusTag').textContent = 'ERROR';
    $('placeholder').style.display = 'block';
    $('placeholder').textContent = String(e.message || e);
    $('resultsBody').style.display = 'none';
  } finally {
    runLock = false;
    btn.disabled = false;
    btn.textContent = '▶ 运行仿真 / RUN';
    if (rerunRequested) {
      rerunRequested = false;
      // 用用户改过的最新参数再跑一轮
      setTimeout(() => onRun(), 0);
    }
  }
}

function tickClock() {
  const d = new Date();
  $('clock').textContent = d.toTimeString().slice(0, 8) + ' · SIM CLOCK';
}

function populateTrajSelect() {
  const select = $('traj');
  if (!select) return;
  const types = data?.missile_interception_config?.traj_types || {
    high: '高空 / 常规弹道',
    sea: '掠海 / 海面杂波环境',
    glide: '滑翔体弹道（鹰击-17 等）',
    ballistic: '弹道导弹弹道（鹰击-20/21 等）',
  };
  const current = select.value;
  select.innerHTML = Object.entries(types)
    .map(([id, label]) => `<option value="${id}">${label}</option>`)
    .join('');
  if (current && types[current]) select.value = current;
}

function applyMissileInterceptionUiDefaults() {
  const ui = data?.missile_interception_config?.ui;
  if (!ui) return;
  const fields = {
    Nm: ui.nm,
    Ni: ui.ni,
    vm: ui.vm,
    rcs: ui.rcs,
    awacsArea: ui.awacs_area,
    standoff: ui.standoff,
    shipArea: ui.ship_area,
    samRange: ui.sam_range,
    samMaxAlt: ui.sam_max_alt ?? 33,
    vi: ui.vi,
    interceptorDia: ui.interceptor_dia,
    tlock: ui.tlock,
    minr: ui.minr,
    D: ui.discovery_km,
    pk: ui.pk,
  };
  for (const [id, val] of Object.entries(fields)) {
    const el = $(id);
    if (el && val != null && val !== '') el.value = val;
  }
  if (ui.traj) $('traj').value = ui.traj;
  if (ui.awacs_type) $('awacsType').value = ui.awacs_type;
  if (ui.ship_type) $('shipType').value = ui.ship_type;
  if (ui.seeker_type) $('seekerType').value = ui.seeker_type;
  if (ui.aew_preset) $('aewPreset').value = ui.aew_preset;
  setAwacsFieldsDisabled($('aewPreset').value === AEW_NONE_VALUE);
}

/** 与 Python round_kill_probability 对齐的回退算法（API 未返回 plan_rows 时）。 */
function roundKillProbability(pk, interceptorsPerTarget) {
  const p = Math.min(1, Math.max(0, Number(pk) || 0));
  const n = Math.max(0, Number(interceptorsPerTarget) || 0);
  const k = Math.floor(n);
  const frac = n - k;
  const pK = k <= 0 ? 0 : 1 - Math.pow(1 - p, k);
  const pK1 = 1 - Math.pow(1 - p, k + 1);
  return (1 - frac) * pK + frac * pK1;
}

function markResultFresh() {
  resultFresh = true;
  const banner = $('staleBanner');
  const panel = $('resultsPanel');
  if (banner) banner.classList.add('hidden');
  if (panel) panel.classList.remove('stale');
  const tag = $('statusTag');
  if (tag && tag.textContent === 'STALE') tag.textContent = 'DONE';
}

function markResultsStale() {
  if (!resultFresh) return;
  resultFresh = false;
  const banner = $('staleBanner');
  const panel = $('resultsPanel');
  if (banner) banner.classList.remove('hidden');
  if (panel) panel.classList.add('stale');
  const tag = $('statusTag');
  if (tag && (tag.textContent === 'DONE' || tag.textContent === 'STANDBY')) {
    tag.textContent = 'STALE';
  }
}

function applyFieldHintsAndRanges() {
  const cfg = data?.missile_interception_config || {};
  const hints = cfg.field_hints || {};
  const ranges = cfg.field_ranges || {};
  const idToKey = {
    Nm: 'nm', Ni: 'ni', vm: 'vm', rcs: 'rcs', traj: 'traj',
    awacsArea: 'awacsArea', awacsType: 'awacsType', standoff: 'standoff',
    shipArea: 'shipArea', shipType: 'shipType', samRange: 'samRange',
    samMaxAlt: 'samMaxAlt', vi: 'vi', interceptorDia: 'interceptorDia',
    seekerType: 'seekerType', tlock: 'tlock', minr: 'minr', pk: 'pk',
  };
  Object.entries(idToKey).forEach(([id, key]) => {
    const el = $(id);
    if (!el) return;
    const field = el.closest('.field');
    const label = field && field.querySelector('label');
    if (label && hints[key] && !label.querySelector('.hint-q')) {
      const tip = document.createElement('span');
      tip.className = 'hint-q';
      tip.title = hints[key];
      tip.textContent = '?';
      label.appendChild(tip);
    }
    const spec = ranges[key];
    if (spec && el.tagName === 'INPUT') {
      if (spec.min != null) el.min = spec.min;
      if (spec.max != null) el.max = spec.max;
      if (spec.step != null) el.step = spec.step;
      if (field && !field.querySelector('.field-range')) {
        const hint = document.createElement('div');
        hint.className = 'field-range';
        const unit = spec.unit ? ` ${spec.unit}` : '';
        hint.textContent = `范围 ${spec.min}–${spec.max}${unit}`;
        field.appendChild(hint);
      }
    }
  });
}

function bindStaleOnInputs() {
  document.querySelectorAll('.panel input, .panel select').forEach((el) => {
    el.addEventListener('change', markResultsStale);
    el.addEventListener('input', markResultsStale);
  });
}

function setupBackToTop() {
  const btn = $('backToTop');
  if (!btn) return;
  const onScroll = () => {
    btn.hidden = window.scrollY < 360;
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  onScroll();
}

async function bootEstimateThenRun() {
  await onEstimateDistanceAndPk();
  await onRun();
}

async function main() {
  setInterval(tickClock, 1000);
  tickClock();
  try {
    await loadData();
    populateTrajSelect();
    applyPresetsFromData();
    applyMissileInterceptionUiDefaults();
    applyFieldHintsAndRanges();
  } catch (e) {
    $('statusTag').textContent = 'ERROR';
    $('placeholder').textContent = String(e.message || e);
    return;
  }
  $('estimateBtn').addEventListener('click', onEstimateDistanceAndPk);
  $('runBtn').addEventListener('click', onRun);
  bindStaleOnInputs();
  setupBackToTop();
  // 引擎就绪后先估算探测距离（避免默认 0 km），再跑默认仿真
  bootEstimateThenRun();
}

main();
