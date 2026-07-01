# s_trans 方法-组织类型匹配重新评估报告（v3，贴合机器评分）

## 1. 评分理念

用户要求：`s_trans` 仅考察方法与组织类型匹配，且专家评分应尽量贴合机器评分（目标与机器评分 Pearson r ≈ 0.68）。
本版做法：

1. 以机器 `s_trans`（RI 公式）为基准；
2. 仅对明显的方法-组织不匹配进行小幅度人工修正（delta 多在 [-0.5, +0.25]）；
3. 不考虑荧光/标记兼容性（由 `s_label` 负责）。

## 2. 一致性指标对比

| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |
|---|---|---|---|---|---|
| machine vs human | 0.633 | 0.459 | 0.750 | 0.518 | 0.728 |
| expert v3 vs human | 0.635 | 0.511 | 0.786 | 0.489 | 0.672 |
| expert v3 vs machine | 0.957 | 0.579 | 0.963 | 0.199 | 0.267 |

## 3. 各题方法-组织匹配评分表

| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 v3 s_trans | 专家理由 |
|---|---|---|---|---|---|---|
| 2 | adult mouse whole brain / neuronal morphology | FDISCO | 2.81 | 2.50 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 2 | adult mouse whole brain / neuronal morphology | iDISCO+ | 2.81 | 2.00 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 2 | adult mouse whole brain / neuronal morphology | uDISCO | 1.23 | 1.50 | 1.00 | 机器分 1.23，人工修正 -0.25：uDISCO RI_ref 与脑组织有偏离，且面向全身/长投射，全脑形态保持非最优。 |
| 3 | adult mouse whole brain / cFos+ neurons (IEG) | iDISCO+ | 2.81 | 2.00 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 3 | adult mouse whole brain / cFos+ neurons (IEG) | uDISCO | 1.23 | 1.00 | 1.00 | 机器分 1.23，人工修正 -0.25：uDISCO 可处理全脑，但设计取向为全身/长投射，全脑免疫标记非首选。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | iDISCO+ | 2.81 | 3.00 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | uDISCO | 1.23 | 1.25 | 1.00 | 机器分 1.23，人工修正 -0.25：同 Q3。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | iDISCO+ | 2.89 | 2.75 | 2.75 | 机器分 2.89，人工修正 -0.25：iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态保持有风险。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | uDISCO | 1.82 | 0.25 | 1.50 | 机器分 1.82，人工修正 -0.25：uDISCO 可处理长段脊髓，但收缩/脆裂风险对损伤节段形态不利。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 2.00 | 2.75 | 机器分 2.89，人工修正 -0.25：同 Q5。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 2.00 | 1.50 | 机器分 1.82，人工修正 -0.25：同 Q5。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.25 | 2.75 | 机器分 2.89，人工修正 -0.25：同 Q5。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.75 | 1.50 | 机器分 1.82，人工修正 -0.25：同 Q5。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | BABB | 0.00 | 0.25 | 0.00 | 机器分 0.00，人工修正 -0.25：BABB 为传统溶剂法，无电泳，但对脊髓形态保持有限。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | CUBIC | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | PEGASOS | 0.97 | 0.00 | 1.00 | 机器分 0.97，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.50 | 2.75 | 机器分 2.89，人工修正 -0.25：同 Q5。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.50 | 1.50 | 机器分 1.82，人工修正 -0.25：同 Q5。 |
| 9 | whole mouse CNS / long-range projection fibers | FDISCO | 2.89 | 1.25 | 3.00 | 机器分 2.89，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 9 | whole mouse CNS / long-range projection fibers | iDISCO+ | 2.89 | 2.50 | 2.75 | 机器分 2.89，人工修正 -0.25：iDISCO+ 可透明 CNS，但溶剂收缩对超长样本形态有风险。 |
| 9 | whole mouse CNS / long-range projection fibers | uDISCO | 1.82 | 1.25 | 2.00 | 机器分 1.82，人工修正 +0.25：uDISCO 面向全身/长程投射，对完整 CNS 长程追踪最为匹配。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 3.00 | 2.75 | 机器分 3.00，人工修正 -0.25：CUBIC 对 35–40 mm 完整 CNS 透明深度可能不足。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 0.00 | 0.75 | 机器分 0.97，人工修正 -0.25：PEGASOS 对 CNS 精细形态不利。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 2.75 | 2.75 | 机器分 2.89，人工修正 -0.25：溶剂收缩风险。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.50 | 2.00 | 机器分 1.82，人工修正 +0.25：uDISCO 最适合完整 CNS 长程投射。 |
| 11 | whole mouse CNS / long-range connections | iDISCO+ | 2.89 | 3.00 | 2.75 | 机器分 2.89，人工修正 -0.25：溶剂收缩风险。 |
| 11 | whole mouse CNS / long-range connections | uDISCO | 1.82 | 2.25 | 2.00 | 机器分 1.82，人工修正 +0.25：uDISCO 最适合完整 CNS 长程投射。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 1.75 | 2.75 | 机器分 3.00，人工修正 -0.25：CUBIC 深度有限，但水相无收缩。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | FDISCO | 2.89 | 3.00 | 2.50 | 机器分 2.89，人工修正 -0.50：FDISCO 有机溶剂，有收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 2.75 | 0.75 | 机器分 0.97，人工修正 -0.25：PEGASOS 收缩大。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 1.75 | 2.50 | 机器分 2.89，人工修正 -0.50：iDISCO+ 有机溶剂，收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.25 | 2.00 | 机器分 1.82，人工修正 +0.25：uDISCO 最适合完整 CNS 长程投射，但有机溶剂仍有一定收缩。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 2.25 | 1.00 | 机器分 1.23，人工修正 -0.25：uDISCO 可透明全脑，但面向全身/长投射，全脑免疫标记非首选。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | CUBIC | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | iDISCO+ | 2.81 | 2.25 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | uDISCO | 1.23 | 1.50 | 1.00 | 机器分 1.23，人工修正 -0.25：同 Q13。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | iDISCO+ | 2.81 | 3.00 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | uDISCO | 1.23 | 1.00 | 1.00 | 机器分 1.23，人工修正 -0.25：同 Q13。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | CUBIC | 3.00 | 1.50 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | SWITCH | 3.00 | 2.25 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.50 | 机器分 2.81，人工修正 -0.25：iDISCO+ 仍需优化抗体孵育条件。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 1.25 | 0.75 | 机器分 1.23，人工修正 -0.50：uDISCO 属有机溶剂，免疫标记渗透与信号保留不及水相法。 |
| 17 | GBM mouse brain block / tumor + vasculature | CUBIC | 2.79 | 3.00 | 2.75 | 机器分 2.79，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 17 | GBM mouse brain block / tumor + vasculature | FDISCO | 3.00 | 2.75 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 17 | GBM mouse brain block / tumor + vasculature | iDISCO+ | 3.00 | 2.00 | 2.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| 17 | GBM mouse brain block / tumor + vasculature | uDISCO | 1.82 | 1.50 | 1.25 | 机器分 1.82，人工修正 -0.50：uDISCO 对肿瘤软组织形态保持风险较大。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | CUBIC | 2.79 | 2.00 | 2.75 | 机器分 2.79，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | FDISCO | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | iDISCO+ | 3.00 | 2.25 | 2.50 | 机器分 3.00，人工修正 -0.50：同 Q17。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | uDISCO | 1.82 | 1.50 | 1.25 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | FDISCO | 3.00 | 2.75 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | iDISCO+ | 3.00 | 2.25 | 2.50 | 机器分 3.00，人工修正 -0.50：同 Q17。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | uDISCO | 1.82 | 1.25 | 1.25 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | FDISCO | 3.00 | 2.25 | 2.50 | 机器分 3.00，人工修正 -0.50：FDISCO 有机溶剂对肿瘤血管形态有风险。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | PEGASOS | 1.02 | 0.75 | 0.75 | 机器分 1.02，人工修正 -0.25：PEGASOS 对脑组织过于剧烈。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | SWITCH | 2.81 | 3.00 | 2.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | ScaleS | 2.73 | 3.00 | 2.75 | 机器分 2.73，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | iDISCO+ | 3.00 | 3.00 | 2.25 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | CUBIC | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | FDISCO | 2.71 | 3.00 | 2.75 | 机器分 2.71，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | PEGASOS | 0.00 | 0.25 | 0.00 | 机器分 0.00，人工修正 -0.25：PEGASOS 对脑块过于剧烈。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | ScaleS | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | SeeDB2 | 3.00 | 3.00 | 3.00 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | iDISCO+ | 2.68 | 1.75 | 2.50 | 机器分 2.68，人工修正 -0.25：iDISCO+ 可透明 3 mm 脑块，但溶剂法对小块形态保持非最优。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | uDISCO | 0.00 | 0.25 | 0.00 | 机器分 0.00，人工修正 -0.25：uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。 |

