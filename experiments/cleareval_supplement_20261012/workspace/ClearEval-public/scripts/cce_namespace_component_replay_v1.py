"""Posthoc partial component replay with typed-record namespaces only.

Pure processing entry point; no batch reader or generation command. A caller
must verify terminal source/raw/request identity and preserve original status.
"""
import cce_codex_fieldwise_replay_v2 as original
import cce_record_namespace_scope_v1 as namespace
import cce_record_namespace_fieldwise_v1 as fw
from cce_codex_fieldwise_replay_v2 import require, silent, base, g, partial, j, independent_direct

def independent_processing(raw,doc,case,step):
    """Never modifies raw. Internal views supply only their explicit component."""
    result={'raw_sha256':g.rawsha(raw),'processing_version':fw.VERSION,'full_conversion_success':False,
        'original_technical_status_promoted':False,'expert_truth':False,'raw_repaired':False,'views':{},'new_model_calls':0}
    try:
        cv=fw.convert(raw,doc,case);num=silent(fw.score_conversion,case,cv,step)
        result.update(full_conversion_success=True,conversion=cv,numeric=num,metrics=num['metrics'],processing_status='full_fieldwise_conversion')
        return result
    except Exception as e:result['full_conversion_or_scoring_failure']={'type':type(e).__name__,'reason':str(e)}
    metrics=base.scoring.derive({},step,False)
    try:metrics,evidence=independent_direct.recover_direct(raw,doc,step);result['independent_direct']=evidence
    except Exception as e:result['independent_direct_error']=str(e)
    try:
        payload=base.integrity.parse_judge_object(raw)
        require(isinstance(payload,dict) and set(payload)<={'scores','score_evidence','grounded_extraction'},'UNATTRIBUTABLE_TOP_LEVEL')
        extraction=payload['grounded_extraction'];require(isinstance(extraction,dict),'EXTRACTION_OBJECT')
        require(extraction['source_id']==doc['source_id'] and extraction['schema_version']==g.VERSION,'SOURCE_OR_WIRE_IDENTITY')
        require(doc==g.document(case['model_response'],g.source_id_for_case(case)),'EXACT_SOURCE_DOCUMENT')
        spec=g.schema_for_document(doc)['properties']['grounded_extraction']['properties']
        require(not(set(extraction)-set(spec)),'UNATTRIBUTABLE_EXTRACTION_FIELDS')
        records,issues,duplicates=namespace.records_audit(payload,doc,g)
        result.update(record_audit=records,record_errors=issues,duplicate_ids=duplicates)
        views=[('method',['method_mentions'],[],['s_method','s_trans'],{'method_mentions'}),
            ('time',['method_mentions','operations','timeline','precedence_edges','total_time_claims'],['t','c','u'],['s_time'],{'method_mentions','operations','total_time_claims'}),
            ('label',['method_mentions','entities','relations','intrinsic_signals'],['e','u'],['s_label'],{'method_mentions','entities','relations','intrinsic_signals'})]
        for name,keep,coverage,components,groups in views:
            item={'components':components,'status':'invalid_or_unknown_dependency','internal_view_only':True,'model_raw_modified':False}
            result['views'][name]=item
            try:
                require(not namespace.dependency_has_duplicate(records,groups),'DUPLICATE_ID_TAINTS_DEPENDENCY')
                view,audit=partial.neutral_view(payload,doc,g,keep,coverage)
                # Relevant records and full relevant coverage remain byte-value
                # identical. Unrelated placeholders are never model facts.
                cv=fw.convert(g.canonical(view),doc,case);num=silent(fw.score_conversion,case,cv,step)
                item.update(status='validated_dependency_view',view_audit=audit,view_sha256=j.digest(view),
                    projected_extraction=cv['legacy_projection']['extraction'],component_gate_notes=num.get('component_gate_notes'),
                    component_values={k:num['metrics'][k] for k in components})
                for key in components:metrics[key]=num['metrics'][key]
            except Exception as e:item['error']={'type':type(e).__name__,'reason':str(e)}
        result['name_binding_failures']=[]
        for record in records:
            if record['group'] not in ['method_mentions','entities'] or record['valid_shape_and_local_source']:continue
            r=record['raw_record'];support=record['resolved_fields'].get('u');entry={'pointer':record['pointer'],'raw_record':r,'errors':record['errors']}
            if support and isinstance(r,dict) and isinstance(r.get('n'),str):
                entry['source_unit']={k:support[k] for k in ['unit_id','start','end','quote'] if k in support}
                entry['source_context']=support.get('context')
                entry['complete_name_occurrences']=g.name_occurrence_inventory(r['n'],support,doc)
            result['name_binding_failures'].append(entry)
    except Exception as e:result['independent_extraction_unavailable']={'type':type(e).__name__,'reason':str(e)}
    result['metrics']=base.scoring.derive(metrics,step,True)
    result['processing_status']='partial_dependency_replay'
    return result
