# TerraMow Home Assistant集成

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · **中文**

---

这是一个适用于TerraMow机器人割草机的Home Assistant集成。

### 功能

**控制**
- 割草机实体：启动、暂停和回充
- 分区割草：分区选择实体和 `terramow.start_select_region` 服务
- **日程编辑** — `terramow.add_schedule` / `terramow.delete_schedule` 服务将每周割草时段写入割草机，并通过回读校验。*注意：* 当前零售固件尚不接受通过本地 MQTT 写入日程（厂商 App 使用蓝牙/云端）——在固件支持之前，请使用**随天气调整割草蓝图**在 HA 侧进行排程
- **交互式地图卡片** — 面向仪表板的矢量草坪地图，可平移/缩放：机器人实时位置（按活动着色，带跟随模式）、卡片上的启动 / 暂停 / 回充控件、电量 / 作业进度 / 预计剩余时间标签、已割区域阴影（含各分区进度）、割草路径、基站、可点选分区并直接割草、禁区和虚拟墙、在发生位置标注的活动故障，以及草坪的 **Wi-Fi 热力图**；**视图按钮**可在 两者 / 路径 / 区域 / Wi-Fi 之间循环切换。支持主题、自动注册，并带有 UI 编辑器（`custom:terramow-map-card`）
- 沿边修剪按钮
- 在 Home Assistant 中调整设置：割草高度、速度、间距、刀盘转速、沿边切割距离、主方向模式与角度、彻底切割边角、高草沿边修剪模式
- 维护：刀盘和基站计数器的重置按钮

**监控**
- 实时地图摄像头，包含割草路径、机器人位置和基站（另有面向仪表板的纯地图摄像头，分辨率可在选项中配置）
- 电池：电量、充电状态、温度状态、充电器已连接、电源开关
- 作业进度：当前会话面积、进度（%）、时长和作业类型；累计割草时间、作业次数和已割面积
- 状态：任务 / 子任务 / 任务状态、运行模式、电源模式、返回基站原因、雨水检测、问题指示、数据保存和数据转换指示
- **故障传感器** — 以可读文本呈现当前故障（例如*割草机卡住*、*割草机被抬起*或*正常*），这样通知或语音助手无需用模板解析属性即可说明问题所在
- 进行中作业传感器（在心跳中断期间仍保持当前任务）以及割草机侧的 Wi-Fi 信号强度传感器
- 地图：状态、面积，以及已检测 / 可构建 / 正在备份标志
- 日程：下次计划启动传感器和只读的**割草日程日历**（下一次割草会显示在日历卡片上）
- 固件更新实体、设备页面上的固件版本，以及版本兼容性传感器
- 所有实体在设备推送时立即更新——没有轮询延迟

**高级诊断**（通过逆向工程获得的数据点——大多位于*诊断*实体类别中，许多默认停用；参见[非官方数据点说明](zh/developers/data_point_unofficial.md)）
- 错误与事件：活动错误数量（原始错误列表作为属性）以及最近事件代码。已知错误代码会通过社区整理的目录（`error_codes.py`）转换为可读文本，该目录还会解码割草机的最新错误代码（dp_115）
- 蜂窝网络 / 4G：调制解调器已启用、信号强度（RSRP / RSRQ）、连接类型，以及*强制蜂窝网络*读数
- 环境：设备上报的日出 / 日落、白昼状态、除雾加热、照明灯，以及极端天气警告（可附带信息链接）
- 安全与高级设置：跌落检测和坡度检测状态、雨量传感器阈值、雨后自动恢复及其延迟，以及*强制单一基站*读数
- 运行模式：移动 / 地图 / 割草模式字符串
- 建图与进度：手动建图提示标志（需要重新定位 / 需要接管、边界已闭合）以及地图保存进度百分比

**事件与自动化**
- **割草机事件实体** — 在每个值得关注的状态转换时触发一个独立事件（`mowing_started`、`paused`、`returning`、`docked`、`mowing_completed`、`error`），每个事件都带有原始任务字段，因此自动化可以对*发生的事情*作出反应，而无需轮询活动状态
- 一键导入的自动化蓝图（见下文）

