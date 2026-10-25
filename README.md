# Sprites 资源流水线

> 网页界面预览请看 [网页工作台](docs/web-preview.md)。

将 Agent 生成的原始图片切成单帧，统一处理后，通过配置组装动作，导出游戏图集和展示动画。

## Agent 制作入口（必读）

制作、扩展或修复动作前，先读 [AGENTS.md](AGENTS.md)、[工作区说明](workspaces/README.md)、[Agent Sprite 制作与验收流程](docs/agent-sprite-workflow.md)，再读目标工程的 `README.md` 和 `pipeline.json`，用 `tools/projects.py status <project-id>` 核对现状。架构说明见 [DESIGN.md](DESIGN.md)。

强制顺序为：**绑定已确认的 IDLE 基准 → 规划子动作及实际播放边界 → 以 IDLE 和边界图片约束整张 spritesheet → 导入采用的原画并处理 → 检查每个子动作及接缝 → 核对完整动作编排并验收**。

IDLE 固定形象、比例与视觉尺度；前后边界帧固定姿态、运动和道具状态。直接共享的边界默认只播放一次；不能直接衔接时，以实际采用的前段末帧和后段入口帧生成整张过渡图，再切图并检查两端。单帧生成只修复明确坏帧。完整动作和 Review 必须使用相同的引用、实际边界和运行时节奏，并以正常速度、慢放和逐帧检查通过为完成条件。

基准、来源、选帧范围、取舍和验收版本必须记录在工程说明中；模板见上述流程，任务与生成提示词见 [示例](docs/prompt-sample.md)。配置校验或成功导出不代表动作已通过视觉验收。这些是 Agent 的制作职责，工作台尚未自动强制检查。文档任务不改动现有素材或动作配置。

## 浏览器动作工作台

```powershell
python -m pip install -r tools/requirements-workbench.txt
python tools/serve_sprites.py
```

启动本地服务并打开 **http://127.0.0.1:8765** 的工程列表。点击“新建工程”，输入名称、目录名、画布和锚点，就会在 `workspaces/<目录名>/` 创建独立工程。名称和目录名均支持中文，目录名留空时使用工程名称。前端无需 Node、npm 或构建步骤，素材及工程都留在本机。

- **素材处理**：支持多选批量导入原图和 processed；自动连通域 / 网格 / 手动画框切图；调整整组缩放、位置、单帧覆盖，并预览、应用处理结果。
- **批量编排与删除**：素材库支持多选、Shift 连选、全选当前筛选结果，一次加入动作或删除；原图也可删除，正在被动作引用的素材会受到保护。
- **参考图**：在独立页签中批量导入、查看和删除，保存于 `references/`，不参与切图。
- **动作编排**：跨原图拖入 processed 素材，排序、重复、删除、调整 FPS；游戏播放与展示 WebP 的顺序、时长分别编辑。
- **衔接 Review**：拼接 jump → land → idle 等动作片段，设置次数和范围，配合前帧叠图、Idle 参考及逐帧播放检查衔接。
- **自由导出**：PNG 帧 ZIP、图集与 TexturePacker JSON、动画 WebP、Review 动画，或包含原图、processed 和配置的完整工程 ZIP。

网页模式长期保存 **source + processed + pipeline.json**，切图中间文件和最终导出无须常驻。点击“保存工程”仅保存编排和参数；点击“应用处理并保存工程”才替换对应的 processed 图片。导出使用当前草稿中的动作配置和已应用的 processed 图片。

切图调整会尽量保留原有区域的素材 ID，并阻止删除仍被动作引用的帧。建议使用“保留已有最终帧”将过去在 `frames/` 中手工修过的像素保留为 `_approved/` 素材；这个操作会按已有最终帧重新建立动作引用，请在开始新的编排前使用。

其他工程、端口和无自动打开浏览器的运行方式：

```powershell
python tools/serve_sprites.py --workspace-root workspaces --port 8766 --no-browser
# 显式打开旧布局或任意已有工程，不会迁移文件
python tools/serve_sprites.py --config assets/sprites/dafeiyu/pipeline.json
```

详细操作、保存语义、迁移和数据格式见 [工作台说明](docs/workbench.md)。现有命令行流水线继续可用。

## 工作流程

```text
source/ → source_sprites/ → processed_sprites/ → sprites/ → spritesheets/ + webp/
           extract            process           select        pack / preview
```

1. **切图**：扫描 source 中的所有原始图片，按各自规则切出原始尺寸的单帧。
2. **处理**：对全部切片进行缩放、锚点对齐、偏移等处理，供人工或 Agent 检查。
3. **组装**：确认素材后，在配置中选帧和排序；可以跨原图复用素材，脚本自动生成连续编号。
4. **导出**：最终帧打包为 PNG 图集和 TexturePacker JSON，另生成展示用 WebP。

