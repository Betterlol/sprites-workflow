# Sprite 流水线

命令行负责可独立运行的 extract、process、select、pack / preview 阶段；网页工作台提供同一套处理能力的交互入口。启动和命令示例见 [README](../README.md)，网页说明见 [workbench.md](workbench.md)。

## 配置

`pipeline.json` 使用 version 2；所有相对路径以此文件为基准。`paths.source` 指向原图，其他阶段目录位于输出根目录内且互不重叠。

新工程创建于 `workspaces/<目录名>/`，原图和 processed 均位于工程内部。`project.name` 是可修改的展示名，目录名是网页请求的工程标识；`character` 用于交付文件命名。`paths.manifest` 可指定 manifest 文件位置，新工程默认写入 `exports/manifest.json`，其中图集和预览路径相对于 manifest 所在目录。旧工程省略此字段时保持原有位置。

| 字段 | 作用 |
| --- | --- |
| `frame_size` | 统一 RGBA 画布 `[width, height]` |
| `anchor` | 归一化 x/y 和画布中的 pixels 锚点 |
| `defaults.extract` / `sources.<filename>.extract` | 通用 / 单原图切图规则 |
| `defaults.process` / `sources.<filename>.process` | 通用 / 单原图处理规则 |
| `actions.<name>.sprites` | 按顺序引用 processed 下的 PNG 相对路径，可重复、可跨原图 |
| `actions.<name>.fps` / `loop` | 游戏播放参数 |
| `actions.<name>.animation` | 展示 WebP 参数，独立于游戏顺序 |
| `actions.<name>.pack.columns` | 图集列数 |
| `workbench.reviews` | 网页动作衔接序列，CLI 忽略 |

切图 `method` 支持 `components`、`grid`、`boxes`、`image`。连通域可配置 alpha 阈值、组件大小、主体占比和布局行列；`split_widest` 可处理相连主体的特殊切分。手动区域为 `[left, top, right, bottom]` 数组，右下边界不包含在切片中。

处理 `mode` 支持 `anchor`、`contain`、`copy`。`scale`、`fit_height`、`max_scale` 决定共享缩放；`offset`、`clamp_y`、`padding` 和 `overflow` 决定放置及越界策略；`overrides.<sprite_id>` 为单帧覆盖。单帧 `scale` 覆盖整组最终缩放。

展示播放通过 `animation.order` 引用动作最终帧索引，可重复；`durations_ms` 与每个播放步骤一一对应，或使用统一 `fps` / `duration_ms`；`loop` 为 0 表示无限循环。

## 阶段边界

`extract` 扫描全部原图，不依赖动作引用；`process` 处理全部切片，不改变动作最终帧；`select` 从 processed 按配置复制和编号；`pack` 读取最终帧，保留对最终帧的人工修图。默认命令是 pack，build 才重建整个流水线。

网页直接在内存中切图与预览，明确应用后写入 processed。网页导出只在临时目录产生编号帧及图集，不要求持久化 select 阶段；CLI 仍维持原来的阶段约定。
