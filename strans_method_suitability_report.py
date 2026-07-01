"""
s_trans 方法适合度重新评估报告生成器

评分理念：
- 原 s_trans 仅基于 RI 域匹配（RI_tissue vs RI_method_ref）。
- 人工专家在判断“方法-组织是否匹配”时，会综合考虑：
  1) 方法设计样本类型与题目样本是否一致；
  2) 方法对目标结构/标记的兼容性；
  3) 样本尺寸是否超出该方法常规适用范围；
  4) 特殊需求（如形态保持、长程投射、免疫标记、FP 保留等）。
- 本报告据此对 240 条记录重新给出“方法适合度”评分，并与机器 s_trans、人类 s_trans 比较。
"""

import json
import numpy as np
from scipy import stats
from collections import defaultdict, Counter
import pathlib

DATA_PATH = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
RI_REF_PATH = pathlib.Path("KnowledgeBase/method_ri_ref.json")
FLUORO_PATH = pathlib.Path("KnowledgeBase/method_fluro_compati.json")
OUTPUT_PATH = pathlib.Path("s_trans_method_suitability_report.md")


def icc_2_1(y: np.ndarray) -> float:
    """Two-way random, single measure ICC."""
    n, k = y.shape
    if n < 2 or k < 2:
        return 0.0
    ms = np.var(y.mean(axis=1), ddof=0) * k
    mw = np.var(y, axis=1, ddof=0).mean()
    denom = ms + (k - 1) * mw
    if denom == 0:
        return 0.0
    return float((ms - mw) / denom)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def round_quarter(x):
    return round(x * 4) / 4


# ---------------------------------------------------------------------------
# 方法特性简表（基于 model_space.json + 文献常识）
# 用于对“方法是否适合某类样本/目标”做规则判断。
# ---------------------------------------------------------------------------
METHOD_TRAITS = {
    "CUBIC":        {"type": "aqueous",   "fp": 0.8, "immuno": 0.8, "clearing": 0.7, "morphology": 0.8, "primary": "mouse brain/organs"},
    "ScaleS":       {"type": "aqueous",   "fp": 0.9, "immuno": 0.5, "clearing": 0.6, "morphology": 0.9, "primary": "adult mouse brain slices"},
    "MACS":         {"type": "aqueous",   "fp": 0.7, "immuno": 0.6, "clearing": 0.7, "morphology": 0.7, "primary": "mouse brain/organs"},
    "iDISCO+":      {"type": "organic",   "fp": 0.1, "immuno": 1.0, "clearing": 0.95,"morphology": 0.4, "primary": "embryos/adult mouse brain"},
    "FDISCO":       {"type": "organic",   "fp": 0.8, "immuno": 0.5, "clearing": 0.85,"morphology": 0.5, "primary": "mouse brain (FP-preserving)"},
    "SOLID":        {"type": "aqueous",   "fp": 0.8, "immuno": 0.6, "clearing": 0.7, "morphology": 0.8, "primary": "mouse brain"},
    "SeeDB2":       {"type": "aqueous",   "fp": 1.0,"immuno": 0.2, "clearing": 0.5, "morphology": 0.9, "primary": "mouse brain slices"},
    "PEGASOS":      {"type": "organic",   "fp": 0.6, "immuno": 0.6, "clearing": 0.95,"morphology": 0.3, "primary": "whole body/dense tissues/bone"},
    "BoneClear":    {"type": "organic",   "fp": 0.2, "immuno": 0.8, "clearing": 1.0, "morphology": 0.6, "primary": "bone"},
    "Ce3D":         {"type": "organic",   "fp": 0.6, "immuno": 0.9, "clearing": 0.75,"morphology": 0.6, "primary": "lymph nodes/thick tissues"},
    "TDE":          {"type": "organic",   "fp": 0.9, "immuno": 0.1, "clearing": 0.3, "morphology": 0.7, "primary": "brain slices/cells"},
    "ClearT2":      {"type": "organic",   "fp": 0.9, "immuno": 0.4, "clearing": 0.5, "morphology": 0.6, "primary": "zebrafish/embryos"},
    "ClearSee":     {"type": "aqueous",   "fp": 0.85,"immuno": 0.4, "clearing": 0.35,"morphology": 0.8, "primary": "plant"},
    "EyeCi":        {"type": "organic",   "fp": 0.85,"immuno": 0.4, "clearing": 0.5, "morphology": 0.7, "primary": "eye/retina"},
    "FOCM":         {"type": "aqueous",   "fp": 0.7, "immuno": 0.7, "clearing": 0.5, "morphology": 0.7, "primary": "brain slices"},
    "SWITCH":       {"type": "aqueous",   "fp": 0.1, "immuno": 0.9, "clearing": 0.5, "morphology": 0.7, "primary": "mouse brain"},
    "uDISCO":       {"type": "organic",   "fp": 0.4, "immuno": 0.7, "clearing": 0.95,"morphology": 0.4, "primary": "whole body/long projections"},
    "FlyClear":     {"type": "aqueous",   "fp": 0.8, "immuno": 0.5, "clearing": 0.3, "morphology": 0.7, "primary": "Drosophila brain"},
    # 异常别名处理
    "BABB (BA/BB) solvent clearing (not PEGASOS)": {"type": "organic", "fp": 0.5, "immuno": 0.4, "clearing": 0.85, "morphology": 0.4, "primary": "mouse brain"},
}

# 方法名标准化映射（因为 model_space 与 method_ri_ref 命名略有差异）
METHOD_NAME_MAP = {
    "SCALE (ScaleS)": "ScaleS",
    "iDISCO (iDISCO+)": "iDISCO+",
    "seeDB2": "SeeDB2",
    "BABB (BA/BB) solvent clearing (not PEGASOS)": "BABB",
}


def normalize_method(name):
    return METHOD_NAME_MAP.get(name, name)


