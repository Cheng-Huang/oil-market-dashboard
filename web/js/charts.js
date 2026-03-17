/**
 * ECharts 图表配置工厂
 * 统一深色主题 + 常用布局
 */

const COLORS = {
  green:  '#22c55e',
  red:    '#ef4444',
  amber:  '#f59e0b',
  blue:   '#3b82f6',
  cyan:   '#06b6d4',
  purple: '#a855f7',
  pink:   '#ec4899',
  gray:   '#6b7280',
  white:  '#e5e7eb',
};

const PALETTE = [COLORS.cyan, COLORS.amber, COLORS.green, COLORS.pink, COLORS.purple, COLORS.blue];

/** 通用图表基础配置 */
function baseOption() {
  return {
    backgroundColor: 'transparent',
    textStyle: { color: '#9ca3af', fontFamily: 'system-ui, sans-serif' },
    grid: { left: 60, right: 20, top: 40, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1f2937',
      borderColor: '#374151',
      textStyle: { color: '#e5e7eb', fontSize: 12 },
    },
    legend: {
      textStyle: { color: '#9ca3af', fontSize: 11 },
      top: 8,
      right: 12,
      type: 'scroll',
    },
    xAxis: {
      type: 'category',
      axisLine: { lineStyle: { color: '#374151' } },
      axisTick: { show: false },
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#1f2937' } },
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
  };
}

/** 迷你 sparkline 配置（用于顶部卡片） */
function sparkOption(data, color) {
  const values = data.map(d => d.value);
  const dates = data.map(d => d.date);
  return {
    backgroundColor: 'transparent',
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: dates, show: false },
    yAxis: { type: 'value', show: false, min: 'dataMin', max: 'dataMax' },
    series: [{
      type: 'line',
      data: values,
      showSymbol: false,
      lineStyle: { width: 1.5, color },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: color + '40' },
          { offset: 1, color: color + '05' },
        ]
      }},
    }],
    tooltip: { show: false },
  };
}

/** 折线图 */
function lineChart(series, opts = {}) {
  const opt = baseOption();
  // 取第一个 series 的日期作为 x 轴
  // ── 合并所有 series 的日期为统一 x 轴，按日期对齐值 ──
  const dateSet = new Set();
  series.forEach(s => s.data.forEach(d => dateSet.add(d.date)));
  const dates = Array.from(dateSet).sort();
  opt.xAxis.data = dates;

  if (opts.yAxisName) opt.yAxis.name = opts.yAxisName;
  if (opts.yMin !== undefined) opt.yAxis.min = opts.yMin;

  opt.series = series.map((s, i) => {
    const dateMap = new Map(s.data.map(d => [d.date, d.value]));
    return {
      name: s.name,
      type: 'line',
      data: dates.map(d => dateMap.get(d) ?? null),
      showSymbol: false,
      lineStyle: { width: 1.8 },
      itemStyle: { color: s.color || PALETTE[i % PALETTE.length] },
      ...(s.areaStyle ? { areaStyle: s.areaStyle } : {}),
      ...(s.yAxisIndex !== undefined ? { yAxisIndex: s.yAxisIndex } : {}),
      connectNulls: true,
    };
  });

  // 双 Y 轴支持
  if (opts.dualAxis) {
    opt.yAxis = [
      { type: 'value', splitLine: { lineStyle: { color: '#1f2937' } }, axisLabel: { color: '#6b7280', fontSize: 10 }, name: opts.yAxisName || '' },
      { type: 'value', splitLine: { show: false }, axisLabel: { color: '#6b7280', fontSize: 10 }, name: opts.y2AxisName || '' },
    ];
  }

  if (opts.dataZoom) {
    opt.dataZoom = [{
      type: 'inside',
      start: opts.zoomStart || 60,
      end: 100,
    }];
    opt.grid.bottom = 40;
  }

  return opt;
}

