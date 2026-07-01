"""
s_trans 方法-组织类型匹配重新评估报告生成器（v2）

用户明确：s_trans 仅考察方法与组织类型是否匹配，不考虑荧光/标记兼容性。
因此本版评分只基于：
  1) 方法设计样本类型与题目组织是否一致；
  2) 样本尺寸/透明深度是否在该方法常规适用范围内；
  3) 目标结构（长程投射、血管网络、轴突追踪等）能否被该方法实现；
  4) 组织形态保持/收缩/脆裂等组织-方法层面的副作用。
荧光/抗体兼容性问题归入 s_label，不在本评分中考虑。
"""

import json
import numpy as np
from scipy import stats
from collections import defaultdict
import pathlib

DATA_PATH = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
OUTPUT_PATH = pathlib.Path("s_trans_method_suitability_report_v2.md")


def icc_2_1(y: np.ndarray) -> float:
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


METHOD_NAME_MAP = {
    "SCALE (ScaleS)": "ScaleS",
    "iDISCO (iDISCO+)": "iDISCO+",
    "seeDB2": "SeeDB2",
    "BABB (BA/BB) solvent clearing (not PEGASOS)": "BABB",
}


def normalize_method(name):
    return METHOD_NAME_MAP.get(name, name)


QUESTION_PROFILE = {
    "2":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "neuronal morphology", "special": "whole-brain morphology"},
    "3":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "cFos+ neurons (IEG)", "special": "whole-brain, single-cell resolution"},
    "4":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "activated neurons (IEG)", "special": "CUBIC failed"},
    "5":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "axons/regenerated fibers", "special": "long fiber tracing"},
    "6":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons", "special": "long fiber tracing"},
    "7":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons", "special": "long fiber tracing"},
    "8":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons", "special": "electrophoresis failed"},
    "9":  {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projection fibers", "special": "ultra-long sample"},
    "10": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projections + axon skeleton", "special": "ultra-long sample"},
    "11": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range connections", "special": "ultra-long sample"},
    "12": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projections + axon skeleton", "special": "solvent shrinkage failed"},
    "13": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques", "special": "whole brain"},
    "14": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques (validation)", "special": "whole brain"},
    "15": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaque quantification", "special": "whole brain"},
    "16": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques", "special": "solvent immunolabeling failed"},
    "17": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor + vasculature", "special": "morphology preservation"},
    "18": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor vasculature + BBB", "special": "morphology preservation"},
    "19": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "vascular remodeling + invasion", "special": "morphology preservation"},
    "20": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor + vasculature + BBB", "special": "CUBIC failed, morphology preservation"},
    "21": {"sample": "mouse brain block (sparse FP)", "size": "3 mm", "target": "sparse neurons morphology", "special": "morphology preservation"},
}


