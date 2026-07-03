# TerraMow Home Assistant集成

<div align="center">
  <p>
    <a href="../README.md"><img src="https://img.shields.io/badge/English-blue?style=for-the-badge" alt="English"/></a>
    <a href="#"><img src="https://img.shields.io/badge/中文-red?style=for-the-badge" alt="中文"/></a>
  </p>
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

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
- 固件更新实体和版本兼容性传感器

**集成体验**
- Zeroconf/mDNS 自动发现
- 重新配置流程（无需删除重加即可更改主机/IP）和重新认证流程
- 诊断信息下载，便于反馈问题
- 支持 14 种语言（en、cs、da、de、es、fi、fr、it、nb、nl、pl、pt、sv、zh-Hans）
- 基于 MQTT 的本地推送通信——无需云端

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

需要配置以下参数：
- **主机地址**：TerraMow设备的IP地址或主机名
- **密码**：MQTT认证密码

### 系统要求

- Home Assistant 2023.9.3或更高版本（已在2025.1.1版本上测试）
- TerraMow固件版本6.6.0或更高
- TerraMow APP版本1.6.0或更高

### 支持

如需支持，请在[GitHub](https://github.com/TerraMow/TerraMowHA/issues)上提交问题。

### 开发者信息

对于有兴趣了解或扩展此集成的开发者，请参阅[开发者指南](../docs/zh/developers.md)。

---

## 许可证

本项目采用GNU通用公共许可证v3.0授权 - 详情请参阅[LICENSE](../LICENSE)文件。