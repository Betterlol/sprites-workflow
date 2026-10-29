# Python 包与职责

本轮保持 `pipeline.json` v2、网页 API、命令行参数和素材目录不变。Python 内部按职责分包，现有顶层模块仅保留兼容导入；新代码使用子包中的正式路径。

| 包 | 职责 | 允许依赖 |
| --- | --- | --- |
| `domain` | 数值校验、稳定区域 ID、动作与 Review 播放规则、结构化输入输出契约 | 自身与标准库 |
| `imaging` | 原始图像切割、缩放与锚点定位、内存编码 | domain、自身、图像库 |
| `storage` | 配置与素材读写、切片库存、锁、历史恢复、内存缓存、图集元数据 | domain、自身、必要的图像 IO |
| `application` | 工程查询、编辑、素材操作、渲染协调、导出、任务、QA | domain、imaging、storage、自身 |
| `interfaces` | HTTP 和两个 CLI 的参数转换、请求路由、错误与输出呈现 | 上述各包 |

`tools/check_sprite_architecture.py` 检查反向依赖、运行时导入循环，以及业务代码对兼容模块和独立工具脚本的依赖。类型注解专用的导入不算运行时循环。

## 工程操作

`application.project.Project` 是网页、`tools/projects.py` 和后台任务共用的入口，通过组合把工作交给：

- `session.ProjectSession`：工程生命周期、锁、版本检查、草稿约束和渲染器。
- `queries.project_state`：素材清单、尺寸与边界缓存、工程快照；只依赖 `QueryContext` 契约。
- `editing.EditingOperations`：保存草稿、独立保存切割、增量预览、应用调整、准备缺失素材。
- `assets.AssetOperations`：导入、删除和显式旧素材迁移。
- `exporting.ExportOperations`：临时目录中的只读导出、进度及取消。

每个写操作仍持有同一把工程锁，并在原有位置复核配置和素材版本。文件写入与配置保存仍处在同一历史事务内；没有将它们拆成独立提交。历史回滚、外部修改冲突、删除引用保护和取消行为由临时工程测试覆盖。旧 `--config` 工程的外部目录兼容策略保持不变。

`application.presentation` 保留原有快照 URL 与预览 data URL 表示，供现有 HTTP 和 CLI 输出共用；它不参与领域规则或图像处理。未来更换展示协议时从这个边界调整。

## 渲染与增量更新

`RenderService.render(config, source, stage)` 返回 `RenderResult`，明确包含配置、原始切片、处理帧、区域描述、组缩放和逐帧版本。调用者无需再读取 `Project._render_versions` 一类临时状态。会话持有渲染器，并负责通过工程锁串行调用。

`imaging.processing.process_frames` 只接收画布、处理参数和内存图像，返回 `ProcessResult`。缓存通过 `Cache` 协议传入，不依赖磁盘、网页或工程管理器。图像和缓存结果按只读值使用；调用者需要修改像素时先复制图像。

缓存分为解码原片、草稿切割、处理图像和预览编码，均有容量限制。版本仍包含原片像素、画布、锚点、有效单帧参数和解析后的组缩放。单帧覆盖只改变对应的渲染版本；全局画布、组设置或 `fit_height` 依赖变化可以使多帧失效。应用结果比较实际像素，只写变化的 PNG，保留其他图片的字节和修改时间。

`application.stages` 保留旧批量流水线的明确阶段：批量 `process` 要求已保存且有效的切片，网页预览允许使用尚未保存的切割草稿。两者共用切割算法、处理算法和切片存储，没有强行改变两种入口的保存语义。

动作、Review、QA 和导出检查统一使用 `domain.actions`；原有前端模型继续通过 Node 检查验证重复引用、跨原图顺序和 runtime/display 时长。

## 配置重构的后续边界

`storage.configuration.ConfigRepository` 集中管理工程配置快照、精确字节版本和原子保存；事务与冲突策略属于应用操作，不藏在配置适配器里。

现有 `Config` 仍是 v2 配置的兼容视图，保留路径解析、默认值合并及素材发现。它位于 storage，不传入纯图像处理层。此轮没有把所有配置字典转换成新的对象模型，也没有实现多文件事务或 `.meta`。动作和序列现已增加统一的资源槽位，详见 [资源组合](resource-composition.md)；旧 `sprites` / `clips` 在读取时适配。

下一轮可以在这里定义 source/action/frame 元数据模型、继承规则及配置仓库接口，然后增加拆分文件适配器。需要同步设计跨文件版本、原子提交、历史恢复和旧格式迁移；不能简单把一个 JSON 写入替换成多次独立写入。

## 验证与维护

```powershell
python -m unittest discover -s tests -v
node tests/test_workbench_model.mjs
node tests/test_workbench_session.mjs
python tools/check_sprite_architecture.py
python -m ruff check .
python -m ruff format --check .
```

Ruff 是可选开发工具，不是运行依赖；`pyproject.toml` 将检查范围限定在此次整理的 Python 包与新增检查文件。注解解析测试检查公开类型能否解析，不代替完整静态类型检查。

获准进行浏览器测试时可运行 `python tests/browser_refactor_smoke.py`，需要 Playwright 与 Chromium。该脚本使用系统临时目录、合成图像和独立端口，并在结束时关闭自己的服务，不读取或修改现有工程素材。它验证页面装载、切割保存、重复及跨原图动作、单帧响应增量、选择性 PNG 写入、展示时长和刷新恢复；不代表美术动作质量验收。
