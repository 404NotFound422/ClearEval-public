"""Offline, source-bound local step review. No labels, embedding, or model calls.

Only selected reviewed reference steps enter denominators. This never estimates
full manual SR or a population error rate from the deliberately selected rows.
"""
import argparse, collections, csv, hashlib, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
HUMAN = BASE / 'human_review'
DEFAULT = HUMAN / 'local_step_audit'
EXPERT = ['review_status', 'expert_candidate_covers_reference', 'expert_reference_covered_in_full_answer',
          'expert_covering_span_start', 'expert_covering_span_end', 'expert_covering_span_quote',
          'expert_alternative_span_start', 'expert_alternative_span_end', 'expert_alternative_span_quote',
          'source_location', 'expert_basis', 'reviewer_id', 'review_date']

def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def rawsha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def digest(o): return rawsha(json.dumps(o, ensure_ascii=False, sort_keys=True))
def require(ok, msg):
    if not ok: raise ValueError(msg)
def write(p, obj):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
def csvread(p):
    with pathlib.Path(p).open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))
def csvwrite(p, rows):
    pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
    with pathlib.Path(p).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def binding(path): return {'path': str(pathlib.Path(path).resolve()), 'sha256': sha(path)}
def verify_binding(b): require(sha(b['path']) == b['sha256'], 'Changed frozen source: ' + b['path'])
def stat(n, d): return {'numerator': n, 'denominator': d, 'fraction': n/d if d else None}

