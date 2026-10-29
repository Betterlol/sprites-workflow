# 工程目录与协作（共享参考）

工程位于 `workspaces/<工程ID>/`，以 pipeline.json 为识别入口。网页、CLI 和 Agent 操作同一批文件；配置是共享的创作输入。角色特有的参考、约束、来源和验收写在该工程 README，不写进通用指南。

| 路径 | 约定 |
| --- | --- |
| `pipeline.json` | 共享配置：展示名称、画布、锚点、切图与处理规则、动作引用和 Review |
| `source/` | 确认采用的原画，包括动作 spritesheet 和单帧修复原图；先导入此处再切图、处理 |
| `source_sprites/` | 原尺寸切片缓存（网页与 CLI 共用），可重建，Git 忽略 |
| `processed_sprites/` | 动作实际引用的素材与 `_stage.json`，默认提交或备份 |
| `processed_sprites/imports/` | 兼容已有的人工修图或外部处理帧；不作为新素材的常规入口 |
| `processed_sprites/_approved/` | 已确认的历史最终帧 |
| `references/` | 用户初始参考图、确认后的 idle 基准图及必要记录；不放候选图和迭代图，也不参与自动切图 |
| `README.md` | 工程说明、IDLE 基准、角色约束、子动作边界、完整编排、验收记录和待办 |
| `exports/` | CLI 按需生成的帧、图集、预览、元数据和 manifest；Git 默认忽略 |
| `_work/<task>/` | Agent 的任务草稿与必要证据；不是素材输入或完整工程备份的一部分，见 [工作目录指南](../agents/work-directory.md) |

工程名称与目录名支持中文。创建时目录名留空则使用名称；目录名须符合 Windows 文件名约束，大小写不同也视为重名。`project.name` 是展示名，可在配置中修改；`character` 是交付文件中的英文标识。目录名不满足英文标识要求时，创建器会生成稳定的 `character`。目录名是网页 URL 使用的工程标识，不要在网页编辑中途直接搬动目录。

## 保存与备份

Git 默认保留配置、source、processed、references 和工程说明；source_sprites、exports、锁与临时缓存被忽略。不要随意清空 processed，已有手工处理成果不能按缓存清理。

完整工程 ZIP 包含工程说明、配置、原画、处理帧与正式参考；旧 `reference/` 继续读取和备份，不自动改名。缓存、exports、`_work/` 和 `.sprite-workbench-history/` 不包含在完整工程 ZIP 中。需要长期追溯的结论保留在工程 README，必要正式附件放 references；不要只链接到会被清理的工作文件。

## 并发与外部变化

网页、管理 CLI 和分阶段 CLI 共用 `.sprite-workbench.lock`。锁文件会保留，实际锁由系统随进程释放，无须手动删除。

配置版本和素材版本分别检查。网页未保存草稿不会被外部更新静默覆盖；发生配置冲突时，可下载草稿或合并配置，复核后再保存。只变化图片时可刷新素材并保留草稿。CLI 保存也应携带读取时的版本，详见 [工程操作](project-operations.md)。

直接写文件不遵守进程锁。常规操作使用工作台或 projects.py；确需手动编辑配置时，在独立草稿中修改后通过 CLI save 提交。不要在网页编辑中途移动工程目录，也不要让多个参与者同时覆盖同一份配置。

## 引用与删除

processed 引用相对于 processed_sprites，source 引用相对于 source；参考图引用含 references 或旧 reference 前缀。动作与序列共用引用保护：仍被引用的图片、动作或序列不能直接删除。网页确认强制删除后，先在配置副本中清理引用、调整受影响组合，再提交删除；CLI 和普通删除 API 仍拒绝删除配置中尚在使用的素材。具体操作见 [网页指南](../users/workbench.md#删除恢复与旧素材)。自动生成的单帧即使删除，后续应用原图仍可能重建，删除不等于修改切割规则。
