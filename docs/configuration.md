# 配置与资源组合

本页说明 `pipeline.json` v2 和命令接收的 JSON 内容。命令用法见[操作命令](commands.md)。以下配置示例均为局部字段，需合入已有配置，不是可直接覆盖工程的完整文件。

## 配置层次与提交内容

| 字段 | 含义 |
| --- | --- |
| `version`、`character` | 版本固定为 `2`；角色标识使用英文字母、数字、下划线或连字符 |
| `frame_size`、`anchor` | 画布 `[宽, 高]`；锚点含归一化 `x`、`y` 及实际使用的 `pixels: [x, y]`，修改时保持一致 |
| `paths` | 相对于工程的素材与输出路径，见[工程布局](structure.md) |
| `defaults` | 默认规则；`extract`、`process` 供原图继承，其余适用字段供动作继承 |
| `sources` | 以原图相对路径为键，每项只放 `extract` 和 `process` |
| `actions` | 以动作 ID 为键，描述资源编排、运行时与展示播放设置 |
| `workbench.reviews` | 持久化 Review，也是可被引用的 `sequence` 资源，和动作共用槽位结构 |

`save --data draft.json` 接收**完整配置对象**。可从 `status` 返回值的 `data` 取出配置进行局部修改，保留其余字段；不要提交整个状态响应或仅包含改动字段的补丁。`--revision` 使用读取该配置时的版本。

`save-slices --extract extract.json` 接收**单个切割规则对象**，即对应原图的 `extract` 内容，不包裹 `sources` 或 `extract` 字段。参数格式与完整配置不同。

## 切割规则

| `extract.method` | 内容与顺序 |
| --- | --- |
| `components` | 按透明度识别连通区域；可设置 `alpha_threshold`、`min_component_pixels`、`major_min_pixels`、`major_fraction`，可选成对提供 `cols`、`rows` 约束布局 |
| `grid` | 必填 `cols`、`rows`，按从上到下、每行从左到右的顺序切割 |
| `boxes` | `boxes` 为手动矩形数组，每项 `[left, top, right, bottom]`，坐标为原图像素，右、下边界不包含在矩形中 |
| `image` | 整张原图作为一帧 |

例如，适用于一张至少为 128×64 像素原图的 `extract.json`：

```json
{"method": "boxes", "boxes": [[0, 0, 64, 64], [64, 0, 128, 64]]}
```

已保存的 `identities` 记录稳定帧文件名与 `source_box`，`next_id` 记录后续 ID 分配起点。手动切割的 `region_ids` 若存在，必须与 `boxes` 一一对应，为至少三位的数字字符串，且数字值不能重复。编辑已有规则时保留这些身份字段与对应关系；不要因重排而重新编号，也不要倒退 `next_id`。实际帧 ID 以当前配置及切片记录为准。

## 逐帧处理覆盖

`sources[原图路径].process` 继承 `defaults.process`，`overrides` 再覆盖指定帧的处理参数。原图路径使用 `/`；例如原图 `walk.png` 产生的 `walk/001.png` 对应稳定帧 ID `"001"`。

```json
{
  "sources": {
    "walk.png": {
      "process": {
        "mode": "anchor",
        "overrides": {
          "001": {"offset": [0, -4], "scale_x": 0.95}
        }
      }
    }
  }
}
```

覆盖的键是**已有稳定帧 ID**，不含 `.png` 或目录，也不是画面显示序号、动作播放位置或槽位 ID。该示例将 `001` 的偏移设为 `[0, -4]`、横向比例设为 `0.95`；不影响其他帧的规则。不存在的 ID 会在处理时被拒绝。

| 参数 | 处理语义 |
| --- | --- |
| `mode` | `anchor` 按非透明内容的底部中心对齐锚点；`contain` 将原始切片适配并居中于画布；`copy` 原样保留，输入尺寸必须等于画布尺寸 |
| `scale`、`scale_x` | 正数；统一缩放及额外横向比例。覆盖中的值替换继承值，不是相对乘数；覆盖 `scale` 会替代组内解析出的统一缩放 |
| `fit_height`、`max_scale` | 依据整组帧的最大非透明高度计算组内统一缩放，`max_scale` 限制适配因子；这两项在组级计算，不用于逐帧覆盖 |
| `offset` | `[dx, dy]`，画布像素，右与下为正；逐帧值替换组偏移，不与其相加 |
| `overflow` | `error`（默认）拒绝越界；`clip` 允许裁切超出画布的内容 |

`copy` 模式不执行缩放和偏移，且要求 `scale_x = 1`。对于 `contain`，统一缩放还会乘以该切片自身的画布适配比例。

