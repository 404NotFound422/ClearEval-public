"""Write a current resumable checkpoint; never launch an experiment."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'method_family_followup_v1'
def main():
    ledger=[json.loads(x) for x in (BASE/'judges/request_ledger.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    n=sum(x.get('event')=='request_started' for x in ledger)
    stage={'status':'active_development_followup','requests':n,'limit':300,'remaining':300-n,
        'completed':['method_family_steps_v1','representation_normalization_v1','output_contract_v1','output_identity_v2'],
        'in_progress':['Frozen-prompt public-development E2 and E4 execution and analysis','Current report integration'],
        'original_main_numeric_CCE':50,'new_conditional_operation_numeric_SR':66,'answers':77,
        'human_expert_returns':0,'overall_goal_complete':False,'no_automatic_holdout_run':True,
        'actual_command':[sys.executable,*sys.argv]}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'activity.json').write_text(json.dumps(stage,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=f'''# ClearEval r2 当前检查点

本轮继续执行中，请从 [method_family_followup_v1/activity.json](method_family_followup_v1/activity.json) 与实际产物恢复。当前请求 **{n}/300**，余 **{300-n}**。

同方法候选评分已完成：77份固定答案中66份有条件性SR/联合敏感性数值，27份实际比较两个作者版本；11份NA。原主结果50/77保留。先看[逐答案SR命中数/分母](method_family_steps_v1/t070_per_answer.csv)、[规则及来源](method_family_steps_v1/README.md)。固定13模型Q*仍仅q2。

[词面分割开发诊断](representation_normalization_v1/README.md)已完成21全文/15原配对、三阈值：3个条目合并对的SR/SP差归零。此为既有开发变体的表示检查，不是语义准确性或留出验证。

输出契约v1及完整名称提示v2各完成5次新开发请求，均4成功/1失败；A04泛称重复键仍失败，原严格解析和NA保留。见[v1结果](judges/output_contract_v1/analysis/RESULTS_zh.md)、[v2结果](judges/output_identity_v2/analysis/RESULTS_zh.md)。不声称提示已修复，不推广到留出或替换专家建议版本。

同方法评分、词面分割和两批开发提取均已独立核验。公开开发E2完整配对与E4两评价器重复已冻结并通过运行前检查，正在按E2后E4执行；其目的包括记录失败的可重复性，原4/5失败门槛不改成通过。无新提示调参。实际完成数以各批trial及真实receipt为准，不从计划推定完成。[E2入口](judges/controls_contract_v2/README.md)、[E4入口](judges/identity_stability_dev_v1/README.md)。

已核查可借鉴的正式发表方法，见[文献与改进对应](method_family_followup_v1/PUBLISHED_METHODS_zh.md)；新建议不改变当前冻结实验。

SeeDB2原文及勘误已恢复，但完整切片流程尚不能作为3mm脑块路线：[范围缺口](method_family_reference_seedb_v1/README.md)。专家仍一位5开发+15留出，真实回传0；原旧尺度和湿实验依赖保留。

旧136次报告完整保存在[快照](historical_reports/before_method_family_at_136/snapshot_manifest.json)。旧报告生成器依赖136次账本，不适用于新阶段。当前只读刷新命令：`python scripts/cce_checkpoint_method_family_v1.py`；新阶段完成后再切换正式报告入口。
'''
    (BASE/'STATUS.md').write_text(text,encoding='utf-8')
    (ROOT.parent/'STATUS.md').write_text('# ClearEval 当前状态\n\n最新进度见[仓库STATUS](ClearEval-public/artifacts/cce_validation/STATUS.md)。\n\n'+f'当前请求{n}/300；本轮同方法多版本、分割诊断及公开开发评价实验进行中。不要从旧136次报告重新启动。\n',encoding='utf-8')
    print(json.dumps({'status':'checkpoint_written','requests':n,'new_requests':0}))
if __name__=='__main__':main()
