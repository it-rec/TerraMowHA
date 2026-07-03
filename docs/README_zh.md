# TerraMow Home Assistant集成

<div align="center">
  <p>
    <a href="../README.md"><img src="https://img.shields.io/badge/English-blue?style=for-the-badge" alt="English"/></a>
    <a href="#"><img src="https://img.shields.io/badge/中文-red?style=for-the-badge" alt="中文"/></a>
  </p>
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · **中文**

---

这是一个适用于TerraMow机器人割草机的Home Assistant集成。

### 功能特性

**控制**
- 割草机实体：启动、暂停和回充
- 分区割草：分区选择实体和 `terramow.start_select_region` 服务
- 沿边修剪按钮
- 在 Home Assistant 中直接设置：割草高度、速度、间距、刀盘转速、沿边距离、主方向模式与角度、彻底切角、高草沿边模式
- 维护：刀盘和基站保养计时器重置按钮

**监控**
- 实时地图摄像头（含割草路径、机器人位姿和基站；另有适合仪表盘的纯净地图摄像头，分辨率可在选项中配置）
- 电池：电量、充电状态、温度状态、充电器连接、电源开关
- 作业进度：本次作业面积、进度（%）、时长和作业类型；累计割草时长、次数和面积
- 状态：任务/子任务/任务状态、作业模式、功耗模式、回站原因、雨天检测、故障指示、数据保存与数据转换指示
- 地图：状态、面积、检测/可建图/备份中标志
- 日程：下次预约开始时间
- 固件更新实体、设备页固件版本显示以及版本兼容性传感器
- 所有实体随设备推送即时更新——无轮询延迟

**集成体验**
- Zeroconf/mDNS 自动发现
- 重新配置流程（无需删除重加即可更改主机/IP）和重新认证流程
- 诊断信息下载，便于反馈问题
- 支持 14 种语言（en、cs、da、de、es、fi、fr、it、nb、nl、pl、pt、sv、zh-Hans）
- 基于 MQTT 的本地推送通信——无需云端

### 支持的实体

| 平台 | 实体 |
| --- | --- |
| 割草机 | 启动/暂停/回充控制及实时活动状态 |
| 摄像头 | 含路径、机器人和基站的地图；纯净地图变体 |
| 传感器 | 电池电量、电池状态、电池温度状态、地图状态、地图面积、割草高度、割草速度、作业模式、位姿、累计割草时长/次数/面积、本次作业面积/进度/时长/类型、刀盘和基站剩余保养时间、下次预约开始、版本兼容性、主方向状态、功耗模式、回站原因、任务、子任务、任务状态 |
| 二元传感器 | 充电、导航定位、固件升级中、电源开关、故障、雨天检测、地图检测/可建图/备份中、数据保存中、数据转换中 |
| 选择器 | 分区选择、割草速度、刀盘转速、主方向模式、高草沿边模式 |
| 数值 | 割草高度、沿边距离、割草间距、单主方向角度、自动旋转角度间隔、第一/第二主方向角度 |
| 开关 | 彻底切角 |
| 按钮 | 沿边修剪、重置刀盘计时器、重置基站计时器 |
| 更新 | 固件版本 |

### 安装方法

#### 方法一：通过HACS安装（推荐）
1. 确保已安装[HACS](https://hacs.xyz/)
2. 进入HACS → 集成 → 三点菜单(⋮) → 自定义存储库
3. 添加 `https://github.com/TerraMow/TerraMowHA` 作为存储库URL，类别选择"集成"
4. 进入HACS → 集成 → + → 搜索"TerraMow"
5. 安装并重启Home Assistant

#### 方法二：手动安装
1. 将`custom_components/terramow`文件夹复制到Home Assistant的`/config/custom_components`目录
2. 重启Home Assistant
3. 进入设置 → 设备与服务 → 添加集成
4. 搜索"TerraMow"并按照配置步骤进行设置

### 配置参数

局域网内的设备会通过 Zeroconf 自动发现——确认发现的设备并输入 MQTT 密码即可。手动配置需要以下参数：

- **主机地址**：TerraMow设备的IP地址或主机名
- **密码**：MQTT认证密码

**后续修改设置**
- *重新配置*（设置 → 设备与服务 → TerraMow → 重新配置）：直接修改主机/IP 或密码，例如割草机通过 DHCP 获得新地址后——无需删除并重新添加集成。
- *选项*（配置）：设置地图摄像头输出分辨率。数值越高仪表盘画面越清晰，但每次渲染的带宽和 CPU 开销也越大。
- 如果设备密码发生变化，Home Assistant 会自动启动*重新认证*流程。

### 系统要求

- Home Assistant 2023.9.3或更高版本（已在2025.1.1版本上测试）
- TerraMow固件版本6.6.0或更高
- TerraMow APP版本1.6.0或更高
- 实时地图和割草路径需要固件 HA 模块版本 3；版本 2（如 S800）下其余功能均可用，版本兼容性传感器会有相应提示

### 服务

#### `terramow.start_select_region`

对指定的子分区开始割草。

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### 诊断与故障排查

- **诊断下载**：设置 → 设备与服务 → TerraMow → 三点菜单 → *下载诊断信息*，可导出脱敏的 JSON 快照（设备状态、固件兼容性、原始数据点缓存）——反馈问题时请附上。
- **发现未支持的功能**：割草机发布的数据点多于文档记载。每个未知数据点的首个报文会以 INFO 级别记录一次；为 `terramow` 集成开启调试日志可记录全部报文。如果你发现了缺失功能（如提离报警、日程开关、错误码）对应的数据点，欢迎在 issue 中分享。

### 语言

集成已翻译为：Čeština、Dansk、Deutsch、English、Español、Français、Italiano、Nederlands、Norsk (bokmål)、Polski、Português、Suomi、Svenska 和简体中文。

### 升级说明

- **v0.5.0**：实体状态值由大写改为小写（如 `MISSION_IDLE` → `mission_idle`），以符合 Home Assistant 翻译规范。比较原始状态字符串的自动化或模板需要一次性调整；显示名称不受影响。

### 支持

如需支持，请在[GitHub](https://github.com/TerraMow/TerraMowHA/issues)上提交问题。

### 开发者信息

对于有兴趣了解或扩展此集成的开发者，请参阅[开发者指南](../docs/zh/developers.md)。

本地运行测试套件：

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## 许可证

本项目采用GNU通用公共许可证v3.0授权 - 详情请参阅[LICENSE](../LICENSE)文件。
