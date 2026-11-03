# 工程操作：从任务到命令

以下示例从仓库根目录执行，`demo`、文件名、动作与 Review 均需换成实际对象。按任务选段执行，每条命令检查退出码与 JSON 结果，失败后先排查；不要整页连续运行。自定义工作区在子命令前增加 `--workspace-root`。完整参数见[命令参考](../../../../docs/commands.md)，字段见[配置参考](../../../../docs/configuration.md)。

## 读取状态与版本

```powershell
python src/projects.py list
python src/projects.py status demo
```

阅读 `data`、`revision`、`asset_revision`、素材状态和警告，并实际查看相关图片。`data` 是完整配置，不含网页尚未保存的草稿；存在外部编辑或网页草稿时先核对采用内容。

后续写入传入所依据的版本，发生冲突时重新读取、比较并合入本次改动。只替换版本号重试旧草稿会丢掉并发修改。每次成功写入后采用返回的新状态；`save` 仅返回配置版本，随后重新 `status`。

## 导入与切割

先核对导入目标，避免同名文件冲突。新原画或新生成的修复图保留 source 来源：

```powershell
python src/projects.py import demo --kind source --file "candidate/walk-fixed.png" --revision CONFIG_REV --asset-revision ASSET_REV
python src/projects.py save-slices demo --source "walk-fixed.png" --extract "extract.json" --revision NEW_CONFIG_REV --asset-revision NEW_ASSET_REV
```

导入结果检查 `imported`、`failed`、`skipped`，部分失败不代表全部回滚；下一步使用成功导入后的最新状态。`extract.json` 只含该原图的切割规则对象。已存身份、`region_ids` 与 `next_id` 保持对应，删除仍被引用或带覆盖的区域需先处理依赖。

查看切片完整性与稳定 ID 后，对该原图执行 `apply` 生成正式图片；保存切割本身不更新正式图片。`apply` 也可直接按已保存规则处理原图，不强制先建切片缓存。

## 单帧处理：保存草稿再应用

适用于原画正确、需要改处理参数且允许所有引用同步改变的情况。先从运行时播放定位目标 PNG，再定位其原图与稳定帧 ID；“第三播放步”不等于 `002`。覆盖中的 `offset` 是绝对值，若要在当前偏移上移 4 像素，应以当前生效偏移计算新值。

下面示范完整草稿的读写衔接。先读取状态并写出 UTF-8 无 BOM 的草稿；深度参数用于保留嵌套配置：

```powershell
$spriteState = python src/projects.py --json status demo | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "读取工程失败" }
[System.IO.File]::WriteAllText("draft.json", ($spriteState.data | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
```

