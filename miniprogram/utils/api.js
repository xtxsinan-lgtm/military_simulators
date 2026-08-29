const config = require('../config.js');

/** 读取内置航母/战斗机数据库（CommonJS，微信小程序可可靠 require） */
function loadLocalData() {
  try {
    // 必须用 .js：部分基础库/打包器对 require('.json') 支持不稳定
    return require('../data/data.js');
  } catch (e) {
    const detail = (e && e.message) ? e.message : String(e);
    throw new Error(
      '缺少 data/data.js，请在仓库根目录运行 python3 scripts/build_all.py（' + detail + '）'
    );
  }
}

/**
 * 加载仿真数据：优先使用本地 data.js，保证界面可选；
 * 若配置了 apiBaseUrl，再尝试用远端数据覆盖（失败则保留本地）。
 */
function loadSimulatorData() {
  let local;
  try {
    local = loadLocalData();
  } catch (e) {
    return Promise.reject(e);
  }
  if (!local || !local.carriers || !local.aircraft) {
    return Promise.reject(new Error('本地数据格式无效，请重新运行 build_all.py'));
  }
  const base = config.apiBaseUrl;
  if (!base) {
    return Promise.resolve(local);
  }
  return new Promise((resolve) => {
    wx.request({
      url: `${base}/api/data`,
      method: 'GET',
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data && res.data.carriers) {
          resolve(res.data);
        } else {
          resolve(local);
        }
      },
      fail() {
        resolve(local);
      },
    });
  });
}

/** 调用后端 Python 仿真 API */
function runSimulation(payload) {
  const base = config.apiBaseUrl;
  if (!base) {
    return Promise.reject(
      new Error('未配置 apiBaseUrl。请在 config.js 填写后端地址，或运行 python3 apps/miniprogram_api.py')
    );
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${base}/api/simulate`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: payload,
      timeout: 120000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data) {
          resolve(res.data);
        } else {
          const msg = (res.data && res.data.error) || `仿真请求失败 (${res.statusCode})`;
          reject(new Error(msg));
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '仿真网络请求失败'));
      },
    });
  });
}

/** 调用后端饱和打击仿真 API */
function runMissileInterceptionSimulation(payload) {
  const base = config.apiBaseUrl;
  if (!base) {
    return Promise.reject(
      new Error('未配置 apiBaseUrl。请在 config.js 填写后端地址，或运行 python3 apps/miniprogram_api.py')
    );
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${base}/api/missile_interception/simulate`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: payload,
      timeout: 180000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data) {
          resolve(res.data);
        } else {
          const msg = (res.data && res.data.error) || `饱和打击请求失败 (${res.statusCode})`;
          reject(new Error(msg));
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '饱和打击网络请求失败'));
      },
    });
  });
}

/** 调用后端作战半径 / 升阻比估算 API */
function runCombatRadiusSimulation(payload) {
  const base = config.apiBaseUrl;
  if (!base) {
    return Promise.reject(
      new Error('未配置 apiBaseUrl。请在 config.js 填写后端地址，或运行 python3 apps/miniprogram_api.py')
    );
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${base}/api/combat_radius/simulate`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: payload,
      timeout: 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data) {
          resolve(res.data);
        } else {
          const msg = (res.data && res.data.error) || `作战半径请求失败 (${res.statusCode})`;
          reject(new Error(msg));
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '作战半径网络请求失败'));
      },
    });
  });
}
function modesToList(modes) {
  const src = modes || {};
  return Object.keys(src).map((id) => ({ id, label: src[id] }));
}

module.exports = {
  loadLocalData,
  loadSimulatorData,
  runSimulation,
  runMissileInterceptionSimulation,
  runCombatRadiusSimulation,
  modesToList,
};
