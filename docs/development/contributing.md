# 开发与文档维护

面向人类开发者和开发 Agent。项目运行于 Python 3.10+；本地服务由 tools/serve_sprites.py 启动，前端为原生 ES modules 与 Canvas，不需要前端构建。安装启动见 [首页](../../README.md)，代码分层见 [架构](architecture.md)。

## 修改范围

开发测试使用临时工程和合成图像，不修改现有 assets 或用户工作区素材。保留共享配置、素材版本、稳定帧 ID、资源槽位 ID、锁与历史事务；操作失败不能留下部分更新。兼容入口不承载新增领域逻辑。

用户明确指定的测试和修改范围优先。用户自行体验网页时，不自行运行浏览器或替其作视觉验收；报告未运行项即可。若本次授权自动化检查，按改动范围执行适当检查。

## 代码验证

根 AGENTS 规定的常规代码检查：

```powershell
python -m unittest discover -s tests -v
node tests/test_workbench_model.mjs
node tests/test_workbench_session.mjs
```

Python 架构和格式检查：

```powershell
python tools/check_sprite_architecture.py
python -m ruff check .
python -m ruff format --check .
```

Ruff 是可选开发工具，不是运行依赖；检查范围由 pyproject.toml 指定。注解解析检查不等于完整静态类型检查。

仅在用户授权浏览器测试时使用 `python tests/browser_refactor_smoke.py`；需要 Playwright 和 Chromium。该脚本使用临时工程、合成图片和独立端口，退出关闭自己的服务，不操作已有素材。切割专用脚本为 `tests/browser_slicing_smoke.py`。浏览器检查不代表美术视觉验收。

不能将历史测试结果写成当前结果；交付时说明执行的命令、结果与未执行项。动画导出成功只验证对应产物，不证明角色一致或动作流畅。

## 文档维护

[文档目录](../README.md) 定义各主题的维护位置。修改界面时更新 users，修改配置或 CLI 时更新 reference，修改代码职责时更新 development，修改 Agent 工作规则时更新 AGENTS 或 agents。只链接需要的其他主题，避免重复维护同一套接口说明。

历史设计、计划、截图和交付报告保留当时语境，归入 history 或由该区索引。未来方案要写明未实现；不能让历史页面成为 README 的默认使用入口。

文档移动后检查相对链接、图片和旧入口。纯文档任务只需静态核对链接、Markdown 格式与 diff 范围，不运行软件测试、网页测试或素材流水线；不得修改 artwork 或 pipeline.json。
