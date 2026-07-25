# 仪表板示例

一个可直接粘贴使用的 TerraMow 集成 Lovelace 视图：实时地图、割草控件、作业进度以及最
有用的诊断信息。

如果您的实体使用了其他前缀，请替换下面实体 id 中的 `terramow`（可在 设置 → 设备与服务
→ TerraMow 下查看任一 TerraMow 实体）。

## 交互式地图卡片

本集成自带一个自定义 Lovelace 卡片并会自动注册 —— 无需手动添加资源，也无需单独安装
HACS 前端。它会出现在卡片选择器中，名称为 **TerraMow Map Card**（带 UI 编辑器），也可
以用 YAML 添加：

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

与 PNG 摄像头不同，该卡片通过实时 WebSocket 数据流以矢量方式渲染地图：任意缩放级别都
清晰，跟随您的仪表板主题，并且机器人标记的移动无需重新加载图像。

**交互方式**

- **拖动**可平移，**滚动 / 双指捏合**可缩放，**双击**（或 ⛶ 按钮）可重新适配整片草坪。
- **点击某个分区**即可选中（再次点击取消选中）；随后会出现一个操作栏，显示分区名称和
  总面积 —— 按下它即可通过 `terramow.start_select_region` 精确割选中的分区。设备自身
  报告为当前作业已选中的分区会以强调色着色。
- **点击机器人标记**可打开割草机的详情对话框。
- **情境控件**（右下角）只提供在当前状态下有意义的操作：停靠或暂停时可启动，割草或返回
  途中可暂停，工作中可回充。
- **跟随按钮**（十字准线，右上角）会在割草机工作时保持视图以其为中心；平移或缩放会解除
  跟随。该标记按活动着色（割草为绿色、返回为蓝色、暂停为橙色、错误为红色），并在割草时
  轻微脉动。
- **长按某个分区**可显示该分区的割草设置（割草高度、速度、条带间距、刀盘转速、沿边切割、
  方向、割草顺序），以及这些设置是该分区专属的还是全局的。
- **双指旋转**可转动地图；**指北针按钮**可将其重置为配置的 `rotation`。设置
  `rotate_gesture: false` 可锁定旋转。
- **键盘**：卡片获得焦点后，方向键可在各分区之间循环，回车键选中 —— 与点击手势构建的
  选择相同。
- **图例按钮**会列出您地图上实际存在的要素类型，因此遇到不熟悉的颜色或标记可以就地查阅。
- **活动故障**会标注在割草机上报故障的位置（并带上错误代码目录中的故障文本），这样卡住
  或被抬起的割草机一眼就能定位，而不是只在传感器中出现名称。

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `entity` | *必填* | 任意 TerraMow 实体；割草机实体是最自然的选择 |
| `show_controls` | `true` | 卡片上的情境式启动 / 暂停 / 回充按钮 |
| `zone_selection` | `true` | 点击（或用方向键选择）分区以开始选区割草 |
| `show_coverage` | `false` | 按真实切割宽度为已割条带添加阴影 |
| `show_wifi` | `false` | Wi-Fi 热力图叠加层，由割草机在割草过程中采样（绿色 = 信号强） |
| `show_current_path` | `true` | 绘制当前作业的割草路径，包含中途回充之前的轨迹 |
| `show_history_path` | `true` | 绘制上一次作业的路径（淡化显示） |
| `show_hud` | `true` | 状态标签（状态、电量、作业进度、预计剩余时间、地图） |
| `show_markers` | `true` | 被困 / 维护 / 通道标记 |
| `show_direction` | `true` | 每个区域的割草条带方向箭头 |
| `zone_info` | `true` | 长按某个分区以显示其割草设置 |
| `show_layer_counts` | `false` | 调试：在图例中列出接收到的图层数量 |
| `rotate_gesture` | `true` | 双指旋转地图（指北针按钮可重置） |
| `rotation` | `0` | 默认地图旋转角度（度）；指北针按钮会重置为该数值 |
| `fit_height` | `420` | 卡片画布高度（像素） |
| `fit_padding` | `0.95` | 适配视图时草坪占卡片的比例（`0.5`–`1.0`）；数值越大缩放越紧凑 |

**视图模式**

卡片标题栏中的一个按钮可循环切换绘制哪个叠加层 —— **两者**（已割区域 + 路径）、
**路径**、**区域**（仅已割区域，含各分区进度）和 **Wi-Fi**（热力图）。上面的
`show_coverage` / `show_current_path` / `show_history_path` / `show_wifi` 标志用于确定
*初始*模式，因此原先用这些标志来决定外观的卡片会保持原样；之后则以按钮为准，所选模式
会按实体保存在浏览器的本地存储中。

Wi-Fi 热力图是自行采样得来的：割草机在行驶时上报自身的信号强度（dp_109），卡片再把这些
采样点归入草坪的网格。割草行程之间的空洞会依据相邻网格补全，但割草机从未经过的地面会
保持空白 —— 卡片绝不会臆造未经测量的信号。请先完成一次完整割草，再将其视为完整数据。

适配视图取景的是草坪本身 —— 已绘制的分区、禁区和基站 —— 而不是更大范围的扫描区域，因此
大地图上的小块草坪会填满卡片，而不是孤零零地待在空白之中。将 `fit_padding` 调高至接近
`1` 可获得更紧凑的缩放，调低则留出更多边距。

该卡片适合墙面平板使用：静态几何图形会在帧之间缓存，路径更新以点增量方式传输，并且在
标签页隐藏时实时数据流会自动暂停。

**注意事项**

- 实时地图数据需要固件 HA 模块版本 3（与地图摄像头的要求相同）；在更旧的固件上，卡片会
  显示占位内容。
