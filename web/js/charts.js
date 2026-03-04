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
  const dates = series[0]?.data?.map(d => d.date) || [];
  opt.xAxis.data = dates;

  if (opts.yAxisName) opt.yAxis.name = opts.yAxisName;
  if (opts.yMin !== undefined) opt.yAxis.min = opts.yMin;

  opt.series = series.map((s, i) => ({
    name: s.name,
    type: 'line',
    data: s.data.map(d => d.value),
    showSymbol: false,
    lineStyle: { width: 1.8 },
    itemStyle: { color: s.color || PALETTE[i % PALETTE.length] },
    ...(s.areaStyle ? { areaStyle: s.areaStyle } : {}),
    ...(s.yAxisIndex !== undefined ? { yAxisIndex: s.yAxisIndex } : {}),
  }));

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

/** 面积图（库存 + 5 年区间带） */
function inventoryAreaChart(seriesData, label) {
  const opt = baseOption();
  const dates = seriesData.map(d => d.date);
  const values = seriesData.map(d => d.value);

  // 简化5年区间：用全序列的 ±1 标准差模拟
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const std = Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length);
  const upper = values.map(() => Math.round(mean + std));
  const lower = values.map(() => Math.round(mean - std));

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
