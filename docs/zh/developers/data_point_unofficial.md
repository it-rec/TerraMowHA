非官方 / 逆向工程数据点
===

> ⚠️ **这不是 TerraMow 官方文档。**
>
> 本页中的数据点**未**在官方的 [`data_point.md`](./data_point.md) 中说明。它们的
> 字段名称和含义是**根据单台设备的实时诊断信息逆向推导得出的**
> （TerraMow S1200，序列号 `MP511…`，固件 `9.9.210`）。在**其他型号（S800、V1000
> 等）和其他固件版本**上，它们可能有所不同，也可能不存在。
>
> 基于这些数据点构建的每个实体：
> - 都采用**防御性解析** —— 字段缺失或结构不同时，实体会报告 `None` /
>   `unavailable`，绝不会让集成崩溃；
> - 都归类为**诊断**类别，以便与官方支持的实体清楚区分；较为冷门的实体**默认停用**，
>   如需使用请在实体设置中启用；
> - 都仅根据观察到的负载推导而来，因此请把下面的语义视为尽力而为的解读，而非契约。
>
> 权威参考仍然是 [`data_point.md`](./data_point.md)。如果您能在自己的设备/固件上确认
> 或纠正其中任何一项，请提交 issue 并附上诊断导出文件（`设置 → 设备与服务 →
> TerraMow → ⋮ → 下载诊断信息`，其中的 `unknown_data_point_payloads` 区块）。

## 这些数据点是如何发现的

集成会订阅 `data_point/0..200/robot`。任何没有注册处理器的 id 都会被记录一次，其最新
负载会保留下来用于诊断导出（`unknown_data_point_payloads`）。下面的条目就来自这样的
导出文件。

导出文件还会为每个未记录的 dp 附带**带时间戳的变更历史**
（`unknown_data_point_history`）—— 其中只记录*数值变化*，因此它是一份紧凑的状态转换
轨迹，而不是原始流量。这是解码**动态** dp（例如 dp_109、dp_134）的最佳方式：开启调试
日志，让割草机执行几个有意为之的动作（开始/停止割草、回充、更改某项设置），然后**导出
一次**，把时间戳与您所做的操作对应起来。

## 已实现的数据点

