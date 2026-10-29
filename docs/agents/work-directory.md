# Agent 的 `_work` 工作目录

`workspaces/<project-id>/_work/<task>/` 用来暂存一次制作任务的候选、提示词、比较图和检查记录。它不是工作台的素材输入，也不是必须填满的交付目录。一个任务只在确有草稿或证据需要留存时创建目录；不要求固定子目录或每一步都保存截图。

## 放在哪里

| 内容 | 位置 |
| --- | --- |
| 未采纳的候选图、迭代草稿、临时脚本和提示词 | 本任务的 `_work/<task>/` |
| 已采纳的原画或单帧修复原图 | 用 `projects.py import --kind source` 导入 `source/`，再按工程规则处理 |
| 工作台实际引用的处理结果 | `processed_sprites/`，通过工作台或 `projects.py apply` 管理 |
| 用户参考、已确认的 IDLE 基准和必要的正式记录 | `references/`；候选不放在这里 |
| 最终取舍、来源、边界、验收版本和结论 | 工程 `README.md`；需随完整工程备份保存的附件再放入正式目录 |
| 可重新生成的 QA 图、动画和资源 ZIP | 优先放在 `exports/` 或任务外指定的新输出目录；确需链接留证时才放 `_work/` |

完整工程备份不包含 `_work/` 和 `exports/`。不要让唯一的正式结论只存在于这些目录。历史 `_work/` 中可能有工程说明链接到的证据或交付文件；检查引用和所有者前不要批量删除、移动或改名。

## 先用通用工具完成重复检查

以下命令从仓库根目录执行。`projects.py` 与网页共用工程锁；这些检查命令读取**已保存**的配置和已应用的 processed 图片，不会替你保存网页草稿。

| 需要做的事 | 优先使用 | 人仍需判断的部分 |
| --- | --- | --- |
| 核对当前工程与素材状态 | `python tools/projects.py status <project-id>` | 说明与实际引用是否一致 |
| 看动作、Review 或选定处理帧 | `python tools/projects.py qa <project-id> --action <action> --output <新目录>`；特殊节奏用 `--sequence <JSON>` | 实际观看正常速度、慢放、逐帧与关键接缝 |
| 检查子动作拼接是否等于完整游戏动作 | `python tools/projects.py check-composition <project-id> --action <full> --review <parts>`；未保存的临时编排可用 `--sequence <JSON>` | 重复端点是否有意停顿、动作接缝是否自然 |
| 核对交付资源包 | `python tools/projects.py check-export <project-id> --archive <ZIP> --format all --action <action>` | 接受哪些格式与动作、颜色量化是否满足交付观感 |

`qa` 一次生成 WebP、GIF、逐槽位对照图和时序报告；优先检查这些产物并记录少量关键画面，避免为每个槽位抓一张网页截图。`check-composition` 和 `check-export` 返回 JSON：`valid=false` 表示有客观差异，先读具体差异，再通过正常工程操作修正；它们不会自动改素材、去重或批准画面。命令参数和序列 JSON 格式见 [工程操作参考](../reference/project-operations.md)。

## 保留 Agent 的处理空间

候选图的构思、尺度与锚点调整、表情和运动质量、接缝自然度，都需要结合角色和动作判断。先用工作台预览和现有处理规则试验；如果通用工具表达不了某次特殊检查，可以在本任务 `_work/` 写一次性脚本或少量手工对比图，并在记录中说明目的、输入和结论。不要为了迁就工具而改动正式动作、降低 FPS、隐去坏帧或把候选提前写入 `processed_sprites/`。

任务结束时，在工程 `README.md` 留下实际检查的动作/Review、配置版本或文件摘要、关键证据路径、通过与待办。只保留复查所需的候选和证据；新产生的批量中间截图可在核对引用后清理。工具报告不能代替实际视觉验收或网页交互检查；是否由 Agent 打开网页检查，遵守当前用户指定的测试范围。用户自行验收时，列出待检查项即可。