**集成使用体验**
- 通过 Zeroconf/mDNS 自动发现
- 重新配置流程（无需重新添加即可更改主机/IP）和重新认证流程
- **修复提示** — 针对固件不兼容以及刀片 / 基站维护到期的可操作仪表板卡片
- 诊断下载，便于提交错误报告
- 已翻译为 33 种语言（bg、ca、cs、da、de、el、en、es、et、fi、fr、hr、hu、it、ja、ko、lt、lv、nb、nl、pl、pt、pt-BR、ro、ru、sk、sl、sr、sv、tr、uk、zh-Hans、zh-Hant）
- **命令确认** — 分区割草会等待设备的 dp_119 确认，并在被拒绝时上报，而不是静默地“成功”
- 基于 MQTT 的本地推送通信——无需云端

### 支持的实体

| 平台 | 实体 |
| --- | --- |
| 割草机 | 启动 / 暂停 / 回充控制，带实时活动状态 |
| 摄像头 | 含路径、机器人和基站的地图；纯地图的简洁变体 |
| 传感器 | 电池电量、电池状态、电池温度状态、地图状态、地图面积、割草高度、割草速度、运行模式、位姿、累计割草时间 / 作业次数 / 已割面积、当前会话面积 / 进度 / 时长 / 作业类型、进行中作业、故障、刀片和基站剩余时间、下次计划启动、版本兼容性、主方向状态、电源模式、返回基站原因、任务、子任务、任务状态。*诊断：*活动错误、最近事件、Wi-Fi 信号、蜂窝 RSRP / RSRQ / 类型、日出、日落、移动 / 地图 / 割草模式、雨量传感器阈值、雨后恢复延迟、地图保存进度 |
| 二元传感器 | 正在充电、导航已定位、固件升级中、电源开关、问题、检测到雨水、地图已检测 / 可构建 / 正在备份、正在保存数据、数据转换中。*诊断：*蜂窝网络已启用、除雾加热、照明、白昼、极端天气、跌落 / 坡度检测、雨后自动恢复、强制单一基站、强制蜂窝网络、手动建图重新定位 / 接管 / 边界已闭合、状态标志 134（未解码） |
| 选择 | 分区选择、割草速度、刀盘转速、主方向模式、高草沿边修剪模式 |
| 数值 | 割草高度、沿边切割距离、割草间距、单方向角度、自动旋转角度间隔、第一 / 第二方向角度 |
| 开关 | 彻底切割边角 |
| 按钮 | 沿边修剪、重置刀片计时器、重置基站计时器 |
| 更新 | 固件版本 |
| 事件 | 割草机事件（割草开始 / 暂停 / 返回 / 已回充 / 完成 / 错误） |
| 日历 | 割草日程（下一次计划割草） |

### 安装

