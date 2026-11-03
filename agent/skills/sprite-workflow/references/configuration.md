# 配置与资源组合

本页给出制作流程所需的 `pipeline.json` v2 与命令 JSON 语义。工程配置示例是局部字段，在对应对象中新增或修改，保留其他原图、动作、Review 与设置；独立的切割规则和临时播放序列则按其示例直接组成输入文件。

## 工程配置与提交内容

| 字段 | 用途 |
| --- | --- |
| `version`、`character` | 版本为 `2`；角色标识使用英文字母、数字、下划线或连字符 |
| `frame_size`、`anchor` | RGBA 画布 `[宽, 高]`；锚点含归一化 `x`、`y` 和实际使用的 `pixels: [x, y]`，调整时保持一致 |
| `paths` | 路径相对于 `pipeline.json` 所在目录；使用当前配置，不套用另一工程的路径 |
| `defaults` | 默认切割、处理和动作规则；原图继承 `extract`、`process`，动作继承适用字段 |
| `sources` | 以原图相对路径为键，每项只含 `extract`、`process` |
| `actions` | 以动作 ID 为键，描述正式帧引用、编排与播放 |
| `workbench.reviews` | 持久化 Review，也是可引用的 `sequence` 资源 |

新工程通常使用 `source/` 保存原图、`references/` 保存参考、`source_sprites/` 保存可重建的原尺寸切片、`processed_sprites/` 保存正式 PNG。动作的单帧引用相对于正式帧目录；路径及源图对应关系以当前工程状态为准。人工修图可位于 `processed_sprites/imports/`，不能认为所有正式图片都可无损重建。

`save --data draft.json` 接收从 `status.data` 修改得到的**完整配置对象**；保留其余字段，不提交整个状态响应或字段补丁。`--revision` 使用读取该配置时的版本。

`save-slices --extract extract.json` 接收**单个切割规则对象**，不包裹 `sources` 或 `extract` 字段。保存配置只写规则，保存切割只写该原图的规则与原始切片，`apply` 才更新对应正式图片。

## 切割规则与稳定身份

| `extract.method` | 内容 |
| --- | --- |
| `components` | 按透明度识别连通区域，可设 `alpha_threshold`、`min_component_pixels`、`major_min_pixels`、`major_fraction`，可成对提供 `cols`、`rows` 约束布局 |
| `grid` | 必填 `cols`、`rows`，从上到下、每行从左到右切割 |
| `boxes` | `boxes` 为 `[left, top, right, bottom]` 数组，单位为原图像素，右、下边界不包含 |
| `image` | 整张原图作为一帧 |

适用于至少 128×64 像素原图的 `extract.json`：

```json
{"method": "boxes", "boxes": [[0, 0, 64, 64], [64, 0, 128, 64]]}
```

`identities` 保存稳定帧文件名与 `source_box`，`next_id` 是后续 ID 分配起点。手动切割的 `region_ids` 若存在，应与 `boxes` 一一对应，使用至少三位的数字字符串，数字值不可重复。修改已有区域时保留身份与对应关系，不因重排重新编号，也不倒退 `next_id`。

## 逐帧处理覆盖

`sources[原图路径].process` 继承 `defaults.process`，`overrides` 再覆盖指定稳定帧的参数。原图路径使用 `/`。例如 `walk.png` 产生的 `walk/001.png`，其覆盖键为 `"001"`，不含目录或 `.png`，也不是动作播放位置或槽位 ID：

```json
{
  "sources": {
    "walk.png": {
      "process": {
        "mode": "anchor",
        "overrides": {"001": {"offset": [0, -4], "scale_x": 0.95}}
      }
    }
  }
}
```

| 参数 | 语义 |
| --- | --- |
| `mode` | `anchor` 按非透明内容底部中心对齐锚点；`contain` 将切片适配并居中于画布；`copy` 原样保留，输入尺寸必须等于画布 |
| `scale`、`scale_x` | 正数；统一缩放和额外横向比例。单帧值替换继承值，不是相对乘数；单帧 `scale` 替代组内解析出的统一缩放 |
| `fit_height`、`max_scale` | 根据整组最大非透明高度计算共享缩放，`max_scale` 限制适配因子；在组级计算，不用于逐帧覆盖 |
| `offset` | 画布像素 `[dx, dy]`，右、下为正；单帧值替换组偏移，不与其相加 |
| `overflow` | `error` 默认拒绝越界，`clip` 允许裁切超出画布内容 |

`copy` 不执行缩放和偏移，要求 `scale_x = 1`；`contain` 的统一缩放还会乘该切片自身的画布适配比例。不存在的覆盖 ID 在处理时会被拒绝。

