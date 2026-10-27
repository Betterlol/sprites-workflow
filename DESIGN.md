# Sprite Workbench 设计

## 制作规范与实现边界

Agent 必须先读 [AGENTS.md](AGENTS.md)、[工作区说明](workspaces/README.md)、[Agent Sprite 制作与验收流程](docs/agent-sprite-workflow.md)，以及目标工程的 `README.md` 和 `pipeline.json`。该流程是 IDLE 基准、子动作边界、过渡生成和完整动作验收的统一规范；工程说明记录本角色的精确参考与制作取舍。

制作顺序为：确认 IDLE 基准 → 规划子动作和实际运行时边界 → 以参考图片约束整张 spritesheet → 导入确认采用的原画 → 切图和处理 → 子动作与接缝 Review → 完整动作编排核对及视觉验收 → 导出核对。

- IDLE 约束形象、比例、配色和本体尺度；边界参考约束姿态、表情、运动趋势和道具状态。生成必须实际提供图片，不能只写路径。IDLE 形象基准与动作实际离开 / 返回的 IDLE 槽位分别记录。
- 直接共享边界只播放一次，明确完整动作采用的子动作范围；无法直接衔接时，以前段实际末帧和后段实际入口帧生成整张过渡 sheet，采用核对后的中间帧，保留原始端点。单帧生成限于具体坏帧修复。
- 子动作独立可玩，完整动作复用其 processed 引用。完整编排与 Review 的顺序、边界、重复和时长必须一致；修改子动作不会自动同步完整动作。
- 正常运行速度、慢放和逐帧检查均为必需。端点姿态相似不能证明运动连续；需检查尺度、接地点、方向与速度、表情和道具状态。素材、处理或播放参数变化会使相关验收结论失效。

这些是 Agent 必须执行的制作和验收规则。目前的工具提供处理、引用保护和 Review 播放能力，不自动运行图像生成、不自动绑定正式 IDLE 参考、不自动组装完整动作，也不自动判定动作自然度。制作记录保存在工程 README 或其链接的正式参考记录中，不引入新的配置字段。文档任务不触发素材或动作配置变更。

## 本地网页工作台

工程管理统一以 `workspaces/<目录名>/pipeline.json` 为入口，默认先展示工程列表，支持创建空工程、切换和显式 `--config` 打开旧布局。网页请求始终携带工程 ID，没有服务端全局当前工程。网页与 `tools/projects.py` 使用共享领域操作、配置与素材版本检查和跨进程锁。现有 `assets/` 不自动迁移。

`tools/serve_sprites.py` 启动同源的本地 FastAPI 服务与浏览器界面。前端使用原生 ES modules 和 Canvas 2D，无前端构建依赖。分阶段 CLI 继续保留；Agent 常规操作优先使用 `tools/projects.py`，避免绕过共享保护。

网页工作流为：原图 → 切割预览 / 区域直接编辑 → 独立保存切割与原尺寸切片 → 参数预览并明确应用到 processed → 动作引用与 Review 编排 → 按需导出。

- `pipeline.json` 由人、Agent、CLI 共用，网页只在显式提交时回写，以文件摘要检测外部修改并保护未保存草稿。
- 动作保存 `actions.*.sprites` 引用，不持久化复制另一套最终帧。运行时顺序 / FPS 与 `animation` 展示顺序 / 逐步时长独立；视觉验收以运行时参数为准。
- Review 保存在 `workbench.reviews`，引用动作、片段范围和有界重复次数，不继承动作的无限循环。Review 播放和配置合法不等于已经完成视觉检查。
- “Idle 参考”叠图读取 `actions.idle.sprites[0]`；Agent 另行核对它与正式参考的关系。
- 预览与 CLI 共用切图、处理函数。`fit_height` 按每张原图完整轮廓确定共享倍率，跨原图本体尺度和接地点由制作流程复核。
- 自动识别匹配区域旧 ID；手动编辑用 `region_ids` 绑定 `boxes`，保留 ID 并使用 `next_id` 分配新 ID；若应用会移除仍被动作引用的素材，则失败且保留原结果。
- 导出复用打包器，仅在临时目录生成网页交付文件。已有最终帧可迁移到 `processed_sprites/_approved/` 保留手工修图，`imports/` 兼容已有外部帧；两者不作为新原画的常规入口。

## 数据阶段

| 阶段 | 输入与输出 | 职责 |
| --- | --- | --- |
| 原画采纳 | `_work/<task>/` → `source/` | 只导入确认采用的整张 sheet 或具体单帧修复原图；正式 IDLE 和用户参考放 `references/` |
| extract | `source/` → `source_sprites/` | 保留原尺寸切片；网页独立保存可复用缓存，以原图/规则指纹和切片校验和验证有效性 |
| process | 切片 → `processed_sprites/` | 按共享函数缩放、定位，检查本体尺度与锚点；通过 apply 明确写入 |
| select | processed 引用 → 有序动作帧 | 配置选择、排序、重复和复用；CLI 写入 `exports/frames/`，网页导出临时生成 |
| pack / preview | 动作帧 → 图集、元数据和 WebP | CLI 默认写入工程 `exports/`；网页按需下载 ZIP |

操作、保存和协作接口见 [工作台说明](docs/workbench.md)，配置格式和阶段边界见 [流水线说明](docs/sprite-workflow.md)，启动和常用命令见 [README](README.md)。
