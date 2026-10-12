"""Translate the frozen panel step manifest to the runner contract, without scoring."""
import copy, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_round3_runner_v2 as runner
import cce_validation as core

R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
PANEL=R3/'representation_repair/controlled_panel_v1'
OUT=R3/'canonical_source_v1/inputs_01'


def main():
    freeze=runner.j.read(PANEL/'panel_freeze.json')
    runner.base.verify_bindings(freeze['bindings'])
    cases=runner.j.read(PANEL/'cases.json')['cases']
    source=runner.j.read(PANEL/'step_inputs_t070.json')
    rows={r['case_id']:r for r in runner.j.read(PANEL/'step_results.json') if r['threshold']==.7}
    refs=runner.j.read(PANEL/'references.json')['references']
    config_path=ROOT/'artifacts/cce_validation/judges/local_controls_supplement_v2/step_config.json'
    config=runner.j.read(config_path)
    assert config['threshold']==.7 and config['adapter_sha256']==runner.j.filehash(core.__file__)
    paths=[Path(__file__),Path(core.__file__),PANEL/'panel_freeze.json',PANEL/'cases.json',
        PANEL/'references.json',PANEL/'step_inputs_t070.json',PANEL/'step_results.json',
        PANEL/'execution.json',config_path]
    provenance=[runner.bind(p) for p in paths]
    steps={};checks=[]
    for c in cases:
        cid=c['case_id'];s=source[cid];r=rows[cid];value=r['step_result']
        selected=next(x for x in refs if x['reference_id']==s['reference_id'])
        assert core.digest(c['references'])==s['references_sha256']==r['references_sha256']
        assert core.digest(selected)==s['selected_reference_sha256']
        assert s['answer_sha256']==r['answer_sha256']==c['answer_sha256']==runner.base.grounded.rawsha(c['model_response'])
        assert s['question_sha256']==r['question_sha256']==c['question_sha256']
        assert all(s[k]==value[k] for k in ['sr','sp','reference_id','candidate_reference_ids'])
        runner.base.verify_bindings(s['source_bindings'])
        step={k:copy.deepcopy(s[k]) for k in ['sr','sp','answer_sha256','question_sha256','question_id','reference_id','candidate_reference_ids','formal_eligible']}
        step.update(references_sha256=runner.j.digest(c['references']),
            selected_reference_sha256=runner.j.digest(selected),threshold=.7,
            encoder=copy.deepcopy(config['encoder']),adapter_version=config['adapter_version'],
            adapter_sha256=config['adapter_sha256'],step_config_sha256=runner.j.filehash(config_path),
            step_config_hash_kind='source_config_file_bytes',
            reference_n=value['reference_n'],generated_n=value['generated_n'],
            step_missing_reason=value.get('step_missing_reason'),reference_status=value.get('reference_status','source_extracted'),
            reuse_kind='verified_frozen_actual_original_fulltext_step_result',provenance=provenance,
            source_manifest_hash_encoding='cce_validation.digest',runner_hash_encoding='runner.j.digest',
            original_references_object_digest=s['references_sha256'],original_selected_reference_object_digest=s['selected_reference_sha256'])
        steps[cid]=step
        checks.append({'case_id':cid,'SR':step['sr'],'SP':step['sp'],
            'identical_original_actual_values':True,'only_manifest_hash_serialization_and_metadata_adapted':True})
    runner.save_once(OUT/'cases.json',{'cases':cases})
    runner.save_once(OUT/'steps.json',steps)
    runner.checked_cases(OUT/'cases.json',OUT/'steps.json')
    runner.save_once(OUT/'verification.json',{'status':'pass','checks':checks,'bindings':provenance,
        'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,'new_embeddings':0,'new_step_calculations':0})
    print(json.dumps({'status':'prepared','answers':len(cases),'original_step_values_preserved':True,'out':str(OUT)}))


if __name__=='__main__':main()