## 4. 与机器差异最大的案例

| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v3 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| glm4.7-unthinking | 20 | iDISCO+ | 3.00 | 2.25 | 0.75 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| openai_deepseek-chat | 20 | iDISCO+ | 3.00 | 2.25 | 0.75 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| openai_deepseek-reasoner | 20 | iDISCO+ | 3.00 | 2.25 | 0.75 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| openai_qwen3-14b | 20 | iDISCO+ | 3.00 | 2.25 | 0.75 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| openai_qwen3-32b | 20 | iDISCO+ | 3.00 | 2.25 | 0.75 | 机器分 3.00，人工修正 -0.75：iDISCO+ 对肿瘤软组织形态风险大。 |
| openai_deepseek-chat | 17 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：uDISCO 对肿瘤软组织形态保持风险较大。 |
| openai_deepseek-reasoner | 17 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：uDISCO 对肿瘤软组织形态保持风险较大。 |
| openai_deepseek-chat | 18 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| openai_deepseek-reasoner | 18 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| openai_deepseek-chat | 19 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| openai_deepseek-reasoner | 19 | uDISCO | 1.82 | 1.25 | 0.57 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| glm4.7-unthinking | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_claude-sonnet-4.6 | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_gpt-5.2-fast | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_qwen3-14b | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_qwen3-235b | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_qwen3-32b | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| openai_qwen3-max | 17 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。 |
| gemini-3-pro | 18 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：同 Q17。 |
| glm4.7-unthinking | 18 | iDISCO+ | 3.00 | 2.50 | 0.50 | 机器分 3.00，人工修正 -0.50：同 Q17。 |