工程目录约定见 [workspaces/README.md](workspaces/README.md)。每个工程包含自己的配置、`source/`、`source_sprites/`、`processed_sprites/` 和 `references/`。网页按需导出 ZIP；CLI 的最终帧、图集、WebP 和元数据写入工程的 `exports/`，首次创建不生成这些交付目录。已有 `reference/` 继续兼容读取和备份，不自动搬动。

现有 `assets/` 保持原样，由用户手动整理；工作台不会自动迁移或删除它。

## 配置

每个工程的 `pipeline.json` 是网页、CLI 和 Agent 共用的配置。`build_sprites.py` 负责分阶段构建，不回写配置；`projects.py` 与网页共用保存、应用、导入能力，会在明确提交时更新配置。

- `sources` 配置各原图的切图、处理参数；所有原图都会参与处理，无须先被动作引用。
- `actions.<动作>.sprites` 配置已处理素材的组装顺序。
- `actions.<动作>.animation` 配置 WebP 的播放顺序、逐帧时长和循环次数，独立于游戏运行时的播放参数。

`source/` 保存确认采用的原画，包括动作 spritesheet 和单帧修复原图；切出的缓存帧、复制的起止帧和 processed 输出不要回填到 `source/`。

## 使用方法

需要 Python 3.10+，以下命令在仓库根目录执行：

```powershell
python -m pip install -r tools/requirements-sprites.txt

# 终端 / Agent 也可创建和操作工程，输出 JSON
python tools/projects.py create "大肥鱼" --id dafeiyu
python tools/projects.py --json list
python tools/projects.py status dafeiyu
python tools/projects.py apply dafeiyu --source idle.png

# 切出全部原图的单帧，检查 source_sprites/
python tools/build_dafeiyu_sprites.py extract

# 分阶段处理会覆盖对应 processed；Agent 常规制作优先使用 projects.py apply
python tools/build_dafeiyu_sprites.py process

# 确认配置中的选帧顺序后，发布到 exports/frames/
python tools/build_dafeiyu_sprites.py select

# 导出图集、元数据和 WebP
python tools/build_dafeiyu_sprites.py pack
```

常用操作：

```powershell
# 只重切、处理指定原图；参数包含扩展名
python tools/build_dafeiyu_sprites.py extract --source die.png
python tools/build_dafeiyu_sprites.py process --source die.png

# 只组装、导出指定动作
python tools/build_dafeiyu_sprites.py select --action die_reveal
python tools/build_dafeiyu_sprites.py pack --action die_reveal

# 只更新 WebP / 只导出游戏资源
python tools/build_dafeiyu_sprites.py preview --action die_reveal
python tools/build_dafeiyu_sprites.py pack --no-preview

# 完整重建，连续执行所有阶段
python tools/build_dafeiyu_sprites.py build
```

无参数运行等价于 pack。历史上已手工修改的 processed 可从 select 继续，已有最终 frames 的修图可从 pack 继续；新修图必须按 Agent 流程先导入 source 再处理。build 会重新生成中间素材和最终帧，不作为 Agent 常规增量制作入口。

其他角色使用通用入口，例如：

```powershell
python tools/build_sprites.py extract --config workspaces/my_character/pipeline.json
```

导出时可排除旧动作，例如导出除旧版进食外的全部动作：

```powershell
python tools/projects.py export dafeiyu --format all --exclude-action eat_rice_legacy --output "E:\SpriteExports\dafeiyu.zip"
```

`--exclude-action` 可重复使用，也可与 `--action` 合用：先选动作，再排除。分阶段 CLI 的 `select`、`pack`、`preview`、`build` 同样支持此参数。未知动作名或排除后没有剩余动作会报错；完整工程备份（`--format project`）不支持排除动作。

## Git 提交约定

`source_sprites/`、工程锁、临时文件和工作区工程的 `exports/` 通过 [.gitignore](.gitignore) 忽略。`pipeline.json`、`source/`、`references/`、工程说明和 `processed_sprites/` 默认保留，应一起提交或备份。

**使用网页工作台时，不要随意清空 processed。** 新采纳的人工修图也先作为原图导入 `source/`，再切图、处理并更新动作引用；已有 `processed_sprites/imports/` 素材作为历史兼容保留，避免在原图对应的 processed 目录中直接修图后被“应用处理”覆盖。

可复现的处理调整应写入配置；交付文件按需导出，默认不作为工程的唯一数据来源。协作约定和命令见 [工作区说明](workspaces/README.md)。

详细参数与示例见 [流水线说明](docs/sprite-workflow.md)。运行检查：

```powershell
python -m unittest discover -s tests -v
```
