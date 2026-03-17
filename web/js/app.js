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

// ══════════════════════════════════════════════════════
// 新增渲染函数: 全球需求 / OPEC产量 / 全球库存 / 期权
// ══════════════════════════════════════════════════════

// ── 全球需求 ─────────────────────────────────────────
function renderGlobalDemandChart(globalDemand) {
  if (!globalDemand?.steo_by_region) return;
  const chart = initChart('chart-global-demand');
  if (!chart) return;

  const regionMap = {
    world_consumption: { name: '全球', color: COLORS.white },
    us_consumption: { name: '美国', color: COLORS.cyan },
    oecd_europe_consumption: { name: 'OECD 欧洲', color: COLORS.blue },
    non_oecd_consumption: { name: '非OECD', color: COLORS.amber },
    oecd_consumption: { name: 'OECD', color: COLORS.green },
  };

  const series = [];
  for (const [key, cfg] of Object.entries(regionMap)) {
    const data = globalDemand.steo_by_region[key];
    if (data?.length) {
      series.push({ name: cfg.name, data, color: cfg.color });
    }
  }
  if (series.length === 0) return;

  const opt = lineChart(series, { dataZoom: true, zoomStart: 70, yAxisName: 'mb/d' });
  chart.setOption(opt);
}

// ── OPEC+ 主要产油国 ────────────────────────────────
function renderOPECProductionChart(opecProd) {
  if (!opecProd?.production_by_country) return;
  const chart = initChart('chart-opec-production');
  if (!chart) return;

  // 只展示 OPEC+ 核心国原油产量（EIA International 国别数据）
  const countryMap = {
    saudi: { name: '沙特', color: COLORS.green },
    russia: { name: '俄罗斯', color: COLORS.red },
    iraq: { name: '伊拉克', color: COLORS.amber },
    uae: { name: '阿联酋', color: COLORS.cyan },
    iran: { name: '伊朗', color: COLORS.purple },
    kuwait: { name: '科威特', color: COLORS.pink },
    nigeria: { name: '尼日利亚', color: COLORS.blue },
    canada: { name: '加拿大', color: '#8b5cf6' },
  };

  const series = [];
  let latestDate = '';
  for (const [key, cfg] of Object.entries(countryMap)) {
    let data = opecProd.production_by_country[key];
    if (data?.length) {
      data = data.slice(-120);
      series.push({ name: cfg.name, data, color: cfg.color });
      const last = data[data.length - 1].date;
      if (last > latestDate) latestDate = last;
    }
  }
  if (series.length === 0) return;

  const opt = lineChart(series, { dataZoom: true, zoomStart: 50, yAxisName: 'mb/d' });

  // 标注数据截止日期（EIA International 有 3-4 月滞后）
  if (latestDate) {
    opt.title = {
      text: `数据截至 ${latestDate}（EIA International 滞后约 3-4 个月）`,
      textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 'normal' },
      left: 'center', bottom: 4,
    };
    opt.grid.bottom = 50;
  }

  chart.setOption(opt);

  // 更新面板标题显示日期
  const titleEl = document.getElementById('chart-opec-production')?.closest('.panel')?.querySelector('.panel-title');
  if (titleEl && latestDate) {
    titleEl.textContent = `🏗️ OPEC+ 主要产油国 · 截至 ${latestDate}`;
  }
}

// ── OPEC+ 减产执行 & 闲置产能 ──────────────────────
function renderOPECCompliance(opecProd) {
  const panel = document.getElementById('opec-compliance-panel');
  if (!panel || !opecProd) return;

  const hasQuota = opecProd.quota_compliance?.by_country && Object.keys(opecProd.quota_compliance.by_country).length > 0;
  const hasSpare = opecProd.spare_capacity?.by_country && Object.keys(opecProd.spare_capacity.by_country).length > 0;
  if (!hasQuota && !hasSpare) return;

  panel.style.display = '';

  if (hasQuota) {
    const dom = document.getElementById('chart-opec-compliance');
    if (dom) {
      const chart = echarts.init(dom, null, { renderer: 'canvas' });
      chart.setOption(quotaComplianceChart(opecProd.quota_compliance.by_country));
    }
  }

  if (hasSpare) {
    const dom = document.getElementById('chart-spare-capacity');
    if (dom) {
      const chart = echarts.init(dom, null, { renderer: 'canvas' });
      chart.setOption(spareCapacityChart(opecProd.spare_capacity.by_country));
    }
  }
}

