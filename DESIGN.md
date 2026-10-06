## Agent 生成 spritesheets 的工作流搭建
1. source/ -> source_sprites/
> 将 sprites 从 source 切出来，统一脚本，尽量不做缩放/移位等操作。
2. source_sprites/ -> porcessed_sprites/ -> sprites/
> 对 sprites 进行缩放/移位等操作，处理并确认无误后，放置到 processed_sprites/，再人工/Agent 确认后，放置到 sprites/。（修改顺序时，需要手动调整编号）
> 对于我们的实现来说，直接 source/ -> porcessed_sprites/ 也是可以的了。
> 或者，也可以不手动放置到 sprites/，而是在配置中说明使用哪些 proceesed_sprites/ 中的 sprites 资源，利用脚本自动拉取 processed_sprites/ 中的 sprites 资源，生成 sprites/。（这样可以自动完成顺序编号）
3. sprites/ -> spritesheets/ & webp/
> 将 sprites 进行打包，生成 spritesheets/ 和 webp/，spritesheets/ 用于游戏运行，webp/ 用于网页展示。
> 生成 webp/ 需要支持配置 animation，即配置每帧持续时间，帧的执行顺序等，最终生成 webp/ 的动画效果。（仅供展示使用，而非游戏运行使用）

## 工作流开始 prompt
为 2d 动作类游戏提供动作资源：参考 <空洞骑士> 动作模版 [HollowKnight](HollowKnight/Knight) 和 <大肥鱼> 角色人设图 [dafeiyu-game-identity.png](asserts/refer/dafeiyu-game-identity.png) （提示：生成完 idle 动作之后，也可以额外提供 idle 作为参考），生成可以 <大肥鱼> 的高清晰度的 sprites。
<大肥鱼> 的动作至少包括以下：
- idle（站立） 
- run（奔跑） 
- jump（跳跃）
- land （落地）
- dash（冲刺） 
- attack（普通攻击） 
- hurt（受伤） 
- die（死亡） 
- attack_special（技能攻击） 
请确保所有动作都流畅自然，符合2D动作游戏的标准。
最终验收标准：提供生成的 spritesheet 和 切好的 sprites 资源（默认顺序播放），确保动作有高清晰度，且流程自然（动作切换也是自然的，即每个动作人物体型尺寸等不会有过大变化）

> 注意事项：提供的 sheet.json 是 <空洞骑士> 素材切割，我们不需要按照它的切割方式，<空洞骑士> 素材仅提供动作参考，而非强制对准！你需要自己维护大肥鱼角色的 anchor，尺寸等元数据；如果需要，请写 python 脚本完成空洞骑士模版素材的放大，大肥鱼 spritesheet 的切割等实际功能。
>（不建议对生成的素材做太大缩放，会影响清晰度）