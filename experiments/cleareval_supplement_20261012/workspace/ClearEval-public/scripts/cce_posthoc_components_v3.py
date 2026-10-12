"""Preserve all dependency-view rules and retain their label calculation trace."""
import types
import cce_namespace_fw5_component_replay_v1 as original
import cce_posthoc_scoring_v3 as scoring
import cce_posthoc_source_backend_v3 as ground

_process=types.FunctionType(original.independent_processing.__code__,
    {**vars(original),'fw':scoring,'g':ground},name='independent_processing_v3')

def independent_processing(raw,doc,case,step):
    with scoring.capture_scoring_calls() as calls:
        result=_process(raw,doc,case,step)
    try:raw_object_digest=original.j.digest(original.base.integrity.parse_judge_object(raw))
    except Exception:raw_object_digest=None
    for call in calls:
        call['dependency_view_names']=[name for name,v in result.get('views',{}).items()
            if v.get('view_sha256')==call['input_view_sha256']]
        call['matches_original_payload_object']=call['input_view_sha256']==raw_object_digest
    result['component_scoring_audit']=calls
    return result