// ── 隐含库存变化 ────────────────────────────────────
function renderImpliedStockchange(globalInv) {
  if (!globalInv?.implied_stockchange?.length) {
    const panel = document.getElementById('chart-implied-stockchange')?.closest('.panel');
    if (panel) panel.style.display = 'none';
    return;
  }
  const chart = initChart('chart-implied-stockchange');
  if (!chart) return;
  chart.setOption(impliedStockchangeChart(globalInv.implied_stockchange));
}

// ── 全球 SPR & 库存偏差 ─────────────────────────────
function renderSPRPanel(globalInv) {
  const panel = document.getElementById('spr-panel');
  if (!panel || !globalInv) return;

  const hasSPR = globalInv.global_spr?.by_country && Object.keys(globalInv.global_spr.by_country).length > 0;
  const hasDev = globalInv.oecd_deviation?.deviation_mb != null;
  if (!hasSPR && !hasDev) return;

  panel.style.display = '';

  // SPR 柱图
  if (hasSPR) {
    const dom = document.getElementById('chart-spr');
    if (dom) {
      const chart = echarts.init(dom, null, { renderer: 'canvas' });
      chart.setOption(sprBarChart(globalInv.global_spr.by_country));
    }
  }

  // 库存偏差卡片
  if (hasDev) {
    const dev = globalInv.oecd_deviation;
    const devEl = document.getElementById('spr-deviation-card');
    if (devEl) {
      const isAbove = dev.assessment === 'above';
      const devColor = isAbove ? 'text-red-400' : 'text-green-400';
      const devIcon = isAbove ? '📈' : '📉';
      const devBg = isAbove ? 'bg-red-900/20' : 'bg-green-900/20';
      devEl.innerHTML = `
        <div class="${devBg} rounded-xl p-6 text-center w-full">
          <div class="text-4xl mb-2">${devIcon}</div>
          <div class="text-sm text-gray-400 mb-1">美国商业库存 vs 5年均值</div>
          <div class="text-3xl font-bold ${devColor} mb-1">${dev.deviation_mb > 0 ? '+' : ''}${dev.deviation_mb} mb</div>
          <div class="text-sm text-gray-500">${dev.deviation_pct > 0 ? '+' : ''}${dev.deviation_pct}% 偏差</div>
          <div class="mt-3 grid grid-cols-2 gap-3 text-xs">
            <div class="bg-oil-700/50 rounded p-2">
              <div class="text-gray-500">当前</div>
              <div class="text-white font-medium">${fmt(dev.latest_value_mb, 1)} mb</div>
            </div>
            <div class="bg-oil-700/50 rounded p-2">
              <div class="text-gray-500">5年均值</div>
              <div class="text-white font-medium">${fmt(dev.avg_5y_mb, 1)} mb</div>
            </div>
          </div>
          <div class="text-[10px] text-gray-600 mt-2">数据日期: ${dev.latest_date}</div>
        </div>
      `;
    }
  }
}

