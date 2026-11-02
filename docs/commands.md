# 功能与操作命令

以下命令均从仓库根目录执行。示例中的 `demo` 是工程目录名，`walk.png`、`walk` 和 `transition` 分别代表已有原图、动作和 Review；使用时替换为实际名称。安装方式见 [README](../README.md)。

## 网页工作台

| 功能 | 支持的操作 |
| --- | --- |
| 工程与素材 | 新建、打开工程，设置画布与锚点，导入原图、正式单帧和参考图，搜索、多选与删除素材 |
| 切割 | 自动识别、网格切割、手动区域编辑，预览并单独保存切割结果 |
| 调整 | 缩放、横向缩放、位置与逐帧覆盖，使用参考图、辅助线和前帧叠图检查对齐 |
| 编排与播放 | 组合单帧、动作与序列，排序、重复、调节时长与速度，用 Review 检查片段衔接 |
| 保存与恢复 | 保存配置草稿、应用图像调整、准备缺失素材，查看版本记录并恢复；检测外部修改并提供草稿合并 |
| 导出 | PNG 帧、PNG 图集与 TexturePacker JSON、WebP、GIF、Review 动画及完整工程 ZIP；支持动作选择、进度与取消 |

## 启动命令

```powershell
python main.py
python main.py --port 9000 --no-browser
python main.py --workspace-root "D:/SpriteProjects"
python main.py --config "D:/OldProject/pipeline.json"
```

| 参数 | 含义 |
| --- | --- |
| `--port` | 本地服务端口，默认 `8765` |
| `--no-browser` | 启动服务但不自动打开浏览器 |
| `--workspace-root` | 工程根目录，默认是本仓库的 `workspaces/` |
| `--config` | 直接打开指定配置文件，支持旧工程布局 |

服务监听 `127.0.0.1`；在终端按 `Ctrl+C` 停止。

## 工程命令

入口为 `python src/projects.py`，与网页共用工程操作。默认管理本仓库 `workspaces/` 下的工程；全局参数放在子命令之前：

```powershell
python src/projects.py --workspace-root "D:/SpriteProjects" --json list
```

结果为 JSON，`--json` 使其紧凑输出。成功返回码为 `0`，操作失败或检查不通过返回 `1`；命令参数错误返回 `2`。

| 命令及示例参数 | 简要介绍 |
| --- | --- |
| `create "示例角色" --id demo --width 640 --height 640` | 新建独立工程；省略 `--id` 时使用工程名称作为目录名。锚点由 `--anchor-x`、`--anchor-y` 设置，默认 `0.5`、`0.9` |
| `list` | 列出工程及基本信息 |
| `status demo` | 查看配置、素材、版本标识和警告 |
| `validate demo` | 校验配置与资源引用；存在警告时也返回不通过 |
| `import demo --kind source --file "walk.png"` | 导入素材；`--kind` 为 `source`、`processed` 或 `reference`，重复 `--file` 可批量导入 |
| `delete demo --kind processed --ref "walk/000.png"` | 删除素材；重复 `--ref` 可批量删除，仍在使用的资源受引用保护 |
| `save demo --data "draft.json" --revision REVISION` | 保存整份配置草稿，不重新处理图片；`REVISION` 使用 `status` 返回的 `revision` |
| `save-slices demo --source "walk.png"` | 保存指定原图的切割规则与原始切片；可用 `--extract "extract.json"` 提供规则，不更新正式单帧 |
| `apply demo --source "walk.png"` | 按已保存规则处理指定原图，更新正式单帧并保存配置 |
| `prepare demo` | 补齐缺失的处理素材，保留已有正式单帧 |
| `export demo --format all --output "demo-all.zip"` | 导出 ZIP；默认格式为 `project`，格式与筛选参数见下文 |
| `qa demo --action walk --output "qa-walk"` | 生成联系表、WebP、GIF 和播放报告；只读取工程素材，输出到新目录 |
| `history demo` | 列出可恢复的图片操作记录 |
| `restore demo VERSION` | 恢复 `history` 返回的版本；恢复前检查文件是否又被修改 |
| `check-composition demo --action walk --review transition` | 比较动作与 Review 的运行时帧顺序、时长和边界；也可用 `--sequence "sequence.json"` 代替 Review |
| `check-export demo --archive "demo-all.zip"` | 检查资源 ZIP 与当前正式单帧是否一致；可用 `--format`、重复 `--action` 指定预期内容 |