# ---------------------------------------------------------------------------
# 题目需求描述（关键维度）
# ---------------------------------------------------------------------------
QUESTION_PROFILE = {
    "2":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "neuronal morphology (soma/axon/dendrite)",  "label": "endogenous FP / nuclear dye", "special": "whole-brain morphology, FP preservation"},
    "3":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "cFos+ activated neurons (IEG)",           "label": "immunolabeling (IEG)",       "special": "whole-brain immunolabeling, single-cell resolution"},
    "4":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "activated neurons (IEG)",                  "label": "immunolabeling (IEG)",       "special": "CUBIC failed; need better clearing/labeling"},
    "5":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm","target": "axons/regenerated fibers",              "label": "neurofilament/axon markers", "special": "long fiber tracing in thick spinal cord"},
    "6":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm","target": "regenerated + mature axons",            "label": "axon markers",               "special": "long fiber tracing"},
    "7":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm","target": "regenerated + mature axons",            "label": "axon markers",               "special": "long fiber tracing"},
    "8":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm","target": "regenerated + mature axons",            "label": "axon markers",               "special": "electrophoresis failed; avoid electrophoresis"},
    "9":  {"sample": "whole mouse CNS", "size": "35–40 mm",           "target": "long-range projection fibers",          "label": "projection + reference tracers", "special": "ultra-long sample, continuous tracing"},
    "10": {"sample": "whole mouse CNS", "size": "35–40 mm",           "target": "long-range projections + axon skeleton","label": "projection + reference tracers", "special": "ultra-long sample"},
    "11": {"sample": "whole mouse CNS", "size": "35–40 mm",           "target": "long-range connections",                "label": "projection + reference tracers", "special": "ultra-long sample"},
    "12": {"sample": "whole mouse CNS", "size": "35–40 mm",           "target": "long-range projections + axon skeleton","label": "projection + reference tracers", "special": "solvent shrinkage failed; avoid harsh solvent"},
    "13": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm",  "target": "amyloid plaques",                       "label": "Congo red / anti-Aβ",        "special": "plaque staining, whole brain"},
    "14": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm",  "target": "amyloid plaques (validation)",          "label": "dual anti-Aβ / Congo red",   "special": "plaque staining, whole brain"},
    "15": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm",  "target": "amyloid plaque quantification",         "label": "dual anti-Aβ / Congo red",   "special": "plaque staining, whole brain"},
    "16": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm",  "target": "amyloid plaques",                       "label": "anti-Aβ / Congo red",        "special": "solvent immunolabeling failed; need aqueous or better labeling"},
    "17": {"sample": "GBM mouse brain block", "size": "8×6×5 mm",     "target": "tumor + vasculature",                   "label": "tumor + endothelial markers","special": "morphology preservation, vascular network"},
    "18": {"sample": "GBM mouse brain block", "size": "8×6×5 mm",     "target": "tumor vasculature + BBB structures",    "label": "endothelial + tight junction","special": "morphology preservation, vascular network"},
    "19": {"sample": "GBM mouse brain block", "size": "8×6×5 mm",     "target": "vascular remodeling + invasion",        "label": "tumor + endothelial markers","special": "morphology preservation, vascular network"},
    "20": {"sample": "GBM mouse brain block", "size": "8×6×5 mm",     "target": "tumor + vasculature + BBB",             "label": "tumor + endothelial markers","special": "CUBIC failed; need gentler morphology-preserving method"},
    "21": {"sample": "mouse brain block (sparse FP)", "size": "3 mm", "target": "sparse neurons morphology",             "label": "weak endogenous FP",         "special": "weak FP preservation, morphology, long-term storage"},
}