/** 面积图（库存 + 5 年季节性区间带） */
function inventoryAreaChart(seriesData, label) {
  const opt = baseOption();
  const dates = seriesData.map(d => d.date);
  const values = seriesData.map(d => d.value);

  // ── 按周序号 (week-of-year) 计算真正的 5 年季节性 min/max ──
  // 将数据按 ISO 周号分组, 排除最近 1 年（用于对比）
  function isoWeek(dateStr) {
    const d = new Date(dateStr);
    const jan4 = new Date(d.getFullYear(), 0, 4);
    const dayDiff = (d - jan4 + (jan4.getTimezoneOffset() - d.getTimezoneOffset()) * 60000) / 86400000;
    return Math.ceil((dayDiff + jan4.getDay() + 1) / 7);
  }

  // 分年份
  const byWeek = {};  // { weekNum: [values from prior years] }
  const latestYear = new Date(dates[dates.length - 1]).getFullYear();
  for (let i = 0; i < dates.length; i++) {
    const yr = new Date(dates[i]).getFullYear();
    if (yr >= latestYear) continue; // 排除当年/最后一年
    const wk = isoWeek(dates[i]);
    if (!byWeek[wk]) byWeek[wk] = [];
    byWeek[wk].push(values[i]);
  }

  // 为每个数据点计算其对应周的历史 min/max
  const upper = [];
  const lower = [];
  const hasSeasonal = Object.keys(byWeek).length > 10;

  if (hasSeasonal) {
    for (let i = 0; i < dates.length; i++) {
      const wk = isoWeek(dates[i]);
      const hist = byWeek[wk];
      if (hist && hist.length >= 2) {
        upper.push(Math.round(Math.max(...hist)));
        lower.push(Math.round(Math.min(...hist)));
      } else {
        // 回退到邻近周
        const nearby = [];
        for (let dw = -2; dw <= 2; dw++) {
          const nw = ((wk - 1 + dw + 52) % 52) + 1;
          if (byWeek[nw]) nearby.push(...byWeek[nw]);
        }
        if (nearby.length >= 2) {
          upper.push(Math.round(Math.max(...nearby)));
          lower.push(Math.round(Math.min(...nearby)));
        } else {
          upper.push(values[i]);
          lower.push(values[i]);
        }
      }
    }
  } else {
    // 数据不足 → 回退到均值 ± 标准差
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const std = Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length);
    for (let i = 0; i < values.length; i++) {
      upper.push(Math.round(mean + std));
      lower.push(Math.round(mean - std));
    }
  }

  opt.xAxis.data = dates;
  opt.legend.data = [label, '5Y 区间上沿', '5Y 区间下沿'];

  opt.series = [
    {
      name: '5Y 区间上沿',
      type: 'line',
      data: upper,
      showSymbol: false,
      lineStyle: { width: 0 },
      areaStyle: { color: '#374151', opacity: 0.3 },
      stack: 'band',
      z: 1,
    },
    {
      name: '5Y 区间下沿',
      type: 'line',
      data: lower,
      showSymbol: false,
      lineStyle: { width: 0 },
      areaStyle: { color: 'transparent' },
      stack: 'band',
      z: 1,
    },
    {
      name: label,
      type: 'line',
      data: values,
      showSymbol: false,
      lineStyle: { width: 2, color: COLORS.cyan },
      z: 10,
    },
  ];

  opt.dataZoom = [{ type: 'inside', start: 60, end: 100 }];
  return opt;
}

/** 柱形图（CFTC 净多头） */
function barChart(data, label, opts = {}) {
  const opt = baseOption();
  const dates = data.map(d => d.date);
  const values = data.map(d => d.net_long !== undefined ? d.net_long : d.value);

  opt.xAxis.data = dates;
  opt.series = [{
    name: label,
    type: 'bar',
    data: values.map(v => ({
      value: v,
      itemStyle: { color: v >= 0 ? COLORS.green + 'cc' : COLORS.red + 'cc' },
    })),
    barMaxWidth: 6,
  }];

  opt.dataZoom = [{ type: 'inside', start: 50, end: 100 }];
  return opt;
}

