# Changelog

## [2026-03-16] — 航运要道 + 预测市场模块

### 新增

- **`etl/fetch_maritime.py`** — 航运要道监控模块
  - 从 IMF PortWatch (ArcGIS) 获取霍尔木兹海峡、曼德海峡、苏伊士运河、马六甲海峡的每日油轮/总船舶通行量
  - 计算 7 日 / 90 日滚动均值，周环比变化
  - 基于通行量骤降自动生成风险信号（danger / warning / normal）
  - 通过 Yahoo Finance 拉取油轮上市公司（FRO, STNG, INSW, DHT）股价作为运价代理

- **`etl/fetch_polymarket.py`** — Polymarket 预测市场模块
  - 通过 Gamma Events API 获取石油相关地缘政治事件的概率数据
  - 覆盖供给侧风险（伊朗）、需求侧风险（经济衰退）、地缘政治（俄乌/北约/中印）三个分类
  - 按成交量排序，每分类展示最活跃的 8 个子市场

- **`web/index.html`** — 新增航运要道面板和 Polymarket 面板的 HTML 结构
- **`web/js/app.js`** — 新增 `renderMaritime()` 和 `renderPolymarket()` 渲染函数
  - 航运模块：风险信号卡片、咽喉要道统计卡片、霍尔木兹海峡通行量柱线图、油轮运价指标
  - Polymarket 模块：三列分类展示，带概率进度条和 Polymarket 链接
  - 新增 `escapeHtml()` 工具函数防止 XSS

### 修改

- **`etl/run_all.py`** — 集成新模块
  - 新增 `[6/9] Polymarket` 和 `[7/9] 航运数据` 步骤
  - `meta.json` 的 `sources` 新增 `polymarket` 和 `maritime` 字段
- **`web/index.html`** — Footer 数据来源新增 Polymarket / IMF PortWatch

### 修复

- **`etl/run_all.py`** — 修正 ETL 步骤编号不一致问题（部分步骤显示 `[x/6]`，部分显示 `[x/9]`），统一为 `[1/9]` ~ `[9/9]`
- **`etl/fetch_polymarket.py`** — 当所有事件 slug 失效导致市场数为 0 时，输出警告提示检查 `CURATED_EVENTS` 配置
- **`web/js/charts.js`** — 修复 `lineChart()` 按数组位置而非日期对齐多 series 数据的 bug，导致日期范围不同的数据系列（如炼厂开工率 1990~ vs 原油产量 1983~）错位，2019 年后的炼厂开工率无法显示。现改用 `Set` 合并所有日期为统一 x 轴，用 `Map` 按日期查找对应值