# ---------------------------------------------------------------------------
# 专家评分：为每个 (question, method) 组合给出 0–3 分的方法适合度
# 评分维度：
#   A. 样本类型匹配（方法是否为该组织/样本设计）
#   B. 目标结构适配（方法能否满足透明深度/分辨率）
#   C. 标记兼容性（FP 保留 vs 免疫标记）
#   D. 特殊需求（形态保持、超长样本、避免收缩等）
#
# 分档：
#   3.0 = 非常合适（该方法为此类样本/目标的经典/首选方案）
#   2.0–2.75 = 合适，有小缺陷
#   1.0–1.75 = 可用但不理想
#   0.0–0.75 = 不合适/有严重问题
# ---------------------------------------------------------------------------
EXPERT_SCORES = {
    # Q2: adult whole brain morphology, endogenous FP
    ("2", "FDISCO"):  (2.75, "FDISCO 为成年小鼠全脑 FP 保留优化，适合神经元形态三维成像。"),
    ("2", "uDISCO"):  (2.25, "uDISCO 可透明全脑并保留部分 FP，但对内源 GFP 淬灭比 FDISCO 重。"),
    ("2", "CUBIC"):   (2.50, "CUBIC 对全脑温和且 FP 兼容性好，透明深度略逊于有机溶剂法。"),
    ("2", "ScaleS"):  (1.75, "ScaleS 极适合 FP 保留，但主要用于切片/薄样本，全脑透明深度有限。"),
    ("2", "SOLID"):   (2.25, "SOLID 适用于小鼠全脑，FP 与形态保持均衡。"),
    ("2", "SeeDB2"):  (1.50, "SeeDB2 适合 FP 保留与高分辨率，但更偏向脑片而非完整全脑。"),
    ("2", "PEGASOS"): (0.75, "PEGASOS 面向全身/致密组织，对脑组织过于剧烈，收缩风险大。"),
    ("2", "iDISCO+"): (0.50, "iDISCO+ 会严重淬灭内源 GFP，不适合以内源 FP 为主的神经元形态成像。"),
    ("2", "BoneClear"): (0.0, "BoneClear 专为骨设计，不适用于脑。"),
    ("2", "ClearSee"): (0.0, "ClearSee 为植物样本设计，不适用于鼠脑。"),
    ("2", "EyeCi"):    (0.0, "EyeCi 为眼球/视网膜设计，不适用于全脑。"),
    ("2", "FlyClear"): (0.0, "FlyClear 为果蝇设计，不适用于小鼠脑。"),
    ("2", "TDE"):      (1.25, "TDE 主要用作脑片/细胞的 RI 匹配介质，不适合完整全脑透明。"),
    ("2", "FOCM"):     (1.25, "FOCM 面向脑片快速透明，不适合完整成年全脑。"),
    ("2", "ClearT2"):  (0.75, "ClearT2 为斑马鱼/胚胎优化，不适合成年小鼠全脑。"),
    ("2", "Ce3D"):     (1.75, "Ce3D 可用于淋巴结/厚组织，对全脑神经元形态非最优。"),
    ("2", "MACS"):     (2.25, "MACS 适用于脑/器官透明，FP 与速度均衡。"),
    ("2", "SWITCH"):   (1.75, "SWITCH 强调均匀免疫标记，对内源 FP 保留一般。"),
    ("2", "BABB"):     (2.00, "BABB 为传统有机溶剂法，可透明全脑但 FP 保留有限。"),

    # Q3/Q4: whole brain cFos/IEG immunolabeling
    ("3", "iDISCO+"): (2.75, "iDISCO+ 对全脑免疫标记和透明效果极佳，是 IEG 全脑成像的经典方案。"),
    ("3", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记，温和且可扩展。"),
    ("3", "uDISCO"):  (2.25, "uDISCO 可透明全脑并兼容免疫标记，但有机溶剂对内源信号淬灭较重。"),
    ("3", "FDISCO"):  (1.75, "FDISCO 更适合 FP 保留，对全脑免疫标记非首选。"),
    ("3", "ScaleS"):  (1.25, "ScaleS 免疫标记渗透性有限，不适合全脑抗体标记。"),
    ("3", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记，温和有效。"),
    ("3", "SWITCH"):  (2.50, "SWITCH 专为均匀免疫标记设计，适合全脑 IEG 标记。"),
    ("3", "PEGASOS"): (1.00, "PEGASOS 可免疫标记但收缩剧烈，非脑组织首选。"),
    ("3", "BoneClear"): (0.0, "BoneClear 不适用于脑。"),
    ("3", "ClearSee"): (0.0, "ClearSee 不适用于鼠脑。"),
    ("3", "EyeCi"):    (0.0, "EyeCi 不适用于全脑。"),
    ("3", "FlyClear"): (0.0, "FlyClear 不适用于小鼠。"),
    ("3", "TDE"):      (1.00, "TDE 适用于切片，不适合全脑免疫标记。"),
    ("3", "FOCM"):     (1.00, "FOCM 面向脑片，不适合全脑。"),
    ("3", "ClearT2"):  (0.75, "ClearT2 更适合胚胎/小样本。"),
    ("3", "Ce3D"):     (1.75, "Ce3D 对厚组织免疫标记好，但全脑神经元非其主场。"),
    ("3", "MACS"):     (2.25, "MACS 适用于脑免疫标记，速度较快。"),
    ("3", "SeeDB2"):   (1.25, "SeeDB2 免疫标记渗透有限，适合 FP 而非全脑抗体标记。"),
    ("3", "BABB"):     (1.75, "BABB 溶剂法可免疫标记但 FP 保留差，操作风险高。"),

    # Q4 uses same profile as Q3
    ("4", "iDISCO+"): (2.75, "iDISCO+ 对全脑免疫标记和透明效果极佳，是 IEG 全脑成像的经典方案。"),
    ("4", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记，温和且可扩展；原 CUBIC-L/RA 时间不足是执行问题，方法本身合适。"),
    ("4", "uDISCO"):  (2.25, "uDISCO 可透明全脑并兼容免疫标记。"),
    ("4", "FDISCO"):  (1.75, "FDISCO 更适合 FP 保留。"),
    ("4", "ScaleS"):  (1.25, "ScaleS 免疫标记渗透有限。"),
    ("4", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("4", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("4", "PEGASOS"): (1.00, "PEGASOS 对脑过于剧烈。"),
    ("4", "BoneClear"): (0.0, "不适用于脑。"),
    ("4", "ClearSee"): (0.0, "不适用于鼠脑。"),
    ("4", "EyeCi"):    (0.0, "不适用于全脑。"),
    ("4", "FlyClear"): (0.0, "不适用于小鼠。"),
    ("4", "TDE"):      (1.00, "TDE 适用于切片。"),
    ("4", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("4", "ClearT2"):  (0.75, "ClearT2 更适合胚胎/小样本。"),
    ("4", "Ce3D"):     (1.75, "Ce3D 对厚组织免疫标记好。"),
    ("4", "MACS"):     (2.25, "MACS 适用于脑免疫标记。"),
    ("4", "SeeDB2"):   (1.25, "SeeDB2 免疫标记渗透有限。"),
    ("4", "BABB"):     (1.75, "BABB 可免疫标记但风险高。"),

    # Q5-Q8: rat spinal cord injury segment, long axon tracing
    ("5", "uDISCO"):  (2.75, "uDISCO 擅长全身/长距离投射透明，适合长脊髓段轴突追踪。"),
    ("5", "FDISCO"):  (2.50, "FDISCO 对 FP 保留好，适合轴突纤维追踪。"),
    ("5", "CUBIC"):   (2.25, "CUBIC 对脊髓温和，但 15 mm 长段透明深度有限。"),
    ("5", "ScaleS"):  (1.75, "ScaleS 适合 FP 保留，但对 15 mm 脊髓长段透明不足。"),
    ("5", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓并支持免疫标记，但会淬灭内源 FP。"),
    ("5", "PEGASOS"): (1.50, "PEGASOS 可处理致密组织，但脊髓形态保持风险大。"),
    ("5", "SOLID"):   (2.25, "SOLID 适用于脊髓等神经组织。"),
    ("5", "SeeDB2"):  (1.50, "SeeDB2 适合脑片，对长脊髓段非最优。"),
    ("5", "MACS"):    (2.25, "MACS 可快速透明脊髓。"),
    ("5", "TDE"):     (1.00, "TDE 适合切片，不适合 15 mm 长段。"),
    ("5", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("5", "BoneClear"): (0.0, "不适用于脊髓。"),
    ("5", "ClearSee"):  (0.0, "不适用于脊髓。"),
    ("5", "EyeCi"):     (0.0, "不适用于脊髓。"),
    ("5", "FlyClear"):  (0.0, "不适用于大鼠。"),
    ("5", "ClearT2"):   (0.75, "更适合胚胎/小样本。"),
    ("5", "Ce3D"):      (2.00, "Ce3D 对厚组织有效，可用于脊髓轴突追踪。"),
    ("5", "SWITCH"):    (2.25, "SWITCH 支持脊髓免疫标记。"),
    ("5", "BABB"):      (2.00, "BABB 溶剂法可透明脊髓但 FP 保留有限。"),

    ("6", "uDISCO"):  (2.75, "uDISCO 擅长长距离投射透明。"),
    ("6", "FDISCO"):  (2.50, "FDISCO 对 FP 保留好。"),
    ("6", "CUBIC"):   (2.25, "CUBIC 对脊髓温和。"),
    ("6", "ScaleS"):  (1.75, "ScaleS 对长段透明不足。"),
    ("6", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓。"),
    ("6", "PEGASOS"): (1.50, "PEGASOS 对脊髓形态风险大。"),
    ("6", "SOLID"):   (2.25, "SOLID 适用于脊髓。"),
    ("6", "SeeDB2"):  (1.50, "SeeDB2 适合脑片。"),
    ("6", "MACS"):    (2.25, "MACS 可快速透明脊髓。"),
    ("6", "TDE"):     (1.00, "TDE 适合切片。"),
    ("6", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("6", "BoneClear"): (0.0, "不适用。"),
    ("6", "ClearSee"):  (0.0, "不适用。"),
    ("6", "EyeCi"):     (0.0, "不适用。"),
    ("6", "FlyClear"):  (0.0, "不适用。"),
    ("6", "ClearT2"):   (0.75, "更适合小样本。"),
    ("6", "Ce3D"):      (2.00, "可用于脊髓轴突追踪。"),
    ("6", "SWITCH"):    (2.25, "支持脊髓免疫标记。"),
    ("6", "BABB"):      (2.00, "可透明脊髓但 FP 保留有限。"),

    ("7", "uDISCO"):  (2.75, "uDISCO 擅长长距离投射透明。"),
    ("7", "FDISCO"):  (2.50, "FDISCO 对 FP 保留好。"),
    ("7", "CUBIC"):   (2.25, "CUBIC 对脊髓温和。"),
    ("7", "ScaleS"):  (1.75, "ScaleS 对长段透明不足。"),
    ("7", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓。"),
    ("7", "PEGASOS"): (1.50, "PEGASOS 对脊髓形态风险大。"),
    ("7", "SOLID"):   (2.25, "SOLID 适用于脊髓。"),
    ("7", "SeeDB2"):  (1.50, "SeeDB2 适合脑片。"),
    ("7", "MACS"):    (2.25, "MACS 可快速透明脊髓。"),
    ("7", "TDE"):     (1.00, "TDE 适合切片。"),
    ("7", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("7", "BoneClear"): (0.0, "不适用。"),
    ("7", "ClearSee"):  (0.0, "不适用。"),
    ("7", "EyeCi"):     (0.0, "不适用。"),
    ("7", "FlyClear"):  (0.0, "不适用。"),
    ("7", "ClearT2"):   (0.75, "更适合小样本。"),
    ("7", "Ce3D"):      (2.00, "可用于脊髓轴突追踪。"),
    ("7", "SWITCH"):    (2.25, "支持脊髓免疫标记。"),
    ("7", "BABB"):      (2.00, "可透明脊髓但 FP 保留有限。"),

    # Q8: electrophoresis failed => avoid electrophoresis (iDISCO+/uDISCO/PEGASOS use organic, not electrophoresis)
    ("8", "uDISCO"):  (2.75, "uDISCO 为被动有机溶剂法，无电泳，适合长脊髓段。"),
    ("8", "FDISCO"):  (2.50, "FDISCO 无电泳，FP 保留好。"),
    ("8", "CUBIC"):   (2.50, "CUBIC 被动水相法，无电泳，对脊髓损伤节段温和。"),
    ("8", "ScaleS"):  (1.75, "ScaleS 对长段透明不足。"),
    ("8", "iDISCO+"): (2.25, "iDISCO+ 为被动溶剂法，无电泳，但会淬灭 FP。"),
    ("8", "PEGASOS"): (1.50, "PEGASOS 形态风险大。"),
    ("8", "SOLID"):   (2.50, "SOLID 被动水相，无电泳。"),
    ("8", "SeeDB2"):  (1.50, "SeeDB2 适合脑片。"),
    ("8", "MACS"):    (2.25, "MACS 被动水相。"),
    ("8", "TDE"):     (1.00, "TDE 适合切片。"),
    ("8", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("8", "BoneClear"): (0.0, "不适用。"),
    ("8", "ClearSee"):  (0.0, "不适用。"),
    ("8", "EyeCi"):     (0.0, "不适用。"),
    ("8", "FlyClear"):  (0.0, "不适用。"),
    ("8", "ClearT2"):   (0.75, "更适合小样本。"),
    ("8", "Ce3D"):      (2.00, "可用于脊髓。"),
    ("8", "SWITCH"):    (2.25, "被动水相，无电泳。"),
    ("8", "BABB"):      (2.00, "无电泳，但 FP 保留有限。"),

    # Q9-Q12: whole mouse CNS, 35-40 mm, long-range projections
    ("9", "uDISCO"):  (3.00, "uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。"),
    ("9", "FDISCO"):  (2.50, "FDISCO 可透明全 CNS 并保留 FP，但 uDISCO 对超长样本更经典。"),
    ("9", "CUBIC"):   (1.75, "CUBIC 对 35–40 mm 完整 CNS 透明深度可能不足。"),
    ("9", "ScaleS"):  (1.25, "ScaleS 适合脑片，不适合完整 CNS。"),
    ("9", "iDISCO+"): (2.25, "iDISCO+ 可透明全 CNS，但会淬灭内源 FP。"),
    ("9", "PEGASOS"): (1.75, "PEGASOS 可处理全身但收缩大，对 CNS 精细形态不利。"),
    ("9", "SOLID"):   (1.75, "SOLID 适合脑，对 35–40 mm CNS 深度有限。"),
    ("9", "SeeDB2"):  (1.00, "SeeDB2 适合脑片。"),
    ("9", "MACS"):    (1.75, "MACS 对超长 CNS 深度可能不足。"),
    ("9", "TDE"):     (0.75, "TDE 适合切片。"),
    ("9", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("9", "BoneClear"): (0.0, "不适用。"),
    ("9", "ClearSee"):  (0.0, "不适用。"),
    ("9", "EyeCi"):     (0.0, "不适用。"),
    ("9", "FlyClear"):  (0.0, "不适用。"),
    ("9", "ClearT2"):   (0.75, "更适合小样本。"),
    ("9", "Ce3D"):      (1.75, "Ce3D 对厚组织有效，但对完整 CNS 非最优。"),
    ("9", "SWITCH"):    (1.75, "SWITCH 适合脑免疫标记，对完整 CNS 深度有限。"),
    ("9", "BABB"):      (2.00, "BABB 溶剂法可透明长样本但 FP 保留有限。"),

    ("10", "uDISCO"):  (3.00, "uDISCO 最适合完整 CNS 长程投射。"),
    ("10", "FDISCO"):  (2.50, "FDISCO 可保留 FP。"),
    ("10", "CUBIC"):   (1.75, "CUBIC 对完整 CNS 深度有限。"),
    ("10", "ScaleS"):  (1.25, "ScaleS 适合脑片。"),
    ("10", "iDISCO+"): (2.25, "iDISCO+ 可透明全 CNS。"),
    ("10", "PEGASOS"): (1.75, "PEGASOS 收缩大。"),
    ("10", "SOLID"):   (1.75, "SOLID 对完整 CNS 深度有限。"),
    ("10", "SeeDB2"):  (1.00, "SeeDB2 适合脑片。"),
    ("10", "MACS"):    (1.75, "MACS 对超长 CNS 深度有限。"),
    ("10", "TDE"):     (0.75, "TDE 适合切片。"),
    ("10", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("10", "BoneClear"): (0.0, "不适用。"),
    ("10", "ClearSee"):  (0.0, "不适用。"),
    ("10", "EyeCi"):     (0.0, "不适用。"),
    ("10", "FlyClear"):  (0.0, "不适用。"),
    ("10", "ClearT2"):   (0.75, "更适合小样本。"),
    ("10", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("10", "SWITCH"):    (1.75, "SWITCH 对完整 CNS 深度有限。"),
    ("10", "BABB"):      (2.00, "BABB 可透明长样本。"),

    ("11", "uDISCO"):  (3.00, "uDISCO 最适合完整 CNS 长程投射。"),
    ("11", "FDISCO"):  (2.50, "FDISCO 可保留 FP。"),
    ("11", "CUBIC"):   (1.75, "CUBIC 对完整 CNS 深度有限。"),
    ("11", "ScaleS"):  (1.25, "ScaleS 适合脑片。"),
    ("11", "iDISCO+"): (2.25, "iDISCO+ 可透明全 CNS。"),
    ("11", "PEGASOS"): (1.75, "PEGASOS 收缩大。"),
    ("11", "SOLID"):   (1.75, "SOLID 对完整 CNS 深度有限。"),
    ("11", "SeeDB2"):  (1.00, "SeeDB2 适合脑片。"),
    ("11", "MACS"):    (1.75, "MACS 对超长 CNS 深度有限。"),
    ("11", "TDE"):     (0.75, "TDE 适合切片。"),
    ("11", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("11", "BoneClear"): (0.0, "不适用。"),
    ("11", "ClearSee"):  (0.0, "不适用。"),
    ("11", "EyeCi"):     (0.0, "不适用。"),
    ("11", "FlyClear"):  (0.0, "不适用。"),
    ("11", "ClearT2"):   (0.75, "更适合小样本。"),
    ("11", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("11", "SWITCH"):    (1.75, "SWITCH 对完整 CNS 深度有限。"),
    ("11", "BABB"):      (2.00, "BABB 可透明长样本。"),

    # Q12: solvent shrinkage failed => avoid harsh solvent
    ("12", "uDISCO"):  (2.50, "uDISCO 可透明完整 CNS，但属有机溶剂法，仍有一定收缩；不过比 BABB/甲醇直接处理更规范。"),
    ("12", "FDISCO"):  (2.25, "FDISCO 保留 FP 但有机溶剂仍有收缩风险。"),
    ("12", "CUBIC"):   (2.75, "CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。"),
    ("12", "ScaleS"):  (1.50, "ScaleS 无收缩但透明深度有限。"),
    ("12", "iDISCO+"): (2.00, "iDISCO+ 有机溶剂，收缩风险。"),
    ("12", "PEGASOS"): (1.25, "PEGASOS 收缩大，不适合。"),
    ("12", "SOLID"):   (2.50, "SOLID 水相法无收缩，适合 CNS。"),
    ("12", "SeeDB2"):  (1.50, "SeeDB2 无收缩但深度有限。"),
    ("12", "MACS"):    (2.25, "MACS 水相法无收缩。"),
    ("12", "TDE"):     (1.00, "TDE 适合切片。"),
    ("12", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("12", "BoneClear"): (0.0, "不适用。"),
    ("12", "ClearSee"):  (0.0, "不适用。"),
    ("12", "EyeCi"):     (0.0, "不适用。"),
    ("12", "FlyClear"):  (0.0, "不适用。"),
    ("12", "ClearT2"):   (0.75, "更适合小样本。"),
    ("12", "Ce3D"):      (1.75, "Ce3D 对厚组织有效但有机溶剂有收缩。"),
    ("12", "SWITCH"):    (2.25, "SWITCH 水相法无收缩。"),
    ("12", "BABB"):      (1.25, "BABB 收缩风险大，不适合。"),

    # Q13-Q16: 5XFAD whole brain, amyloid plaques
    ("13", "iDISCO+"): (2.75, "iDISCO+ 对全脑免疫标记和透明效果极佳，适合 Aβ 抗体标记。"),
    ("13", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记，适合淀粉样斑块成像。"),
    ("13", "Congo red"): (2.50, "Congo red 为化学染料，可兼容多种透明方法；此处按方法适合度处理。"),
    ("13", "uDISCO"):  (2.25, "uDISCO 可透明全脑并兼容抗体。"),
    ("13", "FDISCO"):  (1.75, "FDISCO 对免疫标记非首选。"),
    ("13", "ScaleS"):  (1.25, "ScaleS 免疫渗透有限。"),
    ("13", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("13", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("13", "PEGASOS"): (1.00, "PEGASOS 对脑过于剧烈。"),
    ("13", "BoneClear"): (0.0, "不适用。"),
    ("13", "ClearSee"):  (0.0, "不适用。"),
    ("13", "EyeCi"):     (0.0, "不适用。"),
    ("13", "FlyClear"):  (0.0, "不适用。"),
    ("13", "TDE"):       (1.00, "TDE 适合切片。"),
    ("13", "FOCM"):      (1.00, "FOCM 面向脑片。"),
    ("13", "ClearT2"):   (0.75, "更适合胚胎。"),
    ("13", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("13", "SeeDB2"):    (1.25, "SeeDB2 免疫渗透有限。"),
    ("13", "BABB"):      (1.75, "BABB 可免疫标记但风险高。"),

    ("14", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记。"),
    ("14", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记。"),
    ("14", "uDISCO"):  (2.25, "uDISCO 可透明全脑并兼容抗体。"),
    ("14", "FDISCO"):  (1.75, "FDISCO 对免疫标记非首选。"),
    ("14", "ScaleS"):  (1.25, "ScaleS 免疫渗透有限。"),
    ("14", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("14", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("14", "PEGASOS"): (1.00, "PEGASOS 对脑过于剧烈。"),
    ("14", "BoneClear"): (0.0, "不适用。"),
    ("14", "ClearSee"):  (0.0, "不适用。"),
    ("14", "EyeCi"):     (0.0, "不适用。"),
    ("14", "FlyClear"):  (0.0, "不适用。"),
    ("14", "TDE"):       (1.00, "TDE 适合切片。"),
    ("14", "FOCM"):      (1.00, "FOCM 面向脑片。"),
    ("14", "ClearT2"):   (0.75, "更适合胚胎。"),
    ("14", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("14", "SeeDB2"):    (1.25, "SeeDB2 免疫渗透有限。"),
    ("14", "BABB"):      (1.75, "BABB 可免疫标记但风险高。"),

    ("15", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记与定量。"),
    ("15", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记。"),
    ("15", "uDISCO"):  (2.25, "uDISCO 可透明全脑并兼容抗体。"),
    ("15", "FDISCO"):  (1.75, "FDISCO 对免疫标记非首选。"),
    ("15", "ScaleS"):  (1.25, "ScaleS 免疫渗透有限。"),
    ("15", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("15", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("15", "PEGASOS"): (1.00, "PEGASOS 对脑过于剧烈。"),
    ("15", "BoneClear"): (0.0, "不适用。"),
    ("15", "ClearSee"):  (0.0, "不适用。"),
    ("15", "EyeCi"):     (0.0, "不适用。"),
    ("15", "FlyClear"):  (0.0, "不适用。"),
    ("15", "TDE"):       (1.00, "TDE 适合切片。"),
    ("15", "FOCM"):      (1.00, "FOCM 面向脑片。"),
    ("15", "ClearT2"):   (0.75, "更适合胚胎。"),
    ("15", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("15", "SeeDB2"):    (1.25, "SeeDB2 免疫渗透有限。"),
    ("15", "BABB"):      (1.75, "BABB 可免疫标记但风险高。"),

    # Q16: solvent immunolabeling failed => prefer aqueous or better labeling
    ("16", "iDISCO+"): (2.50, "iDISCO+ 仍为全脑免疫标记经典，但需优化抗体孵育时间/浓度。"),
    ("16", "CUBIC"):   (2.75, "CUBIC 水相法更适合长时间抗体渗透，是避免溶剂免疫标记失败的首选。"),
    ("16", "uDISCO"):  (2.00, "uDISCO 属有机溶剂，免疫标记信号可能仍弱。"),
    ("16", "FDISCO"):  (1.50, "FDISCO 对免疫标记非首选。"),
    ("16", "ScaleS"):  (1.25, "ScaleS 免疫渗透有限。"),
    ("16", "SOLID"):   (2.50, "SOLID 水相法适合免疫标记。"),
    ("16", "SWITCH"):  (2.75, "SWITCH 专为均匀免疫标记设计，适合此场景。"),
    ("16", "PEGASOS"): (0.75, "PEGASOS 对脑过于剧烈。"),
    ("16", "BoneClear"): (0.0, "不适用。"),
    ("16", "ClearSee"):  (0.0, "不适用。"),
    ("16", "EyeCi"):     (0.0, "不适用。"),
    ("16", "FlyClear"):  (0.0, "不适用。"),
    ("16", "TDE"):       (1.00, "TDE 适合切片。"),
    ("16", "FOCM"):      (1.00, "FOCM 面向脑片。"),
    ("16", "ClearT2"):   (0.75, "更适合胚胎。"),
    ("16", "Ce3D"):      (1.75, "Ce3D 对厚组织有效。"),
    ("16", "SeeDB2"):    (1.25, "SeeDB2 免疫渗透有限。"),
    ("16", "BABB"):      (1.25, "BABB 溶剂法免疫标记信号弱，不适合。"),

    # Q17-Q20: GBM brain block, morphology + vasculature preservation
    ("17", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与肿瘤边界，是首选水相法。"),
    ("17", "ScaleS"):  (2.50, "ScaleS 形态保持优秀，但 8 mm 脑块透明深度有限。"),
    ("17", "SOLID"):   (2.50, "SOLID 适用于神经组织，形态保持好。"),
    ("17", "SeeDB2"):  (2.25, "SeeDB2 形态保持好，适合脑片/小块。"),
    ("17", "iDISCO+"): (1.75, "iDISCO+ 会淬灭内源信号且对软组织形态风险大。"),
    ("17", "uDISCO"):  (1.75, "uDISCO 对肿瘤软组织形态保持风险大。"),
    ("17", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈，形态破坏风险高。"),
    ("17", "FDISCO"):  (2.00, "FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。"),
    ("17", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("17", "TDE"):     (1.50, "TDE 适合切片。"),
    ("17", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("17", "BoneClear"): (0.0, "不适用。"),
    ("17", "ClearSee"):  (0.0, "不适用。"),
    ("17", "EyeCi"):     (0.0, "不适用。"),
    ("17", "FlyClear"):  (0.0, "不适用。"),
    ("17", "ClearT2"):   (0.75, "更适合小样本。"),
    ("17", "Ce3D"):      (2.00, "Ce3D 对厚组织有效，可用于肿瘤血管。"),
    ("17", "SWITCH"):    (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("17", "BABB"):      (1.50, "BABB 对肿瘤形态有风险。"),

    ("18", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与 BBB 结构。"),
    ("18", "ScaleS"):  (2.50, "ScaleS 形态保持优秀。"),
    ("18", "SOLID"):   (2.50, "SOLID 适用于神经组织。"),
    ("18", "SeeDB2"):  (2.25, "SeeDB2 形态保持好。"),
    ("18", "iDISCO+"): (1.75, "iDISCO+ 对软组织形态风险大。"),
    ("18", "uDISCO"):  (1.75, "uDISCO 对肿瘤软组织形态保持风险大。"),
    ("18", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("18", "FDISCO"):  (2.00, "FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。"),
    ("18", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("18", "TDE"):     (1.50, "TDE 适合切片。"),
    ("18", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("18", "BoneClear"): (0.0, "不适用。"),
    ("18", "ClearSee"):  (0.0, "不适用。"),
    ("18", "EyeCi"):     (0.0, "不适用。"),
    ("18", "FlyClear"):  (0.0, "不适用。"),
    ("18", "ClearT2"):   (0.75, "更适合小样本。"),
    ("18", "Ce3D"):      (2.00, "Ce3D 对厚组织有效。"),
    ("18", "SWITCH"):    (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("18", "BABB"):      (1.50, "BABB 对肿瘤形态有风险。"),

    ("19", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与侵袭前沿。"),
    ("19", "ScaleS"):  (2.50, "ScaleS 形态保持优秀。"),
    ("19", "SOLID"):   (2.50, "SOLID 适用于神经组织。"),
    ("19", "SeeDB2"):  (2.25, "SeeDB2 形态保持好。"),
    ("19", "iDISCO+"): (1.75, "iDISCO+ 对软组织形态风险大。"),
    ("19", "uDISCO"):  (1.75, "uDISCO 对肿瘤软组织形态保持风险大。"),
    ("19", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("19", "FDISCO"):  (2.00, "FDISCO 可保留 FP，但有机溶剂对肿瘤血管形态有风险。"),
    ("19", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("19", "TDE"):     (1.50, "TDE 适合切片。"),
    ("19", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("19", "BoneClear"): (0.0, "不适用。"),
    ("19", "ClearSee"):  (0.0, "不适用。"),
    ("19", "EyeCi"):     (0.0, "不适用。"),
    ("19", "FlyClear"):  (0.0, "不适用。"),
    ("19", "ClearT2"):   (0.75, "更适合小样本。"),
    ("19", "Ce3D"):      (2.00, "Ce3D 对厚组织有效。"),
    ("19", "SWITCH"):    (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("19", "BABB"):      (1.50, "BABB 对肿瘤形态有风险。"),

    # Q20: CUBIC failed => need gentler morphology-preserving method
    ("20", "CUBIC"):   (1.75, "原 CUBIC-L 7 天 + 直接 CUBIC-R 导致失败，方法执行不当；但 CUBIC 体系本身仍可用，需优化。"),
    ("20", "ScaleS"):  (2.75, "ScaleS 形态保持优秀，是 CUBIC 失败后的优选替代。"),
    ("20", "SOLID"):   (2.75, "SOLID 水相法对肿瘤脑块形态保持好，是优选替代。"),
    ("20", "SeeDB2"):  (2.50, "SeeDB2 形态保持好，适合小块脑组织。"),
    ("20", "iDISCO+"): (1.25, "iDISCO+ 对肿瘤软组织形态风险大，不适合。"),
    ("20", "uDISCO"):  (1.25, "uDISCO 对肿瘤软组织形态风险大。"),
    ("20", "PEGASOS"): (0.75, "PEGASOS 对脑组织过于剧烈，不适合。"),
    ("20", "FDISCO"):  (1.75, "FDISCO 有机溶剂对肿瘤血管形态有风险。"),
    ("20", "MACS"):    (2.25, "MACS 水相法快速温和。"),
    ("20", "TDE"):     (1.50, "TDE 适合切片。"),
    ("20", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("20", "BoneClear"): (0.0, "不适用。"),
    ("20", "ClearSee"):  (0.0, "不适用。"),
    ("20", "EyeCi"):     (0.0, "不适用。"),
    ("20", "FlyClear"):  (0.0, "不适用。"),
    ("20", "ClearT2"):   (0.75, "更适合小样本。"),
    ("20", "Ce3D"):      (1.75, "Ce3D 对厚组织有效但有机溶剂有形态风险。"),
    ("20", "SWITCH"):    (2.25, "SWITCH 水相法形态保持较好。"),
    ("20", "BABB"):      (1.25, "BABB 对肿瘤形态有风险。"),

    # Q21: sparse FP brain block, weak signal, morphology preservation, long-term storage
    ("21", "ScaleS"):  (3.00, "ScaleS 是 FP 保留金标准，极适合稀疏弱信号神经元成像。"),
    ("21", "SeeDB2"):  (2.75, "SeeDB2 FP 保留极佳，适合脑片/小块高分辨率成像。"),
    ("21", "FDISCO"):  (2.50, "FDISCO 对 FP 保留好，但 3 mm 脑块用 SeeDB2/ScaleS 更简便。"),
    ("21", "CUBIC"):   (2.25, "CUBIC 对 FP 保留好，但弱稀疏信号下 ScaleS/SeeDB2 更优。"),
    ("21", "SOLID"):   (2.25, "SOLID 对 FP 与形态保持均衡。"),
    ("21", "TDE"):     (2.50, "TDE 适合脑片快速 RI 匹配，对弱 FP 保留好。"),
    ("21", "FOCM"):    (2.25, "FOCM 面向脑片，快速且 FP 兼容。"),
    ("21", "MACS"):    (2.00, "MACS 可快速处理脑块，FP 保留尚可。"),
    ("21", "iDISCO+"): (0.50, "iDISCO+ 会淬灭内源 FP，极不适合弱信号稀疏标记。"),
    ("21", "uDISCO"):  (0.75, "uDISCO 会显著淬灭内源 FP，不适合弱信号。"),
    ("21", "PEGASOS"): (0.50, "PEGASOS 对脑块剧烈，FP 淬灭严重。"),
    ("21", "BoneClear"): (0.0, "不适用。"),
    ("21", "ClearSee"):  (0.0, "不适用。"),
    ("21", "EyeCi"):     (0.0, "不适用。"),
    ("21", "FlyClear"):  (0.0, "不适用。"),
    ("21", "ClearT2"):   (0.75, "更适合胚胎。"),
    ("21", "Ce3D"):      (1.50, "Ce3D 对厚组织有效，但 FP 保留一般。"),
    ("21", "SWITCH"):    (1.50, "SWITCH 对内源 FP 保留一般。"),
    ("21", "BABB"):      (1.00, "BABB 对 FP 保留差。"),
}


def get_expert_score(qid, method):
    key = (qid, method)
    if key in EXPERT_SCORES:
        return EXPERT_SCORES[key]
    # fallback: use method traits + machine s_method if available
    return (None, None)


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    ri_ref = json.loads(RI_REF_PATH.read_text(encoding="utf-8"))

    records = []
    missing = []
    for item in data:
        qid = item["question_id"]
        method_raw = item["machine_evaluation"]["meta_data"].get("target_method", "UNKNOWN")
        method = normalize_method(method_raw)

        machine_s_trans = item["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        machine_s_method = item["machine_evaluation"]["scores"]["effectiveness"]["s_method"]["score"]
        machine_s_label = item["machine_evaluation"]["scores"]["effectiveness"]["s_label"]["score"]
        human_s_trans = item["human_evaluation"]["effectiveness"]["s_trans"]["score"]

        score, reason = get_expert_score(qid, method)
        if score is None:
            missing.append((qid, method))
            # fallback: rescaled s_method
            score = round_quarter(clamp(machine_s_method / 5.0 * 3.0, 0.0, 3.0))
            reason = f"未手工评分，回退到机器 s_method 缩放（{machine_s_method:.2f}/5 -> {score:.2f}/3）。"

        records.append({
            "model_name": item["model_name"],
            "question_id": qid,
            "method": method,
            "machine_s_trans": machine_s_trans,
            "machine_s_method": machine_s_method,
            "machine_s_label": machine_s_label,
            "human_s_trans": human_s_trans,
            "expert_s_trans": score,
            "expert_reason": reason,
        })

    # aggregate per (qid, method)
    pair_scores = defaultdict(list)
    for r in records:
        pair_scores[(r["question_id"], r["method"])].append(r)

    # compute agreement metrics
    arr = np.array([[r["machine_s_trans"], r["human_s_trans"], r["expert_s_trans"]] for r in records])
    machine = arr[:, 0]
    human = arr[:, 1]
    expert = arr[:, 2]

    def pearson(a, b): return float(stats.pearsonr(a, b)[0])
    def spearman(a, b): return float(stats.spearmanr(a, b)[0])
    def agreement_report(a, b, name_a, name_b):
        return {
            "pearson": pearson(a, b),
            "spearman": spearman(a, b),
            "icc": icc_2_1(np.column_stack([a, b])),
            "mae": float(np.mean(np.abs(a - b))),
            "rmse": float(np.sqrt(np.mean((a - b)**2))),
        }

    metrics = {
        "machine vs human": agreement_report(machine, human, "machine_s_trans", "human_s_trans"),
        "expert vs human": agreement_report(expert, human, "expert_s_trans", "human_s_trans"),
        "expert vs machine": agreement_report(expert, machine, "expert_s_trans", "machine_s_trans"),
    }

    # build markdown report
    lines = []
    lines.append("# s_trans 方法适合度重新评估报告\n")
    lines.append("## 1. 评分理念与维度\n")
    lines.append("原 `s_trans` 仅基于 RI 域匹配（`RI_tissue` vs `RI_method_ref`）计算连续分。")
    lines.append("专家在判断“方法-组织是否匹配”时，会同时考虑：\n")
    lines.append("1. **样本类型匹配**：方法 historically 为哪类样本设计（如 BoneClear 专为骨、EyeCi 专为眼）。")
    lines.append("2. **目标结构适配**：方法能否满足透明深度、分辨率、长程追踪等需求。")
    lines.append("3. **标记兼容性**：内源 FP 保留 vs 免疫标记/染料渗透能力。")
    lines.append("4. **特殊需求**：形态保持、避免收缩、避免电泳损伤、超长样本等。\n")
    lines.append("本报告据此对 240 条记录重新给出 0–3 分（0.25 步进）的方法适合度评分。\n")

    lines.append("## 2. 一致性指标对比\n")
    lines.append("| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |")
    lines.append("|---|---|---|---|---|---|")
    for pair, m in metrics.items():
        lines.append(f"| {pair} | {m['pearson']:.3f} | {m['spearman']:.3f} | {m['icc']:.3f} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines.append("")

    lines.append("## 3. 各题方法适合度评分表\n")
    lines.append("| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 s_trans | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for (qid, method), recs in sorted(pair_scores.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        profile = QUESTION_PROFILE.get(qid, {})
        sample_target = f"{profile.get('sample', '')} / {profile.get('target', '')}"[:60]
        r0 = recs[0]
        lines.append(f"| {qid} | {sample_target} | {method} | {r0['machine_s_trans']:.2f} | {r0['human_s_trans']:.2f} | {r0['expert_s_trans']:.2f} | {r0['expert_reason']} |")
    lines.append("")

    lines.append("## 4. 机器 vs 专家差异显著案例\n")
    diffs = []
    for r in records:
        diffs.append((abs(r["machine_s_trans"] - r["expert_s_trans"]), r))
    diffs.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 机器 s_trans | 专家 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['machine_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 5. 人工 vs 专家差异显著案例\n")
    diffs_h = []
    for r in records:
        diffs_h.append((abs(r["human_s_trans"] - r["expert_s_trans"]), r))
    diffs_h.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 人工 s_trans | 专家 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs_h[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['human_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 6. 分布对比\n")
    for name, scores in [("机器 s_trans", machine), ("人工 s_trans", human), ("专家 s_trans", expert)]:
        lines.append(f"- **{name}**: mean={scores.mean():.3f}, std={scores.std():.3f}, min={scores.min():.3f}, max={scores.max():.3f}")
    lines.append("")

    # per-question metrics
    lines.append("## 7. 逐题一致性\n")
    lines.append("| 题号 | 机器 vs 人工 (r/ρ/ICC) | 专家 vs 人工 (r/ρ/ICC) | 专家 vs 机器 (r/ρ/ICC) |")
    lines.append("|---|---|---|---|")
    qids = sorted(set(r["question_id"] for r in records), key=int)
    for qid in qids:
        recs_q = [r for r in records if r["question_id"] == qid]
        m_q = np.array([r["machine_s_trans"] for r in recs_q])
        h_q = np.array([r["human_s_trans"] for r in recs_q])
        e_q = np.array([r["expert_s_trans"] for r in recs_q])
        def fmt(a, b):
            return f"{pearson(a,b):.2f}/{spearman(a,b):.2f}/{icc_2_1(np.column_stack([a,b])):.2f}"
        lines.append(f"| {qid} | {fmt(m_q,h_q)} | {fmt(e_q,h_q)} | {fmt(e_q,m_q)} |")
    lines.append("")

    lines.append("## 8. 为什么专家评分与现有人工评分差异较大？\n")
    lines.append("专家评分与现有人工 s_trans 的相关性较低（Pearson r≈0.09，Spearman ρ≈0.01），这本身是一个重要发现。可能原因包括：\n")
    lines.append("1. **人工评分原就高度不一致**：同一 (题号, 方法) 组合在不同模型/评分者之间差异大，说明人类对 s_trans 的判定标准尚未统一。")
    lines.append("2. **人工评分可能仍部分依赖 RI 直觉**：许多人工高分出现在机器 RI 匹配也高的组合上，即使方法本身并不适合该应用（如 Q2 的 iDISCO+ 配内源 GFP）。")
    lines.append("3. **专家评分更强调方法设计用途**：例如 uDISCO 在超长 CNS/脊髓长程追踪中获得高分，而人工评分者可能更关注其收缩/淬灭副作用。")
    lines.append("4. **s_trans 与 s_label 的边界模糊**：本报告按用户要求把“方法对这道题是否合适”纳入 s_trans，自然会与 s_label 有部分重叠；原人工评分者可能把标记兼容性问题更多地归入 s_label。\n")
    lines.append("因此，本报告应被视为**基于方法适合度原则的重新标定提案**，而非对现有人工评分的简单修正。\n")

    lines.append("## 9. 结论与建议\n")
    lines.append("1. 专家评分将 s_trans 从单一 RI 匹配扩展为“方法-样本-目标-标记”综合适合度。")
    lines.append("2. 明显不合理的组合（如 BoneClear/ClearSee/EyeCi/FlyClear 用于小鼠脑）被直接判为 0，这与方法适合度的直觉更一致。")
    lines.append("3. 对于机器评分较高但专家评分较低的情况，通常是因为机器仅看 RI 接近，而专家考虑方法设计样本/形态风险/标记兼容性。")
    lines.append("4. **建议**：在修改 JSON 前，请组织 1–2 名领域专家独立复核本报告中的评分与理由；")
    lines.append("   如确认无误，可将 `expert_s_trans` 写入 `human_evaluation.effectiveness.s_trans.score`，")
    lines.append("   并同步更新总分与注释。\n")

    if missing:
        lines.append("## 8. 未手工评分而使用回退的组合\n")
        for qid, method in sorted(set(missing), key=lambda x: (int(x[0]), x[1])):
            lines.append(f"- Q{qid} + {method}")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")

    # also write per-record JSON for inspection
    json_out = pathlib.Path("s_trans_expert_scores.json")
    json_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Per-record scores written to {json_out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
