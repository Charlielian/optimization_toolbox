## 📊 优化百宝箱（Optimization Toolbox）

一个面向无线网络优化场景的一站式工具集，基于 **Streamlit + SQLite + GeoPandas/Folium** 实现。  
支持面板数据分析、容智策略评估、干扰分析、工参整理、Polygon 操作、在线地图可视化等常见优化工作流，并内置数据库与批量导入/备份能力。

---

## 1. 项目结构概览

```text
优化百宝箱_工具集合V3.21/
├── optimization_toolboxV3.21.py   # 统一入口脚本（web / cli / 维护命令）
├── main_app.py                    # Streamlit 主应用
├── database.py                    # 统一数据库管理器（SQLite）
├── optimization_toolbox.db        # 默认数据库（自动创建/升级）
├── requirements.txt               # Python 依赖
├── tools/                         # 各功能模块
│   ├── traffic_monitor.py             # 📈 容智策略分析引擎（容量/流量分析）
│   ├── interference_monitor.py        # 📡 干扰分析引擎
│   ├── gc_organizer.py                # 📋 工参整理与导出
│   ├── panel_reader.py                # 📊 面板数据分析（网格评估、过程分/结果分）
│   ├── polygon_merger.py              # 🗺️ Polygon 合并/分割操作入口
│   ├── optimized_polygon_clipper.py   # Polygon 裁剪/精度优化
│   ├── polygon_precision_optimizer.py # Polygon 精度压缩
│   ├── online_map.py                  # 🌐 在线地图（GPKG/SQLite 空间数据 + 多种底图）
│   ├── system_manager.py              # ⚙️ 系统管理与数据维护
│   ├── traffic_monitor_clean.py       # 简化版流量分析工具
│   └── field_migration_manager.py     # 字段迁移/字段映射工具
├── utils/
│   ├── error_handler.py           # 统一异常捕获与友好提示
│   ├── grid_matcher.py            # 网格与小区匹配工具
│   └── field_mapper.py            # 字段映射工具
├── 打包.md                        # Windows EXE 打包说明（PyInstaller）
├── build_exe.spec                 # PyInstaller 配置
├── build.bat / build_simple.bat   # Windows 一键打包脚本
├── 映射小区/                      # 网格-小区映射表等数据
├── 标签匹配/                      # 标签配置与匹配规则
├── 网格/                          # 网格 GPKG 等空间数据
├── 过滤方案ID清单/
│   └── vcscheme_id.txt            # 需要从过程分计算中排除的方案ID清单
└── logs/                          # 运行与导入日志
```

---

## 2. 功能总览

- **📈 容智策略分析引擎（`tools/traffic_monitor.py`）**
  - 导入容量/流量性能数据，按照策略进行分析与可视化。
  - 支持容量类 `performance_data` 的批量导入、过滤、指标统计。

- **📡 干扰分析引擎（`tools/interference_monitor.py`）**
  - 导入 `interference_data` 干扰数据，查看小区干扰情况。
  - 与工参、映射小区等表联动，支持按 CGI/网格维度分析。

- **📋 工参集合（`tools/gc_organizer.py`）**
  - 从工参 Excel/CSV 读取数据，统一整理为 `engineering_params`。
  - 支持字段清洗、批量导出为标准模板。

- **📊 面板数据分析（`tools/panel_reader.py`）**
  - 支持两类网格面板数据导入：
    - `total` 文件格式（传统字段 vcorder_code / business_key_ 等）
    - **超时方案清单格式**（工单编号、优化单号、方案提交时间等标准字段）
  - 自动识别文件格式并映射到统一的 `panel_data` 结构。
  - 通过 `timeout_scheme_list` 计算 **过程分**（规建/天调/维护/整治/时效性/准确性）。
  - 通过 `grid_result_scores` 计算 **结果分** 与最终质量得分，并绘制雷达图。
  - 支持网格、时间周期、地市等多维查询与导出。

- **🗺️ Polygon 功能操作（`tools/polygon_merger.py` 及相关）**
  - GPKG / GeoJSON / Shapefile 多源 Polygon 数据的合并、分割、裁剪、精度压缩。
  - 详细使用说明见 `tools/POLYGON合并与分割功能文档.md`。

- **🌐 在线地图（`tools/online_map.py`）**
  - 基于 **Folium + GeoPandas + streamlit-folium**：
    - 上传 GPKG、从 SQLite 空间表读取 WKT/WKB 几何。
    - 自动坐标转换（WGS84 ↔ GCJ02 ↔ BD09）。
    - 高德、百度、Google、GEO 卫星、OpenStreetMap、**GMCC 地图**、**Bing 地图（QuadKey）** 等多种底图。
    - 支持图层顺序控制、样式调整、要素弹窗、经纬度快速定位。

