"""Preserve historical navigation and publish the local, completed batch index."""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
P=R3/'source_context_validation_proposal_01'
D=R3/'delivery_completed_01'


def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def bind(p): return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
    with p.open('x',encoding='utf-8') as f:
        json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


def main():
    completed=read(P/'execution_completed.json')
    assert completed['actual_new_requests']==10 and completed['remaining_requests']==0
    assert read(P/'readout_complete_01/verification.json')['status']=='pass'
    assert read(P/'author_claim_audit_01/verification.json')['status']=='pass'
    previous=read(D/'source_context_proposal_addendum.json')
    prior_paths={Path(b['path']):b for b in previous['new_artifacts']}
    unchanged=[];preserved=[]
    for f,b in prior_paths.items():
        current=bind(f)
        if current['sha256']==b['sha256']:
            unchanged.append(current)
        else:
            assert f==P/'latest_analysis.json',f
            snapshot=P/'latest_analysis_before_execution.json'
            assert bind(snapshot)['sha256']==b['sha256']
            preserved.append({'old':b,'snapshot':bind(snapshot),'current':current,
                'reason':'Mutable analysis pointer advanced after actual approved execution; previous bytes preserved.'})
    for row in previous['navigation_updates']:
        assert bind(Path(row['path']))['sha256']==row['after_sha256']
    folder=P/'navigation_before_execution_delivery'
    folder.mkdir()
    stamp=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    introductions={
        ROOT.parent/'STATUS.md':f'{stamp}（北京时间）实际执行续记：已按用户“批准”完成追加 10/10 次本地 Qwen 评价，复用 5 份基线，形成 15 个观测、10 个实际配对；全包累计 438/438，无重试。三条件原始 SR/SP、EGES 和 Com 均逐值不变，完整 CCE 均为 1/5。A05 的操作参考值错配在 K2 修正，但量表落档、题目范围和 3 mm 参考适用性问题仍在，候选未升级为主评价器。797 项机械检查通过、375 处答案引用可定位；作者来源核查不冒称专家结果。专家回执与湿实验仍为 0，整体目标未完成。[完整结果与实例](ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/source_context_validation_proposal_01/RESULTS_zh.md) · [逐答案 CSV](ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/source_context_validation_proposal_01/RESULTS_PER_ANSWER.csv) · [实际命令](ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/source_context_validation_proposal_01/RUN_COMMANDS_ACTUAL.md)。当前额度以[本批预算快照](ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/source_context_validation_proposal_01/budget_snapshot.json)为准，剩余 0；旧第三轮固定计次入口仅适用于其历史阶段。下列“待批准／428”文字保留为当时的记录。[交付续记](ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/delivery_completed_01/source_context_execution_addendum.json)。',
        R3/'STATUS.md':f'{stamp}（北京时间）实际执行续记：[来源限定＋证据说明对比](source_context_validation_proposal_01/RESULTS_zh.md)已完成 10/10 新请求、5 份原成功基线复用和 10 个实际配对；十份均技术成功，全包 438/438，无重试，授权余量 0。SR/SP、EGES 和 Com 逐值不变，主完整 CCE 为 K0/K1/K2 各 1/5。局部参考值对应改善，但出现／保留了题目范围与量表判档问题，K2 未替换主评价器。797 项计算与来源检查通过，375 处答案引用可定位；24 条预定优先记录和 3 条探索记录已作作者核查，不增加专家预算或冒称科学准确率。专家和湿实验回传仍为 0，整体目标未完成。[逐答案表](source_context_validation_proposal_01/RESULTS_PER_ANSWER.csv) · [实际命令](source_context_validation_proposal_01/RUN_COMMANDS_ACTUAL.md) · [完成记录](source_context_validation_proposal_01/execution_completed.json) · [交付续记](delivery_completed_01/source_context_execution_addendum.json)。当前恢复应使用本批分析入口和预算快照，旧 Round3 计数器不能用于这十次新阶段请求；本轮 run 已无待执行格，新增评价需另行授权。以下早期的“待批准／428”记录保留原义。'
    }
    nav=[]
    for path,intro in introductions.items():
        before=path.read_bytes()
        snapshot=folder/('root_STATUS.md' if path==ROOT.parent/'STATUS.md' else 'round3_STATUS.md')
        with snapshot.open('xb') as f:f.write(before)
        original=before.decode('utf-8')
        heading,sep,body=original.partition('\n')
        path.write_bytes((heading+sep+'\n'+intro+'\n'+body).encode('utf-8'))
        nav.append({'path':str(path),'before_sha256':hashlib.sha256(before).hexdigest(),
                    'snapshot':bind(snapshot),'after_sha256':bind(path)['sha256'],'change_kind':'navigation_only'})
    save(P/'latest_results.json',{'status':'completed_with_scientific_limitations',
        'completion':bind(P/'execution_completed.json'),'report':bind(P/'RESULTS_zh.md'),
        'per_answer_csv':bind(P/'RESULTS_PER_ANSWER.csv'),
        'source_claim_audit':bind(P/'author_claim_audit_01/summary.json'),
        'scientific_goal_complete':False,'candidate_promoted':False})
    files=sorted({*P.rglob('*'),*(ROOT/'scripts'/n for n in [
        'cce_source_context_readout_v1.py','cce_source_context_claim_audit_v1.py',
        'cce_write_source_context_annotations_v1.py','cce_deliver_source_context_results_v1.py'])})
    fresh=[bind(f) for f in files if f.is_file() and (f not in prior_paths or bind(f)['sha256']!=prior_paths[f]['sha256'])]
    links=[]
    documents=[P/'RESULTS_zh.md',P/'MANUSCRIPT_SUPPLEMENT_EN.md',P/'early_mechanism_note_01_zh.md',*introductions]
    for doc in documents:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if re.match(r'https?://',target) or target.startswith('#'):continue
            target=target.split('#')[0].strip('<>')
            f=(doc.parent/target).resolve()
            # The addendum being generated below is the sole intentional forward link.
            assert f.exists() or f==D/'source_context_execution_addendum.json',(doc,target)
            links.append({'document':str(doc),'target':target,'resolved':str(f)})
    manifest={'created_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Actual approved ten-request execution, paired readout, author source audit, and manuscript supplement.',
        'experiment_complete':True,'overall_research_goal_complete':False,'candidate_promoted':False,
        'prior_addendum':bind(D/'source_context_proposal_addendum.json'),
        'prior_artifacts_unchanged':unchanged,'preserved_mutable_artifacts':preserved,
        'navigation_updates':nav,'new_or_updated_artifacts':fresh,'verified_local_links':links,
        'authorization':bind(P/'additional_authorization.json'),'execution_seal':bind(P/'execution_seal.json'),
        'actual_new_requests':10,'cached_baselines':5,'actual_pairs':10,'package_requests':438,
        'remaining_requests':0,'automatic_retries':False,
        'ledger_before':bind(P/'baseline_ledger_snapshot.jsonl'),'ledger_after':bind(P/'ledger_after_execution.jsonl'),
        'global_budget_before':bind(P/'global_budget_before_execution.json'),
        'global_budget_after':bind(ROOT/'artifacts/cce_validation/budget.json'),
        'external_dependencies':bind(P/'external_dependencies_after_execution.json')}
    save(D/'source_context_execution_addendum.json',manifest)
    for row in links:assert Path(row['resolved']).exists()
    for b in fresh+unchanged:assert bind(Path(b['path']))==b
    print(json.dumps({'status':'pass','new_or_updated_artifacts':len(fresh),
        'unchanged_prior_artifacts':len(unchanged),'preserved_pointer_snapshots':len(preserved),
        'verified_local_links':len(links),'navigation_updates':len(nav)},ensure_ascii=False))


if __name__=='__main__':main()