保存覆盖后，对相应原图 `apply` 才会更新正式 PNG；只补缺失素材的 `prepare` 不能代替应用。共享 PNG 的所有引用都会看到图片变化；若仅修改一次播放，应制作独立变体并改目标引用。

## 动作与 Review

动作可用 `sprites: ["walk/000.png", "walk/001.png"]` 表达简单序列，或用 `slots` 表达组合，不同时填写两种内容。`fps` 决定未显式指定时长的单帧默认时长；动作和 Review 的顶层 `loop` 均为布尔值。

| 槽位字段 | 约定 |
| --- | --- |
| `id` | 同一资源内唯一的非空字符串，重排时保留原 ID |
| `resource` | `{"kind": "action", "ref": "rise"}`；`kind` 为 `sprite`、`action` 或 `sequence` |
| `resource.ref` | 单帧为相对正式帧目录的 PNG 路径；动作是 `actions` 的键；序列是 `workbench.reviews` 的键 |
| `start`、`end` | 按所选模式展开后的播放步位置，从 0 开始且包含结束位置；默认全段，`end: null` 也表示最后一步 |
| `repeat` | 截取片段的重复次数，整数 `1–100`，默认 `1` |
| `speed` | `0.01–100`，默认 `1`；每步时长除以该值并取整，至少 `1 ms` |
| `duration_ms` | 仅用于 `sprite` 槽位，正整数毫秒；复合片段用 `speed` 或修改子资源时长 |
| `mode` | `runtime` 或 `display`；动作槽位默认引用运行时，序列槽位默认继承当前序列模式 |

范围不是子资源的槽位号或稳定帧 ID；先截取展开步，再重复与调速。单帧资源只能选第 `0` 步。子资源长度或顺序变化后复查范围；被引用动作的顶层无限循环不在组合内无限展开。组合不得循环引用，最多嵌套 32 层、展开 10,000 步。动作及 Review ID 使用英文字母、数字、下划线或连字符。

假设 `rise` 为 `[jump/000.png, jump/001.png]`，`fall` 为 `[jump/001.png, land/000.png]`，确认共享边界无意停顿后，可把下面两部分合入完整草稿。独立 Review 表示预期组成，与完整动作比较：

```json
{
  "actions": {
    "jump_land": {
      "loop": false,
      "slots": [
        {"id": "rise-part", "resource": {"kind": "action", "ref": "rise"}},
        {"id": "fall-part", "resource": {"kind": "action", "ref": "fall"}, "start": 1}
      ]
    }
  },
  "workbench": {
    "reviews": {
      "jump_land_check": {
        "mode": "runtime",
        "loop": false,
        "slots": [
          {"id": "rise-check", "resource": {"kind": "action", "ref": "rise"}},
          {"id": "fall-check", "resource": {"kind": "action", "ref": "fall"}, "start": 1}
        ]
      }
    }
  }
}
```

工具不会自动去重。也可截短前段为 `end: 0` 并保留后段全段，不要两侧同时删除必要姿态。相同 PNG 重复可能是有意停留，需结合时长与动作判断。

Review 的 `mode` 默认 `runtime`，保存后由 `qa --review` 使用；`check-composition --review` 只接受运行时 Review。旧 Review 的 `clips` 仍可读取，例如 `{"clips": [{"action": "rise", "start": 0, "end": null, "repeat": 1}]}`；新编排用 `slots`，已有表示可保留，存在 `slots` 时以它为准，不同时维护两份内容。

## 展示播放

动作的 `animation` 控制展示播放：`order` 使用最终运行时展开结果的 0 起位置，可重排或重复；`durations_ms` 与展示步数一致，包含重复步，优先于统一 `duration_ms` 和 `fps`。`slots` 动作只有重排而未显式设置时长时，继承所选步的实际时长。

`animation.loop` 是整数循环次数，`0` 表示无限；不要与动作和 Review 的布尔 `loop` 混用。槽位设置 `mode: display` 会改变该槽位在游戏运行时中的展开内容；只为 GIF 调整展示时，保持游戏槽位的运行时模式，修改组合动作自己的 `animation`。

## 临时播放序列

`qa --sequence` 与 `check-composition --sequence` 接受独立 JSON，不是持久化 Review 的 `slots`，不会保存编排：

```json
{"steps": [{"ref": "walk/000.png", "duration_ms": 100}, {"ref": "walk/001.png", "duration_ms": 80}], "loop": 1}
```

`ref` 相对正式帧目录，`duration_ms` 是每步毫秒数；`loop` 是整数，`0` 无限，`1` 播放一次。接缝检查使用实际展开时长，完整组成比较提供完整预期序列。