def build(args):
    config, run, per = read(args.config), read(args.run), read(args.per_answer)
    require(digest(config) == run['config_hash'], 'Run/config hash mismatch')
    per = {r['answer_id']: r for r in per}
    matches = {r['answer_id']: r for r in read(args.matches)}
    refs = {r['reference_id']: r for r in read(args.references)['references']}
    ids = csvread(args.identities)
    require(len(ids) == 20 and sum(r['split'] == 'audit_dev' for r in ids) == 5, 'Expected original 5+15 selection')
    threshold = config['completeness']['primary_threshold']
    rows, answers, sources = [], [], []
    for identity in ids:
        aid = identity['answer_id']; packet_path = args.packets / (aid + '.json'); p = read(packet_path)
        require(rawsha(p['answer_text']) == identity['answer_sha256'] == p['answer_sha256'], 'Answer binding mismatch')
        require(rawsha(p['task_text']) == identity['question_sha256'] == p['question_sha256'], 'Question binding mismatch')
        sources.append(binding(packet_path))
        answer = {'answer_id': aid, 'split': identity['split'], 'packet': binding(packet_path),
                  'answer_sha256': identity['answer_sha256'], 'question_sha256': identity['question_sha256']}
        if identity['split'] != 'audit_dev':
            answer.update(status='pending_holdout_expert_configuration_freeze', selected_rows=0)
            answers.append(answer); continue
        key = identity['model_name'] + '__q' + identity['question_id']
        score, step = per[key], matches[key]
        require(score['answer_sha256'] == identity['answer_sha256'] and score['question_sha256'] == identity['question_sha256'], 'Pilot text hash mismatch')
        require(score['config_hash'] == run['config_hash'], 'Per-answer config mismatch')
        ref = refs[step['reference_id']]
        require(score['reference_id'] == ref['reference_id'] and len(step['matches']) == len(ref['steps']), 'Reference match binding mismatch')
        require(sha(ref['source_path']) == ref['source_sha256'], 'Reference source bytes changed')
        candidates = step['matches']
        require(all(c['reference_text'] == ref['steps'][c['reference_index']]['text'] for c in candidates), 'Reference text differs')
        # Rule fixed before labels: RI module first (last RI if repeated), else
        # final reference operation; second is nearest threshold, stable index tie.
        ri = [i for i,s in enumerate(ref['steps']) if s.get('module') == 'ri_matching']
        fixed_index = ri[-1] if ri else len(ref['steps'])-1
        fixed = next(c for c in candidates if c['reference_index'] == fixed_index)
        rest = sorted((c for c in candidates if c is not fixed), key=lambda c:(abs(c['similarity']-threshold), c['reference_index']))
        selected = [(fixed, 'fixed_ri_module_else_final_reference_operation')]
        if rest: selected.append((rest[0], 'nearest_absolute_threshold_margin_other_reference_stable_index_tie'))
        answer.update(status='development_source_extracted_local_candidates_pending_expert',
            selected_rows=len(selected), reference_id=ref['reference_id'], reference_n=len(ref['steps']),
            automatic_matched_reference_n=sum(c['matched'] for c in candidates),
            reference_status=ref['status'], full_manual_SR=None)
        answers.append(answer)
        for match, reason in selected:
            rindex, gindex = match['reference_index'], match['generated_index']
            g = step['generated_steps'][gindex]; refstep = ref['steps'][rindex]
            require(g['text'] == match['generated_text'] and 0 <= g['start'] < g['end'] <= len(p['answer_text']), 'Generated candidate/offset mismatch')
            require(bool(match['matched']) == (match['similarity'] >= threshold), 'Threshold decision mismatch')
            row = {'audit_id': aid + ':' + refstep['step_id'], 'answer_id': aid, 'split': identity['split'],
                'reference_id': ref['reference_id'], 'reference_step_id': refstep['step_id'], 'reference_index': rindex,
                'reference_text': refstep['text'], 'reference_status': ref['status'],
                'source_path': ref['source_path'], 'source_sha256': ref['source_sha256'], 'source_anchor': refstep.get('source_anchor', ''),
                'reference_library_sha256': sha(args.references), 'selection_rule': reason,
                'auto_generated_index': gindex, 'auto_span_start': g['start'], 'auto_span_end': g['end'],
                'auto_normalized_text': g['text'], 'auto_raw_span_quote': p['answer_text'][g['start']:g['end']],
                'auto_matched': str(bool(match['matched'])).lower(), 'auto_similarity': match['similarity'], 'threshold': threshold,
                'config_hash': run['config_hash'], 'answer_sha256': identity['answer_sha256'], 'question_sha256': identity['question_sha256']}
            row.update({k: 'not_reviewed' if k == 'review_status' else '' for k in EXPERT}); rows.append(row)
    manifest = {'version': 'local-step-audit-v2-source-extracted', 'scope': 'assisted_local_development_no_population_error_estimate',
        'sources': {k: binding(getattr(args,k)) for k in ['matches','references','config','run','per_answer','identities','selection','original_review']},
        'script': binding(__file__), 'packets': sources, 'answers': answers, 'rows': rows,
        'selection_policy': 'For each fixed development answer: last ri_matching reference module (else final operation), then another reference nearest threshold; stable index tie. No generator, total-score or direction-of-effect selection. Holdout pending.',
        'expert_labels_added': 0, 'new_model_requests': 0, 'config_expert_frozen': False}
    dest = args.out / 'manifest.json'
    if dest.exists(): require(read(dest) == manifest, 'Frozen build changed: use another output directory')
    else: write(dest, manifest)
    review = args.out / 'review_rows.csv'
    if not review.exists(): csvwrite(review, rows)
    else: verify_rows(manifest, csvread(review))
    write(args.out / 'answer_status.json', answers)
    write(args.out / 'execution_build.json', {'executable':sys.executable,'argv':sys.argv,'new_model_requests':0})
    (args.out / 'README.md').write_text(README, encoding='utf-8')
    print(json.dumps({'selected_answers':len(ids),'development_answers':5,'candidate_rows':len(rows),'holdout_pending':15,'expert_labels_added':0}))

def verify_rows(manifest, rows):
    original = {r['audit_id']:r for r in manifest['rows']}
    require(len(rows) == len(original) and len({r['audit_id'] for r in rows}) == len(rows), 'Review row set changed')
    for row in rows:
        require(row['audit_id'] in original, 'Unknown review row')
        for k,v in original[row['audit_id']].items():
            if k not in EXPERT: require(str(v) == row[k], 'Immutable review field changed: ' + k)