- 卡片会跟随当前的 Home Assistant 主题（浅色和深色）。
- 无头 / 自定义环境（或 YAML 资源模式，集成无法向其写入）仍可通过手动将
  `/terramow-frontend/terramow-map-card.js` 添加为仪表板资源来使用该卡片。请使用与集成
  为自身注册时相同的类型 —— **`js`**（*JavaScript 文件*），而不是 `module`。`js` 在
  Home Assistant 侧已被弃用但仍可使用，而且它是能够可靠加载的类型：从浏览器缓存提供的
  `module` 不会被重新求值，因此自定义元素可能始终未定义，卡片会一直显示
  “Configuration error”（issue #140）。完整理由请参见 `map_card.py` 中的
  `CARD_RESOURCE_TYPE`。
- 首次安装之后，可能需要强制刷新一次（Ctrl+Shift+R），浏览器才能加载刚刚注册的资源。

在下面的示例视图中，您可以把 `picture-entity` 摄像头卡片一对一地替换为交互式卡片。

## 示例视图

```yaml
type: sections
max_columns: 2
title: Lawn
sections:
  - type: grid
    cards:
      - type: picture-entity
        entity: camera.terramow_map
        show_state: false
        show_name: false
        camera_view: auto
        tap_action:
          action: more-info
  - type: grid
    cards:
      - type: entities
        title: Mower
        entities:
          - entity: lawn_mower.terramow
          - entity: select.terramow_zone_select
          - entity: button.terramow_edge_trim
      - type: gauge
        entity: sensor.terramow_current_session_progress
        name: Progress
        min: 0
        max: 100
        severity:
          green: 66
          yellow: 33
          red: 0
      - type: glance
        title: Status
        entities:
          - entity: sensor.terramow_battery
          - entity: sensor.terramow_current_session_area
          - entity: sensor.terramow_current_session_duration
          - entity: binary_sensor.terramow_rain_detected
      - type: entities
        title: Settings
        entities:
          - entity: number.terramow_mowing_height
          - entity: select.terramow_mow_speed
          - entity: select.terramow_blade_speed
          - entity: switch.terramow_thorough_corner_cutting
```

## 实用自动化

割草机遇到问题时发送通知：

```yaml
automation:
  - alias: "TerraMow: problem notification"
    triggers:
      - trigger: state
        entity_id: binary_sensor.terramow_problem
        to: "on"
    actions:
      - action: notify.notify
        data:
          title: "TerraMow needs help"
          message: >
            The mower reports a problem
            (mission: {{ states('sensor.terramow_mission') }}).

  - alias: "TerraMow: returned because of rain"
    triggers:
      - trigger: state
        entity_id: binary_sensor.terramow_rain_detected
        to: "on"
    actions:
      - action: notify.notify
        data:
          message: "TerraMow returned to the station — rain detected."
```

从脚本启动分区割草（服务调用）：

```yaml
script:
  mow_front_lawn:
    sequence:
      - action: terramow.start_select_region
        target:
          entity_id: lawn_mower.terramow
        data:
          region_ids: [1]
```

您安装环境中的实体 id 可能有所不同 —— Home Assistant 会根据设备名称生成它们，可在实体
设置中查看（或重命名）。

## 集成选项

设置 → 设备与服务 → TerraMow → **配置** 会提供本集成的选项。其中大部分用于控制地图摄像
头的渲染方式：

- **地图输出分辨率** —— PNG 的输出边长。数值越高，在大型仪表板上看起来越清晰，但每次渲染
  会消耗更多带宽和 CPU。
- **地图主题** —— `light`（默认）或 `dark`。选择 `dark` 可让地图融入深色仪表板。
- **显示已割区域** —— 按真实切割宽度在路径线下方为已经割过的区域添加阴影，便于看出草坪
  哪些部分还需要处理。

有一个选项影响的是会话传感器而非地图：

- **将任何已结束的作业视为 100 % 完成** —— 某些固件在作业结束时不会发出完成信号，因此
  即使草坪已经割完，`sensor.terramow_current_session_progress` 也不会跳到 100 %，作业
  会显示为已中止。启用此项可将任何已结束的作业视为完成（100 %），与厂商 App 一致 ——
  如果您用进度仪表达到 100 来触发自动化，这会很有用。保持关闭则保留计数器的真实数值。
  *默认：关闭。*

地图几何图形会以超采样方式渲染再降采样，因此多边形和路径边缘经过抗锯齿处理，机器人和
基站图标按真实比例绘制（并加以限制，使其在超大或超小草坪上仍然清晰可辨）。

完整（非简洁）地图还会叠加一个带整齐公制距离的**比例尺**、一个针对已有要素类型的紧凑
**颜色图例**，以及摘要面板中的 **“Updated HH:MM”** 时间戳（使用 Home Assistant 的本地
时间），这样过期图像很容易被发现。该时间戳也作为摄像头属性 `map_updated_at` 提供。

HUD 标签（图例、摘要面板、状态标签、占位文本）会跟随您的 **Home Assistant 界面语言**
—— 德语、法语、西班牙语、意大利语、荷兰语、葡萄牙语和中文（简体/繁体）已翻译，其他语言
回退为英语。解析出的语言作为摄像头属性 `map_language` 提供。

### 第三方交互式地图卡片

地图摄像头会发布 `calibration_points` 属性（三个设备坐标 ↔ 图像像素的参考点，以配置的
输出分辨率表示）。这是社区 [Lovelace 扫地机地图卡片][Lovelace vacuum map cards] 所使用
的校准格式，因此配置了 `calibration_source: camera` 的卡片可以在
`camera.terramow_map` 上叠加可点击的分区，并通过点击地图来调用
`terramow.start_select_region`。像素坐标会自动跟随所选的输出分辨率。

[Lovelace vacuum map cards]: https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card
