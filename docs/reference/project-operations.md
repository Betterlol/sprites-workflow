# 工程操作与 CLI（共享参考）

面向终端用户、Agent 和开发者。这里定义操作、版本保护与 QA 的使用方式；网页操作见 [用户指南](../users/workbench.md)，美术制作要求见 [Agent 制作流程](../agents/artwork-workflow.md)。以下示例中的工程与文件均为占位示例，不是操作现有素材的授权。

## 操作职责

| 目的 | 入口 | 是否写入工程 |
| --- | --- | --- |
| 查看工程、检查配置、列历史 | list、status、validate、history | 否 |
| 检查播放、组成、交付包 | qa、check-composition、check-export | 不改工程；qa 新建外部证据目录 |
| 创建、导入、配置保存、删除、恢复 | create、import、save、delete、restore | 是，按版本与引用保护执行 |
| 保存切割、应用参数、补充缺失素材 | save-slices、apply、prepare | 是，各自保存边界不同 |
| 导出 | export | 不改原素材与配置，新建 ZIP |

## 常用命令

在仓库根目录执行，命令输出 JSON，失败时退出码非零。自定义工作区可在子命令前加 `--workspace-root <路径>`；`--json` 输出紧凑 JSON。

```powershell
python tools/projects.py create "大肥鱼" --id dafeiyu --width 640 --height 640
python tools/projects.py --json list
python tools/projects.py status dafeiyu
python tools/projects.py validate dafeiyu
python tools/projects.py import dafeiyu --kind source --file path/to/idle.png
python tools/projects.py apply dafeiyu --source idle.png
python tools/projects.py prepare dafeiyu
# 新修图同样先导入 source，再处理；不是直接导入 processed
python tools/projects.py import dafeiyu --kind source --file path/to/fixed.png
python tools/projects.py apply dafeiyu --source fixed.png
python tools/projects.py import dafeiyu --kind source --file path/to/action_a.png --file path/to/action_b.png
python tools/projects.py import dafeiyu --kind reference --file path/to/identity.png --file path/to/style.png
# 以下删除示例仅针对已有兼容素材；不要为套用示例创建或删除真实素材
python tools/projects.py delete dafeiyu --kind processed --ref imports/a.png --ref imports/b.png
python tools/projects.py delete dafeiyu --kind source --ref unused.png
python tools/projects.py delete dafeiyu --kind reference --ref references/style.png
python tools/projects.py export dafeiyu --format project --output path/to/backup.zip
python tools/projects.py export dafeiyu --format all --action idle --output path/to/idle.zip
python tools/projects.py export dafeiyu --format all --exclude-action eat_rice_legacy --output path/to/game-actions.zip
python tools/projects.py qa dafeiyu --action idle --output path/to/idle-qa
python tools/projects.py qa dafeiyu --action idle --mode display --output path/to/idle-display-qa
python tools/projects.py qa dafeiyu --review idle_to_attack --output path/to/review-qa
python tools/projects.py qa dafeiyu --ref idle/000.png --ref attack/000.png --output path/to/join-qa
python tools/projects.py qa dafeiyu --sequence path/to/playback.json --output path/to/custom-qa
python tools/projects.py check-composition dafeiyu --action sing --review sing_parts
python tools/projects.py check-composition dafeiyu --action sing --sequence path/to/playback.json
python tools/projects.py check-export dafeiyu --archive path/to/game-actions.zip --format all --action sing
```

动作资源导出的 `--action` 和 `--exclude-action` 都可重复指定；不传 `--action` 时从全部动作开始，再应用排除项。未知动作名、排除后没有剩余动作、在 `--format project` 完整工程备份中使用排除参数，都会报错且不生成 ZIP。筛选只影响本次产物，不修改工程配置。

`qa` 从已保存配置和 `processed_sprites/` 读取素材，按动作的游戏/展示播放、已保存的 Review 或重复给出的 `--ref` 顺序，生成 `preview.webp`、`preview.gif`、每页最多 36 个播放槽位的 `contact-*.png` 和 `report.json`。原始素材引用使用工程默认 FPS。报告记录逐槽位引用、起始时间、时长、配置及素材摘要；动画编码可能合并相同画面，GIF 时长还会按 10 ms 取整，因此逐槽位时间以报告为准。输出必须是不存在的新目录，不能位于 source、processed 或 references 内；命令不修改工程素材和配置。结果供实际观看和复查，不能自动判定运动是否自然。

需要自定义逐帧时长时，`--sequence` 接收 JSON，例如 `{"loop":1,"steps":[{"ref":"idle/000.png","duration_ms":150},{"ref":"attack/000.png","duration_ms":80}]}`。`loop` 与 WebP 相同：0 为无限循环，1 为播放一次；最多 10000 步。它不创建动作或 Review，也不改变正式编排，适合临时检查特殊接缝。

`check-composition` 把完整动作的**游戏播放**槽位与一个已保存的 runtime Review 或序列 JSON 逐项比较引用和毫秒时长，返回首个差异、两侧槽位总数/时长及各片段边界；匹配时 `valid=true`、退出码 0，不匹配时 `valid=false`、退出码 1。边界重复引用只报告，不擅自去重或判定画面好坏。命令只读，需要当前已保存配置和现有 processed 帧。

