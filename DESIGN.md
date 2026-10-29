# Sprite Workbench 设计入口

面向需要理解产品和技术边界的用户、Agent 与开发者。详细职责分别维护在对应文档中，本页只保留总体关系。

网页以人的创作流程为主：共享工作目录 → 原图切割与独立保存 → 单帧 / 整组预览并显式应用 → 资源槽位组合 → 按需导出。动作与序列都能复用单帧或其他组合，日常编辑按游戏时序，展示设置位于导出面板。

网页和 projects.py 共用应用操作、配置与素材版本、工程锁、引用保护和历史事务。分阶段 CLI 保留独立构建能力；它不替代美术采纳与视觉验收。pipeline.json v2 仍是共享输入，尚未实现 .meta 拆分。

| 主题 | 当前说明 |
| --- | --- |
| 网页与保存语义 | [用户指南](docs/users/workbench.md) |
| 文件、缓存与备份 | [工程目录](docs/reference/project-layout.md) |
| 处理阶段与配置 | [配置参考](docs/reference/pipeline.md) |
| 组合、继承时长与来源 | [资源规则](docs/reference/resources.md) |
| 包职责、增量渲染与配置仓库 | [代码架构](docs/development/architecture.md) |
| Agent 制作和视觉完成门槛 | [制作流程](docs/agents/artwork-workflow.md) |
| 旧方案、截图与概念图 | [历史资料](docs/history/README.md) |

全部入口与维护职责见 [文档目录](docs/README.md)。
