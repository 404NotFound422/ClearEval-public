# s_trans 方法-组织类型匹配重新评估报告（v2，不考虑荧光）

## 1. 评分理念

用户明确：`s_trans` **仅考察方法与组织类型是否匹配**，不考虑荧光/标记兼容性（荧光兼容由 `s_label` 负责）。
本版评分只基于：

1. **方法设计样本类型**与题目组织是否一致（如 BoneClear 专为骨）。
2. **样本尺寸/透明深度**是否在该方法常规适用范围内（如 TDE 不适合完整全脑）。
3. **目标结构**能否被该方法实现（如超长 CNS 长程投射需要全身/长投射透明法）。
4. **组织-方法层面的副作用**（形态保持、收缩、脆裂等）。

## 2. 一致性指标对比

| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |
|---|---|---|---|---|---|
| machine vs human | 0.633 | 0.459 | 0.750 | 0.518 | 0.728 |
| expert v2 vs human | 0.339 | 0.225 | 0.549 | 0.629 | 0.795 |
| expert v2 vs machine | 0.489 | -0.005 | 0.649 | 0.502 | 0.633 |

## 3. 各题方法-组织匹配评分表

| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 v2 s_trans | 专家理由 |
|---|---|---|---|---|---|---|
| 2 | adult mouse whole brain / neuronal morphology | FDISCO | 2.81 | 2.50 | 2.75 | FDISCO 为成年小鼠全脑优化，透明深度与神经元形态保持兼顾。 |
| 2 | adult mouse whole brain / neuronal morphology | iDISCO+ | 2.81 | 2.00 | 2.75 | iDISCO+ 专为成年小鼠脑/器官设计，透明深度极佳。 |
| 2 | adult mouse whole brain / neuronal morphology | uDISCO | 1.23 | 1.50 | 2.50 | uDISCO 面向全身/小鼠整体透明，可处理成年全脑。 |
| 3 | adult mouse whole brain / cFos+ neurons (IEG) | iDISCO+ | 2.81 | 2.00 | 2.75 | iDISCO+ 为成年小鼠脑/器官设计，是全脑免疫标记的经典组织透明法。 |
| 3 | adult mouse whole brain / cFos+ neurons (IEG) | uDISCO | 1.23 | 1.00 | 2.25 | uDISCO 可透明全脑，但主要用于全身/长投射样本。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | iDISCO+ | 2.81 | 3.00 | 2.75 | iDISCO+ 为成年小鼠脑设计，是全脑免疫标记经典方案。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | uDISCO | 1.23 | 1.25 | 2.25 | uDISCO 可透明全脑。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | iDISCO+ | 2.89 | 2.75 | 2.25 | iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态有风险。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | uDISCO | 1.82 | 0.25 | 2.00 | uDISCO 可处理长段组织，但收缩/脆裂风险对损伤脊髓形态不利。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 2.00 | 2.25 | iDISCO+ 可透明脊髓，但溶剂法形态风险。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 2.00 | 2.00 | uDISCO 可处理长段，但收缩/脆裂风险。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.25 | 2.25 | iDISCO+ 可透明脊髓，但溶剂法形态风险。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.75 | 2.00 | uDISCO 可处理长段，但收缩/脆裂风险。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | BABB | 0.00 | 0.25 | 2.00 | BABB 无电泳，但形态保持有限。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | CUBIC | 3.00 | 3.00 | 2.75 | CUBIC 被动水相法，无电泳，对脊髓损伤节段温和且形态保持好。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | PEGASOS | 0.97 | 0.00 | 1.00 | PEGASOS 对软组织过于剧烈。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.50 | 2.25 | iDISCO+ 为被动溶剂法，无电泳，可透明脊髓。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.50 | 2.00 | uDISCO 被动有机溶剂法，无电泳，但收缩/脆裂风险。 |
| 9 | whole mouse CNS / long-range projection fibers | FDISCO | 2.89 | 1.25 | 2.50 | FDISCO 可透明完整 CNS。 |
| 9 | whole mouse CNS / long-range projection fibers | iDISCO+ | 2.89 | 2.50 | 2.25 | iDISCO+ 可透明完整 CNS。 |
| 9 | whole mouse CNS / long-range projection fibers | uDISCO | 1.82 | 1.25 | 2.75 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 3.00 | 1.75 | CUBIC 对完整 CNS 深度有限。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 0.00 | 1.75 | PEGASOS 对 CNS 形态不利。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 2.75 | 2.25 | iDISCO+ 可透明完整 CNS。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.50 | 2.75 | uDISCO 最适合完整 CNS 长程投射。 |
| 11 | whole mouse CNS / long-range connections | iDISCO+ | 2.89 | 3.00 | 2.25 | iDISCO+ 可透明完整 CNS。 |
| 11 | whole mouse CNS / long-range connections | uDISCO | 1.82 | 2.25 | 2.75 | uDISCO 最适合完整 CNS 长程投射。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 1.75 | 2.75 | CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | FDISCO | 2.89 | 3.00 | 2.00 | FDISCO 有机溶剂，仍有收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 2.75 | 1.00 | PEGASOS 收缩大，不适合。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 1.75 | 1.75 | iDISCO+ 有机溶剂，收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.25 | 2.00 | uDISCO 可透明完整 CNS，但有机溶剂有一定收缩。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.75 | iDISCO+ 为成年小鼠脑设计，是全脑免疫标记的经典组织透明法。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 2.25 | 2.25 | uDISCO 可透明全脑。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | CUBIC | 3.00 | 3.00 | 2.50 | CUBIC 支持全脑免疫标记。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | iDISCO+ | 2.81 | 2.25 | 2.75 | iDISCO+ 适合全脑 Aβ 免疫标记。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | uDISCO | 1.23 | 1.50 | 2.25 | uDISCO 可透明全脑。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | iDISCO+ | 2.81 | 3.00 | 2.75 | iDISCO+ 适合全脑 Aβ 免疫标记与定量。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | uDISCO | 1.23 | 1.00 | 2.25 | uDISCO 可透明全脑。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | CUBIC | 3.00 | 1.50 | 2.75 | CUBIC 水相法更适合长时间抗体渗透，是避免溶剂免疫标记失败的首选。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | SWITCH | 3.00 | 2.25 | 2.75 | SWITCH 专为均匀免疫标记设计，水相法无溶剂问题。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.50 | iDISCO+ 仍为全脑免疫标记经典，但需优化抗体孵育时间/浓度。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 1.25 | 2.00 | uDISCO 属有机溶剂，免疫标记信号可能仍弱。 |
| 17 | GBM mouse brain block / tumor + vasculature | CUBIC | 2.79 | 3.00 | 2.75 | CUBIC 对肿瘤脑组织温和，可保留血管网络与肿瘤边界。 |
| 17 | GBM mouse brain block / tumor + vasculature | FDISCO | 3.00 | 2.75 | 2.25 | FDISCO 可透明成年小鼠脑块。 |
| 17 | GBM mouse brain block / tumor + vasculature | iDISCO+ | 3.00 | 2.00 | 2.25 | iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。 |
| 17 | GBM mouse brain block / tumor + vasculature | uDISCO | 1.82 | 1.50 | 2.00 | uDISCO 对肿瘤软组织形态保持风险较大。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | CUBIC | 2.79 | 2.00 | 2.75 | CUBIC 对肿瘤脑组织温和，可保留血管网络与 BBB 结构。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | FDISCO | 3.00 | 3.00 | 2.25 | FDISCO 可透明成年小鼠脑块。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | iDISCO+ | 3.00 | 2.25 | 2.25 | iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB | uDISCO | 1.82 | 1.50 | 2.00 | uDISCO 对肿瘤软组织形态保持风险较大。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | FDISCO | 3.00 | 2.75 | 2.25 | FDISCO 可透明成年小鼠脑块。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | iDISCO+ | 3.00 | 2.25 | 2.25 | iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | uDISCO | 1.82 | 1.25 | 2.00 | uDISCO 对肿瘤软组织形态保持风险较大。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | FDISCO | 3.00 | 2.25 | 1.75 | FDISCO 有机溶剂对肿瘤血管形态有风险。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | PEGASOS | 1.02 | 0.75 | 0.75 | PEGASOS 对脑组织过于剧烈，不适合。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | SWITCH | 2.81 | 3.00 | 2.25 | SWITCH 水相法形态保持较好。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | ScaleS | 2.73 | 3.00 | 2.75 | ScaleS 形态保持优秀，是 CUBIC 失败后的优选替代。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | iDISCO+ | 3.00 | 3.00 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | CUBIC | 3.00 | 3.00 | 2.25 | CUBIC 适用于小鼠脑块。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | FDISCO | 2.71 | 3.00 | 2.50 | FDISCO 可透明成年小鼠脑块。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | PEGASOS | 0.00 | 0.25 | 0.75 | PEGASOS 对脑块过于剧烈。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | ScaleS | 3.00 | 3.00 | 2.75 | ScaleS 形态保持优秀，极适合 3 mm 脑块高分辨率成像。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | SeeDB2 | 3.00 | 3.00 | 2.75 | SeeDB2 形态保持好，适合脑片/小块。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | iDISCO+ | 2.68 | 1.75 | 2.00 | iDISCO+ 可透明 3 mm 脑块；荧光淬灭问题归入 s_label。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | uDISCO | 0.00 | 0.25 | 1.75 | uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。 |

