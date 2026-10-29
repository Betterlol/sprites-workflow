# Sprite Workbench

本地 Sprite 创作工作台：导入人设与原画，切割、微调单帧，将单帧、动作和衔接序列自由组合，再导出游戏资源和展示动画。以人操作网页为主，Agent 通过共享工程与 CLI 协作。

## 启动

需要 Python 3.10+，在仓库根目录执行：

```powershell
python -m pip install -r tools/requirements-workbench.txt
python tools/serve_sprites.py
```

默认打开 [本机工程列表](http://127.0.0.1:8765)。创建或打开工程后，左侧固定的“工作目录”统一显示参考图、原图、动作、衔接序列和单帧资源，右侧完成当前工作。顶部 **My Projects / 工程名** 可返回工程列表。前端不需要 npm 或构建步骤。

```powershell
python tools/serve_sprites.py --workspace-root workspaces --port 8766 --no-browser
# 显式打开已有旧布局，不自动迁移
python tools/serve_sprites.py --config <已有pipeline.json路径>
```

工程和素材保存在本机。现有 `assets/` 不自动搬迁、清理或重建。

## 使用与协作

- 网页用户：[操作指南](docs/users/workbench.md)，包括切割、单帧调整、组合、保存与导出。
- Agent：[任务入口](docs/agents/README.md) 与 [AGENTS.md](AGENTS.md)。美术任务先读制作与验收流程；代码、文档任务不触发素材制作。
- 共享工程：[目录与协作](docs/reference/project-layout.md)、[CLI 操作](docs/reference/project-operations.md)、[配置与阶段](docs/reference/pipeline.md)、[资源组合](docs/reference/resources.md)。
- 开发维护：[开发指南](docs/development/contributing.md)、[代码架构](docs/development/architecture.md)。
- 全部文档：[文档目录](docs/README.md)。旧截图、概念图与历史方案见 [历史资料](docs/history/README.md)。

“保存工程”保存配置；“保存当前切割”独立保存切割与可复用切片；“应用调整并保存工程”才将处理结果写入正式图片。动作调整按实际游戏顺序和时长预览，展示播放参数在导出设置中配置。

工程配置、source、processed、references 和工程说明应一起保留或备份。参考图不参与切割；缓存与导出不是唯一原始成果。共享配置和素材均受版本冲突保护，详见上述共享参考。
