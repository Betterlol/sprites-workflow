# Sprites 资源流水线

将 Agent 生成的原始图片切成单帧，统一处理后，通过配置组装动作，导出游戏图集和展示动画。

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

[pipeline.json](assets/sprites/dafeiyu/pipeline.json) 是人或 Agent 维护的输入配置，脚本不会生成或回写它。

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

**不要 commit `source_sprites/`、`processed_sprites/` 及其内部文件。** 这些目录是本地生成、检查用的中间产物，已通过 [.gitignore](.gitignore) 忽略。

提交原始图片、pipeline.json、处理脚本及需要交付的最终资源（frames、sheets、previews、metadata 和 manifest）。可复现的处理调整应写入配置；人工修图确认后，先发布为最终帧，再提交最终资源。

详细参数与示例见 [流水线说明](docs/sprite-workflow.md)。运行检查：

```powershell
python -m unittest discover -s tests -v
```
