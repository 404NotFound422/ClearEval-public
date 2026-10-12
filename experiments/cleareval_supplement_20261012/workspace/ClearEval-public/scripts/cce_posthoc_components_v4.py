"""Original dependency-view processing with one uniform v4 scoring adapter."""
import copy,types
import cce_namespace_fw5_component_replay_v1 as original
import cce_posthoc_scoring_v4 as scoring
import cce_posthoc_source_backend_v3 as ground
import cce_dangling_target_label_view_v1 as isolation

_process=types.FunctionType(original.independent_processing.__code__,
    {**vars(original),'fw':scoring,'g':ground},name='independent_processing_v4')

def independent_processing(raw,doc,case,step):
    with scoring.capture_scoring_calls() as calls:
        result=_process(raw,doc,case,step)
        item=result.get('views',{}).get('label',{})
        if (not result['full_conversion_success'] and
            item.get('error',{}).get('reason')=='RELATION_DANGLING_ENTITY'):
            before=copy.deepcopy(result['metrics'])
            try:
                payload=original.base.integrity.parse_judge_object(raw)
                view,view_audit=original.partial.neutral_view(payload,doc,ground,
                    ['method_mentions','entities','relations','intrinsic_signals'],['e','u'])
                # Do not send this derived null to the candidate rule for
                # model-returned nulls. Use the unchanged v3 source converter.
                cv=isolation.convert_with_isolation(ground.canonical(view),doc,case,
                    scoring.previous.convert)
                num=original.silent(scoring.score_conversion,case,cv,step)
                sidecar=cv['dangling_target_label_view_v1']
                item['original_dependency_failure']=copy.deepcopy(item['error'])
                item.update(status='validated_isolated_label_dependency_view',
                    view_audit=view_audit,view_sha256=original.j.digest(view),
                    projected_extraction=cv['legacy_projection']['extraction'],
                    component_values={'s_label':num['metrics']['s_label']},
                    dangling_target_isolation=sidecar,
                    isolated_label_projection=cv['label_occurrence_projection'])
                result['metrics']['s_label']=num['metrics']['s_label']
                result['metrics']=original.base.scoring.derive(result['metrics'],step,True)
                calls[-1]['dangling_target_isolation']=copy.deepcopy(sidecar)
                calls[-1]['label_dependency_projection']=copy.deepcopy(cv['label_occurrence_projection'])
                result['label_only_dependency_isolation_applied']=True
                stable=list(scoring.numeric.DIRECT)+['sr','sp','Com','Cor','s_method','s_trans','s_time']
                assert all(result['metrics'][k]==before[k] for k in stable)
                assert result['full_conversion_success'] is False
            except Exception as exc:
                item['isolation_attempt_failure']={'type':type(exc).__name__,'reason':str(exc)}
    try:raw_object_digest=original.j.digest(original.base.integrity.parse_judge_object(raw))
    except Exception:raw_object_digest=None
    for call in calls:
        call['dependency_view_names']=[name for name,v in result.get('views',{}).items()
            if v.get('view_sha256')==call['input_view_sha256']]
        call['matches_original_payload_object']=call['input_view_sha256']==raw_object_digest
        if call.get('dangling_target_isolation'):
            call['dependency_view_names']=['label']
            call['matches_original_payload_object']=False
    result['component_scoring_audit']=calls
    return result
