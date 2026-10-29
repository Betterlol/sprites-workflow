# Agent 任务入口

此目录面向受托操作本项目的 Agent。先读根目录 [AGENTS.md](../../AGENTS.md)，再按任务选读；不要把所有任务都当成美术制作，也不要把网页使用指南当作 Agent 的验收规范。

| 当前任务 | 必读 | 交付边界 |
| --- | --- | --- |
| 新建、扩展、修复角色动画 | [美术流程](artwork-workflow.md)、[工作目录](work-directory.md)、工作区与目标工程 README、pipeline.json | 来源与精确基准、实际运行边界、编排核对和视觉验收记录；没检查的明确待验收 |
| 代码开发与重构 | [开发 Agent 指南](development.md)、[开发维护](../development/contributing.md)、[架构](../development/architecture.md) | 代码变更、兼容边界与已执行的验证；不自动改现有工程 |
| 文档整理 | [开发 Agent 指南](development.md)、[文档职责](../README.md) | 当前说明与历史证据分开；不改素材、配置或重处理 |
| 只读检查或导出核对 | [CLI 参考](../reference/project-operations.md)、目标工程记录 | 只读结果与检查版本；不能据数据报告宣称美术通过 |
| 提供制作任务或生成提示词 | [任务模板](prompt-sample.md) 与美术流程 | 必须提供真实参考图片，模板不替代已确认来源 |

共享的数据契约见 [配置与阶段](../reference/pipeline.md)、[资源组合](../reference/resources.md)。需要了解用户看到的按钮位置时再查 [网页指南](../users/workbench.md)。

遵守本次用户明确指定的操作和测试范围。已有批准和授权可以沿用；用户负责网页测试时不自行启动浏览器验收。无法执行的验收如实标记待办，不能省略后宣称通过。
