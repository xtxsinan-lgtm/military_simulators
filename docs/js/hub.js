/**
 * 启动页：从 data.json.simulators 动态列出可选模拟器。
 */
const HUB_VERSION = 4;

async function main() {
  const grid = document.getElementById('simGrid');
  const status = document.getElementById('hubStatus');
  try {
    const resp = await fetch(`data.json?v=${HUB_VERSION}`);
    if (!resp.ok) throw new Error(`无法加载 data.json (${resp.status})`);
    const data = await resp.json();
    const sims = data.simulators || [];
    if (!sims.length) throw new Error('data.json 缺少 simulators，请运行 python3 scripts/build_all.py');

    grid.innerHTML = '';
    for (const s of sims) {
      const a = document.createElement('a');
      a.className = `sim-card ${s.id}`;
      a.href = s.html || '#';
      const eyebrow = s.eyebrow || String(s.id || '').toUpperCase();
      a.innerHTML = `
        <div class="sim-id">${eyebrow}</div>
        <h2 class="sim-name">${s.name}</h2>
        <p class="sim-sub">${s.subtitle || ''}</p>
        <div class="sim-cta">进入仿真 →</div>
      `;
      grid.appendChild(a);
    }
  } catch (e) {
    if (status) {
      status.className = 'hub-error';
      status.textContent = String(e.message || e);
    }
  }
}

main();
