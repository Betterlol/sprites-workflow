## Agent 生成 spritesheets 的工作流搭建

### 本地网页工作台

工程管理统一以 `workspaces/<目录名>/pipeline.json` 为入口，默认先展示工程列表，支持创建空工程、切换和显式 `--config` 打开旧布局。网页请求始终携带工程 ID，没有服务端全局当前工程。工程创建和操作通过共享领域逻辑供网页与 `tools/projects.py` 使用；配置版本和素材版本分别检测，网页与 CLI 共用跨进程锁。现有 `assets/` 不自动迁移。

现有 CLI 继续保留，新增 `tools/serve_sprites.py` 启动同源的本地 FastAPI 服务与浏览器界面。前端使用原生 ES modules 和 Canvas 2D，无前端构建依赖。

网页工作流为：原图 → 内存切图 / 参数预览 → 明确应用到 processed → 动作引用与 Review 编排 → 按需导出。

- `pipeline.json` 仍是可由人、Agent、CLI 共同使用的工程配置。网页只在显式保存、应用、导入或迁移时回写；使用文件摘要检测其他窗口或命令行的修改。
- 动作复用 `actions.*.sprites`，不会持久化复制一套最终帧。游戏顺序 / FPS 与 `animation` 展示顺序 / 逐步时长独立。
- Review 保存在 `workbench.reviews`，引用动作、片段范围和重复次数；片段重复显式有界，不继承动作的无限循环。
- 预览与 CLI 共用切图和处理函数；导出复用原有打包器，但仅在临时目录生成文件。
- 已有最终帧可以迁移到 `processed_sprites/_approved/` 并更新引用，保留手工修图。`imports/` 保存外部导入的单帧。
- 自动匹配切图区域的旧 ID；新增区域分配新 ID。若切图移除仍被引用的素材，应用失败且不改动原结果。

操作和接口说明见 [工作台说明](docs/workbench.md)。

已实现的阶段划分、目录映射、配置格式和使用命令见 [Sprites 资源流水线](docs/sprite-workflow.md)。

1. source/ -> source_sprites/
> 将 sprites 从 source 切出来，统一脚本，尽量不做缩放/移位等操作。
2. source_sprites/ -> porcessed_sprites/ -> sprites/
> 对 sprites 进行缩放/移位等操作，处理并确认无误后，放置到 processed_sprites/。
3. porcessed_sprites/ -> sprites/
> 选择性组合式地将 processed_sprites/ 中的 sprites 拼凑出单一 action 的 sprites，放置到 sprites/。
3. sprites/ -> spritesheets/ & webp/
> 将 sprites 进行打包，生成 spritesheets/ 和 webp/，spritesheets/ 用于游戏运行，webp/ 用于网页展示。