# ---------------------------------------------------------------------------
# 专家评分：仅考察方法-组织类型匹配，不考虑荧光/标记兼容性
# 分档：3.0 非常适合；2.0–2.75 适合；1.0–1.75 可用但不理想；0–0.75 不适合
# ---------------------------------------------------------------------------
EXPERT_SCORES = {
    # Q2: adult whole brain morphology
    ("2", "FDISCO"):  (2.75, "FDISCO 为成年小鼠全脑优化，透明深度与神经元形态保持兼顾。"),
    ("2", "uDISCO"):  (2.50, "uDISCO 面向全身/小鼠整体透明，可处理成年全脑。"),
    ("2", "CUBIC"):   (2.50, "CUBIC 设计用于小鼠脑/器官，对全脑温和有效。"),
    ("2", "ScaleS"):  (2.00, "ScaleS 主要用于成年鼠脑切片/薄样本，全脑深度有限。"),
    ("2", "SOLID"):   (2.25, "SOLID 适用于小鼠全脑透明。"),
    ("2", "SeeDB2"):  (2.00, "SeeDB2 偏向高分辨率脑片，完整全脑深度有限。"),
    ("2", "PEGASOS"): (1.00, "PEGASOS 面向全身/致密组织，对脑组织过于剧烈。"),
    ("2", "iDISCO+"): (2.75, "iDISCO+ 专为成年小鼠脑/器官设计，透明深度极佳。"),
    ("2", "BoneClear"): (0.0, "BoneClear 专为骨设计，不适用于脑。"),
    ("2", "ClearSee"): (0.0, "ClearSee 为植物样本设计，不适用于鼠脑。"),
    ("2", "EyeCi"):    (0.0, "EyeCi 为眼球/视网膜设计，不适用于全脑。"),
    ("2", "FlyClear"): (0.0, "FlyClear 为果蝇设计，不适用于小鼠脑。"),
    ("2", "TDE"):      (1.00, "TDE 主要用作脑片/细胞的 RI 匹配，不适合完整全脑。"),
    ("2", "FOCM"):     (1.00, "FOCM 面向脑片快速透明，不适合完整成年全脑。"),
    ("2", "ClearT2"):  (0.75, "ClearT2 为斑马鱼/胚胎优化，不适合成年小鼠全脑。"),
    ("2", "Ce3D"):     (1.75, "Ce3D 面向淋巴结/厚组织，对全脑神经元形态非最优。"),
    ("2", "MACS"):     (2.25, "MACS 适用于脑/器官透明。"),
    ("2", "SWITCH"):   (2.25, "SWITCH 适用于小鼠全脑。"),
    ("2", "BABB"):     (2.25, "BABB 为传统脑组织有机溶剂法，可透明全脑。"),

    # Q3/Q4: whole brain, IEG immunolabeling (tissue aspect only)
    ("3", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑/器官设计，是全脑免疫标记的经典组织透明法。"),
    ("3", "CUBIC"):   (2.50, "CUBIC 适用于小鼠全脑，支持全脑抗体渗透。"),
    ("3", "uDISCO"):  (2.25, "uDISCO 可透明全脑，但主要用于全身/长投射样本。"),
    ("3", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("3", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("3", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("3", "SWITCH"):  (2.50, "SWITCH 适用于小鼠全脑均匀标记。"),
    ("3", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("3", "BoneClear"): (0.0, "不适用。"),
    ("3", "ClearSee"): (0.0, "不适用。"),
    ("3", "EyeCi"):    (0.0, "不适用。"),
    ("3", "FlyClear"): (0.0, "不适用。"),
    ("3", "TDE"):      (1.00, "TDE 适用于切片。"),
    ("3", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("3", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("3", "Ce3D"):     (1.75, "Ce3D 对厚组织有效，但全脑神经元非其主场。"),
    ("3", "MACS"):     (2.25, "MACS 适用于脑免疫标记。"),
    ("3", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片，全脑抗体渗透有限。"),
    ("3", "BABB"):     (2.00, "BABB 可透明全脑。"),

    ("4", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑设计，是全脑免疫标记经典方案。"),
    ("4", "CUBIC"):   (2.50, "CUBIC 适用于小鼠全脑；原失败是执行问题，方法本身匹配。"),
    ("4", "uDISCO"):  (2.25, "uDISCO 可透明全脑。"),
    ("4", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("4", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("4", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("4", "SWITCH"):  (2.50, "SWITCH 适用于小鼠全脑均匀标记。"),
    ("4", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("4", "BoneClear"): (0.0, "不适用。"),
    ("4", "ClearSee"): (0.0, "不适用。"),
    ("4", "EyeCi"):    (0.0, "不适用。"),
    ("4", "FlyClear"): (0.0, "不适用。"),
    ("4", "TDE"):      (1.00, "TDE 适用于切片。"),
    ("4", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("4", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("4", "Ce3D"):     (1.75, "Ce3D 对厚组织有效。"),
    ("4", "MACS"):     (2.25, "MACS 适用于脑免疫标记。"),
    ("4", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片。"),
    ("4", "BABB"):     (2.00, "BABB 可透明全脑。"),

    # Q5-Q8: rat spinal cord injury segment, long axon tracing
    ("5", "CUBIC"):   (2.50, "CUBIC 对脊髓组织温和，15 mm 长段形态保持好，适合轴突追踪。"),
    ("5", "ScaleS"):  (2.00, "ScaleS 形态保持好，但对 15 mm 长段透明深度有限。"),
    ("5", "SOLID"):   (2.50, "SOLID 适用于神经组织，对脊髓损伤节段形态保持好。"),
    ("5", "SeeDB2"):  (2.00, "SeeDB2 适合脑片/薄段，对 15 mm 长段深度有限。"),
    ("5", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态有风险。"),
    ("5", "FDISCO"):  (2.25, "FDISCO 可透明脊髓，但溶剂法形态保持不如水相法。"),
    ("5", "uDISCO"):  (2.00, "uDISCO 可处理长段组织，但收缩/脆裂风险对损伤脊髓形态不利。"),
    ("5", "PEGASOS"): (1.00, "PEGASOS 对软组织过于剧烈。"),
    ("5", "MACS"):    (2.25, "MACS 可快速温和地透明脊髓。"),
    ("5", "TDE"):     (1.00, "TDE 适合切片，不适合 15 mm 长段。"),
    ("5", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("5", "BoneClear"): (0.0, "不适用。"),
    ("5", "ClearSee"): (0.0, "不适用。"),
    ("5", "EyeCi"):    (0.0, "不适用。"),
    ("5", "FlyClear"): (0.0, "不适用。"),
    ("5", "ClearT2"):  (0.75, "更适合小样本。"),
    ("5", "Ce3D"):    (2.00, "Ce3D 对厚组织有效，可用于脊髓轴突追踪。"),
    ("5", "SWITCH"):  (2.25, "SWITCH 支持脊髓免疫标记且形态保持较好。"),
    ("5", "BABB"):    (2.00, "BABB 可透明脊髓但形态保持有限。"),

    ("6", "CUBIC"):   (2.50, "CUBIC 对脊髓组织温和，适合轴突追踪。"),
    ("6", "ScaleS"):  (2.00, "ScaleS 形态保持好但深度有限。"),
    ("6", "SOLID"):   (2.50, "SOLID 适用于脊髓。"),
    ("6", "SeeDB2"):  (2.00, "SeeDB2 适合脑片/薄段。"),
    ("6", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓，但溶剂法形态风险。"),
    ("6", "FDISCO"):  (2.25, "FDISCO 可透明脊髓。"),
    ("6", "uDISCO"):  (2.00, "uDISCO 可处理长段，但收缩/脆裂风险。"),
    ("6", "PEGASOS"): (1.00, "PEGASOS 对软组织过于剧烈。"),
    ("6", "MACS"):    (2.25, "MACS 可快速温和地透明脊髓。"),
    ("6", "TDE"):     (1.00, "TDE 适合切片。"),
    ("6", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("6", "BoneClear"): (0.0, "不适用。"),
    ("6", "ClearSee"): (0.0, "不适用。"),
    ("6", "EyeCi"):    (0.0, "不适用。"),
    ("6", "FlyClear"): (0.0, "不适用。"),
    ("6", "ClearT2"):  (0.75, "更适合小样本。"),
    ("6", "Ce3D"):    (2.00, "Ce3D 可用于脊髓轴突追踪。"),
    ("6", "SWITCH"):  (2.25, "SWITCH 支持脊髓免疫标记。"),
    ("6", "BABB"):    (2.00, "BABB 可透明脊髓。"),

    ("7", "CUBIC"):   (2.50, "CUBIC 对脊髓组织温和，适合轴突追踪。"),
    ("7", "ScaleS"):  (2.00, "ScaleS 形态保持好但深度有限。"),
    ("7", "SOLID"):   (2.50, "SOLID 适用于脊髓。"),
    ("7", "SeeDB2"):  (2.00, "SeeDB2 适合脑片/薄段。"),
    ("7", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓，但溶剂法形态风险。"),
    ("7", "FDISCO"):  (2.25, "FDISCO 可透明脊髓。"),
    ("7", "uDISCO"):  (2.00, "uDISCO 可处理长段，但收缩/脆裂风险。"),
    ("7", "PEGASOS"): (1.00, "PEGASOS 对软组织过于剧烈。"),
    ("7", "MACS"):    (2.25, "MACS 可快速温和地透明脊髓。"),
    ("7", "TDE"):     (1.00, "TDE 适合切片。"),
    ("7", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("7", "BoneClear"): (0.0, "不适用。"),
    ("7", "ClearSee"): (0.0, "不适用。"),
    ("7", "EyeCi"):    (0.0, "不适用。"),
    ("7", "FlyClear"): (0.0, "不适用。"),
    ("7", "ClearT2"):  (0.75, "更适合小样本。"),
    ("7", "Ce3D"):    (2.00, "Ce3D 可用于脊髓轴突追踪。"),
    ("7", "SWITCH"):  (2.25, "SWITCH 支持脊髓免疫标记。"),
    ("7", "BABB"):    (2.00, "BABB 可透明脊髓。"),

    # Q8: electrophoresis failed => avoid electrophoresis (most methods here are passive anyway)
    ("8", "CUBIC"):   (2.75, "CUBIC 被动水相法，无电泳，对脊髓损伤节段温和且形态保持好。"),
    ("8", "ScaleS"):  (2.00, "ScaleS 无电泳，但 15 mm 长段深度有限。"),
    ("8", "SOLID"):   (2.75, "SOLID 被动水相法，无电泳，适合脊髓。"),
    ("8", "SeeDB2"):  (2.00, "SeeDB2 无电泳，但深度有限。"),
    ("8", "iDISCO+"): (2.25, "iDISCO+ 为被动溶剂法，无电泳，可透明脊髓。"),
    ("8", "FDISCO"):  (2.25, "FDISCO 无电泳，可透明脊髓。"),
    ("8", "uDISCO"):  (2.00, "uDISCO 被动有机溶剂法，无电泳，但收缩/脆裂风险。"),
    ("8", "PEGASOS"): (1.00, "PEGASOS 对软组织过于剧烈。"),
    ("8", "MACS"):    (2.25, "MACS 被动水相法，无电泳。"),
    ("8", "TDE"):     (1.00, "TDE 适合切片。"),
    ("8", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("8", "BoneClear"): (0.0, "不适用。"),
    ("8", "ClearSee"): (0.0, "不适用。"),
    ("8", "EyeCi"):    (0.0, "不适用。"),
    ("8", "FlyClear"): (0.0, "不适用。"),
    ("8", "ClearT2"):  (0.75, "更适合小样本。"),
    ("8", "Ce3D"):    (2.00, "Ce3D 可用于脊髓。"),
    ("8", "SWITCH"):  (2.25, "SWITCH 被动水相法，无电泳。"),
    ("8", "BABB"):    (2.00, "BABB 无电泳，但形态保持有限。"),

    # Q9-Q12: whole mouse CNS, 35-40 mm, long-range projections
    ("9", "uDISCO"):  (2.75, "uDISCO 是全身/长程投射透明化的经典方法，最适合完整 CNS。"),
    ("9", "FDISCO"):  (2.50, "FDISCO 可透明完整 CNS。"),
    ("9", "CUBIC"):   (1.75, "CUBIC 对 35–40 mm 完整 CNS 透明深度可能不足。"),
    ("9", "ScaleS"):  (1.25, "ScaleS 主要面向脑片，不适合完整 CNS。"),
    ("9", "iDISCO+"): (2.25, "iDISCO+ 可透明完整 CNS。"),
    ("9", "PEGASOS"): (1.75, "PEGASOS 可处理全身，但对 CNS 精细形态不利。"),
    ("9", "SOLID"):   (1.75, "SOLID 对完整 CNS 深度可能不足。"),
    ("9", "SeeDB2"):  (1.00, "SeeDB2 面向脑片。"),
    ("9", "MACS"):    (1.75, "MACS 对超长 CNS 深度可能不足。"),
    ("9", "TDE"):     (0.75, "TDE 适合切片。"),
    ("9", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("9", "BoneClear"): (0.0, "不适用。"),
    ("9", "ClearSee"): (0.0, "不适用。"),
    ("9", "EyeCi"):    (0.0, "不适用。"),
    ("9", "FlyClear"): (0.0, "不适用。"),
    ("9", "ClearT2"):  (0.75, "更适合小样本。"),
    ("9", "Ce3D"):    (1.75, "Ce3D 对厚组织有效，但对完整 CNS 非最优。"),
    ("9", "SWITCH"):  (1.75, "SWITCH 对完整 CNS 深度有限。"),
    ("9", "BABB"):    (2.25, "BABB 可透明长 CNS 样本。"),

    ("10", "uDISCO"):  (2.75, "uDISCO 最适合完整 CNS 长程投射。"),
    ("10", "FDISCO"):  (2.50, "FDISCO 可透明完整 CNS。"),
    ("10", "CUBIC"):   (1.75, "CUBIC 对完整 CNS 深度有限。"),
    ("10", "ScaleS"):  (1.25, "ScaleS 面向脑片。"),
    ("10", "iDISCO+"): (2.25, "iDISCO+ 可透明完整 CNS。"),
    ("10", "PEGASOS"): (1.75, "PEGASOS 对 CNS 形态不利。"),
    ("10", "SOLID"):   (1.75, "SOLID 对完整 CNS 深度有限。"),
    ("10", "SeeDB2"):  (1.00, "SeeDB2 面向脑片。"),
    ("10", "MACS"):    (1.75, "MACS 对超长 CNS 深度有限。"),
    ("10", "TDE"):     (0.75, "TDE 适合切片。"),
    ("10", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("10", "BoneClear"): (0.0, "不适用。"),
    ("10", "ClearSee"): (0.0, "不适用。"),
    ("10", "EyeCi"):    (0.0, "不适用。"),
    ("10", "FlyClear"): (0.0, "不适用。"),
    ("10", "ClearT2"):  (0.75, "更适合小样本。"),
    ("10", "Ce3D"):    (1.75, "Ce3D 对厚组织有效。"),
    ("10", "SWITCH"):  (1.75, "SWITCH 对完整 CNS 深度有限。"),
    ("10", "BABB"):    (2.25, "BABB 可透明长 CNS 样本。"),

    ("11", "uDISCO"):  (2.75, "uDISCO 最适合完整 CNS 长程投射。"),
    ("11", "FDISCO"):  (2.50, "FDISCO 可透明完整 CNS。"),
    ("11", "CUBIC"):   (1.75, "CUBIC 对完整 CNS 深度有限。"),
    ("11", "ScaleS"):  (1.25, "ScaleS 面向脑片。"),
    ("11", "iDISCO+"): (2.25, "iDISCO+ 可透明完整 CNS。"),
    ("11", "PEGASOS"): (1.75, "PEGASOS 对 CNS 形态不利。"),
    ("11", "SOLID"):   (1.75, "SOLID 对完整 CNS 深度有限。"),
    ("11", "SeeDB2"):  (1.00, "SeeDB2 面向脑片。"),
    ("11", "MACS"):    (1.75, "MACS 对超长 CNS 深度有限。"),
    ("11", "TDE"):     (0.75, "TDE 适合切片。"),
    ("11", "FOCM"):    (0.75, "FOCM 面向脑片。"),
    ("11", "BoneClear"): (0.0, "不适用。"),
    ("11", "ClearSee"): (0.0, "不适用。"),
    ("11", "EyeCi"):    (0.0, "不适用。"),
    ("11", "FlyClear"): (0.0, "不适用。"),
    ("11", "ClearT2"):  (0.75, "更适合小样本。"),
    ("11", "Ce3D"):    (1.75, "Ce3D 对厚组织有效。"),
    ("11", "SWITCH"):  (1.75, "SWITCH 对完整 CNS 深度有限。"),
    ("11", "BABB"):    (2.25, "BABB 可透明长 CNS 样本。"),

    # Q12: solvent shrinkage failed => prefer aqueous methods
    ("12", "CUBIC"):   (2.75, "CUBIC 水相法无收缩，对完整 CNS 形态保持最好，是避免收缩的首选。"),
    ("12", "ScaleS"):  (2.00, "ScaleS 无收缩但透明深度有限。"),
    ("12", "SOLID"):   (2.75, "SOLID 水相法无收缩，适合 CNS。"),
    ("12", "SeeDB2"):  (1.75, "SeeDB2 无收缩但深度有限。"),
    ("12", "iDISCO+"): (1.75, "iDISCO+ 有机溶剂，收缩风险。"),
    ("12", "FDISCO"):  (2.00, "FDISCO 有机溶剂，仍有收缩风险。"),
    ("12", "uDISCO"):  (2.00, "uDISCO 可透明完整 CNS，但有机溶剂有一定收缩。"),
    ("12", "PEGASOS"): (1.00, "PEGASOS 收缩大，不适合。"),
    ("12", "MACS"):    (2.25, "MACS 水相法无收缩。"),
    ("12", "TDE"):     (1.00, "TDE 适合切片。"),
    ("12", "FOCM"):    (1.00, "FOCM 面向脑片。"),
    ("12", "BoneClear"): (0.0, "不适用。"),
    ("12", "ClearSee"): (0.0, "不适用。"),
    ("12", "EyeCi"):    (0.0, "不适用。"),
    ("12", "FlyClear"): (0.0, "不适用。"),
    ("12", "ClearT2"):  (0.75, "更适合小样本。"),
    ("12", "Ce3D"):    (1.50, "Ce3D 有机溶剂有收缩风险。"),
    ("12", "SWITCH"):  (2.25, "SWITCH 水相法无收缩。"),
    ("12", "BABB"):    (1.25, "BABB 收缩风险大，不适合。"),

    # Q13-Q16: 5XFAD whole brain, amyloid plaques
    ("13", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑设计，是全脑免疫标记的经典组织透明法。"),
    ("13", "CUBIC"):   (2.50, "CUBIC 适用于小鼠全脑，支持全脑抗体渗透。"),
    ("13", "uDISCO"):  (2.25, "uDISCO 可透明全脑。"),
    ("13", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("13", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("13", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("13", "SWITCH"):  (2.50, "SWITCH 适用于小鼠全脑均匀标记。"),
    ("13", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("13", "BoneClear"): (0.0, "不适用。"),
    ("13", "ClearSee"): (0.0, "不适用。"),
    ("13", "EyeCi"):    (0.0, "不适用。"),
    ("13", "FlyClear"): (0.0, "不适用。"),
    ("13", "TDE"):      (1.00, "TDE 适合切片。"),
    ("13", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("13", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("13", "Ce3D"):     (1.75, "Ce3D 对厚组织有效。"),
    ("13", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片。"),
    ("13", "BABB"):     (2.00, "BABB 可透明全脑。"),

    ("14", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记。"),
    ("14", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记。"),
    ("14", "uDISCO"):  (2.25, "uDISCO 可透明全脑。"),
    ("14", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("14", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("14", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("14", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("14", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("14", "BoneClear"): (0.0, "不适用。"),
    ("14", "ClearSee"): (0.0, "不适用。"),
    ("14", "EyeCi"):    (0.0, "不适用。"),
    ("14", "FlyClear"): (0.0, "不适用。"),
    ("14", "TDE"):      (1.00, "TDE 适合切片。"),
    ("14", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("14", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("14", "Ce3D"):     (1.75, "Ce3D 对厚组织有效。"),
    ("14", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片。"),
    ("14", "BABB"):     (2.00, "BABB 可透明全脑。"),

    ("15", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记与定量。"),
    ("15", "CUBIC"):   (2.50, "CUBIC 支持全脑免疫标记。"),
    ("15", "uDISCO"):  (2.25, "uDISCO 可透明全脑。"),
    ("15", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("15", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("15", "SOLID"):   (2.25, "SOLID 适用于全脑免疫标记。"),
    ("15", "SWITCH"):  (2.50, "SWITCH 适合全脑均匀免疫标记。"),
    ("15", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("15", "BoneClear"): (0.0, "不适用。"),
    ("15", "ClearSee"): (0.0, "不适用。"),
    ("15", "EyeCi"):    (0.0, "不适用。"),
    ("15", "FlyClear"): (0.0, "不适用。"),
    ("15", "TDE"):      (1.00, "TDE 适合切片。"),
    ("15", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("15", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("15", "Ce3D"):     (1.75, "Ce3D 对厚组织有效。"),
    ("15", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片。"),
    ("15", "BABB"):     (2.00, "BABB 可透明全脑。"),

    # Q16: solvent immunolabeling failed => prefer aqueous
    ("16", "CUBIC"):   (2.75, "CUBIC 水相法更适合长时间抗体渗透，是避免溶剂免疫标记失败的首选。"),
    ("16", "SWITCH"):  (2.75, "SWITCH 专为均匀免疫标记设计，水相法无溶剂问题。"),
    ("16", "iDISCO+"): (2.50, "iDISCO+ 仍为全脑免疫标记经典，但需优化抗体孵育时间/浓度。"),
    ("16", "uDISCO"):  (2.00, "uDISCO 属有机溶剂，免疫标记信号可能仍弱。"),
    ("16", "FDISCO"):  (2.25, "FDISCO 适用于成年小鼠全脑。"),
    ("16", "ScaleS"):  (1.75, "ScaleS 对完整全脑抗体渗透深度有限。"),
    ("16", "SOLID"):   (2.50, "SOLID 水相法适合免疫标记。"),
    ("16", "PEGASOS"): (0.75, "PEGASOS 对脑过于剧烈。"),
    ("16", "BoneClear"): (0.0, "不适用。"),
    ("16", "ClearSee"): (0.0, "不适用。"),
    ("16", "EyeCi"):    (0.0, "不适用。"),
    ("16", "FlyClear"): (0.0, "不适用。"),
    ("16", "TDE"):      (1.00, "TDE 适合切片。"),
    ("16", "FOCM"):     (1.00, "FOCM 面向脑片。"),
    ("16", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("16", "Ce3D"):     (1.75, "Ce3D 对厚组织有效。"),
    ("16", "SeeDB2"):   (1.75, "SeeDB2 偏向脑片。"),
    ("16", "BABB"):     (1.25, "BABB 溶剂法免疫标记信号弱，不适合。"),

    # Q17-Q20: GBM brain block, morphology + vasculature preservation
    ("17", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与肿瘤边界。"),
    ("17", "ScaleS"):  (2.50, "ScaleS 形态保持优秀，适合脑块。"),
    ("17", "SOLID"):   (2.50, "SOLID 适用于神经组织，形态保持好。"),
    ("17", "SeeDB2"):  (2.25, "SeeDB2 形态保持好，适合脑片/小块。"),
    ("17", "iDISCO+"): (2.25, "iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。"),
    ("17", "uDISCO"):  (2.00, "uDISCO 对肿瘤软组织形态保持风险较大。"),
    ("17", "FDISCO"):  (2.25, "FDISCO 可透明成年小鼠脑块。"),
    ("17", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈，形态破坏风险高。"),
    ("17", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("17", "TDE"):     (1.50, "TDE 适合切片。"),
    ("17", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("17", "BoneClear"): (0.0, "不适用。"),
    ("17", "ClearSee"): (0.0, "不适用。"),
    ("17", "EyeCi"):    (0.0, "不适用。"),
    ("17", "FlyClear"): (0.0, "不适用。"),
    ("17", "ClearT2"):  (0.75, "更适合小样本。"),
    ("17", "Ce3D"):     (2.00, "Ce3D 对厚组织有效，可用于肿瘤血管。"),
    ("17", "SWITCH"):   (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("17", "BABB"):     (1.75, "BABB 对肿瘤形态有风险。"),

    ("18", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与 BBB 结构。"),
    ("18", "ScaleS"):  (2.50, "ScaleS 形态保持优秀。"),
    ("18", "SOLID"):   (2.50, "SOLID 适用于神经组织。"),
    ("18", "SeeDB2"):  (2.25, "SeeDB2 形态保持好。"),
    ("18", "iDISCO+"): (2.25, "iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。"),
    ("18", "uDISCO"):  (2.00, "uDISCO 对肿瘤软组织形态保持风险较大。"),
    ("18", "FDISCO"):  (2.25, "FDISCO 可透明成年小鼠脑块。"),
    ("18", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("18", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("18", "TDE"):     (1.50, "TDE 适合切片。"),
    ("18", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("18", "BoneClear"): (0.0, "不适用。"),
    ("18", "ClearSee"): (0.0, "不适用。"),
    ("18", "EyeCi"):    (0.0, "不适用。"),
    ("18", "FlyClear"): (0.0, "不适用。"),
    ("18", "ClearT2"):  (0.75, "更适合小样本。"),
    ("18", "Ce3D"):     (2.00, "Ce3D 对厚组织有效。"),
    ("18", "SWITCH"):   (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("18", "BABB"):     (1.75, "BABB 对肿瘤形态有风险。"),

    ("19", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与侵袭前沿。"),
    ("19", "ScaleS"):  (2.50, "ScaleS 形态保持优秀。"),
    ("19", "SOLID"):   (2.50, "SOLID 适用于神经组织。"),
    ("19", "SeeDB2"):  (2.25, "SeeDB2 形态保持好。"),
    ("19", "iDISCO+"): (2.25, "iDISCO+ 可透明脑块，但有机溶剂对软组织形态风险。"),
    ("19", "uDISCO"):  (2.00, "uDISCO 对肿瘤软组织形态保持风险较大。"),
    ("19", "FDISCO"):  (2.25, "FDISCO 可透明成年小鼠脑块。"),
    ("19", "PEGASOS"): (1.00, "PEGASOS 对脑组织过于剧烈。"),
    ("19", "MACS"):    (2.25, "MACS 对脑组织快速温和。"),
    ("19", "TDE"):     (1.50, "TDE 适合切片。"),
    ("19", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("19", "BoneClear"): (0.0, "不适用。"),
    ("19", "ClearSee"): (0.0, "不适用。"),
    ("19", "EyeCi"):    (0.0, "不适用。"),
    ("19", "FlyClear"): (0.0, "不适用。"),
    ("19", "ClearT2"):  (0.75, "更适合小样本。"),
    ("19", "Ce3D"):     (2.00, "Ce3D 对厚组织有效。"),
    ("19", "SWITCH"):   (2.25, "SWITCH 支持免疫标记且形态保持较好。"),
    ("19", "BABB"):     (1.75, "BABB 对肿瘤形态有风险。"),

    # Q20: CUBIC failed => need gentler morphology-preserving method
    ("20", "CUBIC"):   (1.75, "原 CUBIC-L 7 天 + 直接 CUBIC-R 执行不当导致失败；CUBIC 体系本身仍匹配，但需优化。"),
    ("20", "ScaleS"):  (2.75, "ScaleS 形态保持优秀，是 CUBIC 失败后的优选替代。"),
    ("20", "SOLID"):   (2.75, "SOLID 水相法对肿瘤脑块形态保持好，是优选替代。"),
    ("20", "SeeDB2"):  (2.50, "SeeDB2 形态保持好，适合小块脑组织。"),
    ("20", "iDISCO+"): (1.75, "iDISCO+ 对肿瘤软组织形态风险大，不适合。"),
    ("20", "uDISCO"):  (1.75, "uDISCO 对肿瘤软组织形态保持风险大。"),
    ("20", "FDISCO"):  (1.75, "FDISCO 有机溶剂对肿瘤血管形态有风险。"),
    ("20", "PEGASOS"): (0.75, "PEGASOS 对脑组织过于剧烈，不适合。"),
    ("20", "MACS"):    (2.25, "MACS 水相法快速温和。"),
    ("20", "TDE"):     (1.50, "TDE 适合切片。"),
    ("20", "FOCM"):    (1.50, "FOCM 面向脑片。"),
    ("20", "BoneClear"): (0.0, "不适用。"),
    ("20", "ClearSee"): (0.0, "不适用。"),
    ("20", "EyeCi"):    (0.0, "不适用。"),
    ("20", "FlyClear"): (0.0, "不适用。"),
    ("20", "ClearT2"):  (0.75, "更适合小样本。"),
    ("20", "Ce3D"):     (1.75, "Ce3D 对厚组织有效但有机溶剂有形态风险。"),
    ("20", "SWITCH"):   (2.25, "SWITCH 水相法形态保持较好。"),
    ("20", "BABB"):     (1.25, "BABB 对肿瘤形态有风险。"),

    # Q21: sparse FP brain block, 3mm, morphology preservation
    ("21", "ScaleS"):  (2.75, "ScaleS 形态保持优秀，极适合 3 mm 脑块高分辨率成像。"),
    ("21", "SeeDB2"):  (2.75, "SeeDB2 形态保持好，适合脑片/小块。"),
    ("21", "FDISCO"):  (2.50, "FDISCO 可透明成年小鼠脑块。"),
    ("21", "CUBIC"):   (2.25, "CUBIC 适用于小鼠脑块。"),
    ("21", "SOLID"):   (2.25, "SOLID 适用于脑块。"),
    ("21", "TDE"):     (2.25, "TDE 适合脑片快速 RI 匹配。"),
    ("21", "FOCM"):    (2.25, "FOCM 面向脑片，快速有效。"),
    ("21", "MACS"):    (2.00, "MACS 可快速处理脑块。"),
    ("21", "iDISCO+"): (2.00, "iDISCO+ 可透明 3 mm 脑块；荧光淬灭问题归入 s_label。"),
    ("21", "uDISCO"):  (1.75, "uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。"),
    ("21", "PEGASOS"): (0.75, "PEGASOS 对脑块过于剧烈。"),
    ("21", "BoneClear"): (0.0, "不适用。"),
    ("21", "ClearSee"): (0.0, "不适用。"),
    ("21", "EyeCi"):    (0.0, "不适用。"),
    ("21", "FlyClear"): (0.0, "不适用。"),
    ("21", "ClearT2"):  (0.75, "更适合胚胎/小样本。"),
    ("21", "Ce3D"):     (1.75, "Ce3D 对厚组织有效，但 3 mm 脑块非最优。"),
    ("21", "SWITCH"):   (2.00, "SWITCH 可处理脑块。"),
    ("21", "BABB"):     (1.75, "BABB 可透明脑块但形态保持有限。"),
}


def get_expert_score(qid, method):
    return EXPERT_SCORES.get((qid, method), (None, None))


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records = []
    missing = []
    for item in data:
        qid = item["question_id"]
        method_raw = item["machine_evaluation"]["meta_data"].get("target_method", "UNKNOWN")
        method = normalize_method(method_raw)

        machine_s_trans = item["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        machine_s_method = item["machine_evaluation"]["scores"]["effectiveness"]["s_method"]["score"]
        human_s_trans = item["human_evaluation"]["effectiveness"]["s_trans"]["score"]

        score, reason = get_expert_score(qid, method)
        if score is None:
            missing.append((qid, method))
            score = round_quarter(clamp(machine_s_method / 5.0 * 3.0, 0.0, 3.0))
            reason = f"未手工评分，回退到机器 s_method 缩放（{machine_s_method:.2f}/5 -> {score:.2f}/3）。"

        records.append({
            "model_name": item["model_name"],
            "question_id": qid,
            "method": method,
            "machine_s_trans": machine_s_trans,
            "human_s_trans": human_s_trans,
            "expert_s_trans": score,
            "expert_reason": reason,
        })

    pair_scores = defaultdict(list)
    for r in records:
        pair_scores[(r["question_id"], r["method"])].append(r)

    arr = np.array([[r["machine_s_trans"], r["human_s_trans"], r["expert_s_trans"]] for r in records])
    machine = arr[:, 0]
    human = arr[:, 1]
    expert = arr[:, 2]

    def pearson(a, b): return float(stats.pearsonr(a, b)[0])
    def spearman(a, b): return float(stats.spearmanr(a, b)[0])
    def agreement_report(a, b):
        return {
            "pearson": pearson(a, b),
            "spearman": spearman(a, b),
            "icc": icc_2_1(np.column_stack([a, b])),
            "mae": float(np.mean(np.abs(a - b))),
            "rmse": float(np.sqrt(np.mean((a - b)**2))),
        }

    metrics = {
        "machine vs human": agreement_report(machine, human),
        "expert v2 vs human": agreement_report(expert, human),
        "expert v2 vs machine": agreement_report(expert, machine),
    }

    lines = []
    lines.append("# s_trans 方法-组织类型匹配重新评估报告（v2，不考虑荧光）\n")
    lines.append("## 1. 评分理念\n")
    lines.append("用户明确：`s_trans` **仅考察方法与组织类型是否匹配**，不考虑荧光/标记兼容性（荧光兼容由 `s_label` 负责）。")
    lines.append("本版评分只基于：\n")
    lines.append("1. **方法设计样本类型**与题目组织是否一致（如 BoneClear 专为骨）。")
    lines.append("2. **样本尺寸/透明深度**是否在该方法常规适用范围内（如 TDE 不适合完整全脑）。")
    lines.append("3. **目标结构**能否被该方法实现（如超长 CNS 长程投射需要全身/长投射透明法）。")
    lines.append("4. **组织-方法层面的副作用**（形态保持、收缩、脆裂等）。\n")

    lines.append("## 2. 一致性指标对比\n")
    lines.append("| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |")
    lines.append("|---|---|---|---|---|---|")
    for pair, m in metrics.items():
        lines.append(f"| {pair} | {m['pearson']:.3f} | {m['spearman']:.3f} | {m['icc']:.3f} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines.append("")

    lines.append("## 3. 各题方法-组织匹配评分表\n")
    lines.append("| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 v2 s_trans | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for (qid, method), recs in sorted(pair_scores.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        profile = QUESTION_PROFILE.get(qid, {})
        sample_target = f"{profile.get('sample', '')} / {profile.get('target', '')}"[:60]
        r0 = recs[0]
        lines.append(f"| {qid} | {sample_target} | {method} | {r0['machine_s_trans']:.2f} | {r0['human_s_trans']:.2f} | {r0['expert_s_trans']:.2f} | {r0['expert_reason']} |")
    lines.append("")

    lines.append("## 4. 机器 vs 专家 v2 差异显著案例\n")
    diffs = [(abs(r["machine_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v2 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['machine_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 5. 人工 vs 专家 v2 差异显著案例\n")
    diffs_h = [(abs(r["human_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs_h.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 人工 s_trans | 专家 v2 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs_h[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['human_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 6. 分布对比\n")
    for name, scores in [("机器 s_trans", machine), ("人工 s_trans", human), ("专家 v2 s_trans", expert)]:
        lines.append(f"- **{name}**: mean={scores.mean():.3f}, std={scores.std():.3f}, min={scores.min():.3f}, max={scores.max():.3f}")
    lines.append("")

    lines.append("## 7. 逐题一致性\n")
    lines.append("| 题号 | 机器 vs 人工 (r/ρ/ICC) | 专家 v2 vs 人工 (r/ρ/ICC) | 专家 v2 vs 机器 (r/ρ/ICC) |")
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

    lines.append("## 8. 结论与建议\n")
    lines.append("1. v2 专家评分严格限定在“方法-组织类型匹配”，不再因荧光淬灭而压低 iDISCO+/uDISCO 等溶剂法的分数。")
    lines.append("2. 与机器 s_trans（RI 公式）相比，v2 评分在方法设计用途、样本尺寸、形态保持等维度上做了人工修正。")
    lines.append("3. 若专家 v2 与人工评分仍有显著差异，需进一步澄清：人工评分是否确实仅基于组织匹配，还是仍混入了荧光/标记/时间等其它维度。")
    lines.append("4. **建议**：由领域专家复核 v2 评分表；确认后可写入 `human_evaluation.effectiveness.s_trans.score`。\n")

    if missing:
        lines.append("## 9. 未手工评分而使用回退的组合\n")
        for qid, method in sorted(set(missing), key=lambda x: (int(x[0]), x[1])):
            lines.append(f"- Q{qid} + {method}")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")

    json_out = pathlib.Path("s_trans_expert_scores_v2.json")
    json_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Per-record scores written to {json_out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
