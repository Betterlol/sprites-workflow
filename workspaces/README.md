# 工程工作区

每个直接子目录是一份独立工程，目录中的 `pipeline.json` 是识别入口。文件夹可以整体复制或备份；工程列表每次刷新直接扫描磁盘，不依赖额外注册表。

| 路径 | 约定 |
| --- | --- |
| `pipeline.json` | 共享配置：展示名称、画布、锚点、切图与处理规则、动作引用和 Review |
| `source/` | 原始图片；可从网页导入，也可由人或 Agent 直接添加 |
| `source_sprites/` | CLI 原尺寸切片缓存，可重建，Git 忽略 |
| `processed_sprites/` | 动作实际引用的素材与 `_stage.json`，默认提交或备份 |
| `processed_sprites/imports/` | 人工修图和外部导入单帧，必须与工程画布一致 |
| `processed_sprites/_approved/` | 已确认的历史最终帧 |
| `references/` | 人设、参考图片、生成提示词等，不参与自动切图；网页可批量导入和管理参考图 |
| `README.md` | 工程说明、角色约束和待办 |
| `exports/` | CLI 按需生成的帧、图集、预览、元数据和 manifest；Git 默认忽略 |

工程名称与目录名支持中文。创建时目录名留空则使用名称；目录名须符合 Windows 文件名约束，大小写不同也视为重名。`project.name` 是展示名，可在配置中修改；`character` 是交付文件中的英文标识。目录名不满足英文标识要求时，创建器会生成稳定的 `character`。目录名是网页 URL 使用的工程标识，不要在网页编辑中途直接搬动目录。

## 终端与 Agent

在仓库根目录执行，命令输出 JSON，失败时退出码非零。自定义工作区可在子命令前加 `--workspace-root <路径>`；`--json` 输出紧凑 JSON。

```powershell
python tools/projects.py create "大肥鱼" --id dafeiyu --width 640 --height 640
python tools/projects.py --json list
python tools/projects.py status dafeiyu
python tools/projects.py validate dafeiyu
python tools/projects.py import dafeiyu --kind source --file path/to/idle.png
python tools/projects.py apply dafeiyu --source idle.png
python tools/projects.py prepare dafeiyu
python tools/projects.py import dafeiyu --kind processed --file path/to/fixed.png
python tools/projects.py import dafeiyu --kind processed --file path/to/a.png --file path/to/b.png
python tools/projects.py import dafeiyu --kind reference --file path/to/identity.png --file path/to/style.png
python tools/projects.py delete dafeiyu --kind processed --ref imports/a.png --ref imports/b.png
python tools/projects.py delete dafeiyu --kind source --ref unused.png
python tools/projects.py delete dafeiyu --kind reference --ref references/style.png
python tools/projects.py export dafeiyu --format project --output path/to/backup.zip
python tools/projects.py export dafeiyu --format all --action idle --output path/to/idle.zip
python tools/projects.py export dafeiyu --format all --exclude-action eat_rice_legacy --output path/to/game-actions.zip
```

动作资源导出的 `--action` 和 `--exclude-action` 都可重复指定；不传 `--action` 时从全部动作开始，再应用排除项。未知动作名、排除后没有剩余动作、在 `--format project` 完整工程备份中使用排除参数，都会报错且不生成 ZIP。筛选只影响本次产物，不修改工程配置。

需要修改配置时，先读取 `status` 的 `data` 和 `revision`，把修改后的配置写入独立草稿 JSON，再提交：

```powershell
python tools/projects.py save dafeiyu --data path/to/pipeline-draft.json --revision <status返回的revision>
```

`apply`、`prepare`、`import` 也可传 `--revision` 和 `--asset-revision`，拒绝提交基于旧状态的操作。不传时，会在同一把锁内读取最新状态并执行。`apply` 直接更新 processed 和配置，不需要先生成切片缓存。创建不会覆盖已有目录，导出不会覆盖已有 ZIP。

`import` 可重复传入 `--file`，返回 `imported`、`failed` 和 `skipped`，失败时退出码非零；已成功的导入会保留，普通单张错误不阻断后续图片。`delete` 同样支持版本参数，可重复传入 `--ref`；正在被动作使用的素材会阻止整批删除。删除原图同时删除对应切片和 processed；删除生成的单帧不会永久改变切图规则，之后应用可能重新生成。删除没有网页撤销，文件写入失败会回滚已移动的内容。

新工程使用 `references/`；旧 `reference/` 继续读取和备份，不自动重命名。参考图的 `--ref` 包含目录前缀，例如 `references/identity.png`；source 的引用相对 `source/`，processed 的引用相对 `processed_sprites/`。

分阶段构建仍可使用：

```powershell
python tools/build_sprites.py extract --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py process --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py select --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py pack --config workspaces/dafeiyu/pipeline.json
```

其中 `extract/process` 不回写配置；`process` 会覆盖所选原图对应的 processed。`build` 明确重建全部阶段。要使用网页相同的引用保护与身份持久化行为，优先使用 `projects.py apply/prepare`。

分阶段 CLI 的 `select/pack/preview/build` 也支持可重复的 `--exclude-action`。筛选不会清理之前已导出的动作文件；`build` 仍会准备全部原图，只筛选组装和打包的动作。

## 人与 Agent 协作

1. 双方共用磁盘文件。原图放 `source/`，参考资料放 `references/`，不要把参考图放进原图扫描目录。
2. 处理调整优先写规则；独立修图放入 `processed_sprites/imports/`，动作通过相对路径引用。不要为调整动作顺序重命名素材编号。
3. 网页、管理 CLI、分阶段 CLI 共用 `.sprite-workbench.lock`。锁文件会保留，实际锁由系统随进程释放，不需要手动删除。
4. 直接写文件不会自动遵守锁。优先使用管理 CLI；必须手工修改时先写临时文件再替换，并刷新网页确认外部变化。两边不要同时编辑同一配置。
5. 网页有草稿时不会静默覆盖；图片变化可刷新素材，配置冲突可先下载草稿再合并。
6. 提交或备份配置、source、processed、references 和说明。缓存与导出可以重建；人工修图不能按缓存清理。

已有 `assets/` 由用户自行整理，程序不做自动迁移。旧目录可用 `python tools/serve_sprites.py --config <原pipeline.json>` 显式打开。工作区列表中的工程要求 source 位于本工程内。