## 4. 机器 vs 专家 v2 差异显著案例

| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v2 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| openai_deepseek-reasoner | 8 | BABB | 0.00 | 2.00 | 2.00 | BABB 无电泳，但形态保持有限。 |
| openai_qwen3-235b | 21 | uDISCO | 0.00 | 1.75 | 1.75 | uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。 |
| glm4.7-unthinking | 2 | uDISCO | 1.23 | 2.50 | 1.27 | uDISCO 面向全身/小鼠整体透明，可处理成年全脑。 |
| openai_deepseek-chat | 2 | uDISCO | 1.23 | 2.50 | 1.27 | uDISCO 面向全身/小鼠整体透明，可处理成年全脑。 |
| openai_deepseek-reasoner | 2 | uDISCO | 1.23 | 2.50 | 1.27 | uDISCO 面向全身/小鼠整体透明，可处理成年全脑。 |
| openai_qwen3-32b | 10 | CUBIC | 3.00 | 1.75 | 1.25 | CUBIC 对完整 CNS 深度有限。 |
| gemini-3-flash | 20 | FDISCO | 3.00 | 1.75 | 1.25 | FDISCO 有机溶剂对肿瘤血管形态有风险。 |
| gemini-3-pro | 20 | FDISCO | 3.00 | 1.75 | 1.25 | FDISCO 有机溶剂对肿瘤血管形态有风险。 |
| glm4.7-unthinking | 20 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_deepseek-chat | 20 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_deepseek-reasoner | 20 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-14b | 20 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-32b | 20 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-235b | 12 | iDISCO+ | 2.89 | 1.75 | 1.14 | iDISCO+ 有机溶剂，收缩风险。 |
| openai_qwen3-max | 12 | iDISCO+ | 2.89 | 1.75 | 1.14 | iDISCO+ 有机溶剂，收缩风险。 |
| openai_deepseek-chat | 3 | uDISCO | 1.23 | 2.25 | 1.02 | uDISCO 可透明全脑，但主要用于全身/长投射样本。 |
| openai_deepseek-reasoner | 3 | uDISCO | 1.23 | 2.25 | 1.02 | uDISCO 可透明全脑，但主要用于全身/长投射样本。 |
| glm4.7-unthinking | 4 | uDISCO | 1.23 | 2.25 | 1.02 | uDISCO 可透明全脑。 |
| openai_deepseek-chat | 4 | uDISCO | 1.23 | 2.25 | 1.02 | uDISCO 可透明全脑。 |
| openai_deepseek-reasoner | 4 | uDISCO | 1.23 | 2.25 | 1.02 | uDISCO 可透明全脑。 |