// ── 期权情绪面板 ─────────────────────────────────────
function renderOptionsPanel(optionsData) {
  const panel = document.getElementById('options-panel');
  if (!panel || !optionsData) return;

  const opts = optionsData.options;
  const ovx = optionsData.ovx_enhanced;
  if (!opts && !ovx) return;

  panel.style.display = '';

  // 1. P/C ratio 卡片 (左)
  const cardsEl = document.getElementById('options-pc-cards');
  if (cardsEl && opts) {
    const agg = opts.aggregate || {};
    const sentiment = opts.sentiment || {};
    const sigColor = {
      extreme_bullish: 'text-green-300', bullish: 'text-green-400',
      neutral: 'text-gray-400', bearish: 'text-red-400', extreme_bearish: 'text-red-300',
    };
    const sigLabel = {
      extreme_bullish: '极度看多', bullish: '偏多',
      neutral: '中性', bearish: '偏空', extreme_bearish: '极度看空',
    };

    let html = '<div class="space-y-3">';
    // Aggregate P/C
    html += `
      <div class="bg-oil-700/50 rounded-lg p-3">
        <div class="text-xs text-gray-500 mb-1">综合 P/C Ratio (Volume)</div>
        <div class="text-2xl font-bold text-white">${fmt(agg.total_pc_ratio_volume, 3)}</div>
        <div class="text-sm ${sigColor[sentiment.volume_signal] || 'text-gray-400'} mt-1">${sigLabel[sentiment.volume_signal] || '--'}</div>
      </div>
    `;
    // P/C OI
    html += `
      <div class="bg-oil-700/50 rounded-lg p-3">
        <div class="text-xs text-gray-500 mb-1">综合 P/C Ratio (OI)</div>
        <div class="text-2xl font-bold text-white">${fmt(agg.total_pc_ratio_oi, 3)}</div>
        <div class="text-sm ${sigColor[sentiment.oi_signal] || 'text-gray-400'} mt-1">${sigLabel[sentiment.oi_signal] || '--'}</div>
      </div>
    `;
    // Key levels
    if (sentiment.key_put_support || sentiment.key_call_resistance) {
      html += `
        <div class="bg-oil-700/50 rounded-lg p-3">
          <div class="text-xs text-gray-500 mb-1">关键期权位</div>
          <div class="flex justify-between text-sm">
            <span class="text-green-400">支撑: $${sentiment.key_put_support || '--'}</span>
            <span class="text-red-400">阻力: $${sentiment.key_call_resistance || '--'}</span>
          </div>
        </div>
      `;
    }
    // By ticker
    const bt = opts.by_ticker || {};
    for (const [sym, info] of Object.entries(bt)) {
      html += `
        <div class="bg-oil-700/50 rounded-lg p-2 text-xs">
          <span class="text-gray-400">${sym}</span>
          <span class="text-white ml-2">P/C=${fmt(info.pc_ratio_volume, 2)}</span>
          <span class="text-gray-500 ml-2">${info.expiries_analyzed} 到期日</span>
        </div>
      `;
    }
    html += '</div>';
    cardsEl.innerHTML = html;
  }

  // 2. P/C ratio 柱图 (中)
  if (opts?.by_expiry?.length) {
    const dom = document.getElementById('chart-options-pc');
    if (dom) {
      const chart = echarts.init(dom, null, { renderer: 'canvas' });
      chart.setOption(optionsPCChart(opts.by_expiry));
    }
  }

  // 3. OVX 增强卡片 (右)
  const ovxEl = document.getElementById('options-ovx-card');
  if (ovxEl && ovx) {
    const regimeColor = {
      extreme_panic: 'text-red-300', panic: 'text-red-400',
      elevated: 'text-amber-400', normal: 'text-green-400',
    };
    const regimeLabel = {
      extreme_panic: '极度恐慌', panic: '恐慌',
      elevated: '偏高', normal: '正常',
    };
    const regimeBg = {
      extreme_panic: 'bg-red-900/30', panic: 'bg-red-900/20',
      elevated: 'bg-amber-900/20', normal: 'bg-green-900/20',
    };

    ovxEl.innerHTML = `
      <div class="${regimeBg[ovx.regime] || 'bg-oil-700/50'} rounded-xl p-4 text-center h-full flex flex-col justify-center">
        <div class="text-xs text-gray-500 mb-1">OVX 原油波动率指数</div>
        <div class="text-4xl font-bold ${regimeColor[ovx.regime] || 'text-white'}">${ovx.latest}</div>
        <div class="text-sm ${regimeColor[ovx.regime] || 'text-gray-400'} mt-1">${regimeLabel[ovx.regime] || ovx.regime}</div>
        <div class="mt-3 text-xs text-gray-500">百分位: ${ovx.percentile}%</div>
        <div class="w-full bg-gray-700/50 rounded-full h-2 mt-1">
          <div class="h-2 rounded-full transition-all ${ovx.percentile > 90 ? 'bg-red-500' : ovx.percentile > 70 ? 'bg-amber-500' : 'bg-green-500'}"
               style="width: ${Math.min(ovx.percentile, 100)}%"></div>
        </div>
        <div class="grid grid-cols-2 gap-2 mt-3 text-xs">
          <div class="bg-oil-700/50 rounded p-2">
            <div class="text-gray-500">20日均</div>
            <div class="text-white">${ovx.avg_20d}</div>
          </div>
          <div class="bg-oil-700/50 rounded p-2">
            <div class="text-gray-500">60日均</div>
            <div class="text-white">${ovx.avg_60d}</div>
          </div>
        </div>
        <div class="text-[10px] text-gray-600 mt-2">Vol-of-Vol(5d): ${ovx.vol_of_vol_5d}% · ${ovx.date}</div>
      </div>
    `;
  }
}
// ── 航运要道监控 ─────────────────────────────────────
function renderMaritime(maritime) {
  const panel = document.getElementById('maritime-panel');
  if (!panel || !maritime?.chokepoints) return;
  
  const cps = maritime.chokepoints;
  if (Object.keys(cps).length === 0) return;
  panel.style.display = '';

  // 1. 风险信号
  const alertsEl = document.getElementById('maritime-alerts');
  if (alertsEl && maritime.risk_signals) {
    alertsEl.innerHTML = maritime.risk_signals.map(sig => {
      const cls = sig.level === 'danger' ? 'bg-red-900/40 border-red-500/50 text-red-300'
                : sig.level === 'warning' ? 'bg-amber-900/40 border-amber-500/50 text-amber-300'
                : 'bg-green-900/30 border-green-500/50 text-green-300';
      return `<div class="border rounded-lg px-3 py-2 text-sm mb-2 ${cls}">${escapeHtml(sig.message)}</div>`;
    }).join('');
  }

  // 2. 咽喉要道卡片
  const cpContainer = document.getElementById('maritime-chokepoints');
  if (cpContainer) {
    cpContainer.innerHTML = '';
    const cpOrder = ['chokepoint6', 'chokepoint4', 'chokepoint1', 'chokepoint5'];
    for (const cpId of cpOrder) {
      const cp = cps[cpId];
      if (!cp) continue;
      const ts = cp.tanker_stats || {};
      const tots = cp.total_stats || {};
      const wowColor = ts.wow_change > 5 ? 'text-green-400' : ts.wow_change < -15 ? 'text-red-400' : ts.wow_change < -5 ? 'text-amber-400' : 'text-gray-400';
      const wowIcon = ts.wow_change > 0 ? '↑' : ts.wow_change < 0 ? '↓' : '→';
      
      const card = document.createElement('div');
      card.className = 'bg-oil-700/50 rounded-lg p-3';
      card.innerHTML = `
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-semibold text-white">${escapeHtml(cp.name)}</span>
          <span class="text-[10px] text-gray-500">${escapeHtml(cp.oil_share)}</span>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center">
          <div>
            <div class="text-lg font-bold text-cyan-400">${ts.avg_7d || 0}</div>
            <div class="text-[10px] text-gray-500">油轮/日(7d均)</div>
          </div>
          <div>
            <div class="text-lg font-bold text-gray-300">${ts.avg_90d || 0}</div>
            <div class="text-[10px] text-gray-500">油轮/日(90d均)</div>
          </div>
          <div>
            <div class="text-lg font-bold ${wowColor}">${wowIcon} ${Math.abs(ts.wow_change || 0)}%</div>
            <div class="text-[10px] text-gray-500">周环比</div>
          </div>
        </div>
        <div class="mt-2 text-[10px] text-gray-500">
          总船舶: ${tots.avg_7d || 0}/日(7d) · 数据: ${cp.data_range?.start || ''} ~ ${cp.data_range?.end || ''}
        </div>
      `;
      cpContainer.appendChild(card);
    }
  }

  // 3. 霍尔木兹海峡油轮通行量图表
  const hormuz = cps['chokepoint6'];
  if (hormuz?.chart_data?.length) {
    const chart = initChart('chart-hormuz-tanker');
    if (chart) {
      const dates = hormuz.chart_data.map(d => d.date);
      const tankerRaw = hormuz.chart_data.map(d => d.tanker);
      const tanker7d = hormuz.chart_data.map(d => d.tanker_7d);
      const totalRaw = hormuz.chart_data.map(d => d.total);
      const total7d = hormuz.chart_data.map(d => d.total_7d);

      const opt = baseOption();
      opt.title = { text: '霍尔木兹海峡 — 每日通行量', textStyle: { color: '#9ca3af', fontSize: 13 }, left: 10, top: 5 };
      opt.grid = { left: 55, right: 55, top: 50, bottom: 60 };
      opt.legend = { textStyle: { color: '#9ca3af', fontSize: 10 }, top: 6, right: 10 };
      opt.xAxis.data = dates;
      opt.yAxis = [
        { type: 'value', name: '船舶数', splitLine: { lineStyle: { color: '#1f2937' } }, axisLabel: { color: '#6b7280', fontSize: 10 } },
      ];
      opt.series = [
        {
          name: '油轮(日)',
          type: 'bar',
          data: tankerRaw,
          itemStyle: { color: COLORS.cyan + '40' },
          barWidth: '60%',
        },
        {
          name: '油轮(7日均)',
          type: 'line',
          data: tanker7d,
          showSymbol: false,
          lineStyle: { width: 2.5, color: COLORS.cyan },
          z: 10,
        },
        {
          name: '总船舶(7日均)',
          type: 'line',
          data: total7d,
          showSymbol: false,
          lineStyle: { width: 1.5, color: COLORS.amber, type: 'dashed' },
        },
      ];
      opt.dataZoom = [{ type: 'inside', start: 0, end: 100 }, { type: 'slider', start: 0, end: 100, height: 20, bottom: 8 }];
      chart.setOption(opt);
    }
  }

  // 4. 油轮运价指标
  const stocksEl = document.getElementById('maritime-tanker-stocks');
  if (stocksEl && maritime.tanker_stocks?.length) {
    let html = '<h3 class="text-sm font-semibold text-gray-400 mb-2">📊 油轮运价指标 (上市公司股价代理)</h3>';
    html += '<div class="grid grid-cols-2 md:grid-cols-4 gap-2">';
    for (const s of maritime.tanker_stocks) {
      const chgColor = s.change_5d >= 0 ? 'text-green-400' : 'text-red-400';
      const chg1mColor = s.change_1m >= 0 ? 'text-green-400' : 'text-red-400';
      html += `
        <div class="bg-oil-700/50 rounded-lg p-2.5 text-center">
          <div class="text-xs text-gray-500 mb-1">${escapeHtml(s.label)}</div>
          <div class="text-lg font-bold text-white">$${s.price}</div>
          <div class="flex justify-center gap-2 mt-1 text-[10px]">
            <span class="${chgColor}">${s.change_5d >= 0 ? '+' : ''}${s.change_5d}% 5日</span>
            <span class="${chg1mColor}">${s.change_1m >= 0 ? '+' : ''}${s.change_1m}% 月</span>
          </div>
        </div>
      `;
    }
    html += '</div>';
    stocksEl.innerHTML = html;
  }
}

