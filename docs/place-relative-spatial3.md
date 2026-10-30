# Spatial：left / right / on top

当前 `place_relative` 仅评测 left、right、on_top 三种指令，每 block 三回合，共 20 blocks。
三回合共享物体、布局、机器人初态；根据指令把目标放到参考物体的对应位置。

seed 编码保留每场景五个槽位，取 offsets 0、1、4；front/back 已退休，执行入口拒绝这些 offsets。
保留这种稀疏编码可维持现有 scene seed 和原始证据身份。不得重新编号为连续三槽位。
成功采用当前几何条件，没有额外持续稳定时间要求。

[固定 seeds](../seed-manifests/20-blocks/place_relative.json) · [成绩](../result/results.md)