def validate_review(row, text):
    status = row['review_status']
    require(status in {'not_reviewed','reviewed','needs_source'}, 'Invalid review status')
    if status == 'not_reviewed':
        require(not any(row[k] for k in EXPERT if k != 'review_status'), 'Judgments present on not_reviewed row')
        return False
    require(all(row[k].strip() for k in ['source_location','expert_basis','reviewer_id','review_date']), 'Review provenance incomplete')
    allowed = {'yes','no','insufficient_evidence'}
    require(row['expert_candidate_covers_reference'] in allowed and row['expert_reference_covered_in_full_answer'] in allowed, 'Both distinct coverage decisions required')
    if status == 'needs_source': return False
    for prefix in ['expert_covering_span','expert_alternative_span']:
        parts = [row[prefix+s] for s in ['_start','_end','_quote']]
        if any(parts):
            require(all(parts), 'Incomplete expert span')
            start,end = int(parts[0]),int(parts[1])
            require(0 <= start < end <= len(text) and text[start:end] == parts[2], 'Expert span is not verbatim at claimed offsets')
    if row['expert_candidate_covers_reference'] == 'yes':
        require(row['expert_reference_covered_in_full_answer'] == 'yes', 'Candidate coverage implies full-answer coverage')
        require(bool(row['expert_covering_span_quote']), 'Positive candidate decision needs exact covering span')
        require(int(row['auto_span_start']) <= int(row['expert_covering_span_start']) < int(row['expert_covering_span_end']) <= int(row['auto_span_end']), 'Candidate evidence lies outside automatic candidate')
    if row['expert_reference_covered_in_full_answer'] == 'yes' and row['expert_candidate_covers_reference'] != 'yes':
        require(bool(row['expert_alternative_span_quote']), 'Positive whole-answer coverage needs alternative span')
    return True

def summarize(args):
    manifest = read(args.out/'manifest.json')
    verify_binding(manifest['script'])
    for key,b in manifest['sources'].items():
        # The original human table is an integrity snapshot, not a frozen model
        # input; its genuine later expert return must not block this local review.
        if key != 'original_review': verify_binding(b)
    rows = csvread(args.review or args.out/'review_rows.csv'); verify_rows(manifest,rows)
    packets = {}
    for answer in manifest['answers']:
        verify_binding(answer['packet']); packets[answer['answer_id']] = read(answer['packet']['path'])
    accepted=[]
    for row in rows:
        if validate_review(row,packets[row['answer_id']]['answer_text']): accepted.append(row)
    false_match_den=[r for r in accepted if r['auto_matched']=='true' and r['expert_candidate_covers_reference'] in {'yes','no'}]
    actual_positive=[r for r in accepted if r['expert_reference_covered_in_full_answer']=='yes']
    missed_negative=[r for r in accepted if r['auto_matched']=='false' and r['expert_reference_covered_in_full_answer'] in {'yes','no'}]
    answer_results=[]
    for a in manifest['answers']:
        judged=[r for r in accepted if r['answer_id']==a['answer_id'] and r['expert_reference_covered_in_full_answer'] in {'yes','no'}]
        delta=sum((r['expert_reference_covered_in_full_answer']=='yes')-(r['auto_matched']=='true') for r in judged)
        result={'answer_id':a['answer_id'],'split':a['split'],'selected_rows':a['selected_rows'],
            'definitively_reviewed_references':len(judged),'status':'local_review_returned' if judged else 'pending',
            'confirmed_local_matched_count_delta':delta if judged else None,
            'confirmed_local_SR_contribution_delta':delta/a['reference_n'] if judged else None,
            'manual_SR':None,'full_answer_corrected_SR':None}
        if judged:
            pos=sum(r['expert_reference_covered_in_full_answer']=='yes' for r in judged); unreviewed=a['reference_n']-len(judged)
            result['full_answer_coverage_fraction_bounds_from_partial_review_only']=[pos/a['reference_n'],(pos+unreviewed)/a['reference_n']]
            result['full_answer_SR_delta_bounds_from_partial_review_only']=[(pos-a['automatic_matched_reference_n'])/a['reference_n'],(pos+unreviewed-a['automatic_matched_reference_n'])/a['reference_n']]
        answer_results.append(result)
    result={'status':'local_partial_review_available' if accepted else 'needs_human_labels','review_mode':'ASSISTED',
        'reviewed_rows':len(accepted),'not_reviewed_rows':sum(r['review_status']=='not_reviewed' for r in rows),
        'needs_source_rows':sum(r['review_status']=='needs_source' for r in rows),
        'false_match_fraction_among_reviewed_auto_positive_candidates':stat(sum(r['expert_candidate_covers_reference']=='no' for r in false_match_den),len(false_match_den)),
        'false_negative_fraction_among_reviewed_actual_covered_references':stat(sum(r['auto_matched']=='false' for r in actual_positive),len(actual_positive)),
        'missed_coverage_fraction_among_reviewed_auto_negative_references':stat(sum(r['expert_reference_covered_in_full_answer']=='yes' for r in missed_negative),len(missed_negative)),
        'answers':answer_results,'manual_SR':None,'expert_labels_added':0,'new_model_requests':0,
        'limitations':'Purposive local development candidates; no full manual SR, population rate, holdout result, or complete reference confirmation. Candidate mispairing alone does not imply SR loss when an alternative span covers the reference.',
        'review_file':binding(args.review or args.out/'review_rows.csv'),'manifest_sha256':sha(args.out/'manifest.json')}
    write(args.out/'summary.json',result)
    write(args.out/'execution_summary.json',{'executable':sys.executable,'argv':sys.argv,'new_model_requests':0})
    print(json.dumps({k:result[k] for k in ['status','reviewed_rows','not_reviewed_rows','needs_source_rows']}))