[![打开您的 Home Assistant 实例并在 Home Assistant Community Store 中打开仓库。](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### 方法一：HACS（推荐）
1. 确保已安装 [HACS](https://hacs.xyz/)
2. 使用上方按钮将集成添加到 HACS
3. 打开 HACS，搜索“TerraMow”并选择该集成
4. 安装并重启 Home Assistant

#### 方法二：手动安装
1. 将 `custom_components/terramow` 文件夹复制到 Home Assistant 的 `/config/custom_components` 文件夹
2. 重启 Home Assistant
3. 前往 设置 → 设备与服务 → 添加集成
4. 搜索“TerraMow”并按照配置步骤操作

### 配置

本地网络中的设备会通过 Zeroconf 自动发现——接受发现的设备并输入 MQTT 密码。手动设置需要以下参数：

- **主机**：TerraMow 设备的 IP 地址或主机名
- **密码**：用于认证的 MQTT 密码

**之后更改设置**
- *重新配置*（设置 → 设备与服务 → TerraMow → 重新配置）：就地更改主机/IP 或密码，例如割草机获得了新的 DHCP 地址之后——无需删除并重新添加集成。
- *选项*（配置）：
  - **地图输出分辨率** — 数值越高越清晰，但每次渲染会消耗更多带宽和 CPU。
  - **地图主题** — `light` 或 `dark`。
  - **显示已割区域** — 在路径线下方为已经割过的区域添加阴影。
  - **将任何已结束的作业视为 100 % 完成** — 某些固件在作业结束时不会发出完成信号，因此即使草坪已经割完，会话进度也不会跳到 100 %（会显示为“已中止”）。启用此项可将任何已结束的作业视为完成，与厂商 App 一致；保持关闭则保留计数器的真实数值。*默认：关闭。*
- 如果设备密码发生变化，Home Assistant 会自动启动*重新认证*流程。

### 要求

- Home Assistant 2024.6.0 或更高版本（CI 会针对当前 HA Core 版本进行验证）
- TerraMow 固件版本 6.6.0 或更高
- TerraMow App 版本 1.6.0 或更高
- 实时地图和割草路径需要固件 HA 模块版本 3；在版本 2（例如 S800）上其他功能均可正常使用，版本兼容性传感器会予以说明

### 支持的设备

本集成适用于提供本地 MQTT/HTTP 接口的 TerraMow 机器人割草机——即任何搭载所需固件的型号。它已用于 TerraMow S 系列，包括 **S800**（上报固件 HA 模块版本 2）以及使用版本 3 的较新机型。任何搭载固件 6.6.0+ 和 App 1.6.0+ 的 TerraMow 割草机都应可正常工作；版本兼容性传感器和修复提示会告知某台设备的固件是否对某项功能而言过旧。

### 服务

#### `terramow.start_select_region`

针对所选子区域列表开始割草。

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

在割草机上写入或删除每周割草时段。每次写入都会与设备确认（dp_119 确认以及日程回读）。

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` 需要时段的 `item_id`（显示为日历事件的 uid，并在添加时段时返回）。

> **注意：** 当前零售固件尚不接受通过本地 MQTT 写入日程（厂商 App 使用蓝牙/云端）。在固件支持之前，请使用**随天气调整割草蓝图**在 HA 侧进行排程。

### 交互式地图卡片

本集成自带 Lovelace 卡片——自动注册，无需手动添加资源，也无需单独安装 HACS 前端：

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

它以矢量方式绘制草坪（任意缩放级别都清晰，跟随您的 HA 主题）：分区、禁区、虚拟墙、割草路径、基站以及机器人的实时位置。拖动可平移，滚动或双指捏合可缩放，双击可重新适配。**点选一个或多个分区**，然后按下出现的按钮即可精确割这些分区（底层调用 `terramow.start_select_region`）。

**视图按钮**可切换卡片在草坪上叠加的内容：

| 模式 | 显示内容 |
| --- | --- |
| **两者** | 已割区域*和*割草路径（启用区域显示时为默认） |
| **路径** | 仅显示当前作业和上一次作业的路径 |
| **区域** | 仅显示已割区域的阴影，并带各分区进度 |
| **Wi-Fi** | 草坪的 **Wi-Fi 热力图**，由割草机在割草过程中自行采样（绿色 = 信号强）。割草行程之间的空隙会依据相邻采样插值；割草机从未经过的地面保持空白 |

所选模式会按实体保存在浏览器中。选项和细节请参见[仪表板指南](zh/dashboard.md#交互式地图卡片)。实时地图数据需要固件 HA 模块版本 3（与地图摄像头相同）。该卡片也会出现在仪表板的卡片选择器中，名称为 **TerraMow Map Card**，并配有完整的 UI 编辑器——无需编写 YAML。

### 仪表板示例

一个开箱即用的 Lovelace 视图（实时地图、控件、进度仪表、状态一览）以及通知自动化：请参见[仪表板指南](zh/dashboard.md)。

### 自动化蓝图

针对最常见通知的一键导入蓝图——每个蓝图只需指定相关的 TerraMow 实体和一个通知动作：

- **随天气调整割草** — 按您的日程开始割草，并在检测到或预报有雨时自动跳过
  [![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **问题通知** — 当割草机报告故障时
  [![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **因雨返回** — 当割草机因下雨返回基站时
  [![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **割草完成** — 当一次割草作业完成时
  [![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**直接使用事件实体** — 割草机事件实体是最灵活的触发器。其 `event_type` 属性取值为 `mowing_started`、`paused`、`returning`、`docked`、`mowing_completed`、`error` 之一，并携带原始字段 `mission`、`sub_mission`、`state`、`back_to_station_reason` 和 `has_error`：

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow 已完成割草 🌱"
```

### 修复提示

本集成会创建可操作的 Home Assistant 修复提示（设置 → 设备与服务 → 修复），而不是把问题隐藏在传感器里：

- **固件不兼容 / 需要更新** — 固件对本集成（或某项功能）而言过旧。由版本兼容性检查得出；当兼容固件上报后自动消除。
- **刀片维护到期** — 刀盘已达到建议的 240 小时保养周期。清洁或更换刀片，然后按下*重置刀片计时器*按钮以清除该提示。
- **基站维护到期** — 基站已达到建议的 30 天保养周期。清洁基站，然后按下*重置基站计时器*按钮以清除该提示。

### 诊断与排障

- **诊断下载**：设置 → 设备与服务 → TerraMow → 三点菜单 → *下载诊断信息*，会生成一份已脱敏的 JSON 快照（设备状态、固件兼容性、原始数据点缓存）——请在提交错误报告时附上。
- **发现尚未支持的功能**：割草机发布的数据点比已记录的更多。每个未知数据点的首个负载会在 INFO 级别记录一次；为 `terramow` 集成开启调试日志即可记录全部内容。如果您发现了对应某项缺失功能的数据点（例如抬起报警、日程开关、错误代码），欢迎在 issue 中分享。

### 数据如何更新

TerraMow 是一个**本地推送**集成。割草机在设备上运行 MQTT broker；Home Assistant 通过局域网直接连接（无需云端）并订阅设备的数据点主题，因此实体状态会在割草机报告变化的那一刻更新，而不是按轮询间隔更新。较大的负载（地图、实时路径）通过 MQTT 通告，并按需通过本地 HTTP 获取。如果割草机处于休眠或不在网络中，连接会以指数退避方式重试，割草机实体则以 `error` 活动状态呈现连接中断。

**命令会明确失败，而不是静默失败。** 当您发送命令时——`dock`、`start_mowing`、`pause`、沿边修剪、分区割草或任何设置更改——命令会以 MQTT QoS 1 发布（因此短暂重连会缓存它，而不是丢弃）。如果割草机离线或无法访问、broker 拒绝发布，或者命令到达的速度超过设备的接受能力，服务调用会**以错误失败**，而不是静默地报告成功。这意味着在割草机无法访问时调用 `lawn_mower.dock` 的自动化会看到失败（并可重试或发出通知），而不会误以为割草机正在返回，实际上它从未收到命令。

### 已知限制

- **无云端 / 远程访问** — Home Assistant 必须与割草机处于同一局域网；没有云端回退方案。
- **受固件限制的功能** — 实时地图和割草路径视图需要固件 HA 模块版本 3；在版本 2（例如 S800）上其他功能均可使用，兼容性传感器 / 修复提示会说明该限制。
- **固件更新**需通过 TerraMow App 完成，而不是从 Home Assistant 进行；固件 `update` 实体仅供参考。
- **位姿传感器和纯地图摄像头默认停用**（位姿传感器约以 2 Hz 更新）；如需使用，请在实体设置中启用。
- **许多高级诊断实体默认停用**，并归入*诊断*类别（蜂窝网络、日出/日落、运行模式、手动建图标志等）；它们来自逆向工程获得的数据点，因此请只启用您需要的项目。参见[非官方数据点说明](zh/developers/data_point_unofficial.md)。
- 设备的部分数据点尚无文档；未知数据点会记录一次，以帮助发现缺失的功能。

### 使用场景

- **与降雨相关的通知** — 当割草机因下雨返回基站时收到推送（参见上文蓝图）。
- **故障告警** — 割草机报告问题（卡住、被抬起、受阻）的那一刻即收到通知。
- **在自动化中进行分区割草** — 调用 `terramow.start_select_region`，按日程或通过仪表板按钮割特定子区域。
- **维护提醒** — 刀片 / 基站剩余时间传感器和重置按钮可用于实现自动化的维护提醒。
- **在仪表板上显示实时地图** — 展示带有机器人位置和割草路径的地图摄像头（参见仪表板指南）。

### 语言

本集成已翻译为：Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文。

### 升级说明

- **v0.5.0**：实体状态值由大写改为小写（例如 `MISSION_IDLE` → `mission_idle`），以符合 Home Assistant 的翻译要求。比较原始状态字符串的自动化或模板需要做一次性调整；显示名称保持不变。

### 支持

如需支持，请在 [GitHub](https://github.com/it-rec/TerraMowHA/issues) 上提交 issue。

### 开发者信息

面向希望了解或扩展本集成的开发者（开发者文档为英文，部分内容有中文版）：

- [贡献指南](../CONTRIBUTING.md) — 环境搭建、质量要求（100 % 覆盖率、`mypy --strict`、翻译）、PR 与发布流程
- [架构](ARCHITECTURE.md) — 集成内部实现：hub 生命周期、执行模型、数据点目录、地图/路径流水线
- [开发者指南](zh/developers.md) — 设备的 MQTT/HTTP 通信协议（[英文版](en/developers.md)）
- [本分支相对上游的新增内容](UPSTREAM_DELTA.md)

在本地运行测试套件：

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## 许可证

本项目采用 GNU General Public License v3.0 许可 — 详情请参见 [LICENSE](../LICENSE) 文件。
