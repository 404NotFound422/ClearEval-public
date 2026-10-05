"""Build actual old-bound candidates beside the server data; no outbound prompts needed."""
from copy import deepcopy
import json
from pathlib import Path
from oeq_scientific import build_context, apply_assessment, ROOT
from experiments.construct_validity.contract import digest
from experiments.construct_validity.fidelity import text_hash

DEPENDENCIES = ["oeq_scientific.py", "prompts/oeq_scientific_assessment.txt",
    "KnowledgeBase/source_registry.json", "KnowledgeBase/primary_sources",
    "KnowledgeBase/source_condition_rules.json", "experiments/construct_validity/source_conditions.py",
    "dataset/Q+AR/src/model_space_signed.json", "verified_marker_aliases.py",
    "experiments/construct_validity/objectives.py", "experiments/construct_validity/compact_grounding.py",
    "experiments/construct_validity/task_state.py", "experiments/construct_validity/requirement_scope.py", "prompts/oeq_scientific_record_assessment.txt", 'prompts/oeq_record_output.schema.json', "models/Ollama_LLM.py", "models/Model_Loader.py"]


def build_cases(candidate_dir):
    candidate_dir=Path(candidate_dir)
    public=json.loads((candidate_dir/'public_inputs.json').read_text(encoding='utf-8-sig'))
    before=ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
    questions={str(q['question_id']):q for q in json.loads(before.read_text(encoding='utf-8-sig'))}
    cases=[]
    for task in public['tasks']:
        candidate=json.loads((candidate_dir/(task['task_id']+'.result.json')).read_text(encoding='utf-8-sig'))
        if candidate.get('status') != 'COMPLETE':
            raise ValueError('Only actual completed candidates are eligible')
        protocol=candidate['content']
        if text_hash(protocol)!=candidate['content_sha256']:
            raise ValueError('Completed candidate bytes differ')
        question=questions[str(task['question_id'])]
        if question['question']!=task['question']:
            raise ValueError('Existing candidate belongs to another question snapshot')
        context=build_context(question,protocol)
        visible={k:deepcopy(v) for k,v in context.items() if k not in {'prompt','prompt_sha256'}}
        for card in visible['cards']:
            card.get('source_document',{}).pop('text',None)
        visible['protocol']=protocol
        visible['candidate_origin']={k:candidate.get(k) for k in ['model','model_digest','status','content_sha256','invocation_id']}
        visible['task_scope']='EXISTING_OLD_BOUND_INPUT_NOT_CURRENT_253_QUESTION_VALIDATION'
        cases.append(dict(id=task['task_id'],task_id=task['task_id'],input=visible,input_sha256=digest(visible)))
    return cases


def process(public_input, parsed_teacher):
    context=build_context(public_input['question_meta'],public_input['protocol'])
    if context['context_sha256']!=public_input['context_sha256']:
        raise ValueError('Frozen context changed')
    return apply_assessment(parsed_teacher,context,public_input['protocol'])


def render(public_input):
    context=build_context(public_input['question_meta'],public_input['protocol'])
    if context['context_sha256']!=public_input['context_sha256']:
        raise ValueError('Context changed before rendering')
    return context['prompt']


def prepare_study(study,candidate_dir):
    from .prepare import prepare
    judges=[dict(id='qwen38q4',role='TEACHER',transport='OLLAMA_LOOPBACK',family='QWEN',
        model='qwen3.8:27b-q4_K_M',revision='25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e',
        params=dict(temperature=0,seed=42,num_ctx=16384,num_predict=8192),base_url='http://127.0.0.1:11434',timeout_seconds=10800),
        dict(id='gpt61sol',role='TEACHER',transport='EXTERNAL_ACTUAL',family='GPT',model='gpt-6.1-sol',
             revision='UNKNOWN',params=None,parameters_disclosure='CODEX_SUBAGENT_SAMPLING_UNAVAILABLE')]
    return prepare(study,cases=build_cases(candidate_dir),judges=judges,
        prompt=(ROOT/'prompts/oeq_scientific_assessment.txt').read_text(encoding='utf-8'),
        label='grounded-normal-layer-existing-candidates-source-frozen',repeats=3,
        processors=[dict(id='grounded_bridge',entrypoint='experiments.evaluator_development_v2.oeq_cases:process')],
        builder='experiments.evaluator_development_v2.oeq_cases:build_cases',
        prompt_builder='experiments.evaluator_development_v2.oeq_cases:render',
        code_paths=['oeq_scientific.py','verified_marker_aliases.py','evaluation_contract.py',
                    'experiments/construct_validity/objectives.py',
                    'experiments/evidence_materials/demand_migration.py'])

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',required=True)
    parser.add_argument('--candidate-dir',required=True)
    args=parser.parse_args()
    print(json.dumps({'round':str(prepare_study(args.study,args.candidate_dir))}))