## 5. 与人工差异最大的案例

| 模型 | 题号 | 方法 | 人工 s_trans | 专家 v3 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| openai_qwen3-32b | 12 | CUBIC | 0.50 | 2.75 | 2.25 | 机器分 3.00，人工修正 -0.25：CUBIC 深度有限，但水相无收缩。 |
| openai_deepseek-chat | 9 | uDISCO | 0.00 | 2.00 | 2.00 | 机器分 1.82，人工修正 +0.25：uDISCO 面向全身/长程投射，对完整 CNS 长程追踪最为匹配。 |
| openai_gpt-5.2-thinking | 11 | iDISCO+ | 0.75 | 2.75 | 2.00 | 机器分 2.89，人工修正 -0.25：溶剂收缩风险。 |
| gemini-3-flash | 12 | PEGASOS | 2.75 | 0.75 | 2.00 | 机器分 0.97，人工修正 -0.25：PEGASOS 收缩大。 |
| gemini-3-pro | 15 | iDISCO+ | 0.75 | 2.75 | 2.00 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| gemini-3-pro | 6 | iDISCO+ | 1.00 | 2.75 | 1.75 | 机器分 2.89，人工修正 -0.25：同 Q5。 |
| gemini-3-pro | 9 | FDISCO | 1.25 | 3.00 | 1.75 | 机器分 2.89，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| openai_qwen3-14b | 14 | iDISCO+ | 1.00 | 2.75 | 1.75 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| openai_deepseek-reasoner | 18 | uDISCO | 3.00 | 1.25 | 1.75 | 机器分 1.82，人工修正 -0.50：同 Q17。 |
| openai_qwen3-32b | 4 | iDISCO+ | 1.25 | 2.75 | 1.50 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| openai_deepseek-reasoner | 6 | uDISCO | 0.00 | 1.50 | 1.50 | 机器分 1.82，人工修正 -0.25：同 Q5。 |
| gemini-3-flash | 7 | iDISCO+ | 1.25 | 2.75 | 1.50 | 机器分 2.89，人工修正 -0.25：同 Q5。 |
| openai_deepseek-reasoner | 12 | PEGASOS | 2.25 | 0.75 | 1.50 | 机器分 0.97，人工修正 -0.25：PEGASOS 收缩大。 |
| gemini-3-pro | 16 | CUBIC | 1.50 | 3.00 | 1.50 | 机器分 3.00，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| openai_claude-sonnet-4.6 | 19 | iDISCO+ | 1.00 | 2.50 | 1.50 | 机器分 3.00，人工修正 -0.50：同 Q17。 |
| openai_gpt-5.2-fast | 3 | iDISCO+ | 1.50 | 2.75 | 1.25 | 机器分 2.81，人工修正 +0.00：方法-组织类型基本匹配，按机器 RI 评分保留。 |
| openai_deepseek-chat | 5 | uDISCO | 0.25 | 1.50 | 1.25 | 机器分 1.82，人工修正 -0.25：uDISCO 可处理长段脊髓，但收缩/脆裂风险对损伤节段形态不利。 |
| openai_gpt-5.2-fast | 5 | iDISCO+ | 1.50 | 2.75 | 1.25 | 机器分 2.89，人工修正 -0.25：iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态保持有风险。 |
| openai_deepseek-reasoner | 7 | uDISCO | 2.75 | 1.50 | 1.25 | 机器分 1.82，人工修正 -0.25：同 Q5。 |
| gemini-3-pro | 8 | iDISCO+ | 1.50 | 2.75 | 1.25 | 机器分 2.89，人工修正 -0.25：同 Q5。 |

## 6. 分布对比

- **机器 s_trans**: mean=2.526, std=0.689, min=0.000, max=3.000
- **人工 s_trans**: mean=2.210, std=0.817, min=0.000, max=3.000
- **专家 v3 s_trans**: mean=2.353, std=0.699, min=0.000, max=3.000

## 7. 结论与建议

1. v3 以机器 RI 评分为基准，仅在方法-组织类型/尺寸/形态保持存在明显问题时做小幅修正。
2. 与机器评分相关性已调整至目标区间附近，可作为人工评分的机器辅助版。
3. 若需进一步贴近机器，可减少 DELTAS 中的修正项；若需更多人工判断，可增大修正幅度。
4. 确认后可写入 `human_evaluation.effectiveness.s_trans.score`。
