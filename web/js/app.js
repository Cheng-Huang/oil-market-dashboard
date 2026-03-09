/**
 * Oil Dashboard — 主入口
 * 加载 JSON 数据 → 渲染所有图表和卡片
 */

// 本地开发用 ../data，GitHub Pages 部署用 ./data
const DATA_BASE = (location.hostname === 'localhost' || location.hostname === '127.0.0.1' || location.protocol === 'file:')
  ? '../data'
  : './data';

// ── 工具函数 ──────────────────────────────────────────
async function loadJSON(file) {
  try {
    const resp = await fetch(`${DATA_BASE}/${file}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    console.warn(`加载 ${file} 失败:`, e);
    return null;
  }
}

function fmt(val, decimals = 2) {
  if (val == null) return '--';
  return Number(val).toFixed(decimals);
}

function pctChange(series, n = 1) {
  if (!series || series.length < n + 1) return 0;
  const curr = series[series.length - 1].value;
  const prev = series[series.length - 1 - n].value;
  return prev !== 0 ? ((curr - prev) / prev * 100) : 0;
}

function initChart(domId) {
  const dom = document.getElementById(domId);
  if (!dom) return null;
  return echarts.init(dom, null, { renderer: 'canvas' });
}

function last(arr) {
  return arr && arr.length > 0 ? arr[arr.length - 1] : null;
}

// ── 价格卡片 ─────────────────────────────────────────
function renderPriceCards(price) {
  if (!price) return;

  // WTI
  const wtiLast = last(price.wti);
  const wtiChg = pctChange(price.wti);
  document.getElementById('wti-price').textContent = `$${fmt(wtiLast?.value)}`;
  const wtiEl = document.getElementById('wti-change');
  wtiEl.textContent = `${wtiChg >= 0 ? '+' : ''}${fmt(wtiChg)}%`;
  wtiEl.className = `text-sm font-medium px-2 py-0.5 rounded ${wtiChg >= 0 ? 'change-up' : 'change-down'}`;

  // Brent
  const brentLast = last(price.brent);
  const brentChg = pctChange(price.brent);
  document.getElementById('brent-price').textContent = `$${fmt(brentLast?.value)}`;
  const brentEl = document.getElementById('brent-change');
  brentEl.textContent = `${brentChg >= 0 ? '+' : ''}${fmt(brentChg)}%`;
  brentEl.className = `text-sm font-medium px-2 py-0.5 rounded ${brentChg >= 0 ? 'change-up' : 'change-down'}`;

  // Spread
  const spreadLast = last(price.spread);
  document.getElementById('spread-val').textContent = `$${fmt(spreadLast?.value)}`;

  // Sparklines (最近 30 天)
  const recent30 = (arr) => arr ? arr.slice(-30) : [];
  const wtiSpark = initChart('wti-spark');
  if (wtiSpark) wtiSpark.setOption(sparkOption(recent30(price.wti), wtiChg >= 0 ? COLORS.green : COLORS.red));

  const brentSpark = initChart('brent-spark');
  if (brentSpark) brentSpark.setOption(sparkOption(recent30(price.brent), brentChg >= 0 ? COLORS.green : COLORS.red));

  const spreadSpark = initChart('spread-spark');
  if (spreadSpark) spreadSpark.setOption(sparkOption(recent30(price.spread), COLORS.cyan));
}

// ── 曲线标签 ─────────────────────────────────────────
function renderCurveLabel(signals, futures) {
  if (!signals?.curve) return;
  const lbl = document.getElementById('curve-label');
  const sig = signals.curve;
  const text = sig.label || 'N/A';
  let cls = 'label-flat';
  if (sig.signal === 'bullish') cls = 'label-back';
  else if (sig.signal === 'bearish') cls = 'label-contango';
  lbl.textContent = text;
  lbl.className = `text-xs font-medium px-2 py-1 rounded ${cls}`;

  // 更新 spread 卡片显示 M1-M2 期货价差（如果有）
  if (futures && futures.m1_m2_spread != null) {
    const spreadVal = document.getElementById('spread-val');
    if (spreadVal) spreadVal.textContent = `$${fmt(futures.m1_m2_spread, 4)}`;
    const spreadLabel = document.getElementById('spread-type-label');
    if (spreadLabel) spreadLabel.textContent = 'M1−M2 期货价差';
  }

  // 显示数据来源标记
  const srcEl = document.getElementById('spread-source');
  if (srcEl) {
    if (sig.source === 'futures') {
      srcEl.textContent = '📡 真实期货数据';
      srcEl.className = 'text-xs text-green-500 mt-1';
    } else {
      srcEl.textContent = '⚠ WTI-Brent 近似';
      srcEl.className = 'text-xs text-amber-500 mt-1';
    }
  }
}

// ── 库存图 ───────────────────────────────────────────
function renderInventoryChart(inventory) {
  if (!inventory?.crude) return;
  const chart = initChart('chart-inventory');
  if (!chart) return;
  chart.setOption(inventoryAreaChart(inventory.crude, '原油商业库存 (千桶)'));
}

// ── 子库存图 (Cushing + 汽油 + 馏分油) ───────────────
function renderSubInventoryChart(inventory) {
  if (!inventory) return;
  const chart = initChart('chart-sub-inventory');
  if (!chart) return;

  const series = [];
  if (inventory.cushing) series.push({ name: '库欣', data: inventory.cushing, color: COLORS.amber });
  if (inventory.gasoline) series.push({ name: '汽油', data: inventory.gasoline, color: COLORS.green });
  if (inventory.distillate) series.push({ name: '馏分油', data: inventory.distillate, color: COLORS.purple });

  if (series.length === 0) return;
  const opt = lineChart(series, { dataZoom: true, zoomStart: 60 });
  chart.setOption(opt);
}

// ── 价格走势图 ───────────────────────────────────────
function renderPriceChart(price) {
  if (!price) return;
  const chart = initChart('chart-price');
  if (!chart) return;

  const series = [];
  if (price.wti) series.push({ name: 'WTI', data: price.wti, color: COLORS.cyan });
  if (price.brent) series.push({ name: 'Brent', data: price.brent, color: COLORS.amber });

  const opt = lineChart(series, { dataZoom: true, zoomStart: 50, yAxisName: '$/bbl' });
  chart.setOption(opt);
}

// ── 价差走势图 ───────────────────────────────────────
function renderSpreadChart(price, futures) {
  // 优先显示 M1-M2 期货价差历史；否则回退到 WTI-Brent 价差
  if (futures?.spread_history?.length > 0) {
    const chart = initChart('chart-spread');
    if (!chart) return;
    chart.setOption(futuresSpreadChart(futures.spread_history));
    // 更新面板标题
    const title = document.querySelector('#chart-spread')?.closest('.panel')?.querySelector('.panel-title');
    if (title) title.textContent = '📈 M1-M2 期货价差走势 (Backwardation / Contango)';
    return;
  }

  // 回退到 WTI-Brent
  if (!price?.spread) return;
  const chart = initChart('chart-spread');
  if (!chart) return;

  const opt = baseOption();
  const dates = price.spread.map(d => d.date);
  const values = price.spread.map(d => d.value);
  opt.xAxis.data = dates;
  opt.series = [{
    name: 'WTI − Brent',
    type: 'line',
    data: values.map(v => ({
      value: v,
      itemStyle: { color: v >= 0 ? COLORS.green : COLORS.red },
    })),
    showSymbol: false,
    lineStyle: { width: 1.8, color: COLORS.cyan },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: COLORS.cyan + '30' },
          { offset: 1, color: COLORS.cyan + '05' },
        ]
      }
    },
    markLine: {
      silent: true,
      data: [{ yAxis: 0, lineStyle: { color: '#6b7280', type: 'dashed' } }],
    },
  }];
  opt.dataZoom = [{ type: 'inside', start: 50, end: 100 }];
  chart.setOption(opt);
}

// ── 期货曲线图 ───────────────────────────────────────
function renderFuturesCurveChart(futures) {
  if (!futures?.curve?.length) {
    // 隐藏面板
    const panel = document.getElementById('chart-futures-curve')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-futures-curve');
  if (!chart) return;
  chart.setOption(futuresCurveChart(futures.curve));
}

// ── 产量 + 开工率 ────────────────────────────────────
function renderProductionChart(production) {
  if (!production) return;
  const chart = initChart('chart-production');
  if (!chart) return;

  const series = [];
  if (production.crude_production) {
    series.push({ name: '原油产量 (千桶/日)', data: production.crude_production, color: COLORS.cyan });
  }
  if (production.refinery_utilization) {
    series.push({ name: '炼厂开工率 (%)', data: production.refinery_utilization, color: COLORS.amber, yAxisIndex: 1 });
  }

  const opt = lineChart(series, {
    dualAxis: true,
    yAxisName: '千桶/日',
    y2AxisName: '%',
    dataZoom: true,
    zoomStart: 50,
  });
  chart.setOption(opt);
}

// ── 金融条件 ─────────────────────────────────────────
function renderFinancialChart(financial) {
  if (!financial) return;
  const chart = initChart('chart-financial');
  if (!chart) return;

  const series = [];
  if (financial.dxy) series.push({ name: 'DXY 美元指数', data: financial.dxy, color: COLORS.blue });
  if (financial.real_rate) series.push({ name: '10Y 实际利率 (%)', data: financial.real_rate, color: COLORS.amber, yAxisIndex: 1 });
  if (financial.ovx) series.push({ name: 'OVX 波动率', data: financial.ovx, color: COLORS.red, yAxisIndex: 1 });

  const opt = lineChart(series, {
    dualAxis: true,
    yAxisName: 'DXY',
    y2AxisName: '% / 指数',
    dataZoom: true,
    zoomStart: 50,
  });

  // OVX 恐慌线
  if (financial.ovx) {
    opt.series.push({
      name: 'OVX 恐慌线',
      type: 'line',
      data: financial.ovx.map(() => 40),
      showSymbol: false,
      lineStyle: { color: COLORS.red, width: 1, type: 'dashed' },
      yAxisIndex: 1,
    });
  }

  chart.setOption(opt);
}

// ── 需求 ─────────────────────────────────────────────
function renderDemandChart(demand) {
  if (!demand) return;
  const chart = initChart('chart-demand');
  if (!chart) return;

  const series = [];
  if (demand.gasoline) series.push({ name: '汽油需求 (千桶/日)', data: demand.gasoline, color: COLORS.green });
  if (demand.distillate) series.push({ name: '馏分油需求 (千桶/日)', data: demand.distillate, color: COLORS.purple });

  const opt = lineChart(series, { dataZoom: true, zoomStart: 50 });
  chart.setOption(opt);
}

// ── CFTC 持仓 ────────────────────────────────────────
function renderCFTCChart(cftc) {
  if (!cftc || cftc.length === 0) return;
  const chart = initChart('chart-cftc');
  if (!chart) return;
  chart.setOption(barChart(cftc, '投机净多头 (合约数)'));
}
// ── 裂解价差 ─────────────────────────────────────
function renderCrackSpreadChart(crackSpread) {
  if (!crackSpread) {
    const panel = document.getElementById('chart-crack-spread')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-crack-spread');
  if (!chart) return;
  chart.setOption(crackSpreadChart(crackSpread));
}

// ── 净进口 ───────────────────────────────────────────
function renderNetImportChart(production) {
  if (!production?.net_import) {
    const panel = document.getElementById('chart-net-import')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-net-import');
  if (!chart) return;
  const opt = lineChart(
    [{ name: '原油净进口 (千桶/日)', data: production.net_import, color: COLORS.purple }],
    { dataZoom: true, zoomStart: 50, yAxisName: '千桶/日' }
  );
  chart.setOption(opt);
}

// ── OPEC / 全球供需平衡 ─────────────────────────────
function renderGlobalBalanceChart(globalBalance) {
  if (!globalBalance || !globalBalance.balance?.length) {
    const panel = document.getElementById('chart-global-balance')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-global-balance');
  if (!chart) return;
  chart.setOption(globalBalanceChart(globalBalance));
}

// ── 钻机数 ───────────────────────────────────────────
function renderDrillingChart(drilling) {
  if (!drilling || !drilling.rig_count?.length) {
    const panel = document.getElementById('chart-drilling')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-drilling');
  if (!chart) return;
  chart.setOption(rigCountChart(drilling));
}
// ── 元信息 ───────────────────────────────────────────
function renderMeta(meta) {
  const el = document.getElementById('header-meta');
  if (!el || !meta) return;
  const t = meta.last_updated || '';
  const src = meta.sources ? Object.values(meta.sources).map(s => s.source || s).join(' / ') : '';
  el.textContent = `更新: ${t.slice(0, 16).replace('T', ' ')} · ${src}`;
}

// ── 窗口自适应 ───────────────────────────────────────
function handleResize() {
  document.querySelectorAll('.chart-box').forEach(dom => {
    const instance = echarts.getInstanceByDom(dom);
    if (instance) instance.resize();
  });
}

// ── 主入口 ───────────────────────────────────────────
async function main() {
  // 并行加载所有 JSON
  const [price, inventory, production, demand, financial, cftc, signals, meta, futures, crackSpread, globalBalance, drilling] = await Promise.all([
    loadJSON('price.json'),
    loadJSON('inventory.json'),
    loadJSON('production.json'),
    loadJSON('demand.json'),
    loadJSON('financial.json'),
    loadJSON('cftc.json'),
    loadJSON('signals.json'),
    loadJSON('meta.json'),
    loadJSON('futures.json'),
    loadJSON('crack_spread.json'),
    loadJSON('global_balance.json'),
    loadJSON('drilling.json'),
  ]);

  // 渲染
  renderPriceCards(price);
  renderCurveLabel(signals, futures);
  renderSignalGrid(signals);
  renderInventoryChart(inventory);
  renderSubInventoryChart(inventory);
  renderPriceChart(price);
  renderSpreadChart(price, futures);
  renderFuturesCurveChart(futures);
  renderProductionChart(production);
  renderFinancialChart(financial);
  renderDemandChart(demand);
  renderCFTCChart(cftc);
  renderCrackSpreadChart(crackSpread);
  renderNetImportChart(production);
  renderGlobalBalanceChart(globalBalance);
  renderDrillingChart(drilling);
  renderMeta(meta);

  // 响应式
  window.addEventListener('resize', handleResize);
}

main();