README = '''# 局部步骤核查：同 20 份答案，v2 来源参考

当前只给固定 5 份开发答案各 2 个候选，共 10 行。15 份留出仍等待专家冻结配置；原 selection 与 160 行 review_items.csv 不变。参考为 source_extracted，尚无专家确认。

选择规则预先固定：优先参考的 RI 模块（多条时最后一条，没有时末操作），另选最接近阈值的一条，索引打破并列。未按模型身份、总分或预期结论选样。阈值邻域选样本身不支持总体错误率。

只填写 review_rows.csv 的 expert_*、source_location、reviewer_id、review_date、review_status。其他列绑定原始文件。review_status 为 not_reviewed / reviewed / needs_source；覆盖判断为 yes / no / insufficient_evidence。未审不用填写，更不进入分母。只核自己实际审阅的关键步骤，无需补成全量。

区分两个问题：自动候选片段是否真的覆盖这条参考，以及全文其他位置是否覆盖它。肯定候选覆盖时必须给候选内逐字 span；候选不覆盖而全文覆盖时必须给 alternative span。offset 是原 answer_text 的 Unicode 字符索引，左闭右开，非字节。source_location 写参考原文位置和核查依据；expert_basis 解释判断，不补造参数。

summarize 分别给误配与漏配实际分子/分母。误配的分母是实际审阅且能确定候选覆盖的 auto-positive 行；漏配的分母是实际确认全文覆盖的参考行。另给自动未匹配候选中的已发现覆盖比例。证据不足与未审不进入对应分母。

答案级输出只报告已核参考的覆盖计数变化、其对 SR 的贡献变化及未核部分允许的上下界；不输出完整人工 SR。错误候选但存在替代覆盖时，不自动判定 SR 降低。上下界不是估计值或金标。当前专家 0 时全部影响为 pending/NA。

审阅附件使用原 reviewer/Axx.json 全文与本目录的匿名 ID；本目录 reviewer 表不展示模型名或答案总分。manifest.json 含内部来源绑定，分发专家只需 review_rows.csv、README.md 与原匿名全文包。
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','summarize'])
    p.add_argument('--out',type=pathlib.Path,default=DEFAULT);p.add_argument('--review',type=pathlib.Path)
    for name,value in {'matches':BASE/'supplement_v2_t070_step_matches.json','references':BASE/'reference_recovery/supplement_bound/references_supplement_v2.json',
        'config':BASE/'supplement_v2_t070_resolved_config.json','run':BASE/'supplement_v2_t070_run.json','per-answer':BASE/'supplement_v2_t070_per_answer.json',
        'identities':HUMAN/'private/identity_manifest.csv','selection':HUMAN/'selection.json','original-review':HUMAN/'reviewer/review_items.csv','packets':HUMAN/'reviewer'}.items():
        p.add_argument('--'+name,type=pathlib.Path,default=value)
    args=p.parse_args();{'build':build,'summarize':summarize}[args.command](args)
if __name__=='__main__':main()