## 5. 人工 vs 专家 v2 差异显著案例

| 模型 | 题号 | 方法 | 人工 s_trans | 专家 v2 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| openai_deepseek-chat | 9 | uDISCO | 0.00 | 2.75 | 2.75 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| openai_deepseek-reasoner | 4 | uDISCO | 0.00 | 2.25 | 2.25 | uDISCO 可透明全脑。 |
| openai_qwen3-32b | 12 | CUBIC | 0.50 | 2.75 | 2.25 | CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。 |
| openai_deepseek-reasoner | 2 | uDISCO | 0.50 | 2.50 | 2.00 | uDISCO 面向全身/小鼠整体透明，可处理成年全脑。 |
| openai_deepseek-reasoner | 6 | uDISCO | 0.00 | 2.00 | 2.00 | uDISCO 可处理长段，但收缩/脆裂风险。 |
| gemini-3-pro | 15 | iDISCO+ | 0.75 | 2.75 | 2.00 | iDISCO+ 适合全脑 Aβ 免疫标记与定量。 |
| openai_deepseek-chat | 5 | uDISCO | 0.25 | 2.00 | 1.75 | uDISCO 可处理长段组织，但收缩/脆裂风险对损伤脊髓形态不利。 |
| openai_deepseek-reasoner | 8 | BABB | 0.25 | 2.00 | 1.75 | BABB 无电泳，但形态保持有限。 |
| gemini-3-pro | 10 | PEGASOS | 0.00 | 1.75 | 1.75 | PEGASOS 对 CNS 形态不利。 |
| gemini-3-flash | 12 | PEGASOS | 2.75 | 1.00 | 1.75 | PEGASOS 收缩大，不适合。 |
| openai_qwen3-14b | 14 | iDISCO+ | 1.00 | 2.75 | 1.75 | iDISCO+ 适合全脑 Aβ 免疫标记。 |
| openai_deepseek-reasoner | 19 | uDISCO | 0.25 | 2.00 | 1.75 | uDISCO 对肿瘤软组织形态保持风险较大。 |
| openai_qwen3-32b | 4 | iDISCO+ | 1.25 | 2.75 | 1.50 | iDISCO+ 为成年小鼠脑设计，是全脑免疫标记经典方案。 |
| gemini-3-flash | 9 | uDISCO | 1.25 | 2.75 | 1.50 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| glm4.7-unthinking | 9 | uDISCO | 1.25 | 2.75 | 1.50 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| openai_gpt-5.2-thinking | 11 | iDISCO+ | 0.75 | 2.25 | 1.50 | iDISCO+ 可透明完整 CNS。 |
| openai_deepseek-reasoner | 16 | uDISCO | 0.50 | 2.00 | 1.50 | uDISCO 属有机溶剂，免疫标记信号可能仍弱。 |
| openai_qwen3-235b | 21 | uDISCO | 0.25 | 1.75 | 1.50 | uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。 |
| openai_deepseek-chat | 3 | uDISCO | 1.00 | 2.25 | 1.25 | uDISCO 可透明全脑，但主要用于全身/长投射样本。 |
| openai_deepseek-reasoner | 3 | uDISCO | 1.00 | 2.25 | 1.25 | uDISCO 可透明全脑，但主要用于全身/长投射样本。 |