在 `draft.json` 中只修改目标原图 `process.overrides` 下的稳定帧 ID，保留其他内容；写法见配置参考的[逐帧处理覆盖](../../../../docs/configuration.md#逐帧处理覆盖)。核对影响范围后保存：

```powershell
python src/projects.py save demo --data "draft.json" --revision $spriteState.revision
if ($LASTEXITCODE -ne 0) { throw "草稿未保存，请处理错误或版本冲突" }
$spriteState = python src/projects.py --json status demo | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "读取工程失败" }
python src/projects.py apply demo --source "walk.png" --revision $spriteState.revision --asset-revision $spriteState.asset_revision
```

`apply` 按原图规则处理整组，只写变化的结果；它不能保证保留来源目录中外部修改过的正式 PNG。存在人工修图时，先比较源图处理结果与当前正式图片，选择保留修图的独立变体或可重建的源图修复路径。`prepare` 保留已有正式帧，不能代替这次参数应用；批量 `process/build` 也不适合用来试修一帧。

### 只改变一次播放

同一 PNG 被多个位置或动作引用时，直接修改它会影响全部引用。若目标仅是某一次播放，从当前采用图片制作独立变体，通过 `import --kind processed` 导入并保留来源映射，或将修复原画导入 source 后处理；以导入结果及最新状态确认真实引用，不猜文件名。

```powershell
python src/projects.py import demo --kind processed --file "candidate/walk-step3-up4.png" --revision CONFIG_REV --asset-revision ASSET_REV
python src/projects.py status demo
```

变体制作沿用当前可用的图像编辑工具；精确平移保留画布尺寸、RGBA 与原采用内容，检查边缘是否越界。工程 CLI 不提供独立 PNG 平移命令，不编造此类参数。简记原采用帧与版本、新引用及目标播放位置即可。

仅重定向目标槽位。若目标在共享子动作内部，为当前动作建立局部编排或独立子资源，保留原片段的范围与逐步时长，避免修改共享子资源。局部展开为显式单帧会固定该处当前编排，后续子动作变化不会自动同步，应记录这一取舍。此路径不需要对原来含人工修图的整张原图执行 `apply`。

## 播放与编排核对

```powershell
python src/projects.py qa demo --action rise --mode runtime --output "qa/rise-runtime-v1"
python src/projects.py qa demo --action fall --mode runtime --output "qa/fall-runtime-v1"
```

查看 `report.json` 的 `steps`、`ref`、`duration_ms` 和来源信息，并实际播放。范围按所选模式的展开步计算，从 0 开始且包含 `end`。重复边界是否去掉依据真实姿态与停留；同一 PNG 连续出现可能是有意停顿。

在完整草稿中保存目标动作及独立的预期组成 Review，语法见[动作与槽位](../../../../docs/configuration.md#动作与槽位)。例如配置参考的 `jump_land` / `jump_land_check`：保留 `rise` 全段，只有确认 `fall` 首步重复时才设 `start: 1`。动作引用保留子资源各步时长，复合片段用 `speed` 调速。

```powershell
python src/projects.py check-composition demo --action jump_land --review jump_land_check
python src/projects.py qa demo --action jump_land --mode runtime --output "qa/jump-land-runtime-v1"
python src/projects.py qa demo --review jump_land_check --output "qa/jump-land-review-v1"
```

Review 使用 `runtime`，不附加 `qa --mode`；预期组成来自计划采用的各段，避免仅引用最终动作自身做自我比较。检查 `valid`、`first_mismatch`、两侧步数、总时长与边界；工具无法表达预期时直接比较展开记录。

只查局部接缝时可用 `qa --sequence` 提供显式 `steps` 和实际毫秒时长。`qa --ref` 使用工程默认 FPS，不宜替代带不同逐步时长的真实接缝。临时 `steps` 不会创建持久化 Review，也不应直接拿局部片段与完整动作做相等比较。

先检查每段及过渡两侧，再检查完整动作和实际前后动作；有多个入口或中断位置时检查实际使用的边界。共享 PNG 或子动作变动后，复查受影响的组合。配置、图片或时序变化后重新生成相关证据，不沿用旧目录的结论。

## 展示与交付

游戏编排与展示编排分别确认。组合动作的 GIF 不会因为引用了子动作就自动沿用各段独立的展示顺序。游戏需要保留原运行时组成时，槽位继续引用 `runtime`，展示调整放到组合动作自己的 `animation`；`animation.order` 使用组合后的运行时展开位置。

槽位显式设为 `mode: display` 会改变该槽位在游戏运行时中的展开内容，不是仅供 GIF 使用的开关。只有组合本身确实需要子展示内容时才这样设置，并重新核对游戏结果。展示目标无法由当前运行时帧重排表达时，先明确是否需要独立的展示资源；不静默改变游戏动作。

```powershell
python src/projects.py qa demo --action jump_land --mode display --output "qa/jump-land-display-v1"
python src/projects.py validate demo
python src/projects.py export demo --format all --action jump_land --output "delivery/jump-land-v1.zip"
python src/projects.py check-export demo --archive "delivery/jump-land-v1.zip" --format all --action jump_land
```

QA 目录和 ZIP 都必须是新路径；QA 输出放在原图、正式帧和参考目录之外。格式按交付需求选择，示例 `all` 同时包含游戏帧、图集与展示动画。显式给 `check-export` 预期格式和动作，避免仅检查包内已有内容而漏掉整个缺失项。

实际查看导出图片和动画的透明、尺寸、顺序与节奏。`report.json` 保留配置与图片摘要以及逐步时序；编码可能合并相同画面，GIF 时长存在取整，不能只数编码帧判断漏帧。程序结果不证明视觉质量，也不证明游戏内接入成功。

只需完整工程备份时使用 `export --format project`；该格式不属于 `check-export` 的资源包检查范围。交付记录简记采用来源、变体对应、时序取舍和检查版本；未实际查看的部分明确待验收。

## 常见误用

| 误用 | 正确处理 |
| --- | --- |
| 向 `save` 提交状态响应或字段补丁 | 提交从 `status.data` 修改得到的完整配置 |
| 保存规则后直接交付旧正式帧 | 确认是否需要 `apply`；保留人工修图并核对当前采用版本 |
| 依据编号选边界、给整段统一 FPS | 从最终运行时展开选择位置，保留实际逐步时长 |
| 用成功导出替代验收 | 核对包内容，再实际查看目标播放与前后衔接 |

[返回 skill](../SKILL.md) · [制作技巧](production.md)
