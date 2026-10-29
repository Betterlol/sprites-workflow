# 文档目录

文档按读者分区。用户指南讲操作，Agent 规范讲受托执行时的约束，共享参考讲数据和接口，开发文档讲代码职责。它们描述当前实现；历史资料单独保留。

| 读者 | 从这里开始 | 职责 |
| --- | --- | --- |
| 网页用户 | [网页工作台](users/workbench.md) | 建工程、切割、调整、组合与导出 |
| Agent | [任务入口](agents/README.md)；根目录 [AGENTS.md](../AGENTS.md) | 按任务选读、保护共享成果、记录来源和实际验收 |
| 用户与 Agent | [工程布局](reference/project-layout.md)、[工程操作与 CLI](reference/project-operations.md) | 使用同一份工程、版本与操作接口 |
| 用户、Agent 与开发者 | [配置与阶段](reference/pipeline.md)、[资源组合与播放](reference/resources.md) | 字段含义、保存边界、引用和时长规则 |
| 开发者与开发 Agent | [开发与维护](development/contributing.md)、[代码架构](development/architecture.md) | 修改代码、验证和维护文档 |
| 查阅设计过程 | [历史资料](history/README.md) | 查旧截图、概念图、设计与实施记录 |

## 哪一份说明负责什么

| 内容 | 唯一维护位置 | 使用原则 |
| --- | --- | --- |
| 启动与项目概览 | 根目录 [README](../README.md) | 保持简短，细节链接到对应分区 |
| 网页操作与按钮位置 | users/workbench.md | 随界面更新，不混入历史测试报告 |
| Agent 任务路由和硬性边界 | 根目录 AGENTS.md | 自动发现入口；详细制作步骤链接到 agents |
| 美术制作、参考与视觉完成门槛 | agents/artwork-workflow.md | 是执行规范，不表示工具自动完成这些检查 |
| 工程文件与 CLI 接口 | reference/project-layout.md、project-operations.md | 人与 Agent 共用，不重复列美术流程 |
| 配置和播放语义 | reference/pipeline.md、resources.md | 按当前实现说明，兼容与未实现项明确标出 |
| 代码依赖和验证方式 | development/ | 不把代码测试通过写成美术验收通过 |
| 某个角色的来源、基准、取舍、验收 | 该工程 README.md | 与实际配置、素材版本对应，不复制进通用文档 |
| 历史结果 | history/、superpowers/、designs/ | 保留当时证据；不能当作当前功能或测试结果 |

`pipeline.json` 是当前共享配置输入，不是可随意覆盖的生成文件；当前尚未实现多文件 `.meta`。工程实际状态以当前磁盘文件及 `projects.py status` 为准。发现文档与实现不符时先核对并记录差异，不通过改动用户素材来使文档成立。

文档统一使用本目录列出的正式路径，不再保留旧路径的迁移页。