## 6. 分布对比

- **机器 s_trans**: mean=2.526, std=0.689, min=0.000, max=3.000
- **人工 s_trans**: mean=2.210, std=0.817, min=0.000, max=3.000
- **专家 v2 s_trans**: mean=2.346, std=0.425, min=0.750, max=2.750

## 7. 逐题一致性

| 题号 | 机器 vs 人工 (r/ρ/ICC) | 专家 v2 vs 人工 (r/ρ/ICC) | 专家 v2 vs 机器 (r/ρ/ICC) |
|---|---|---|---|
| 2 | 0.87/0.84/0.93 | 0.87/0.84/0.48 | 1.00/1.00/0.51 |
| 3 | 0.73/0.66/0.70 | 0.73/0.66/0.30 | 1.00/1.00/0.75 |
| 4 | 0.78/0.75/0.81 | 0.78/0.75/0.46 | 1.00/1.00/0.72 |
| 5 | 0.77/0.61/0.73 | 0.77/0.61/0.45 | 1.00/1.00/0.16 |
| 6 | 0.60/0.49/0.54 | 0.60/0.49/0.44 | 1.00/1.00/0.16 |
| 7 | 0.02/0.03/0.17 | 0.02/0.03/0.33 | 1.00/1.00/0.16 |
| 8 | 0.90/0.92/0.91 | 0.89/0.93/0.82 | 0.78/0.96/0.83 |
| 9 | 0.63/0.79/0.68 | -0.73/-0.79/-0.11 | -0.96/-1.00/-0.51 |
| 10 | 0.82/0.78/0.88 | 0.06/-0.31/0.36 | -0.27/-0.50/0.12 |
| 11 | 0.36/0.56/0.60 | -0.36/-0.56/0.11 | -1.00/-1.00/-0.58 |
| 12 | 0.00/-0.03/0.33 | 0.06/0.19/0.37 | 0.86/0.88/0.87 |
| 13 | 0.54/0.54/0.74 | 0.54/0.54/0.57 | 1.00/1.00/0.75 |
| 14 | 0.40/0.50/0.56 | 0.24/0.18/0.26 | 0.90/0.45/0.72 |
| 15 | 0.56/0.53/0.69 | 0.56/0.53/0.41 | 1.00/1.00/0.75 |
| 16 | 0.68/0.32/0.66 | 0.56/0.32/0.44 | 0.95/1.00/0.77 |
| 17 | 0.52/0.28/0.57 | 0.57/0.63/0.58 | 0.52/0.45/0.17 |
| 18 | 0.22/0.29/0.41 | -0.12/-0.06/0.21 | 0.52/0.45/0.17 |
| 19 | 0.74/0.60/0.63 | 0.74/0.60/0.46 | 1.00/1.00/0.09 |
| 20 | 0.79/0.40/0.82 | 0.74/0.57/0.71 | 0.75/0.05/0.48 |
| 21 | 0.92/0.88/0.95 | 0.81/0.73/0.87 | 0.89/0.83/0.87 |

## 8. 结论与建议

1. v2 专家评分严格限定在“方法-组织类型匹配”，不再因荧光淬灭而压低 iDISCO+/uDISCO 等溶剂法的分数。
2. 与机器 s_trans（RI 公式）相比，v2 评分在方法设计用途、样本尺寸、形态保持等维度上做了人工修正。
3. 若专家 v2 与人工评分仍有显著差异，需进一步澄清：人工评分是否确实仅基于组织匹配，还是仍混入了荧光/标记/时间等其它维度。
4. **建议**：由领域专家复核 v2 评分表；确认后可写入 `human_evaluation.effectiveness.s_trans.score`。
