const api = require('../../utils/api.js');

Page({
  data: {
    simulators: [],
    statusText: '加载中…',
    error: false,
  },

  onShow() {
    api.loadSimulatorData()
      .then((data) => {
        const sims = (data.simulators || []).map((s) => ({
          ...s,
          eyebrow: s.eyebrow || String(s.id || '').toUpperCase(),
        }));
        this.setData({
          simulators: sims,
          statusText: sims.length
            ? `已同步 ${ (data.aircraft || []).length } 种舰载机 · ${ (data.carriers || []).length } 艘航母 · 饱和装备预设已加载`
            : 'data.json 缺少 simulators，请运行 build_all.py',
          error: !sims.length,
        });
      })
      .catch((e) => {
        this.setData({ statusText: String(e.message || e), error: true });
      });
  },

  onOpen(e) {
    const page = e.currentTarget.dataset.page;
    if (!page) return;
    // tabBar 页面用 switchTab，其它用 navigateTo
    if (page.indexOf('/pages/index/') === 0
        || page.indexOf('/pages/missile_interception/') === 0
        || page.indexOf('/pages/combat_radius/') === 0) {
      wx.switchTab({ url: page });
    } else {
      wx.navigateTo({ url: page });
    }
  },
});
