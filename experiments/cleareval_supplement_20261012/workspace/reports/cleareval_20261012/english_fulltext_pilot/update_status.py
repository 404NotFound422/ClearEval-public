"""Add the completed pilot to navigation, preserving every earlier status entry."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=Path(r"C:\ClearEval")
verification=json.loads((HERE/"delivery_verification.json").read_text(encoding="utf-8"))
assert verification["passed"]
marker="2026-10-12 全文统一英文实测续记"
root_entry=(marker+"：已完成 8 份存档答案（4 题、4 生成模型）的原文/英文全文重解析，28 个输入位置、12 个受控配对，原文基线 8/8 复现。"
            "C04/C07 英译后 SR 由 0 提升至 1/3、4/7；C04 删除后段 6 条操作仍为 1/3，SP 从 12/37 升至 12/31，C07 删除相应块后 SR/SP 均归零。"
            "确认语言影响与残余阶段/实例错配、长标题误分步、SP 分母变化相互独立；保留全部原始值。"
            "4 份旧时间来源账本的 5 个分支已逐项复算，非新增时间提取。新增生成式请求 0，仍 438/438；8 个 Qwen 全文翻译请求已准备并提交追加最多 8 次／2 小时的确认，未发送，旧定性 Cor 试验仍单独待定。"
            "本轮未新增完整 CCE、重复评价、专家或湿实验结果，论文总体目标仍未完成。"
            "[本轮完整结果](reports/cleareval_20261012/english_fulltext_pilot/REPORT_zh.md) · [实际命令](reports/cleareval_20261012/english_fulltext_pilot/commands.md)。")
day_entry=(marker+"：全文 SR/SP 与 12 个受控配对已运行；C04 删除不降 SR、C07 多参考命中同一句及英文长标题误计步骤均有逐句证据。"
           "[结果、时间实例和后续方案](english_fulltext_pilot/REPORT_zh.md) · [逐答案表](english_fulltext_pilot/baseline_comparison.csv)。"
           "新增生成式调用 0；8 个 Qwen 翻译输入已准备、追加额度待回复。")
snap=HERE/"navigation_before"
snap.mkdir(exist_ok=True)
changes=[]
for path,name,entry in [(ROOT/"STATUS.md","STATUS.md",root_entry),(HERE.parent/"README.md","day_README.md",day_entry)]:
    before=path.read_bytes()
    text=before.decode("utf-8-sig")
    if marker in text:
        changes.append({"path":str(path),"reused_existing_entry":True});continue
    target=snap/name
    assert not target.exists(),"Existing navigation snapshot requires review"
    target.write_bytes(before)
    header,sep,rest=text.partition("\n")
    updated=header+"\n\n"+entry+"\n\n"+rest.lstrip("\r\n")
    path.write_text(updated,encoding="utf-8",newline="")
    changes.append({"path":str(path),"before_sha256":hashlib.sha256(before).hexdigest(),
                    "after_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"before_snapshot":str(target)})
(HERE/"navigation_updates.json").write_text(json.dumps({"utc":datetime.now(timezone.utc).isoformat(),"changes":changes,
                                                       "actual_command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv])},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"navigation_files":len(changes),"new_generative_requests":0}))
