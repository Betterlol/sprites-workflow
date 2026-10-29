# 工程工作区

面向用户和 Agent。每个直接子目录以 `pipeline.json` 标识一份独立工程；工程列表扫描磁盘，不需要额外注册表。工程自己的 README 记录角色基准、来源、制作取舍和实际验收结果。

- [工程目录、备份与协作](../docs/reference/project-layout.md)：各类文件放在哪里、哪些可重建、如何保护共享草稿。
- [工程操作与 CLI](../docs/reference/project-operations.md)：创建、检查、导入、保存、独立切割、处理、导出与 QA。
- [网页操作](../docs/users/workbench.md)：人通过工作台工作的流程。
- [Agent 制作与验收](../docs/agents/artwork-workflow.md)：操作美术素材前必读，同时读取目标工程 README、pipeline.json 并执行 `tools/projects.py status <工程ID>`。

文档任务不得修改素材或 pipeline.json，也不触发重处理。现有 `assets/` 不自动迁移；旧布局可以通过 `serve_sprites.py --config <路径>` 显式打开。完整文档入口见 [文档目录](../docs/README.md)。