只调整某帧时，保留原有切割身份与其他规则，在完整草稿中修改目标 ID 的覆盖。保存配置只更新规则；要更新正式单帧，还需对该原图执行 `apply`，不能用只补缺失素材的 `prepare` 代替。一个正式单帧被多个动作引用时，图片修改会反映到所有引用处。

## 动作与槽位

动作可使用 `sprites: ["walk/000.png", "walk/001.png"]` 表达简单帧序列，也可使用 `slots` 表达组合；不要同时填写两种内容。`fps` 决定未显式指定时长的单帧时长，`loop` 为布尔值。

每个槽位描述一个资源引用：

| 槽位字段 | 约定 |
| --- | --- |
| `id` | 同一资源内唯一的非空字符串；保留已有 ID，重排时随槽位一起移动 |
| `resource` | 例如 `{"kind": "action", "ref": "rise"}`；`kind` 取 `sprite`、`action` 或 `sequence` |
| `resource.ref` | 单帧引用相对于 `processed_sprites/`，使用 `/` 并以 `.png` 结尾；动作引用 `actions` 的键，序列引用 `workbench.reviews` 的键 |
| `start`、`end` | 子资源展开后的播放步位置，**从 0 开始且包含结束位置**；默认从 `0` 到最后一步，`end: null` 也表示最后一步 |
| `repeat` | 截取片段的重复次数，整数 `1–100`，默认 `1` |
| `speed` | 播放速度，`0.01–100`，默认 `1`；每步时长除以该值并取整，至少 `1 ms` |
| `duration_ms` | 仅可用于 `sprite` 槽位，正整数毫秒；引用动作或序列的复合槽位禁止填写，改用 `speed` 或修改子资源时长 |
| `mode` | `runtime` 或 `display`，选择子资源的播放表示；动作槽位默认引用运行时，序列槽位默认继承当前序列的播放模式 |

范围作用于子资源按所选模式展开后的步序列，不是子资源的槽位序号，也不是稳定帧 ID。先截取范围，再按 `repeat` 重复并应用 `speed`；重排或改变子资源展开长度后，需要复查已有范围。单帧资源的范围只能选第 `0` 步。

动作和 Review 的 ID 使用英文字母、数字、下划线或连字符。组合不能循环引用，最多嵌套 32 层，展开结果最多 10,000 步。被引用动作的 `loop` 不会让片段无限展开，重复片段使用槽位的 `repeat`。

### 拼接两个动作并去除重复边界

假设已有 `rise` 展开为 `[jump/000.png, jump/001.png]`，`fall` 展开为 `[jump/001.png, land/000.png]`。保留前段末帧，令后段从 `start: 1` 开始，合成结果为三步：

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
  }
}
```

也可截短前段：本例将前段设为 `end: 0`，后段从 `0` 开始。按实际需要保留一侧，不要两侧同时去掉。工具不会自动删除重复边界；相同引用也可能表示有意停留，需结合时长判断。

## 持久化 Review 与展示播放

Review 保存于 `workbench.reviews[ID]`。例如，与上面拼接动作对应的独立衔接检查序列：

```json
{
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

Review 的 `mode` 默认 `runtime`，`loop` 是布尔值。保存后用 `qa --review jump_land_check` 查看；`check-composition --action jump_land --review jump_land_check` 比较展开后的引用与时长，并报告边界，不自动去重。组合检查要求 Review 使用运行时模式。

旧 Review 的 `clips` 仍可读取，例如 `{"clips": [{"action": "rise", "start": 0, "end": null, "repeat": 1}]}`。新编排使用 `slots`；已有 Review 使用 `clips` 时可保持原表示。存在 `slots` 时以它为准，不要同时维护两份内容。

动作的 `animation` 仅控制展示播放，可包含 `order`、`durations_ms`、`duration_ms`、`fps`、`loop`。`order` 使用运行时展开结果的 0 起位置，可重排和重复；`durations_ms` 必须与展示播放步数一致，包含重复步。它优先于统一 `duration_ms` 和 `fps`。只有重排而没有显式时长设置时，`slots` 动作保留被选步的时长。日常运行时编排不应通过 `animation.order` 修改。

持久化 Review 的布尔 `loop` 与动作的布尔 `loop`，不要和展示动画 `animation.loop` 或命令输入 `sequence.json` 的整数循环次数混用。后两者 `0` 表示无限循环；命令输入的 `sequence.json` 使用 `steps`，不是持久化 Review 的格式，示例见[操作命令](commands.md)。

[返回 README](../README.md) · [操作命令](commands.md) · [设计理念](design.md)