/** 期货曲线图（横轴为合约月份，纵轴为价格） */
function futuresCurveChart(curve) {
  const opt = baseOption();
  const labels = curve.map(c => c.label);
  const prices = curve.map(c => c.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);

  opt.xAxis.data = labels;
  opt.xAxis.axisLabel = { ...opt.xAxis.axisLabel, rotate: 30 };
  opt.yAxis.min = Math.floor(minPrice - 1);
  opt.yAxis.max = Math.ceil(maxPrice + 1);
  opt.yAxis.name = '$/bbl';
  opt.grid.bottom = 50;

  // Determine color based on structure (front > back = backwardation = green)
  const isBack = prices[0] > prices[prices.length - 1];
  const curveColor = isBack ? COLORS.green : COLORS.red;

  opt.series = [{
    name: 'WTI 期货曲线',
    type: 'line',
    data: prices,
    showSymbol: true,
    symbolSize: 6,
    lineStyle: { width: 2.5, color: curveColor },
    itemStyle: { color: curveColor },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: curveColor + '30' },
          { offset: 1, color: curveColor + '05' },
        ]
      }
    },
    label: {
      show: true,
      position: 'top',
      formatter: p => '$' + p.value.toFixed(2),
      fontSize: 10,
      color: '#9ca3af',
    },
  }];

  // Add reference line at front month price
  opt.series.push({
    name: '近月价格',
    type: 'line',
    data: prices.map(() => prices[0]),
    showSymbol: false,
    lineStyle: { color: '#6b7280', width: 1, type: 'dashed' },
    tooltip: { show: false },
  });

  return opt;
}

/** 裂解价差图（3-2-1 + 汽油 + 柴油） */
function crackSpreadChart(crackData) {
  const series = [];
  if (crackData.crack_321) series.push({ name: '3-2-1 Crack Spread', data: crackData.crack_321, color: COLORS.cyan });
  if (crackData.gasoline_crack) series.push({ name: '汽油裂解', data: crackData.gasoline_crack, color: COLORS.green });
  if (crackData.diesel_crack) series.push({ name: '柴油裂解', data: crackData.diesel_crack, color: COLORS.amber });
  if (series.length === 0) return baseOption();
  return lineChart(series, { dataZoom: true, zoomStart: 50, yAxisName: '$/bbl' });
}

/** 全球供需平衡图（产量/消费折线 + 平衡柱状） */
function globalBalanceChart(gb) {
  const opt = baseOption();
  const balance = gb.balance || [];
  const worldProd = gb.world_production || [];
  const worldCons = gb.world_consumption || [];
  const opecProd = gb.opec_production || [];

  const dates = balance.map(d => d.date);
  opt.xAxis.data = dates;

  // 双轴：左=百万桶/日（产/消/OPEC），右=平衡差
  opt.yAxis = [
    { type: 'value', name: '百万桶/日', splitLine: { lineStyle: { color: '#1f2937' } }, axisLabel: { color: '#6b7280', fontSize: 10 } },
    { type: 'value', name: '平衡', splitLine: { show: false }, axisLabel: { color: '#6b7280', fontSize: 10 } },
  ];

  const prodMap = Object.fromEntries(worldProd.map(d => [d.date, d.value]));
  const consMap = Object.fromEntries(worldCons.map(d => [d.date, d.value]));
  const opecMap = Object.fromEntries(opecProd.map(d => [d.date, d.value]));

  opt.series = [
    {
      name: '全球产量',
      type: 'line',
      data: dates.map(dt => prodMap[dt] ?? null),
      showSymbol: false,
      lineStyle: { width: 1.8, color: COLORS.cyan },
      itemStyle: { color: COLORS.cyan },
    },
    {
      name: '全球消费',
      type: 'line',
      data: dates.map(dt => consMap[dt] ?? null),
      showSymbol: false,
      lineStyle: { width: 1.8, color: COLORS.amber },
      itemStyle: { color: COLORS.amber },
    },
    {
      name: 'OPEC 产量',
      type: 'line',
      data: dates.map(dt => opecMap[dt] ?? null),
      showSymbol: false,
      lineStyle: { width: 1.5, color: COLORS.green, type: 'dashed' },
      itemStyle: { color: COLORS.green },
    },
    {
      name: '供需平衡',
      type: 'bar',
      yAxisIndex: 1,
      data: balance.map(d => ({
        value: d.value,
        itemStyle: { color: d.value >= 0 ? COLORS.red + 'aa' : COLORS.green + 'aa' },
      })),
      barMaxWidth: 12,
    },
  ];

  opt.legend.data = ['全球产量', '全球消费', 'OPEC 产量', '供需平衡'];
  opt.dataZoom = [{ type: 'inside', start: 30, end: 100 }];
  opt.grid.bottom = 40;
  return opt;
}

