"""Lexical census of fixed 13-generator 1-shot source archives; never re-score.

Uses the unchanged v11 document/evidence_inventory (the exact `records` component
of candidate_registry). No selected evaluator output, model call, or embedding.
An optional frozen lexical classifier compares roles on the same source spans.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib, json, re, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_grounded_extraction_v11 as g
COHORT=ROOT/'artifacts/cce_validation/cohort_frozen.json'
QUESTIONS=ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
KB=ROOT/'KnowledgeBase/method_fluro_compati.json'
TERM_TYPES=['on_lowercase','on_titlecase','ON_uppercase','compact_uppercase_ND','spaced_uppercase_ND']
OLD_DURATION_KINDS={'duration','dimensional_expression_lead','recurrence_interval_lead'}


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def bind(path):return dict(path=str(Path(path).resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def csvwrite(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False,separators=(',',':'))if isinstance(v,(dict,list))else v for k,v in row.items()})


def term_type(quote):
    if quote=='on':return 'on_lowercase'
    if quote=='On':return 'on_titlecase'
    if quote=='ON':return 'ON_uppercase'
    if re.fullmatch(r'\d+(?:\.\d+)?D',quote):return 'compact_uppercase_ND'
    if re.fullmatch(r'\d+(?:\.\d+)?\s+D',quote):return 'spaced_uppercase_ND'
    return None


def scan_answer(record,model,index,source,lexical=None):
    text=record.get('model_response');qid=record.get('question_id')
    base=dict(generator_model=model,question_id=qid,archive_index=index,archive_path=str(source),
        answer_id=model+'__q'+str(qid),present=True,answer_sha256=g.rawsha(text)if isinstance(text,str)else None,
        question_sha256=g.rawsha(record['specific_question'])if isinstance(record.get('specific_question'),str)else None,
        actual_core_time_effect='not_measured_no_model_extraction_or_score_read',new_model_requests=0)
    if not isinstance(text,str)or not text.strip():
        return {**base,'status':'empty_or_nontext_answer','error':'EMPTY_SOURCE'},[],[]
    try:
        doc=g.document(text,'CENSUS_'+g.rawsha(text)[:24]);records=g.evidence_inventory(doc)
    except Exception as e:
        return {**base,'status':'original_enumerator_error','error':type(e).__name__+':'+str(e)},[],[]
    duration_rows=[r for r in records if r['kind']in OLD_DURATION_KINDS]
    require(all(text[r['span']['start']:r['span']['end']]==r['span']['quote']for r in duration_rows),'SOURCE_OFFSET_IDENTITY')
    counts=Counter();events=[];examples=[];changes=Counter();old_kinds=Counter();new_kinds=Counter()
    for row in duration_rows:
        sp=row['span'];quote=sp['quote'];typ=term_type(quote);kind=row['kind']
        old_kinds[kind]+=1
        left=text[sp['context_start']:sp['start']];right=text[sp['end']:sp['context_end']]
        newkind,reason=lexical.lexical_role(quote,left,right)if lexical else (None,None)
        if lexical:new_kinds[newkind]+=1;changes[kind+' -> '+newkind]+=1
        if not typ:continue
        counts[typ+'_regex_hits']+=1
        counts[typ+'_old_selectable_duration']+=int(kind=='duration')
        counts[typ+'_old_non_duration']+=int(kind!='duration')
        if lexical:
            counts[typ+'_new_selectable_duration']+=int(newkind=='duration')
            counts[typ+'_new_non_duration']+=int(newkind not in ['duration','unresolved_duration_lead'])
            counts[typ+'_new_kind_'+newkind]+=1
        if quote=='3D':
            counts['exact_3D_regex_hits']+=1;counts['exact_3D_old_selectable_duration']+=int(kind=='duration')
            if lexical:counts['exact_3D_new_selectable_duration']+=int(newkind=='duration')
        value=g.duration_value(quote,8)
        event=dict(answer_id=base['answer_id'],generator_model=model,question_id=qid,archive_index=index,
            answer_sha256=base['answer_sha256'],candidate_id=row['candidate_id'],term_type=typ,quote=quote,
            unit_id=sp['unit_id'],start=sp['start'],end=sp['end'],old_kind=kind,
            old_numeric_parser_state=value['state'],old_numeric_parser_hours=value.get('unique_hours'),
            old_numeric_value_not_proof_of_assignment=True,new_kind=newkind,new_reason=reason,
            unit_sha256=g.rawsha(sp['context']),next_word=(re.match(r'\s*([A-Za-z-]+)',right).group(1).lower()if re.match(r'\s*([A-Za-z-]+)',right)else None),
            actual_core_time_assignment=None)
        events.append(event)
        # Examples are short source windows, never a dumped document or protocol.
        a=max(sp['context_start'],sp['start']-35);b=min(sp['context_end'],sp['end']+65)
        examples.append({**event,'excerpt_start':a,'excerpt_end':b,'excerpt':text[a:b],
            'excerpt_sha256':g.rawsha(text[a:b]),'source_archive':str(source)})
    return {**base,'status':'scanned','text_characters':len(text),'source_units':len(doc['units']),
        'all_inventory_records':len(records),'duration_regex_hit_n':len(duration_rows),
        'old_selectable_duration_n':old_kinds['duration'],'old_duration_role_counts':dict(old_kinds),
        'new_duration_role_counts':dict(new_kinds)if lexical else None,'role_transitions':dict(changes)if lexical else None,
        **{k:counts[k]for typ in TERM_TYPES for k in [typ+'_regex_hits',typ+'_old_selectable_duration',typ+'_old_non_duration']},
        **dict(counts)},events,examples


def aggregate(rows,events,groupkey):
    grouped=defaultdict(list);ev=defaultdict(list)
    for row in rows:grouped[row[groupkey]].append(row)
    for e in events:ev[e[groupkey]].append(e)
    result=[]
    for group,subset in sorted(grouped.items(),key=lambda x:str(x[0])):
        selected=ev[group];counts=Counter(e['term_type']for e in selected)
        result.append({groupkey:group,'planned_slots':len(subset),'present_answers':sum(r['present']for r in subset),
            'successfully_scanned_answers':sum(r['status']=='scanned'for r in subset),'missing_or_failed_answers':sum(r['status']!='scanned'for r in subset),
            'target_lexical_hits':len(selected),'answers_with_target_hits':len({e['answer_id']for e in selected}),
            'old_selectable_target_hits':sum(e['old_kind']=='duration'for e in selected),
            **{t+'_hits':counts[t]for t in TERM_TYPES},
            **{t+'_answers':len({e['answer_id']for e in selected if e['term_type']==t})for t in TERM_TYPES}})
    return result


def run(out,module=None):
    require(not out.exists(),'NEW_OUTPUT_DIRECTORY_REQUIRED')
    start=time.perf_counter();cohort=read(COHORT);qids=[int(r['question_id'])for r in read(QUESTIONS)]
    require(len(qids)==len(set(qids))==253 and len(cohort['models'])==13,'FIXED_CORPUS_DIMENSIONS')
    sources=[ROOT/'dataset/Q+AR/model_response'/('from_'+m+'_1-shot.json')for m in cohort['models']]
    for source in sources:require(sha(source)==cohort['input_files'][str(source.relative_to(ROOT))],'FROZEN_ARCHIVE_SHA')
    lexical=importlib.import_module(module)if module else None
    if lexical:require(callable(lexical.lexical_role),'PURE_LEXICAL_INTERFACE')
    bindings=[bind(p)for p in [Path(__file__),Path(g.__file__),COHORT,QUESTIONS,KB,*sources]]
    if lexical:bindings.append(bind(lexical.__file__))
    plan=dict(scope='source_archive_lexical_census_not_reevaluation',created_utc=datetime.now(timezone.utc).isoformat(),
        generator_models=cohort['models'],question_ids=qids,planned_slots=13*253,
        original_functions=['cce_grounded_extraction_v11.document','cce_grounded_extraction_v11.evidence_inventory'],
        exact_registry_component='evidence_inventory is the unchanged records component of candidate_registry; O/P/Q metadata not recomputed',
        target_term_groups=TERM_TYPES,optional_classifier=module,
        lexical_counts_not_semantic_gold=True,core_time_assignment_not_inferable_from_source_candidates=True,
        max_examples_per_term_old_new_role=3,bindings=bindings,new_model_requests=0,new_embeddings=0,
        runtime_memory_plan='One archive (maximum frozen file 4.71 MB) and one source document at a time; no stored full documents. Eight-position original-function pilot estimated about 38 seconds for 3288 answers.',
        command=[sys.executable,*sys.argv])
    write(out/'plan.json',plan)
    rows=[];events=[];examples=[];examplecounts=Counter();file_stats=[]
    for model,source in zip(cohort['models'],sources):
        data=read(source);counts=Counter(int(r['question_id'])for r in data)
        require(set(counts)<=set(qids),'OUT_OF_SCOPE_QUESTION')
        fstart=time.perf_counter()
        for i,record in enumerate(data):
            if counts[int(record['question_id'])]>1:
                rows.append(dict(generator_model=model,question_id=int(record['question_id']),archive_index=i,present=True,
                    status='duplicate_question_identity',answer_id=model+'__q'+str(record['question_id'])));continue
            row,event,example=scan_answer(record,model,i,source,lexical)
            rows.append(row);events.extend(event)
            for e in example:
                key=(e['term_type'],e['old_kind'],e['new_kind'])
                if examplecounts[key]<3:examples.append(e);examplecounts[key]+=1
        for q in qids:
            if q not in counts:rows.append(dict(generator_model=model,question_id=q,archive_index=None,present=False,
                status='archive_answer_missing',answer_id=model+'__q'+str(q)))
        file_stats.append(dict(generator_model=model,archive_records=len(data),unique_question_ids=len(counts),
            missing_qids=[q for q in qids if q not in counts],seconds=time.perf_counter()-fstart,archive=bind(source)))
        print(json.dumps({'model':model,'records':len(data),'seconds':file_stats[-1]['seconds']}),flush=True)
        del data
    for item in bindings:require(sha(item['path'])==item['sha256'],'INPUT_CHANGED_DURING_CENSUS')
    termsummary=[]
    for term in TERM_TYPES:
        es=[e for e in events if e['term_type']==term]
        termsummary.append(dict(term_type=term,regex_hits=len(es),answers_with_hits=len({e['answer_id']for e in es}),
            old_selectable_duration_hits=sum(e['old_kind']=='duration'for e in es),
            answers_with_old_selectable_hits=len({e['answer_id']for e in es if e['old_kind']=='duration'}),
            old_roles=dict(Counter(e['old_kind']for e in es)),new_roles=dict(Counter(e['new_kind']for e in es))if lexical else None,
            new_selectable_duration_hits=sum(e['new_kind']=='duration'for e in es)if lexical else None,
            most_common_next_words=Counter(e['next_word']for e in es).most_common(12)))
    summary=dict(status='complete_source_census',planned_slots=13*253,actual_archive_records=sum(x['archive_records']for x in file_stats),
        present_answers=sum(r['present']for r in rows),scanned_answers=sum(r['status']=='scanned'for r in rows),
        states=dict(Counter(r['status']for r in rows)),duration_regex_hit_n=sum(r.get('duration_regex_hit_n',0)for r in rows),
        old_selectable_duration_n=sum(r.get('old_selectable_duration_n',0)for r in rows),terms=termsummary,
        exact_3D=dict(regex_hits=sum(e['quote']=='3D'for e in events),
            old_selectable_duration_hits=sum(e['quote']=='3D'and e['old_kind']=='duration'for e in events),
            answers_with_old_selectable_3D=len({e['answer_id']for e in events if e['quote']=='3D'and e['old_kind']=='duration'}),
            new_roles=dict(Counter(e['new_kind']for e in events if e['quote']=='3D'))if lexical else None),
        seconds=time.perf_counter()-start,per_archive=file_stats,actual_core_time_miscount_n=None,
        actual_core_time_miscount_reason='Source candidates do not identify evaluator selections, phase, scope, repeats, coverage, or final sum. No evaluator outputs or scores were read.',
        new_model_requests=0,new_embeddings=0,optional_classifier=module,
        limitations=['Lexical census, not a scoring error rate.','Lowercase on and uppercase ND are candidate signatures, not individually human-labeled errors.',
            'Ordinary on versus an explicit overnight abbreviation, and dimensional ND versus day units, require contextual classification; before/after roles remain software labels.',
            'No source catalog IDs, raw outputs, knowledge base, or scores were modified.'])
    csvwrite(out/'per_answer.csv',rows);write(out/'per_answer.json',rows)
    csvwrite(out/'target_occurrences.csv',events)
    write(out/'examples.json',examples)
    csvwrite(out/'by_generator.csv',aggregate(rows,events,'generator_model'))
    csvwrite(out/'by_question.csv',aggregate(rows,events,'question_id'))
    write(out/'summary.json',summary)
    write(out/'actual_commands.json',dict(argv=[sys.executable,*sys.argv],new_model_requests=0,new_embeddings=0))
    write(out/'verification.json',dict(status='pass',all_fixed_archives_hash_matched=True,
        source_offsets_replayed=True,planned_slots_preserved=len(rows)==13*253,
        no_evaluator_output_read=True,no_score_or_formula_replay=True,inputs=bindings,
        outputs=[bind(out/n)for n in ['per_answer.csv','per_answer.json','target_occurrences.csv','examples.json','by_generator.csv','by_question.csv','summary.json']]))
    print(json.dumps({'status':summary['status'],'scanned':summary['scanned_answers'],'planned':summary['planned_slots'],
        'seconds':summary['seconds'],'terms':termsummary,'3D':summary['exact_3D']},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--lexical-module',choices=['cce_duration_scope_fix_v2'])
    a=p.parse_args();run(a.out.resolve(),a.lexical_module)
if __name__=='__main__':main()