// ── Polymarket 预测市场 ──────────────────────────────
function renderPolymarket(polymarket) {
  const panel = document.getElementById('polymarket-panel');
  const content = document.getElementById('polymarket-content');
  if (!panel || !content || !polymarket?.categories) return;

  const cats = polymarket.categories;
  const hasCats = Object.values(cats).some(c => c.markets && c.markets.length > 0);
  if (!hasCats) return;

  panel.style.display = '';
  content.innerHTML = '';

  const catIcons = {
    supply_risk: '⛽',
    demand_risk: '📉',
    geopolitical: '🌍',
  };

  for (const [key, cat] of Object.entries(cats)) {
    if (!cat.markets || cat.markets.length === 0) continue;

    const col = document.createElement('div');
    col.innerHTML = `<h3 class="text-sm font-semibold text-gray-400 mb-2">${catIcons[key] || '📊'} ${cat.label}</h3>`;

    const list = document.createElement('div');
    list.className = 'space-y-2';

    for (const m of cat.markets.slice(0, 6)) {
      const pct = m.yes_price != null ? Math.round(m.yes_price * 100) : null;
      const pctText = pct != null ? `${pct}%` : 'N/A';
      const barColor = pct != null
        ? (pct >= 60 ? 'bg-red-500/70' : pct >= 40 ? 'bg-amber-500/70' : 'bg-green-500/70')
        : 'bg-gray-600';
      const barWidth = pct != null ? pct : 0;

      const item = document.createElement('a');
      item.href = m.url || '#';
      item.target = '_blank';
      item.rel = 'noopener noreferrer';
      item.className = 'block bg-oil-700/50 rounded-lg p-2.5 hover:bg-oil-600/60 transition-colors cursor-pointer';
      item.innerHTML = `
        <div class="flex items-start justify-between gap-2 mb-1.5">
          <span class="text-xs text-gray-300 leading-tight flex-1">${escapeHtml(m.question)}</span>
          <span class="text-sm font-bold text-white whitespace-nowrap">${pctText}</span>
        </div>
        <div class="w-full bg-gray-700/50 rounded-full h-1.5">
          <div class="${barColor} h-1.5 rounded-full transition-all" style="width: ${barWidth}%"></div>
        </div>
        ${m.end_date ? `<div class="text-[10px] text-gray-500 mt-1">截止 ${m.end_date}</div>` : ''}
      `;
      list.appendChild(item);
    }

    col.appendChild(list);
    content.appendChild(col);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
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
  document.querySelectorAll('.chart-box, #chart-opec-compliance, #chart-spare-capacity, #chart-spr, #chart-options-pc, #chart-hormuz-tanker').forEach(dom => {
    const instance = echarts.getInstanceByDom(dom);
    if (instance) instance.resize();
  });
}

// ── 主入口 ───────────────────────────────────────────
async function main() {
  // 并行加载所有 JSON
  const [price, inventory, production, demand, financial, cftc, signals, meta, futures, crackSpread, globalBalance, drilling, polymarket, maritime, globalDemand, opecProd, globalInv, optionsData] = await Promise.all([
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
    loadJSON('polymarket.json'),
    loadJSON('maritime.json'),
    loadJSON('global_demand.json'),
    loadJSON('opec_production.json'),
    loadJSON('global_inventory.json'),
    loadJSON('options.json'),
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
  renderGlobalDemandChart(globalDemand);
  renderOPECProductionChart(opecProd);
  renderOPECCompliance(opecProd);
  renderImpliedStockchange(globalInv);
  renderSPRPanel(globalInv);
  renderOptionsPanel(optionsData);
  renderMaritime(maritime);
  renderPolymarket(polymarket);
  renderMeta(meta);

  // 响应式
  window.addEventListener('resize', handleResize);
}

main();