- **⚙️ 系统管理（`tools/system_manager.py`）**
  - 数据导入与清理：
    - 面板数据、工参、映射小区、干扰数据、性能数据等的一站式管理。
    - **新增：按日期范围批量删除干扰数据和容量性能数据**，带二次确认。
  - 数据库备份、体积统计、完整性检查。

- **统一数据库管理（`database.py`）**
  - 使用 SQLite，集中管理所有表结构、索引与视图。
  - 自动初始化表结构，包括：
    - `cell_mapping`, `engineering_params`, `interference_data`, `performance_data`
    - `panel_data`, `panel_import_batches`, `panel_evaluation_results`, `panel_city_summary`
    - `timeout_scheme_list`, `grid_result_scores`, `north_cell_base_station_data` 等。
  - 在初始化时自动：
    - 迁移历史结构（向后兼容旧版本面板数据）。
    - 从 `过滤方案ID清单/vcscheme_id.txt` 读取方案ID写入 `excluded_scheme_list`，用于过程分过滤。

- **统一入口控制器（`optimization_toolboxV3.21.py`）**
  - 提供命令行入口：
    - `web`：启动 Streamlit Web 界面。
    - `cli`：命令行菜单（查看状态、备份、执行 SQL、运行工具插件等）。
    - `status / backup / cleanup / sql / tool / upgrade` 等常规维护命令。

---

## 3. 环境与安装

### 3.1 系统与 Python 要求

- 推荐：**Windows 10/11** 或 **macOS**。
- Python **3.8 ~ 3.11**（建议与 `requirements.txt` 保持兼容）。

### 3.2 创建虚拟环境（推荐）

```bash
cd 优化百宝箱_工具集合V3.21

# 创建虚拟环境
python -m venv venv

# 激活（Windows）
venv\Scripts\activate

# 激活（macOS / Linux）
source venv/bin/activate
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 中已固定 `numpy==1.24.3`、`pandas==2.0.3` 等版本，用于避免 Windows 上的二进制兼容问题（如 *ValueError: numpy.dtype size changed*）。

---

## 4. 运行方式

### 4.1 通过统一入口脚本启动 Web 界面

在项目根目录（可在虚拟环境中）执行：

```bash
python optimization_toolboxV3.21.py web --port 88011 --host 0.0.0.0
```

常用参数：

- `--port`：Web 端口，默认可设置为 `88011`。
- `--host`：监听地址，`0.0.0.0` 允许局域网访问，`127.0.0.1` 仅本机访问。
- `--headless`：是否无需浏览器自动打开，一般保持默认。

启动后，在浏览器访问：

```text
http://localhost:88011
```

### 4.2 通过 CLI 模式运行维护命令

```bash
python optimization_toolboxV3.21.py cli
```

在交互菜单中可：

- 查看系统状态（数据库统计、表记录数等）。
- 备份数据库。
- 清理导入日志。
- 直接执行 SQL。
- 列出并运行 `tools/` 下的插件。

也可直接在命令行使用子命令，例如：

```bash
# 备份数据库
python optimization_toolboxV3.21.py backup --output backups/