/** 钻机数图 */
function rigCountChart(drilling) {
  const rigData = drilling.rig_count || [];
  if (rigData.length === 0) return baseOption();
  return lineChart(
    [{ name: '美国原油钻机数 (座)', data: rigData, color: COLORS.amber }],
    { dataZoom: true, zoomStart: 0, yAxisName: '座' }
  );
}

/** M1-M2 价差历史走势图 */
function futuresSpreadChart(spreadHistory) {
  const opt = baseOption();
  const dates = spreadHistory.map(d => d.date);
  const values = spreadHistory.map(d => d.value);

  opt.xAxis.data = dates;
  opt.yAxis.name = '$/bbl';
  opt.series = [{
    name: 'M1-M2 价差',
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
    markArea: {
      silent: true,
      data: [
        [{ yAxis: 0.1, itemStyle: { color: COLORS.green + '10' } }, { yAxis: Math.max(...values, 1) }],
        [{ yAxis: Math.min(...values, -1), itemStyle: { color: COLORS.red + '10' } }, { yAxis: -0.1 }],
      ],
    },
  }];

  opt.dataZoom = [{ type: 'inside', start: 0, end: 100 }];
  return opt;
}

// ══════════════════════════════════════════════════════
// 新增图表工厂函数
// ══════════════════════════════════════════════════════

/** OPEC+ 减产执行率（配额 vs 实际横向柱形图） */
function quotaComplianceChart(quotaData) {
  const opt = baseOption();
  const countries = Object.keys(quotaData);
  const quotas = countries.map(c => quotaData[c].quota_mbd);
  const actuals = countries.map(c => quotaData[c].actual_mbd);
  const labels = countries.map(c => c.toUpperCase());

  opt.grid = { left: 80, right: 30, top: 30, bottom: 30 };
  opt.xAxis = { type: 'value', name: 'mb/d', axisLabel: { color: '#6b7280', fontSize: 10 }, splitLine: { lineStyle: { color: '#1f2937' } } };
  opt.yAxis = { type: 'category', data: labels, axisLabel: { color: '#9ca3af', fontSize: 11 }, axisLine: { lineStyle: { color: '#374151' } } };
  opt.legend = { data: ['配额', '实际产量'], textStyle: { color: '#9ca3af', fontSize: 11 }, top: 4, right: 10 };
  opt.series = [
    { name: '配额', type: 'bar', data: quotas, itemStyle: { color: COLORS.cyan + 'aa' }, barGap: '10%' },
    { name: '实际产量', type: 'bar', data: actuals, itemStyle: { color: (params) => actuals[params.dataIndex] > quotas[params.dataIndex] ? COLORS.red + 'cc' : COLORS.green + 'cc' } },
  ];
  opt.tooltip = { ...opt.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } };
  return opt;
}

/** 闲置产能横向柱图 */
function spareCapacityChart(spareData) {
  const opt = baseOption();
  const countries = Object.keys(spareData);
  const values = countries.map(c => spareData[c].spare_capacity_mbd);
  const labels = countries.map(c => c.toUpperCase());

  opt.grid = { left: 80, right: 30, top: 20, bottom: 30 };
  opt.xAxis = { type: 'value', name: 'mb/d', axisLabel: { color: '#6b7280', fontSize: 10 }, splitLine: { lineStyle: { color: '#1f2937' } } };
  opt.yAxis = { type: 'category', data: labels, axisLabel: { color: '#9ca3af', fontSize: 11 }, axisLine: { lineStyle: { color: '#374151' } } };
  opt.series = [{
    type: 'bar',
    data: values.map(v => ({ value: v, itemStyle: { color: v > 1 ? COLORS.amber : v > 0.3 ? COLORS.cyan : COLORS.gray } })),
    barMaxWidth: 20,
    label: { show: true, position: 'right', formatter: '{c} mb/d', fontSize: 10, color: '#9ca3af' },
  }];
  opt.tooltip = { ...opt.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } };
  return opt;
}

