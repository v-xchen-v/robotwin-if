# IF-Ext 分轴评测结果表（讨论草案）

> status: 待 review / 尚未填入实验结果。  
> 目的：先确定 7 个 IF-Ext 单轴任务的主结果表结构、聚合口径和诊断指标，再决定是否写入母设计文档。  
> Canonical task inventory：[eval_cfg/README.md](../../eval_cfg/README.md)、[eval_cfg/if_tasks.yml](../../eval_cfg/if_tasks.yml)。  
> 母设计：[docs/features/09-IF-Ext-单轴扩展任务集设计.md](../../docs/features/09-IF-Ext-单轴扩展任务集设计.md)。

## 主结果表：论文式两 panel 设计

> 主表行 = policy，列 = task 下的 mode / 子轴及该 task 的 `Avg.`。所有 policy 均在同一 RoboTwin raw 50-task training set 上 fine-tune；IF-Ext 仅用于 evaluation，不使用任何 IF-Ext training data。  
> 单元格仅填写 success rate 百分数（例如 `72.2`），不重复写 `%` 或 `成功数/总数`；caption 统一声明指标为 SR (%)，完整计数放附表。  
> `Task Avg` 为该任务各 mode 的 macro average；`Overall` 为 7 个 `Task Avg` 的等权平均，不按 episode 数量加权。  
> 正式评测仅使用完整、均衡的 seed group。表中的 `—` 表示尚未填入结果，不表示 `N/A`。  
> Markdown 原生表格不支持合并表头，下面使用内嵌 HTML 表示 sub-column；最终论文 LaTeX 版对应使用 `\multicolumn` + `\cmidrule`。

### Table Xa — Selection / Grounding

**Table Xa. Fine-grained instruction-following results on selection and grounding tasks.** All policies are fine-tuned on the same RoboTwin raw 50-task training set and evaluated on IF-Ext without any IF-Ext training data. We report success rate (%). “Avg.” denotes the macro average over balanced modes within each task.

<div style="overflow-x: auto;">
<table>
  <thead>
    <tr>
      <th rowspan="2">Policy</th>
      <th colspan="3">Verb<br><code>bottle_verb</code></th>
      <th colspan="3">Noun<br><code>pick_diverse_object</code></th>
      <th colspan="5">Attribute<br><code>attribute_select</code></th>
      <th colspan="3">Arm<br><code>arm_select</code></th>
    </tr>
    <tr>
      <th>Pick</th><th>Shake</th><th>Avg.</th>
      <th>Seen</th><th>Unseen</th><th>Avg.</th>
      <th>Color</th><th>Decal</th><th>Shape</th><th>Size</th><th>Avg.</th>
      <th>Left</th><th>Right</th><th>Avg.</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Policy A</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
    </tr>
    <tr>
      <td>Policy B</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
    </tr>
    <tr>
      <td>…</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
    </tr>
  </tbody>
</table>
</div>

### Table Xb — Structured Execution

**Table Xb. Fine-grained instruction-following results on structured execution tasks.** All policies are fine-tuned on the same RoboTwin raw 50-task training set and evaluated on IF-Ext without any IF-Ext training data. We report success rate (%). Sequence labels denote bottom-to-top stacking orders. “Avg.” denotes the macro average over balanced modes within each task; “Overall” is the unweighted macro average over all seven tasks in Tables Xa and Xb.

<div style="overflow-x: auto;">
<table>
  <thead>
    <tr>
      <th rowspan="2">Policy</th>
      <th colspan="7">Sequence<br><code>stack_sequence</code></th>
      <th colspan="6">Spatial<br><code>place_relative</code></th>
      <th colspan="3">Grasp<br><code>grasp_cube_approach</code></th>
      <th rowspan="2">Overall</th>
    </tr>
    <tr>
      <th>RGB</th><th>RBG</th><th>GRB</th><th>GBR</th><th>BRG</th><th>BGR</th><th>Avg.</th>
      <th>Left</th><th>Right</th><th>Front</th><th>Back</th><th>Top</th><th>Avg.</th>
      <th>Top</th><th>Side</th><th>Avg.</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Policy A</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td>
    </tr>
    <tr>
      <td>Policy B</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td>
    </tr>
    <tr>
      <td>…</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>—</td><td>—</td><td>—</td>
      <td>—</td>
    </tr>
  </tbody>
</table>
</div>