# 执行 SQL
python optimization_toolboxV3.21.py sql "SELECT COUNT(*) FROM panel_data;"
```

---

## 5. 关键数据与配置说明

### 5.1 SQLite 数据库 `optimization_toolbox.db`

首次运行时，`DatabaseManager` 会自动：

- 创建所有业务表、索引与视图。
- 进行必要的字段迁移与兼容处理。
- 从 `过滤方案ID清单/vcscheme_id.txt` 载入排除方案清单。

无需手动建表，直接通过各功能模块导入数据即可。

### 5.2 过滤方案 ID 清单（过程分过滤）

- 路径：`过滤方案ID清单/vcscheme_id.txt`
- 格式：第一行为表头 `vcscheme_id`，后续每行一个方案 ID，例如：

```text
vcscheme_id
CZ_20240604_CZCA0170_01_s_20240820095454981
CZ_20240604_CZCA0170_01_s_20240820095454761
...
```

**作用：**

- 数据库初始化时，`database.py` 会将该文件中的 ID 写入 `excluded_scheme_list` 表。
- 在以下逻辑中，这些方案 **不参与过程分计算**：
  - 面板数据导入（`panel_reader._process_csv_data`）中会直接跳过这些方案。
  - 超时方案清单导入（`_batch_import_timeout_scheme_data`）也会过滤这些方案。
  - 计算过程分 `_calculate_process_scores`、`_calculate_total_process_score` 时会排除它们。

适用于：如“2024 年已完成方案”需要排除在 2025 年网格过程分以外的场景。

### 5.3 网格/映射/标签数据

- `映射小区/`：存放“45G 微网格小区映射关系表”等小区与网格的映射文件，用于填充 `cell_mapping` 表。
- `标签匹配/`：用于网格标签匹配规则（例如 2024/2025 年批次标签），面板导入时用于识别 24/25 年网格。
- `网格/`：存放 GPKG 等空间数据，可由在线地图和 Polygon 工具读取。

---

## 6. 主要功能模块使用说明（简要）

### 6.1 面板数据分析（PanelReader）

入口：主界面侧边栏 → **📊 面板数据分析**

核心流程：

1. **网格数据导入**
   - 上传 `total` 文件或“超时方案清单格式”文件（CSV/Excel）。
   - 系统自动识别格式并写入 `panel_data`。
   - 按标签自动筛选“2025年督办微网格 + 24年标签 / 仅 2025 年标签”。
2. **超时方案清单导入**
   - 通过 `_batch_import_timeout_scheme_data` 写入 `timeout_scheme_list`。
   - 后续用于计算“时效性”相关的过程分。
3. **网格评估与过程分/结果分计算**
   - 选择时间周期、地市、网格后，可查看：
     - 结果分（5 部分）。
     - 过程分（6 项）。
     - 质量得分与雷达图。

### 6.2 在线地图（OnlineMap）

入口：主界面侧边栏 → **🌐 在线地图**

能力概览：

- 加载 GPKG/SQLite 空间数据，按图层显示。
- 支持底图切换：
  - 高德普通/瓦片、百度普通/瓦片、Google 普通/卫星、GEO 卫星、OpenStreetMap。
  - **GMCC 地图**：`https://nqi.gmcc.net:20443/tiles/{z}/{x}/{y}.png`
  - **Bing 地图**：`http://ecn.t3.tiles.virtualearth.net/tiles/a{q}.jpeg?g=1`（内部通过 JS 进行 QuadKey 转换）。
- 支持图层顺序调整、删除、属性弹窗、经纬度定位等。

### 6.3 系统管理（SystemManager）

入口：主界面侧边栏 → **⚙️ 系统管理**

主要能力：

- **按日期删除数据（干扰 + 容量性能）**：
  - 选择数据类型：干扰数据 / 性能数据（容量） / 干扰+性能。
  - 指定开始/结束日期。
  - 输入 `DELETE` 确认后执行不可恢复的批量删除。
- 数据导入、备份、压缩、完整性检查等。

其他模块如流量监控、干扰监控、工参整理、Polygon 操作等，界面均有较详细的操作提示，这里不再展开。

---

## 7. Windows EXE 打包（简要）

详细说明参见 `打包.md`，这里只给出简要流程：

1. 在 Windows 上准备好虚拟环境，安装依赖：

   ```bash
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. 使用推荐的 `build_exe.spec`：

   ```bash
   pyinstaller build_exe.spec
   ```

   或使用简化脚本：

   ```bash
   build.bat          # 使用 spec
   build_simple.bat   # 使用命令行参数
   ```

3. 打包完成后，在 `dist/optimization_toolboxV3.21/` 下会生成可执行文件，可直接分发给无 Python 环境的 Windows 用户。

---

## 8. 常见问题（FAQ）

- **Q：启动时报 `ValueError: numpy.dtype size changed`？**  
  A：这是 NumPy 与 Pandas 二进制不兼容导致的。请确认已按 `requirements.txt` 安装指定版本（特别是 `numpy==1.24.3` 与 `pandas==2.0.3`），并在虚拟环境中运行。

- **Q：面板数据导入后过程分与预期不一致？**  
  A：请确认：
  - `过滤方案ID清单/vcscheme_id.txt` 中的方案是否为需要排除的 24 年完成方案。
  - 超时方案清单是否正确导入 `timeout_scheme_list`。
  - 标签是否包含“2025年督办微网格”及对应 24 年标签。

- **Q：在线地图底图不显示？**  
  A：部分底图（尤其是 Google/Bing）可能因网络环境限制而无法访问。建议优先使用高德/百度/GMCC/OSM 等底图。

---

## 9. 贡献与维护

当前项目主要面向内部使用，尚未做公开发布。若需要二次开发，建议：

- 在 `tools/` 目录新增独立模块，并通过 `optimization_toolboxV3.21.py` 的工具发现机制进行集成。
- 更新 `database.py` 中的表结构与迁移逻辑，保证升级兼容性。
- 如需新增配置项，可优先写入 `system_config` 表，而非硬编码。

如有新的需求或发现问题，可在代码中查看对应模块并按现有风格进行扩展。 


