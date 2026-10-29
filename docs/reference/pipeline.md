# 配置与流水线阶段（共享参考）

描述当前数据和处理边界。网页步骤见 [用户指南](../users/workbench.md)，CLI 参数见 [工程操作](project-operations.md)。美术质量要求由 [Agent 流程](../agents/artwork-workflow.md) 定义，不是本配置自动执行的检查。

## 共享配置

`pipeline.json` 使用 version 2，是人、网页与 Agent 共用的输入；所有相对路径以它为基准。当前仍采用单工程配置文件，尚未实现资源 `.meta` 或多文件原子保存。

新工程位于 workspaces，source 与 processed 在工程内部。project.name 是可修改展示名，文件夹名是工程 ID，character 用于交付文件命名。paths.manifest 可配置清单位置，新工程默认 exports/manifest.json，清单内图集与预览路径相对于清单目录；旧工程未配置时保持原有约定。

| 字段 | 职责 |
| --- | --- |
| `frame_size` | 固定 RGBA 画布 `[width, height]` |
| `anchor` | 归一化 x/y 与画布中的 pixels 锚点 |
| `defaults.extract` / `sources.<filename>.extract` | 通用与单原图切割规则、稳定区域身份 |
| `defaults.process` / `sources.<filename>.process` | 通用与单原图处理规则、单帧覆盖 |
| `actions.<id>.slots` | 单帧 / 动作 / 序列的有序资源引用 |
| `actions.<id>.sprites` | 旧动作平铺 processed PNG 引用，继续兼容 |
| `actions.<id>.fps` / `loop` | 游戏播放的默认 FPS 与顶层循环 |
| `actions.<id>.animation` | 展示播放覆盖：顺序、逐步时长、循环 |
| `actions.<id>.pack.columns` | 图集列数 |
| `workbench.reviews` | 衔接序列资源，支持 slots；旧 clips 继续适配 |

动作和序列共用解析规则，CLI 的 QA、编排比较与导出也读取它们；并非仅网页使用。结构、范围、时长继承与兼容见 [资源组合](resources.md)。

## 切割与处理

切割 method 支持 components、grid、boxes、image。连通域参数控制 alpha 阈值、组件大小、主体占比与布局；split_widest 支持特殊相连主体切分。手动 boxes 使用 `[left, top, right, bottom]`，右下不包含。

boxes 与 region_ids 一一对应；identities 记录区域来源，next_id 分配新 ID。移动、缩放、重新排序保留身份，新增区域不复用已删除编号。自动识别会尝试匹配既有区域，存在歧义时仍需人工核对。

处理 mode 支持 anchor、contain、copy。scale、fit_height、max_scale 决定整组缩放；offset、clamp_y、padding、overflow 控制放置与越界。overrides.<sprite_id> 提供单帧覆盖；单帧 scale 是绝对覆盖而非乘数，留空继承整组。

fit_height 按单张原图最高的完整轮廓计算共享倍率，不能保证跨原图身体同尺度；轮廓锚点也不等于脚底或身体中心。

## 阶段和写入边界

| 入口 / 阶段 | 输入与结果 | 保存边界 |
| --- | --- | --- |
| extract | 原图 → 原尺寸切片 | 批量构建切片，不改动作顺序 |
| save-slices | 当前原图切割 → 稳定切片库存 | 独立保存当前 extract 与身份，不应用 processed |
| process | 已保存的有效切片 → processed | 批量阶段要求有效切片；覆盖所选原图结果 |
| 网页 preview | 草稿切割 / 切片 → 内存处理预览 | 不暗中保存配置或正式 PNG |
| apply | 当前原图 → processed | 可复用有效切片，只写像素变化的 PNG，并保存配置 |
| select | 展开的 processed 引用 → 有序交付帧 | 跨原图、重复和实际时长保留 |
| pack / preview | 有序交付帧 → 图集、元数据、动画 | pack 读取最终帧，可从既有修图继续 |

分阶段 extract/process 不回写配置；默认构建命令是 pack，build 才重建全部阶段。网页导出在临时目录组装，不要求磁盘长期保留 select 产物。管理 CLI 的 apply/prepare 与网页共用应用操作、版本与引用保护，是日常协作入口。

只改一帧处理覆盖时，缓存只使该帧的处理与预览编码失效；原图、切割、画布、整组规则或共享缩放变化可使多帧失效。预览复用切片与处理结果，缓存无效时在内存重建；保存切割才更新切片缓存。

保存工程只写配置，应用才写正式图片。导出使用当前所选编排与已应用图片；未应用的缩放草稿不能当成已交付素材。