`check-export` 只读检查 `projects.py export` 的资源 ZIP：CRC、导出 PNG 与当前 processed 字节、图集像素/时长/元数据、WebP/GIF 播放记录及实际可解码的画面和时长。`--format` 可要求包含指定格式或 `all`；重复 `--action` 可要求指定动作必须存在，同时仍会检查 ZIP 内其他动作。省略时按 ZIP 中已有动作和格式检查，无法识别整个格式组或动作被完全遗漏。返回 `valid`、`issues` 和格式限制说明，不自动修改或修复交付包。完整工程备份不属于此检查；旧 ZIP 若与当前配置或 processed 素材不同，会报告失败。GIF 的期望颜色按项目的 256 色规则量化后比较；合并相同帧时报告会说明可核对的范围。

需要修改配置时，先读取 `status` 的 `data` 和 `revision`，把修改后的配置写入独立草稿 JSON，再提交：

```powershell
python tools/projects.py save dafeiyu --data path/to/pipeline-draft.json --revision <status返回的revision>
```

`apply`、`prepare`、`import` 也可传 `--revision` 和 `--asset-revision`，拒绝提交基于旧状态的操作。不传时，会在同一把锁内读取最新状态并执行。`apply` 直接更新 processed 和配置，不需要先生成切片缓存。创建不会覆盖已有目录，导出不会覆盖已有 ZIP。

`import` 可重复传入 `--file`，返回 `imported`、`failed` 和 `skipped`，失败时退出码非零；已成功的导入会保留，普通单张错误不阻断后续图片。`delete` 同样支持版本参数，可重复传入 `--ref`；正在被动作或序列使用的素材会阻止整批删除。删除原图同时删除对应切片和 processed；删除生成的单帧不会永久改变切图规则，之后应用可能重新生成。删除没有网页撤销，文件写入失败会回滚已移动的内容。

`import --kind processed` 仍支持历史外部帧兼容，但不作为 Agent 新原画或新单帧修复的常规入口。新素材必须保留 source 来源。

新工程使用 `references/`；旧 `reference/` 继续读取和备份，不自动重命名。参考图的 `--ref` 包含目录前缀，例如 `references/identity.png`；source 的引用相对 `source/`，processed 的引用相对 `processed_sprites/`。

`import --kind reference` 支持 GIF；保留原始文件、动画时长和循环设置，不拆帧、不转成 PNG。参考图列表、删除、素材版本保护与完整工程备份均包含 GIF，旧 `reference/` 下的 GIF 也可读取。

分阶段构建仍可使用：

```powershell
python tools/build_sprites.py extract --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py process --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py select --config workspaces/dafeiyu/pipeline.json
python tools/build_sprites.py pack --config workspaces/dafeiyu/pipeline.json
```

其中 `extract/process` 不回写配置；`process` 会覆盖所选原图对应的 processed。`build` 明确重建全部阶段。要使用网页相同的引用保护与身份持久化行为，优先使用 `projects.py apply/prepare`。

分阶段 CLI 的 `select/pack/preview/build` 也支持可重复的 `--exclude-action`。筛选不会清理之前已导出的动作文件；`build` 仍会准备全部原图，只筛选组装和打包的动作。

## 独立保存切割

```powershell
python tools/projects.py save-slices <工程ID> --source idle.png --extract cuts.json --revision <配置版本> --asset-revision <素材版本>
```

`--extract` 可省略；提供时只包含 extract 规则。只保存当前原图切割、稳定帧 ID 与原尺寸切片，不应用处理、不提交其他动作草稿。缓存可重建。删除仍被引用的区域或带有已保存单帧覆盖的区域会受到保护。

## 历史与恢复

```powershell
python tools/projects.py history <工程ID>
python tools/projects.py restore <工程ID> <版本ID> --revision <配置版本> --asset-revision <素材版本>
```

恢复前复核当前文件和版本，拒绝覆盖操作后的外部修改；恢复也会留下新的历史记录。历史在 `.sprite-workbench-history/`，不包含在工程 ZIP 内。

## 持久化序列与临时播放 JSON

保存的序列资源位于 `workbench.reviews`，其槽位可以引用单帧、动作或其他序列；`qa --review` 读取它的编排与已保存模式。`qa --action` 默认 runtime，可用 `--mode display`。`--review` 不接受额外的 `--mode`，需要先明确该序列自身的配置。

`--sequence` 接收的 `steps` JSON 是临时展开播放记录，不是序列资源的 `slots` 配置；它不创建、替换或保存序列资源。两种格式不能互换。`check-composition --review` 要求 runtime Review，比较结果用于数据核对，不是视觉验收。

## 分阶段入口与兼容脚本

`tools/build_sprites.py` 是通用批处理入口；`tools/build_dafeiyu_sprites.py` 是历史工程包装器，不能代替先核对目标工程路径。无参数默认 pack；`build` 才连续重建全部阶段。`preview --action <ID>` 只更新展示动画，`pack --no-preview` 跳过动画。

已经手工修改过的 processed 可以从 select 继续；已有最终 frames 的修图可从 pack 继续。批量 process/build 会重建对应结果，执行前必须确认范围。网页“保留已有最终帧”属于显式兼容迁移，会重新建立动作引用，不是普通保存操作。