例如，表中 `status demo` 的完整命令是 `python src/projects.py status demo`。

`apply`、`save-slices`、`prepare`、`import`、`delete` 和 `restore` 可传入 `--revision` 与 `--asset-revision`，校验先前读取的配置和素材版本。批量导入结果会分别列出成功、失败与跳过的文件。

### 导出与检查参数

`export --format` 支持：

| 格式 | ZIP 内容 |
| --- | --- |
| `project` | 配置、原图、正式单帧、参考资料及工程 README，用于工程备份 |
| `frames` | 动作 PNG 帧序列 |
| `atlas` | PNG 图集与 TexturePacker JSON |
| `webp` / `gif` | 展示动画 |
| `all` | 帧序列、图集、WebP 与 GIF |

资源导出可重复 `--action` 选择动作，再用重复 `--exclude-action` 排除；工程备份不支持排除动作。输出必须是新 ZIP 文件。网页另支持当前 Review 的动画导出，CLI 的 `export --format` 不包含 `review`。

`qa` 的输入四选一：`--action`、`--review`、重复 `--ref` 或 `--sequence`。检查动作时可用 `--mode runtime`（默认）或 `--mode display`；Review 使用自身保存的模式。`--output` 必须是尚不存在的目录。

`qa` 与 `check-composition` 的 `--sequence` 接收显式播放序列，例如：

```json
{"steps": [{"ref": "walk/000.png", "duration_ms": 100}, {"ref": "walk/001.png", "duration_ms": 100}], "loop": 1}
```

`ref` 相对于 `processed_sprites/`，`duration_ms` 为每步毫秒数，`loop: 0` 表示无限循环。该文件是命令输入，与工程中可复用的序列资源区分。

## 分阶段处理命令

入口为 `python src/build_sprites.py`，通过 `--config` 指定工程。它会向配置指定的阶段目录写入结果，与临时生成 ZIP 的工程导出用途不同。

```powershell
python src/build_sprites.py pack --config "workspaces/demo/pipeline.json"
```

| 阶段 | 简要介绍 |
| --- | --- |
| `extract` | 从原图生成保留原始尺寸的切片 |
| `process` | 从已提取且有效的切片生成统一画布的正式单帧；切片缺失或过期时需先执行 `extract` |
| `select` | 按动作编排将正式单帧复制为最终帧序列 |
| `pack` | 打包已有最终帧，写入图集、元数据与清单，默认同时生成 WebP |
| `preview` | 从已有最终帧生成展示 WebP |
| `build` | 依次执行 `extract → process → select → pack` |

省略阶段时默认执行 `pack`。`extract`、`process` 可在尚未配置动作时使用，其余阶段需要有效动作。

| 参数 | 适用范围 |
| --- | --- |
| `--source "walk.png"` | 只处理指定原图，可重复；仅用于 `extract`、`process` |
| `--action walk`、`--exclude-action idle` | 动作选择后再排除，均可重复；用于 `select`、`pack`、`preview`、`build` |
| `--output-root "output/demo"` | 将阶段结果写入另一目录，原图路径仍按原配置解析 |
| `--no-preview` | `pack`、`build` 跳过 WebP 生成 |

`build` 始终准备全部原图，动作筛选只影响后续阶段。`pack`、`preview` 使用已有最终帧；修改处理或编排后，需先执行对应阶段才能反映到这些输出。

`python src/build_dafeiyu_sprites.py` 使用同一套阶段与参数，仅把默认配置设为 `workspaces/dafeiyu/pipeline.json`。

## 开发检查入口

| 命令 | 用途 |
| --- | --- |
| `python src/check_sprite_architecture.py` | 检查 Python 包的依赖方向与运行时导入循环 |
| `python -m unittest discover -s tests -v` | 运行 Python 自动化测试 |
| `node tests/test_workbench_model.mjs` | 检查前端资源、播放、切割与调整模型 |
| `node tests/test_workbench_session.mjs` | 检查前端草稿与会话行为 |

前端测试需要 Node.js，正常使用网页无需安装 Node.js。各入口与子命令的完整参数可通过 `--help` 查看，例如 `python src/projects.py export --help`。

[返回 README](../README.md) · [项目结构](structure.md) · [设计理念](design.md)
