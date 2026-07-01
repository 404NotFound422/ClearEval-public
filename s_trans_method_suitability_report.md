# s_trans 方法适合度重新评估报告

## 1. 评分理念与维度

原 `s_trans` 仅基于 RI 域匹配（`RI_tissue` vs `RI_method_ref`）计算连续分。
专家在判断“方法-组织是否匹配”时，会同时考虑：

1. **样本类型匹配**：方法 historically 为哪类样本设计（如 BoneClear 专为骨、EyeCi 专为眼）。
2. **目标结构适配**：方法能否满足透明深度、分辨率、长程追踪等需求。
3. **标记兼容性**：内源 FP 保留 vs 免疫标记/染料渗透能力。
4. **特殊需求**：形态保持、避免收缩、避免电泳损伤、超长样本等。

本报告据此对 240 条记录重新给出 0–3 分（0.25 步进）的方法适合度评分。

## 2. 一致性指标对比

| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |
|---|---|---|---|---|---|
| machine vs human | 0.633 | 0.459 | 0.750 | 0.518 | 0.728 |
| expert vs human | 0.085 | 0.015 | 0.403 | 0.764 | 0.967 |
| expert vs machine | 0.178 | -0.231 | 0.437 | 0.679 | 0.870 |

## 3. 各题方法适合度评分表

| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 s_trans | 专家理由 |
|---|---|---|---|---|---|---|
| 2 | adult mouse whole brain / neuronal morphology (soma/axon/den | FDISCO | 2.81 | 2.50 | 2.75 | FDISCO 为成年小鼠全脑 FP 保留优化，适合神经元形态三维成像。 |
| 2 | adult mouse whole brain / neuronal morphology (soma/axon/den | iDISCO+ | 2.81 | 2.00 | 0.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| 2 | adult mouse whole brain / neuronal morphology (soma/axon/den | uDISCO | 1.23 | 1.50 | 2.25 | uDISCO 可透明全脑并保留部分 FP，但对内源 GFP 淬灭比 FDISCO 重。 |
| 3 | adult mouse whole brain / cFos+ activated neurons (IEG) | iDISCO+ | 2.81 | 2.00 | 2.75 | iDISCO+ 对全脑免疫标记和透明效果极佳，是 IEG 全脑成像的经典方案。 |
| 3 | adult mouse whole brain / cFos+ activated neurons (IEG) | uDISCO | 1.23 | 1.00 | 2.25 | uDISCO 可透明全脑并兼容免疫标记，但有机溶剂对内源信号淬灭较重。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | iDISCO+ | 2.81 | 3.00 | 2.75 | iDISCO+ 对全脑免疫标记和透明效果极佳，是 IEG 全脑成像的经典方案。 |
| 4 | adult mouse whole brain / activated neurons (IEG) | uDISCO | 1.23 | 1.25 | 2.25 | uDISCO 可透明全脑并兼容免疫标记。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | iDISCO+ | 2.89 | 2.75 | 2.25 | iDISCO+ 可透明脊髓并支持免疫标记，但会淬灭内源 FP。 |
| 5 | rat spinal cord injury segment / axons/regenerated fibers | uDISCO | 1.82 | 0.25 | 2.75 | uDISCO 擅长全身/长距离投射透明，适合长脊髓段轴突追踪。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 2.00 | 2.25 | iDISCO+ 可透明脊髓。 |
| 6 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 2.00 | 2.75 | uDISCO 擅长长距离投射透明。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.25 | 2.25 | iDISCO+ 可透明脊髓。 |
| 7 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.75 | 2.75 | uDISCO 擅长长距离投射透明。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | BABB | 0.00 | 0.25 | 2.00 | 无电泳，但 FP 保留有限。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | CUBIC | 3.00 | 3.00 | 2.50 | CUBIC 被动水相法，无电泳，对脊髓损伤节段温和。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | PEGASOS | 0.97 | 0.00 | 1.50 | PEGASOS 形态风险大。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | iDISCO+ | 2.89 | 1.50 | 2.25 | iDISCO+ 为被动溶剂法，无电泳，但会淬灭 FP。 |
| 8 | rat spinal cord injury segment / regenerated + mature axons | uDISCO | 1.82 | 1.50 | 2.75 | uDISCO 为被动有机溶剂法，无电泳，适合长脊髓段。 |
| 9 | whole mouse CNS / long-range projection fibers | FDISCO | 2.89 | 1.25 | 2.50 | FDISCO 可透明全 CNS 并保留 FP，但 uDISCO 对超长样本更经典。 |
| 9 | whole mouse CNS / long-range projection fibers | iDISCO+ | 2.89 | 2.50 | 2.25 | iDISCO+ 可透明全 CNS，但会淬灭内源 FP。 |
| 9 | whole mouse CNS / long-range projection fibers | uDISCO | 1.82 | 1.25 | 3.00 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 3.00 | 1.75 | CUBIC 对完整 CNS 深度有限。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 0.00 | 1.75 | PEGASOS 收缩大。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 2.75 | 2.25 | iDISCO+ 可透明全 CNS。 |
| 10 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.50 | 3.00 | uDISCO 最适合完整 CNS 长程投射。 |
| 11 | whole mouse CNS / long-range connections | iDISCO+ | 2.89 | 3.00 | 2.25 | iDISCO+ 可透明全 CNS。 |
| 11 | whole mouse CNS / long-range connections | uDISCO | 1.82 | 2.25 | 3.00 | uDISCO 最适合完整 CNS 长程投射。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | CUBIC | 3.00 | 1.75 | 2.75 | CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | FDISCO | 2.89 | 3.00 | 2.25 | FDISCO 保留 FP 但有机溶剂仍有收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | PEGASOS | 0.97 | 2.75 | 1.25 | PEGASOS 收缩大，不适合。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | iDISCO+ | 2.89 | 1.75 | 2.00 | iDISCO+ 有机溶剂，收缩风险。 |
| 12 | whole mouse CNS / long-range projections + axon skeleton | uDISCO | 1.82 | 2.25 | 2.50 | uDISCO 可透明完整 CNS，但属有机溶剂法，仍有一定收缩；不过比 BABB/甲醇直接处理更规范。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.75 | iDISCO+ 对全脑免疫标记和透明效果极佳，适合 Aβ 抗体标记。 |
| 13 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 2.25 | 2.25 | uDISCO 可透明全脑并兼容抗体。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | CUBIC | 3.00 | 3.00 | 2.50 | CUBIC 支持全脑免疫标记。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | iDISCO+ | 2.81 | 2.25 | 2.75 | iDISCO+ 适合全脑 Aβ 免疫标记。 |
| 14 | 5XFAD mouse whole brain / amyloid plaques (validation) | uDISCO | 1.23 | 1.50 | 2.25 | uDISCO 可透明全脑并兼容抗体。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | iDISCO+ | 2.81 | 3.00 | 2.75 | iDISCO+ 适合全脑 Aβ 免疫标记与定量。 |
| 15 | 5XFAD mouse whole brain / amyloid plaque quantification | uDISCO | 1.23 | 1.00 | 2.25 | uDISCO 可透明全脑并兼容抗体。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | CUBIC | 3.00 | 1.50 | 2.75 | CUBIC 水相法更适合长时间抗体渗透，是避免溶剂免疫标记失败的首选。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | SWITCH | 3.00 | 2.25 | 2.75 | SWITCH 专为均匀免疫标记设计，适合此场景。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | iDISCO+ | 2.81 | 2.50 | 2.50 | iDISCO+ 仍为全脑免疫标记经典，但需优化抗体孵育时间/浓度。 |
| 16 | 5XFAD mouse whole brain / amyloid plaques | uDISCO | 1.23 | 1.25 | 2.00 | uDISCO 属有机溶剂，免疫标记信号可能仍弱。 |
| 17 | GBM mouse brain block / tumor + vasculature | CUBIC | 2.79 | 3.00 | 2.75 | CUBIC 对肿瘤脑组织温和，可保留血管网络与肿瘤边界，是首选水相法。 |
| 17 | GBM mouse brain block / tumor + vasculature | FDISCO | 3.00 | 2.75 | 2.00 | FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。 |
| 17 | GBM mouse brain block / tumor + vasculature | iDISCO+ | 3.00 | 2.00 | 1.75 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |
| 17 | GBM mouse brain block / tumor + vasculature | uDISCO | 1.82 | 1.50 | 1.75 | uDISCO 对肿瘤软组织形态保持风险大。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB structures | CUBIC | 2.79 | 2.00 | 2.75 | CUBIC 对肿瘤脑组织温和，可保留血管网络与 BBB 结构。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB structures | FDISCO | 3.00 | 3.00 | 2.00 | FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB structures | iDISCO+ | 3.00 | 2.25 | 1.75 | iDISCO+ 对软组织形态风险大。 |
| 18 | GBM mouse brain block / tumor vasculature + BBB structures | uDISCO | 1.82 | 1.50 | 1.75 | uDISCO 对肿瘤软组织形态保持风险大。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | FDISCO | 3.00 | 2.75 | 2.00 | FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | iDISCO+ | 3.00 | 2.25 | 1.75 | iDISCO+ 对软组织形态风险大。 |
| 19 | GBM mouse brain block / vascular remodeling + invasion | uDISCO | 1.82 | 1.25 | 1.75 | uDISCO 对肿瘤软组织形态保持风险大。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | FDISCO | 3.00 | 2.25 | 1.75 | FDISCO 有机溶剂对肿瘤血管形态有风险。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | PEGASOS | 1.02 | 0.75 | 0.75 | PEGASOS 对脑组织过于剧烈，不适合。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | SWITCH | 2.81 | 3.00 | 2.25 | SWITCH 水相法形态保持较好。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | ScaleS | 2.73 | 3.00 | 2.75 | ScaleS 形态保持优秀，是 CUBIC 失败后的优选替代。 |
| 20 | GBM mouse brain block / tumor + vasculature + BBB | iDISCO+ | 3.00 | 3.00 | 1.25 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | CUBIC | 3.00 | 3.00 | 2.25 | CUBIC 对 FP 保留好，但弱稀疏信号下 ScaleS/SeeDB2 更优。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | FDISCO | 2.71 | 3.00 | 2.50 | FDISCO 对 FP 保留好，但 3 mm 脑块用 SeeDB2/ScaleS 更简便。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | PEGASOS | 0.00 | 0.25 | 0.50 | PEGASOS 对脑块剧烈，FP 淬灭严重。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | ScaleS | 3.00 | 3.00 | 3.00 | ScaleS 是 FP 保留金标准，极适合稀疏弱信号神经元成像。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | SeeDB2 | 3.00 | 3.00 | 2.75 | SeeDB2 FP 保留极佳，适合脑片/小块高分辨率成像。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | iDISCO+ | 2.68 | 1.75 | 0.50 | iDISCO+ 会淬灭内源 FP，极不适合弱信号稀疏标记。 |
| 21 | mouse brain block (sparse FP) / sparse neurons morphology | uDISCO | 0.00 | 0.25 | 0.75 | uDISCO 会显著淬灭内源 FP，不适合弱信号。 |

## 4. 机器 vs 专家差异显著案例

| 模型 | 题号 | 方法 | 机器 s_trans | 专家 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| openai_claude-sonnet-4.6 | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_gpt-5.2-fast | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_gpt-5.2-thinking | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-14b | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-235b | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-32b | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-max | 2 | iDISCO+ | 2.81 | 0.50 | 2.31 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-14b | 21 | iDISCO+ | 2.68 | 0.50 | 2.18 | iDISCO+ 会淬灭内源 FP，极不适合弱信号稀疏标记。 |
| openai_deepseek-reasoner | 8 | BABB | 0.00 | 2.00 | 2.00 | 无电泳，但 FP 保留有限。 |
| glm4.7-unthinking | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_deepseek-chat | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_deepseek-reasoner | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-14b | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-32b | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_qwen3-32b | 10 | CUBIC | 3.00 | 1.75 | 1.25 | CUBIC 对完整 CNS 深度有限。 |
| glm4.7-unthinking | 17 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |
| openai_claude-sonnet-4.6 | 17 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |
| openai_gpt-5.2-fast | 17 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |
| openai_qwen3-14b | 17 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |
| openai_qwen3-235b | 17 | iDISCO+ | 3.00 | 1.75 | 1.25 | iDISCO+ 会淬灭内源信号且对软组织形态风险大。 |

## 5. 人工 vs 专家差异显著案例

| 模型 | 题号 | 方法 | 人工 s_trans | 专家 s_trans | 差异 | 专家理由 |
|---|---|---|---|---|---|---|
| openai_deepseek-chat | 9 | uDISCO | 0.00 | 3.00 | 3.00 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| openai_deepseek-reasoner | 6 | uDISCO | 0.00 | 2.75 | 2.75 | uDISCO 擅长长距离投射透明。 |
| openai_gpt-5.2-fast | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_gpt-5.2-thinking | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-14b | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-235b | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-32b | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_qwen3-max | 2 | iDISCO+ | 3.00 | 0.50 | 2.50 | iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。 |
| openai_deepseek-chat | 5 | uDISCO | 0.25 | 2.75 | 2.50 | uDISCO 擅长全身/长距离投射透明，适合长脊髓段轴突追踪。 |
| openai_deepseek-reasoner | 4 | uDISCO | 0.00 | 2.25 | 2.25 | uDISCO 可透明全脑并兼容免疫标记。 |
| openai_qwen3-32b | 12 | CUBIC | 0.50 | 2.75 | 2.25 | CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。 |
| gemini-3-pro | 15 | iDISCO+ | 0.75 | 2.75 | 2.00 | iDISCO+ 适合全脑 Aβ 免疫标记与定量。 |
| openai_deepseek-reasoner | 2 | uDISCO | 0.50 | 2.25 | 1.75 | uDISCO 可透明全脑并保留部分 FP，但对内源 GFP 淬灭比 FDISCO 重。 |
| openai_deepseek-reasoner | 8 | BABB | 0.25 | 2.00 | 1.75 | 无电泳，但 FP 保留有限。 |
| gemini-3-flash | 9 | uDISCO | 1.25 | 3.00 | 1.75 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| glm4.7-unthinking | 9 | uDISCO | 1.25 | 3.00 | 1.75 | uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。 |
| gemini-3-pro | 10 | PEGASOS | 0.00 | 1.75 | 1.75 | PEGASOS 收缩大。 |
| openai_qwen3-14b | 14 | iDISCO+ | 1.00 | 2.75 | 1.75 | iDISCO+ 适合全脑 Aβ 免疫标记。 |
| glm4.7-unthinking | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |
| openai_deepseek-chat | 20 | iDISCO+ | 3.00 | 1.25 | 1.75 | iDISCO+ 对肿瘤软组织形态风险大，不适合。 |

## 6. 分布对比

- **机器 s_trans**: mean=2.526, std=0.689, min=0.000, max=3.000
- **人工 s_trans**: mean=2.210, std=0.817, min=0.000, max=3.000
- **专家 s_trans**: mean=2.245, std=0.590, min=0.500, max=3.000

## 7. 逐题一致性

| 题号 | 机器 vs 人工 (r/ρ/ICC) | 专家 vs 人工 (r/ρ/ICC) | 专家 vs 机器 (r/ρ/ICC) |
|---|---|---|---|
| 2 | 0.87/0.84/0.93 | -0.52/-0.53/-0.41 | -0.56/-0.47/-0.43 |
| 3 | 0.73/0.66/0.70 | 0.73/0.66/0.30 | 1.00/1.00/0.75 |
| 4 | 0.78/0.75/0.81 | 0.78/0.75/0.46 | 1.00/1.00/0.72 |
| 5 | 0.77/0.61/0.73 | -0.77/-0.61/-0.01 | -1.00/-1.00/-0.69 |
| 6 | 0.60/0.49/0.54 | -0.60/-0.49/0.08 | -1.00/-1.00/-0.69 |
| 7 | 0.02/0.03/0.17 | -0.02/-0.03/0.32 | -1.00/-1.00/-0.69 |
| 8 | 0.90/0.92/0.91 | 0.72/0.54/0.61 | 0.61/0.50/0.66 |
| 9 | 0.63/0.79/0.68 | -0.70/-0.79/-0.27 | -0.98/-1.00/-0.84 |
| 10 | 0.82/0.78/0.88 | -0.01/-0.31/0.30 | -0.37/-0.50/-0.01 |
| 11 | 0.36/0.56/0.60 | -0.36/-0.56/0.02 | -1.00/-1.00/-0.88 |
| 12 | 0.00/-0.03/0.33 | 0.15/0.18/0.45 | 0.81/0.87/0.87 |
| 13 | 0.54/0.54/0.74 | 0.54/0.54/0.57 | 1.00/1.00/0.75 |
| 14 | 0.40/0.50/0.56 | 0.24/0.18/0.26 | 0.90/0.45/0.72 |
| 15 | 0.56/0.53/0.69 | 0.56/0.53/0.41 | 1.00/1.00/0.75 |
| 16 | 0.68/0.32/0.66 | 0.56/0.32/0.44 | 0.95/1.00/0.77 |
| 17 | 0.52/0.28/0.57 | 0.49/0.66/0.34 | 0.07/-0.10/-0.31 |
| 18 | 0.22/0.29/0.41 | -0.19/-0.04/-0.14 | 0.04/-0.21/-0.34 |
| 19 | 0.74/0.60/0.63 | 0.17/0.05/0.24 | 0.13/0.13/-0.51 |
| 20 | 0.79/0.40/0.82 | 0.59/0.56/0.56 | 0.50/0.05/0.24 |
| 21 | 0.92/0.88/0.95 | 0.86/0.71/0.91 | 0.82/0.79/0.88 |

## 8. 为什么专家评分与现有人工评分差异较大？

专家评分与现有人工 s_trans 的相关性较低（Pearson r≈0.09，Spearman ρ≈0.01），这本身是一个重要发现。可能原因包括：

1. **人工评分原就高度不一致**：同一 (题号, 方法) 组合在不同模型/评分者之间差异大，说明人类对 s_trans 的判定标准尚未统一。
2. **人工评分可能仍部分依赖 RI 直觉**：许多人工高分出现在机器 RI 匹配也高的组合上，即使方法本身并不适合该应用（如 Q2 的 iDISCO+ 配内源 GFP）。
3. **专家评分更强调方法设计用途**：例如 uDISCO 在超长 CNS/脊髓长程追踪中获得高分，而人工评分者可能更关注其收缩/淬灭副作用。
4. **s_trans 与 s_label 的边界模糊**：本报告按用户要求把“方法对这道题是否合适”纳入 s_trans，自然会与 s_label 有部分重叠；原人工评分者可能把标记兼容性问题更多地归入 s_label。

因此，本报告应被视为**基于方法适合度原则的重新标定提案**，而非对现有人工评分的简单修正。

## 9. 结论与建议

1. 专家评分将 s_trans 从单一 RI 匹配扩展为“方法-样本-目标-标记”综合适合度。
2. 明显不合理的组合（如 BoneClear/ClearSee/EyeCi/FlyClear 用于小鼠脑）被直接判为 0，这与方法适合度的直觉更一致。
3. 对于机器评分较高但专家评分较低的情况，通常是因为机器仅看 RI 接近，而专家考虑方法设计样本/形态风险/标记兼容性。
4. **建议**：在修改 JSON 前，请组织 1–2 名领域专家独立复核本报告中的评分与理由；
   如确认无误，可将 `expert_s_trans` 写入 `human_evaluation.effectiveness.s_trans.score`，
   并同步更新总分与注释。