`RGB` 等 Sequence 缩写表示 bottom-to-top 的颜色顺序，例如 `RGB` = red bottom、green middle、blue top。Xa/Xb 不单独设置 panel average，避免把 4-task panel 与 3-task panel错误地等权；最终只报告 7-task `Overall`。

## 聚合口径

### Task Avg

对任务 $t$，各 mode 等权：

$$
S_t = \frac{1}{|M_t|}\sum_{m \in M_t} S_{t,m}
$$

完整 balanced seed manifest 下，各 mode 分母相同，因此 task macro 与 task episode-level micro 数值相同；仍明确写作 macro，避免缺失 seed 时发生隐式加权。

### Attribute-Select

主表展示 4 个属性子轴，每个子轴先平均其两个 target value：

$$
S_{\text{color}} = \frac{S_{\text{red}} + S_{\text{blue}}}{2}
$$

同理：

- `decal = mean(cat, dog)`；
- `shape = mean(block, bar)`；
- `size = mean(big, small)`。

任务平均为：

$$
S_{\text{attribute}} = \frac{S_{\text{color}} + S_{\text{decal}} + S_{\text{shape}} + S_{\text{size}}}{4}
$$

`max value-pair gap` 定义为四个属性子轴内 value 对差值绝对值的最大值，用于暴露固定 target/value 偏置：

$$
\max_{a \in \{color,decal,shape,size\}} |S_{a,v_0} - S_{a,v_1}|
$$

### Sequence

六个 bottom-to-top 排列等权：

$$
S_{\text{sequence}} = \frac{1}{6}\sum_{p \in P_6} S_p
$$

默认顺序为 `R→G→B`。诊断 gap 定义为：

$$
\Delta_{\text{prior}} = S_{\text{R→G→B}} - \operatorname{mean}(S_{\text{其他 5 种顺序}})
$$

正值越大，越可能依赖 native 默认堆叠顺序先验。

### IF-Ext Macro

7 个任务等权：

$$
S_{\text{IF-Ext}} = \frac{1}{7}\sum_{t=1}^{7} S_t
$$

不把所有 episode 直接混合为 suite-level micro，否则 mode 较多的 Attribute、Sequence、Spatial 会获得更高隐式权重。

## 建议放在附表或正文的拆分指标

这些信号暂不加入主表，以控制宽度，但正式解释结果时应保留：

- **Noun-Grounding**：Seen/Unseen group micro、per-noun macro、`Seen−Unseen`、`Unseen/Seen retention`；
- **Attribute-Select**：red/blue、cat/dog、block/bar、big/small 八个 value SR；
- **Arm-Select**：`lifted SR`（执行）与 `lifted AND arm_match SR`（严格服从）；
- **Sequence**：`L1 any-stack SR`（执行）与 `L2 ordered-stack SR`（严格服从）；
- **Grasp-Approach**：`lifted SR`（执行）与 `lifted AND orientation_match SR`（严格服从）；
- **同场景对照完整率（候选）**：同一个 scene group 中所有 contrast mode 都成功的 group 比例；是否进入正式指标待讨论。

## 待 review / 待拍板

已确定：

- 主结果采用论文式 `Policy × task sub-columns` 布局，拆成两个 grouped-header panel；所有 policy 均使用同一 RoboTwin raw 50-task fine-tuning protocol，IF-Ext 仅用于 evaluation；
- **Table Xa — Selection / Grounding**：Verb、Noun、Attribute、Arm；
- **Table Xb — Structured Execution**：Sequence、Spatial、Grasp；
- 每个 task 在子轴后保留自己的 `Avg.`；Xa/Xb 不设置 panel average；
- `Overall` 按 7 个 Task Avg 等权计算，暂放在 Xb 最右侧；
- Worst-mode 与诊断 Gap 不占主表列，按需放入附表或正文分析。

1. **Noun 主读数**：Seen/Unseen sub-column 主报 group micro，per-noun macro 放附表；或主表直接改报 per-noun macro。
2. **Attribute 粒度**：主表保留 4 个子轴聚合，8 个 value 放附表；或把 8 个 value 全部展开。
3. **Suite 总分**：是否同时补充但不主推 episode-level micro。
4. **Contrast-complete SR**：是否把同场景完整对照组的 all-correct rate 纳入正式结果，而不只作为诊断。
5. **最终排版宽度**：Xb 有 18 列；转为 LaTeX 后优先尝试 `table*`、缩短表头和收紧 `tabcolsep`，若仍影响可读性再拆出 Sequence 独立 panel，不默认用 `resizebox` 把字体压得过小。