/** 隐含库存变化柱形图 */
function impliedStockchangeChart(data) {
  const opt = baseOption();
  const dates = data.map(d => d.date);
  const values = data.map(d => d.stockchange_mbd);

  opt.xAxis.data = dates;
  opt.yAxis.name = 'mb/d';
  opt.series = [{
    name: '隐含库存变化',
    type: 'bar',
    data: values.map(v => ({
      value: v,
      itemStyle: { color: v >= 0 ? COLORS.red + 'bb' : COLORS.green + 'bb' },
    })),
    barMaxWidth: 16,
    markLine: {
      silent: true,
      data: [{ yAxis: 0, lineStyle: { color: '#6b7280', type: 'dashed' } }],
    },
  }];

  const forecastStart = data.findIndex(d => d.type === 'forecast');
  if (forecastStart > 0) {
    opt.series[0].markArea = {
      silent: true,
      data: [[
        { xAxis: dates[forecastStart], itemStyle: { color: 'rgba(107,114,128,0.08)' } },
        { xAxis: dates[dates.length - 1] }
      ]],
      label: { show: true, position: 'insideTopLeft', formatter: '← 预测区间', fontSize: 10, color: '#6b7280' },
    };
  }

  opt.dataZoom = [{ type: 'inside', start: 0, end: 100 }];
  return opt;
}

/** SPR 各国储备柱图 */
function sprBarChart(sprData) {
  const opt = baseOption();
  const countries = Object.keys(sprData);
  const labels = countries.map(c => sprData[c].name || c);
  const values = countries.map(c => sprData[c].level_mb);

  opt.grid = { left: 80, right: 30, top: 20, bottom: 30 };
  opt.xAxis = { type: 'value', name: '百万桶', axisLabel: { color: '#6b7280', fontSize: 10 }, splitLine: { lineStyle: { color: '#1f2937' } } };
  opt.yAxis = { type: 'category', data: labels, axisLabel: { color: '#9ca3af', fontSize: 11 }, axisLine: { lineStyle: { color: '#374151' } } };
  opt.series = [{
    type: 'bar',
    data: values.map(v => ({
      value: v,
      itemStyle: { color: COLORS.blue + 'cc' },
    })),
    barMaxWidth: 24,
    label: { show: true, position: 'right', formatter: '{c} mb', fontSize: 10, color: '#9ca3af' },
  }];
  opt.tooltip = { ...opt.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } };
  return opt;
}

/** 期权 P/C ratio 柱状对比图 */
function optionsPCChart(byExpiry) {
  const opt = baseOption();
  const labels = byExpiry.map(e => `${e.ticker} ${e.expiry}`);
  const pcVol = byExpiry.map(e => e.pc_ratio_volume);

  opt.grid = { left: 50, right: 20, top: 30, bottom: 60 };
  opt.xAxis = {
    type: 'category', data: labels,
    axisLabel: { color: '#6b7280', fontSize: 9, rotate: 35 },
    axisLine: { lineStyle: { color: '#374151' } },
  };
  opt.yAxis = { type: 'value', name: 'P/C Ratio', splitLine: { lineStyle: { color: '#1f2937' } }, axisLabel: { color: '#6b7280', fontSize: 10 } };
  opt.series = [{
    name: 'P/C Ratio (Volume)',
    type: 'bar',
    data: pcVol.map(v => ({
      value: v,
      itemStyle: {
        color: v > 1.5 ? COLORS.red + 'cc'
          : v > 1.2 ? COLORS.amber + 'cc'
          : v > 0.7 ? COLORS.green + 'cc'
          : COLORS.cyan + 'cc'
      },
    })),
    barMaxWidth: 30,
  }];

  opt.series.push(
    { name: '看空阈值', type: 'line', data: pcVol.map(() => 1.2), showSymbol: false, lineStyle: { width: 1, type: 'dashed', color: COLORS.red + '80' } },
    { name: '中性线', type: 'line', data: pcVol.map(() => 1.0), showSymbol: false, lineStyle: { width: 1, type: 'dashed', color: '#6b7280' } },
  );
  return opt;
}