| ID | 含义 | 观察到的负载 | 呈现方式 |
|----|------|--------------|----------|
| 102 | 设备 / 网络信息；携带真实的 App 固件版本 | `{"version":"9.9.210","sn":"…","wifi_mac":"…","ip":"…","ssid":"…","warranty":{…}}` | 固件 `update` 实体的版本 + 设备 `sw_version`（标识信息不予公开） |
| 116 | 活动错误列表 | `{"error_list":[{"code":…}]}`（参考设备上为空） | **活动错误**传感器（数量 + `errors` 属性）和**故障**传感器（通过 `error_codes.py` 将当前故障呈现为可读文本，含 `error_codes` 属性）；同时驱动**问题**二元传感器 / 割草机 **error** 状态 / 割草机 **error** 事件（列表非空即视为故障，含 `error_codes` 属性），因为仅凭 dp_107 的 `has_error` 会漏掉部分故障（issue [#171]） |
| 118 | 地图保存 / 上传进度（0–100 %）。设备在割草后保存地图期间（`SUB_MISSION_SAVING_MAP` / “正在保存地图”）会持续攀升，通过观察它与 App 屏幕上的“地图保存 %”同步地 `1 → … → 100` 递增而得到确认 | `{"int_value":42}` | **地图保存进度**传感器（`%`；诊断，**默认停用**） |
| 119 | 命令确认 —— 回显命令的 `seq`，并带上 `code:0`（= 正常）或非零错误码。**实地发现（V1000 fw28）：**设备*不会*确认本集成通过本地 MQTT 发送的命令 —— 在那里观察到的 dp_119 确认携带的是类似纪元时间的 seq，属于割草机内部（BLE/云端）指令方；而无法解析的 dp_122 负载会被静默丢弃（没有拒绝码）。因此日程写入协商依赖 `GET` 校验 | `{"seq":1783335426,"code":0}` | **命令确认**：`terramow.start_select_region`（以及地图卡片的点选割草）会等待确认并呈现拒绝结果；被拒绝的即发即弃命令会记录警告；最近一次确认会出现在诊断信息中 |
| 109 | 割草机自身链路的 **Wi-Fi 信号强度**，以百分比表示（约等于 `2 * (RSSI dBm + 100)`）。通过实测确定：紧靠接入点时固定在 98（路由器侧为 −42 dBm），在草坪上隔一道墙时为波动的 52–68（路由器侧为 −75…−80 dBm），在混凝土地下室内为 98（排除了先前关于 GNSS 质量的猜测），且与电池电量无关。请注意，FRITZ!Box 一类路由器侧的读数测量的是这条非对称链路的*另一端*，差异可达约 10 dBm，在 mesh AP 漫游 / 2.4↔5 GHz 切换时差异更大 | `{"int_value":62}` | **Wi-Fi 信号**传感器（%；诊断） |
| 122 | 完整的每周日程（比 dp_138 更丰富）。只有 `SCHEDULE_CMD_TYPE_GET` 的响应会携带 `schedule_list`；`ADD`/`DELETE` 是写命令，确认时不带该字段（因此日程在 MQTT 上是可写的 —— 未来可能实现“编辑日历”功能）。hub 会在连接时发出 `GET`，并捕获 App 方向的 dp_122 流量（DEBUG 日志 + 诊断信息中的 `schedule_app_captures`），以便根据真实的 App 使用记录下确切的 `ADD`/`DELETE` 写入格式 | `{"cmd_type":"SCHEDULE_CMD_TYPE_GET","schedule_list":{"items":[{"id":0,"schedule_type":"SCHEDULE_TYPE_GLOBAL_V2","global_schedule_v2":{"basic_config":{"week_days":["WEEK_DAY_MONDAY",…],"start_time":{"hour":9,"minute":30},"end_time":{"hour":11,"minute":0},"disabled":false,"run_once":false}}}],"global_disabled":false,"disabled_week_days":[],…}}` | 日程 `calendar` 实体（每周时段；事件 uid = 条目 id）以及**可写日程**：`terramow.add_schedule` / `terramow.delete_schedule` 服务。确切的写入负载结构会按固件协商 —— 每个候选格式都会用一次新的 `GET` 来校验，并记录每次尝试。**确定性的实地发现（V1000，overall 固件 28，日程模块 5，home_assistant 模块 3）：**所有写入候选都被静默丢弃 —— 具名动词（`ADD`/`SET`/`UPDATE`/`SAVE`）、数字 `cmd_type` 1-6，以及所有看似合理的负载结构 —— 而 `GET` 则正常应答；请求消息显然只携带 `cmd_type`+`seq`，也就是说**当前固件并未开放本地日程写入**（厂商 App 通过 BLE/云端写入）。这些服务保留下来以备将来的固件；HA 侧的排程由随天气调整割草蓝图覆盖 |
| 123 | 事件日志 | `{"event_list":[{"code":8,"time":"…Z"}]}` | **最近事件**传感器（最新的 `code` + `event_time` 属性） |
| 129 | 各组件固件版本 | `{"ap_app":"9.9.210","main_controller":"09.09.210",…}` | 固件 `update` 实体的 `component_versions` 属性 |
| 134 | 未解码的二元标志。观察到运行期间 `enum_value` 在 `0` 和 `1` 之间切换 —— 所以它是实时状态，**并非**常量。其实际含义未知；呈现出来仅为便于与割草机行为相互印证并加以解码 | `{"enum_value":1}` | **状态标志 134** 二元传感器（原始 `enum_value`：`1` → 开，`0` → 关；诊断，**默认停用**） |
| 135 | 蜂窝 / 4G 调制解调器信息（仅限带调制解调器的型号） | `{"is_enabled":false,"RSRP":0,"RSRQ":0,"type":"CELLULAR_TYPE_UNKNOWN",…}` | **蜂窝网络已启用**二元传感器；**蜂窝 RSRP** / **RSRQ** / **类型**传感器（停用期间信号传感器为 `None`） |
| 150 | 高级设置。除只读呈现外还有一条**未公开的写入路径**，与 dp_122 日程写入一样按固件协商：候选负载结构按破坏性从小到大依次发送（`merged_block`，即回显整个上报块并只替换一个字段 → `nested_field` → `flat_field` → `wrapped_field`），且只有当设备在 `ADVANCED_SETTING_VERIFY_TIMEOUT` 内*把请求的值上报回来*时，写入才算成功 —— 此处 dp_119 的确认不可信（见 dp_119）。已验证的结构会按 hub 记住并在之后优先尝试。若没有任何结构得到确认，服务调用会抛出 `advanced_setting_write_failed`，而不是静默地“成功”。**确定性的实地发现（V1000，home_assistant 模块固件）：**与 dp_122 日程写入一样，所有候选结构（`merged_block`、`nested_field`、`wrapped_field`）都被静默丢弃 —— 在已回基站/休眠以及唤醒并正在割草两种状态下均已测试，以只读的 dp_150 传感器作为基准：它们始终没有变化。也就是说**当前固件并未开放本地 dp_150 写入**；这些写入实体（默认禁用）保留下来以备接受写入的固件，并且会如实抛出错误，而不是报告一次并未发生的写入 | `{"enable_cliff_detection":{"value":true},"enable_slope_detection":{"value":false},"rain_sensor_threshold":{"upper_limit":1000},"after_rain_stop_setting":{"enable_auto_resume":false,"auto_resume_delay_time":{"hours":2,"minutes":0}},…}` *只读：* **跌落检测** / **坡度检测** / **雨后自动恢复** / **强制单一基站** / **强制蜂窝网络**二元传感器；**雨量传感器阈值** / **雨后恢复延迟**传感器。*可写（配置类别，默认禁用）：* **跌落检测** / **坡度检测** / **雨后自动恢复**开关，以及**雨量传感器阈值** / **雨后恢复延迟**数字实体（`mow_spacing`/`mow_speed` 通过 dp_155 提供；样本中 `disable_wifi_*` 被截断，未予呈现） |
| 152 | 环境 / 状态 | `{"is_defogger_heating":false,"is_illuminate_light_on":false,"sunrise":{"hour":5,"minute":29},"sunset":{…},"is_not_in_daylight_period":false,"manual_mapping":{…}}` | **日出** / **日落**传感器；**除雾加热** / **照明** / **白昼**二元传感器；**手动建图：重新定位 / 接管 / 边界已闭合**二元传感器 |
| 154 | 运行模式 | `{"move_mode":"MOVE_MODE_MOW","map_mode":"MAP_MODE_BASE_STATION","mow_mode":"MOW_MODE_GLOBAL"}` | **移动** / **地图** / **割草**模式传感器（原始设备枚举） |
| 157 | 极端天气警告（注意设备端拼写为 `extream`） | `{"has_extream_weather":false,"extream_weather_info_url":""}` | **极端天气**二元传感器（安全类；含 `info_url` 属性） |

## 已观察到但尚未呈现

在此记录以备将来处理；尚未解码为实体。

| ID | 可能的含义 | 观察到的负载（已截断） |
|----|------------|------------------------|
| 103 | **dp_103 命令通道的确认回显**（集成会向 `data_point/103/app` 发布选区割草 / 清扫命令）：`/robot` 一侧会为每个被接受的命令回复 `{seq, ret:0}`。已实时确认（V1000 fw28）：每个通过本地 MQTT 发送的 `start_mowing` / `dock` 都恰好产生一次回显，`seq` 单调递增 —— 因此与 dp_119（在该固件上只携带内部指令方的确认）不同，dp_103 *确实*会确认本地 MQTT 命令。**绘制区域相关发现（2026-07-22）：**一次受控的穷举试验发出了六种绘制区域命令结构（`START_MODE_DRAW_REGION_CLEAN` / `_CUSTOM_REGION_CLEAN` / `_DRAW_CLEAN`，分别配合 `{polygon:{points}}`、`{points}`、`{draw_region_polygons:[…]}` 片段）—— **无一得到任何确认**，而作为对照的 `START_MODE_SELECT_REGION_CLEAN` 得到了确认（`ret:0`）并启动了割草机。因此本地 dp_103 只接受已记录的启动模式（`GLOBAL_CLEAN` / `SELECT_REGION_CLEAN` / `EDGE_TRIM_CLEAN` / `RETURN`）；该固件上**不存在本地绘制区域启动模式**（App 通过 BLE/云端绘制区域），issue [#199] | `{"seq":917327464,"ret":0}` |
| 104 | 由 App 的“结束作业 / 清除自动模式进度”动作触发的**确认**（V1000 fw28）：仅观察到一次，就在用户于厂商 App 中确认“清除”的同一秒；推测是某个结束/清除命令通道的 `/robot` 确认（App 通过 BLE/云端写入，因此本地只能看到确认）。`seq` 类似纪元时间 | `{"seq":1784657579,"ret":0}` |
| 110 | 未知标量 | `{"int_value":60}` |
| 111 | 上传进度（dp_118 的搭档？）。在一次包含中途回充的完整割草过程中始终保持 `{false, 0}` —— 无论它上传什么，正常割草并不会触发它 | `{"is_uploading":false,"process":0}` |
| 114 | **最近事件代码** —— 镜像 dp_123 事件日志中的最新条目。观察到在 dp_123 追加 `{code:90}`（一次重新定位事件）的同一时刻出现 `int_value:90`；更早的 `int_value:8` 与 dp_123 的代码 8 相符。**2026-07-21 再次确认（V1000 fw28）：**dp_114 与 dp_123 的到达间隔小于 100 毫秒，而一天中的 dp_114 数值（`43`、`87`、`65`）都与最新的 dp_123 `code` 相符且时间戳一致（`65` 出现在回充返回入站时；一次地下室重新定位产生了 `135`）—— 这也否定了先前认为该 dp 是链路质量指标的假设。与**最近事件**传感器重复，因此不单独呈现 | `{"int_value":65}` |
| 115 | **最近错误代码** —— 镜像 dp_116 活动错误列表中的最新条目，正如 dp_114 镜像 dp_123 事件日志。已由社区在 S1200 固件 `9.9.210` 上两次确认（issue [#171]）：`int_value:201` 在 dp_116 追加 `{code:201}`（割草机被抬起）的同一瞬间到达，而 `int_value:903` 与 `{code:903}`（割草机卡住）相符。已在 hub 中解码（`active_error_code`）；故障呈现仍基于内容更丰富的 dp_116 列表。已知代码的含义见 `error_codes.py` | `{"int_value":903}` |
| 120 | 形如确认/回显，与 dp_119 属同一族（用 `code` 而非 `ret`）；仅在割草机停靠空闲时观察到一次，上下文不明。`seq` 类似纪元时间 | `{"seq":1784579052,"code":0}` |
| 134 | 未解码的二元标志（呈现为**状态标志 134**）。注意：在一次完整的启动/暂停/恢复/回充过程中它保持**不变**，因此它与割草状态**无关** —— 含义仍然未知 | `{"enum_value":0}` |
| 145 | 自定义通道创建状态 | `{"stage":"CUSTOM_PASSAGE_STAGE_INVALID","is_on_grass":false,…}` |
| 146 | 未知标量 | `{"int_value":1}` |

## 行为发现（官方数据点）

以下是**确实**记录在 [`data_point.md`](./data_point.md) 中的数据点的逆向工程*行为*，
记录在此以便该文件保持为一份干净的厂商镜像。

**dp_107 `mission_status` —— 入站时 `mission` 会重置为 `MISSION_IDLE`，且没有区分
暂停与完成的信号。** 当割草机在**尚未完成**时返回基站（例如日照时间用完，稍后会继续），
固件会报告 `mission = MISSION_IDLE` / `sub_mission = SUB_MISSION_IDLE` /
`state = MISSION_STATE_IDLE` —— 与真正完成的作业逐字节相同。
`back_to_station_reason` 也**无法**区分：官方规范指出该字段仅在 `sub_mission` 为
`SUB_MISSION_RETURN_TO_BASE` 或 `SUB_MISSION_FLEXIBLE_STATION_WAIT` 时才有意义，因此
一旦割草机处于停靠空闲状态，它读作 `BACK_TO_STATION_REASON_NONE`（已在 S1200 固件
`9.9.210` 上确认，issue [#142] 评论
[4961842352](https://github.com/it-rec/TerraMowHA/issues/142#issuecomment-4961842352)）。
没有观察到任何 dp_107 字段标记“中途暂停，将会继续”。

- *后果：*原始的**任务**传感器在此正确地降为*空闲*；会话级的**进行中作业**传感器则用
  一个有界的锁存（`ACTIVE_MISSION_DISPLAY_TIMEOUT`）重建进行中的作业，因为设备没有给出
  直接信号（issue [#173](https://github.com/it-rec/TerraMowHA/issues/173)）。
- *有待关注：*在将来的固件 / 诊断采集中，请检查 dp_107 是否出现新字段，或是否有在入站后
  仍然保持的 `back_to_station_reason`，用以标记可恢复的暂停 —— 同时也留意任何仍未解码的
  邻近 dp 是否跟踪会话进度。其中任何一项都能让“进行中作业”依据真正的完成情况来跟踪，而
  不必依赖超时。

**回充返回、手动结束作业与缺失的 `MISSION_STATE_COMPLETE`（dp_107 / dp_113）。**
一次完整的中断作业实时采集（V1000 fw28，2026-07-21）：当电池在作业中途电量不足时，割草机
在返回途中报告 `mission = MISSION_RECHARGE`，随后入站进入常见的 `MISSION_IDLE`（参见上面
的发现）—— 作业在设备侧仍处于打开状态（App 仍提供*结束*选项）。充满电后割草机**没有**继续
剩余的分区，而当用户在 App 中结束该作业（“清除自动模式进度？”→*清除*）时，设备
**将 dp_113 的会话计数器归零** —— 期间从未发出 `MISSION_STATE_COMPLETE`。dp_104 的确认
（见上表）恰好在那一刻触发。

- *后果：*会话传感器通过 dp_113 计数器归零来判定“作业结束”（issue [#204]/[#207]）：以这种
  方式结束的作业计为*已中止* —— 计数器归零，**不会**跳到 100 %。目前只在固件自行完成的
  作业中观察到 `MISSION_STATE_COMPLETE`（以及 100 % 跳变）。
- *现实校验：*在这次采集中，**厂商 App 显示 100 % 且所有分区均为绿色，尽管其中一个分区
  从未被割过**（dp_113 停在 86 %，会话面积证实了这一缺口）。数据点才是诚实的信息来源 ——
  当 App 与集成不一致时，请相信数据点。

**dp_107 `has_error` 与 dp_116 `error_list` 是相互独立的故障信号。**
一位用户报告了一个在 App 中可见的故障（“割草机找不到基站”），它填充了 dp_116 的
**错误列表**，而 dp_107 的 `has_error` 仍为 `false`，因此割草机的**问题**二元传感器读作
*关*，尽管**活动错误**传感器已显示该错误（issue [#171]）。参考设备（S1200 固件
`9.9.210`）始终报告空的 `error_list`，这正是此问题此前未被注意到的原因。故障解除后
`error_list` 会被清空。

- *后果：*故障呈现会同时读取**两个**信号 —— `has_active_error` 为 `has_error` 或
  `error_list` 非空 —— 因此**问题**二元传感器、割草机的 **error** 活动状态以及 **error**
  事件在任一情况下都会触发。dp_116 的错误代码会作为“问题”传感器的 `error_codes` 属性
  呈现。dp_116 不流经 `on_mission_status`，因此其处理器会直接通知割草机 / 事件监听者，
  以便实时呈现故障。
- *条目结构已确认*（S1200 固件 `9.9.210`，issue [#171] 中的实时采集）：
  `{"error_list": [{"code": int, "time": "<RFC3339>"}]}` —— 与 dp_123 事件日志结构相同。
  每次故障还会以裸代码触发 dp_115（见上表）。
- *已知代码*（来自社区，目录位于 `error_codes.py`）：`201` 割草机被抬起，`903` 和 `909`
  割草机卡住（两个不同的卡住类代码）。这些代码会以可读文本呈现在**活动错误**传感器
  （`errors[].text`）、**问题**二元传感器（`error_descriptions`）、**error** 事件上，
  并且作为实体状态本身呈现在**故障**传感器上 —— 该传感器读取拼接后的描述
  （`"割草机卡住"`），无故障时为 `OK`。地图卡片会在故障上报的位置标注同样的文本。未知
  代码回退为 `Error <code>` —— [#171] 中每一次新的采集都会扩充这份目录。

[#142]: https://github.com/it-rec/TerraMowHA/issues/142
[#171]: https://github.com/it-rec/TerraMowHA/issues/171
[#199]: https://github.com/it-rec/TerraMowHA/issues/199
[#204]: https://github.com/it-rec/TerraMowHA/issues/204
[#207]: https://github.com/it-rec/TerraMowHA/issues/207
