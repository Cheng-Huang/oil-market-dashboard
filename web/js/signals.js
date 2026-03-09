/**
 * 信号面板渲染
 */

const SIGNAL_NAMES = {
  inventory:   '库存趋势',
  curve:       '曲线结构',
  demand:      '需求强度',
  drilling:    '钻井活动',
  opec:        '全球供需',
  financial:   '金融条件',
  positioning: '持仓拥挤',
};

const SIGNAL_EMOJI = {
  bullish: '🟢',
  bearish: '🔴',
  warning: '⚠️',
  neutral: '⚪',
};

const SIGNAL_LABEL = {
  bullish: '利多',
  bearish: '利空',
  warning: '警惕',
  neutral: '中性',
};

function renderSignalGrid(signals) {
  const grid = document.getElementById('signal-grid');
  if (!grid) return;
  grid.innerHTML = '';

  for (const [key, val] of Object.entries(signals)) {
    const name = val.name || SIGNAL_NAMES[key] || key;
    const sig = val.signal || 'neutral';
    const emoji = SIGNAL_EMOJI[sig] || '⚪';
    const label = SIGNAL_LABEL[sig] || '中性';

    const item = document.createElement('div');
    item.className = 'flex items-center gap-1 py-0.5';
    item.innerHTML = `
      <span class="signal-dot ${sig}"></span>
      <span class="text-gray-400">${name}</span>
      <span class="ml-auto text-xs font-medium ${sig === 'bullish' ? 'text-green-400' : sig === 'bearish' ? 'text-red-400' : sig === 'warning' ? 'text-amber-400' : 'text-gray-500'}">${label}</span>
    `;
    grid.appendChild(item);
  }
}
