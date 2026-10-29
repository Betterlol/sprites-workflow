# Sprite Workbench development

## 按任务选读

- 制作、扩展或修复动画：读 [制作流程](docs/agents/artwork-workflow.md)、目标工程 README 和 pipeline.json，再执行 `python tools/projects.py status <工程ID>`。目录规则见 [workspaces/README.md](workspaces/README.md)。
- 修改代码：读 [开发指南](docs/agents/development.md) 与 [架构](docs/development/architecture.md)。
- 仅改文档：按 [文档目录](docs/README.md) 更新链接与说明，不操作素材或 pipeline.json，不重处理或运行功能测试。
- CLI 参数、数据格式和可选技巧按需查阅，不要求逐项通读。历史方案不是当前规范。

## 共同边界

- 工程操作使用 `tools/projects.py`，保留配置 / 素材版本检查、进程锁和网页草稿保护；不覆盖他人修改。导入使用重复 --file，删除使用重复 --ref，保留动作和序列的引用保护。
- 不擅自迁移、删除、重建或整理现有 assets 和无关工程。测试使用临时工程与合成图片。
- 遵守用户本次范围和测试要求，沿用已有批准与授权。用户自行测试网页时不启动浏览器测试。未检查的结果如实列为待验收。
- 美术制作的必需规则集中在制作流程；技巧按需选用。不要求固定模板、逐步截图或重复记录已有信息。

## 代码验证

用户未限制测试时执行 `python -m unittest discover -s tests -v`、`node tests/test_workbench_model.mjs`、`node tests/test_workbench_session.mjs`。纯文档修改只检查链接和 diff。其他开发检查见 [维护指南](docs/development/contributing.md)。

启动网页使用 `python tools/serve_sprites.py`，无需前端构建。
