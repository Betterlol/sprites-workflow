# Sprites 资源流水线

将 Agent 生成的原始图片切成单帧，统一处理后，通过配置组装动作，导出游戏图集和展示动画。

## 浏览器动作工作台

```powershell
python -m pip install -r tools/requirements-workbench.txt
python tools/serve_sprites.py
```

启动本地服务并打开 **http://127.0.0.1:8765**。前端无需 Node、npm 或构建步骤，素材及工程都留在本机。

- **素材处理**：导入原图、自动连通域 / 网格 / 手动画框切图；调整整组缩放、位置、单帧覆盖，并预览、应用处理结果。
- **动作编排**：跨原图拖入 processed 素材，排序、重复、删除、调整 FPS；游戏播放与展示 WebP 的顺序、时长分别编辑。
- **衔接 Review**：拼接 jump → land → idle 等动作片段，设置次数和范围，配合前帧叠图、Idle 参考及逐帧播放检查衔接。
- **自由导出**：PNG 帧 ZIP、图集与 TexturePacker JSON、动画 WebP、Review 动画，或包含原图、processed 和配置的完整工程 ZIP。

网页模式长期保存 **source + processed + pipeline.json**，切图中间文件和最终导出无须常驻。点击“保存工程”仅保存编排和参数；点击“应用处理并保存工程”才替换对应的 processed 图片。导出使用当前草稿中的动作配置和已应用的 processed 图片。

切图调整会尽量保留原有区域的素材 ID，并阻止删除仍被动作引用的帧。建议使用“保留已有最终帧”将过去在 `frames/` 中手工修过的像素保留为 `_approved/` 素材；这个操作会按已有最终帧重新建立动作引用，请在开始新的编排前使用。

其他工程、端口和无自动打开浏览器的运行方式：

```powershell
python tools/serve_sprites.py --config assets/sprites/my_character/pipeline.json --port 8766 --no-browser
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

大肥鱼的 source 为 [dafeiyu_sources/](assets/sprites/dafeiyu_sources/)，其余目录位于 `assets/sprites/dafeiyu/`。为保留已有引用，sprites、spritesheets、webp 分别映射为 **frames/**、**sheets/**、**previews/**。

## 配置

[pipeline.json](assets/sprites/dafeiyu/pipeline.json) 是工程配置；命令行不会回写它，网页在明确保存或应用等操作时更新它。

- `sources` 配置各原图的切图、处理参数；所有原图都会参与处理，无须先被动作引用。
- `actions.<动作>.sprites` 配置已处理素材的组装顺序。
- `actions.<动作>.animation` 配置 WebP 的播放顺序、逐帧时长和循环次数，独立于游戏运行时的播放参数。

source 只放原始生成图；切出的单帧、复制的起止帧和处理结果都不要放回 source。

## 使用方法

需要 Python 3.10+，以下命令在仓库根目录执行：

```powershell
python -m pip install -r tools/requirements-sprites.txt

# 切出全部原图的单帧，检查 source_sprites/
python tools/build_dafeiyu_sprites.py extract

# 生成处理结果，检查 processed_sprites/
python tools/build_dafeiyu_sprites.py process

# 确认配置中的选帧顺序后，发布到 frames/
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

无参数运行等价于 pack。人工修改 processed_sprites 后从 select 继续，修改最终 frames 后从 pack 继续；build 会重新生成中间素材和最终帧。

其他角色使用通用入口，例如：

```powershell
python tools/build_sprites.py extract --config assets/sprites/my_character/pipeline.json
```

## Git 提交约定

`source_sprites/` 和 `processed_sprites/` 中可重建的原图处理目录仍通过 [.gitignore](.gitignore) 忽略。网页导入的 `processed_sprites/imports/` 及保留手工最终帧的 `_approved/` 目录不忽略，应和配置一起保存。

**使用网页工作台时，不要随意清空 processed。** 其中可能有不可由参数重建的修图成果。直接手工修改自动处理目录中的图片时，请导出完整工程备份，或用 `git add -f` 单独保存这些图片。

提交原始图片、pipeline.json、处理脚本及需要交付的最终资源（frames、sheets、previews、metadata 和 manifest）。可复现的处理调整应写入配置；人工修图确认后，先发布为最终帧，再提交最终资源。

详细参数与示例见 [流水线说明](docs/sprite-workflow.md)。运行检查：

```powershell
python -m unittest discover -s tests -v
```
