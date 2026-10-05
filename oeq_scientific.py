"""Production bridge: preserved proposals, grounded fields and layered decisions."""
from copy import deepcopy
from pathlib import Path
import json
import hashlib
import re
from evaluator_integrity import method_identity
from experiments.construct_validity.contract import adjudicate, admissibility_formula, combine, digest, parse_json, validate_extraction, validate_requirements, evaluate_formula
from experiments.construct_validity.fidelity import audit_extraction, validate_span, text_hash, NEGATION, CONDITION, quote_span_candidates, diagnose_extraction
from experiments.construct_validity.evidence import validate_cards
from experiments.construct_validity.objectives import compare_candidates
from experiments.construct_validity.source_conditions import load_rules, diagnose as diagnose_source_conditions
from experiments.construct_validity.compact_grounding import (SCHEMA as RECORD_REF_SCHEMA, build_record_catalog, build_compact_prompt_view, expand_record_refs, PROMPT as RECORD_REF_PROMPT)
from experiments.construct_validity.task_state import propose_task_state
from experiments.construct_validity.requirement_scope import resolve_scope, audit_requirement_quotes, audit_requirement_bindings
VERSION = 'oeq-layered-scientific-v12'
ROOT = Path(__file__).resolve().parent


def _spans(obj, text):
    if isinstance(obj, list):
        return [_spans(v, text) for v in obj]
    if not isinstance(obj, dict):
        return obj
    if set(obj) == {'quote'}:
        q = obj['quote']
        if not isinstance(q, str) or not q or text.count(q) != 1:
            raise ValueError('Quote-only span must be unique; use accurate offsets for repetitions')
        start = text.index(q)
        return dict(start=start, end=start+len(q), quote=q)
    return {k: _spans(v, text) for k,v in obj.items()}


def _cards(workspace):
    """Load frozen source fields without constructing scope or checker results."""
    from experiments.construct_validity.evidence import _checked_verification

    registry = workspace/'KnowledgeBase/source_registry.json'
    if not registry.exists():
        return []
    result = []
    for source in json.loads(registry.read_text(encoding='utf-8-sig'))['sources']:
        snap = source.get('snapshot') or {}
        if not snap.get('text_path') or not source.get('passages'):
            continue
        path = (workspace/snap['text_path']).resolve()
        if not path.is_relative_to(workspace.resolve()):
            raise ValueError('Snapshot escapes workspace')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != snap['text_sha256']:
            raise ValueError('Source snapshot bytes changed')
        text, identity = data.decode('utf-8-sig'), source['identity']
        if snap.get('version') != identity.get('version') or snap.get('identity_url') != identity.get('url'):
            raise ValueError('Source snapshot version/identity missing or changed')
        applicability = deepcopy(source.get('applicability', {}))
        scope_support = deepcopy(source.get('scope_support', {}))
        proofs = deepcopy(source.get('entailment_verifications', []))
        if not isinstance(applicability, dict) or not isinstance(scope_support, dict):
            raise ValueError('Registered source applicability/support must be objects')
        if not isinstance(proofs, list) or any(not isinstance(proof, dict) for proof in proofs):
            raise ValueError('Frozen entailment checks must be an array')
        card = dict(id=source['id'], schema_version='source-grounding-v2', identity=deepcopy(identity),
                           passages=deepcopy(source['passages']), method=source.get('method'),
                           applicability=applicability, scope_support=scope_support,
                           scientific_validation=deepcopy(source.get('scientific_validation')),
                           source_document=dict(text=text, sha256=text_hash(text), url=snap['identity_url'], version=snap['version']))
        if 'entailment_verifications' in source:
            card['entailment_verifications'] = proofs
        result.append(card)
    validate_cards(result)
    for card in result:
        seen = set()
        for proof in card.get('entailment_verifications', []):
            proof_id, data = proof.get('id'), proof.get('input')
            if not isinstance(proof_id, str) or not proof_id or proof_id in seen:
                raise ValueError('Invalid/duplicate frozen entailment identity')
            seen.add(proof_id)
            if not isinstance(data, dict):
                raise ValueError('Frozen entailment input must be an object')
            pids, claim, context = data.get('passage_ids'), data.get('hypothesis'), data.get('applicability')
            if (not isinstance(pids, list) or not pids or any(not isinstance(pid, str) for pid in pids)
                    or len(pids) != len(set(pids)) or not isinstance(claim, str) or not claim
                    or not isinstance(context, dict)):
                raise ValueError('Frozen entailment input fields invalid')
            guards = _checked_verification(dict(verification_id=proof_id, relation=proof.get('relation')),
                                           card, pids, claim, context)
            if guards:
                raise ValueError('Frozen entailment check unbound: ' + ', '.join(guards))
    return result


def _question_requirements(question):
    """Finite scope rules with unchanged question provenance, not domain review."""
    text = question.get('question', question.get('text', ''))
    text = text if isinstance(text, str) else ''
    result = []
    patterns = [
        ('FIXATION_SCOPE', r'(?:(?:do not|avoid|no)\s+(?:repeat(?:ed)? fixation|re-?fix)|(?:\u4e0d\u8981|\u4e0d\u5f97|\u907f\u514d)[^\n\u3002]{0,8}(?:\u91cd\u590d\u56fa\u5b9a|\u518d\u6b21\u56fa\u5b9a|\u91cd\u65b0\u56fa\u5b9a))', 'NO_REPEAT_FIXATION'),
        ('COMPLETED_LABEL_QC_SCOPE', r'(?:(?:do not|avoid|no)\s+(?:re-?label|repeat(?:ed)? label)|(?:\u4e0d\u8981|\u4e0d\u5f97|\u907f\u514d)[^\n\u3002]{0,8}(?:\u91cd\u65b0\u67d3\u8272|\u91cd\u590d\u6807\u8bb0|\u518d\u6b21\u793a\u8e2a))', 'NO_REPEAT_LABEL_QC'),
        ('REPLACEMENT_SAMPLE_SCOPE', r'(?:\u65b0\u540c\u578b|\u540c\u578b\u65b0|\u540c\u7c7b\u65b0\u6837\u672c|replacement sample)', 'NO_OLD_SIGNAL_RECOVERY'),
    ]
    for rid, pattern, kind in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            result.append(dict(id=rid,kind='TEXT',necessary=True,evidence_ids=[],
                text='Respect the explicit operation restriction/replacement sample scope: '+match.group(),
                question_span=dict(start=match.start(),end=match.end(),quote=match.group()),
                literal_rule=dict(type=kind)))
    # Clauses constrain the actual task; no marker name is converted to required staining.
    clauses = re.finditer(r'[^\n\u3002;\uff1b]*(?:\u4e0d\u80fd|\u4e0d\u5f97|\u4e0d\u8de8|\u4e0d\u5c06|\u4ec5\u89e3\u91ca|\u5206\u522b\u6210\u50cf)[^\n\u3002;\uff1b]*', text)
    for i,match in enumerate(clauses):
        if match.group().strip():
            result.append(dict(id='QUESTION_CONSTRAINT_'+str(i+1),kind='TEXT',necessary=True,evidence_ids=[],
                text=match.group().strip(),question_span=dict(start=match.start(),end=match.end(),quote=match.group()),
                validation_policy='SEMANTIC_PROPOSAL_PENDING_VERIFICATION'))
    return result



def _method_clause(protocol, start, end):
    """Bind finite selection cues to the name's clause, without crossing another claim."""
    delimiters = list(re.finditer(r"[\n;\uff1b\u3002!?\uff01\uff1f]|\.(?=\s|$)", protocol))
    left = max((m.end() for m in delimiters if m.end() <= start), default=0)
    right = min((m.start() for m in delimiters if m.start() >= end), default=len(protocol))
    return dict(start=left, end=right, quote=protocol[left:right])


def _explicitly_inactive_method(clause, key, method_keys):
    """Only explicit non-selection of this one method can be ignored."""
    name=r'(?P<name>'+re.escape(key)+r')(?![A-Za-z0-9+])'
    local_names={other for other in method_keys if re.search(
        r'(?<![A-Za-z0-9])'+re.escape(other)+r'(?![A-Za-z0-9+])',clause,re.I)}
    mentions=list(re.finditer(r'(?<![A-Za-z0-9])'+re.escape(key)+r'(?![A-Za-z0-9+])',clause,re.I))
    if local_names != {key} or len(mentions)!=1:
        return False
    denied=r'\b(?:(?:do|does|did)\s+not\s+|never\s+)(?:use|apply|perform|choose|select)\s+(?:the\s+)?(?:\*\*)?'+name
    considered=r'\bconsider(?:ing)?\s+(?:the\s+)?(?:\*\*)?'+name
    return bool(re.search(denied,clause,re.I) or
                (CONDITION.search(clause) and re.search(considered,clause,re.I)))


def _method_assertion_context(protocol, start, end, method_keys, branch=None):
    regions=(branch or {}).get('resolved_spans',(branch or {}).get('spans',[]))
    containing=[r for r in regions if r.get('start',-1)<=start<end<=r.get('end',-1)]
    lower,upper=(containing[0]['start'],containing[0]['end']) if len(containing)==1 else (0,len(protocol))
    local=_method_clause(protocol[lower:upper],start-lower,end-lower)
    clause=dict(start=lower+local['start'],end=lower+local['end'],quote=local['quote'])
    line_start=max(lower,protocol.rfind('\n',lower,start)+1)
    prefix=protocol[line_start:clause['start']]
    for piece in re.finditer(r'[^;\uff1b\u3002!?\uff01\uff1f]+',prefix):
        text=piece.group()
        if ((NEGATION.search(text) or CONDITION.search(text))
                and not any(_explicitly_inactive_method(text,key,method_keys) for key in method_keys)):
            clause=dict(start=line_start+piece.start(),end=clause['end'],
                        quote=protocol[line_start+piece.start():clause['end']])
            break
    # An open colon control is retained within this declared candidate region,
    # including across blank/ordinary lines. No implicit cross-candidate parent.
    inherited=[]
    for line in re.finditer(r'(?m)^.*$',protocol[lower:line_start]):
        value=line.group().rstrip().strip('*').rstrip()
        if (value.endswith((':','\uff1a',';','\uff1b'))
                and (NEGATION.search(value) or CONDITION.search(value))
                and not any(_explicitly_inactive_method(value,key,method_keys) for key in method_keys)):
            inherited.append(lower+line.start())
    if inherited:
        clause=dict(start=min(inherited),end=clause['end'],quote=protocol[min(inherited):clause['end']])
    return clause


def _header_unresolved_method_mentions(header, method_keys):
    mentions,active_or_unresolved=[],[]
    for key in method_keys:
        occurrences=list(re.finditer(r'(?<![A-Za-z0-9])'+re.escape(key)+r'(?![A-Za-z0-9+])',header,re.I))
        if not occurrences:continue
        mentions.append(key)
        if any(not _explicitly_inactive_method(_method_clause(header,m.start(),m.end())['quote'],key,method_keys)
               for m in occurrences):active_or_unresolved.append(key)
    return mentions,active_or_unresolved


def _unreconciled_selected_mentions(protocol, branch, selected_key, method_keys, declared_keys=()):
    regions=branch.get('resolved_spans',branch['spans'])
    result=[]
    for key in method_keys:
        resolved_key=method_identity(key,method_keys).get('resolved_key')
        if resolved_key==selected_key or resolved_key in declared_keys:continue
        pattern=r'\b(?:use|using|apply|perform|choose|select)\s+(?:the\s+)?(?:\*\*)?(?P<name>'+re.escape(key)+r')(?![A-Za-z0-9+])'
        for match in re.finditer(pattern,protocol,re.I):
            a,b=match.span('name')
            belongs=(not regions and branch['id']=='main') or any(r['start']<=a<b<=r['end'] for r in regions)
            if not belongs:continue
            local=_method_assertion_context(protocol,a,b,method_keys,branch)
            if _explicitly_inactive_method(local['quote'],key,method_keys):continue
            result.append(dict(name=key,span=dict(start=a,end=b,quote=protocol[a:b]),
                               context=local['quote'],status='ROLE_RECONCILIATION_REQUIRED'))
    return result


def _method_audit(raw, extraction, context, protocol):
    declarations = raw.get('method_declarations', [])
    if not isinstance(declarations, list):
        raise ValueError('Method declarations must be an array')
    branches = {b['id']:b for b in extraction['branches']}
    details, selected = [], {}
    for d in declarations:
        if not isinstance(d,dict) or set(d) != {'name','branch','span'} or d['branch'] not in branches:
            raise ValueError('Method declaration requires name, declared branch and original span')
        if not isinstance(d['name'], str) or not d['name']:
            raise ValueError('Method declaration name must be nonempty text')
        resolution = quote_span_candidates(protocol,d['span'])
        chosen = resolution['resolved_span']
        if chosen is None:
            viable=[]
            for candidate in resolution['candidate_spans']:
                probe=_method_audit({'method_declarations':[dict(d,span=candidate)]},extraction,context,protocol)
                detail=probe['declarations'][0]
                left=detail['assertion_context_span']['start']
                line=detail['assertion_context']
                named=r'(?:Chosen|Selected)\s+Method(?:\*\*)?\s*:(?:\*\*)?\s*(?P<name>'+re.escape(d['name'])+r')(?![A-Za-z0-9+])'
                exact_role=any(left+match.start('name')==candidate['start'] and left+match.end('name')==candidate['end']
                               for match in re.finditer(named,line,re.I))
                if not detail['guards'] and (exact_role or detail.get('selected_role_established') or detail['binding_rule']=='EXPLICIT_SELECTED_METHOD_DECLARATION_V1'):
                    viable.append(candidate)
            chosen=viable[0] if len(viable)==1 else None
        if chosen is None:
            details.append(dict(branch=d['branch'],name=d['name'],span=None,name_span=None,
                proposed_span=deepcopy(d['span']),quote_resolution=resolution,
                binding_rule='SELECTED_OCCURRENCE_UNPROVEN',assertion_context=None,assertion_context_span=None,
                guards=['METHOD_LOCATION_UNPROVEN'],identity=method_identity(d['name'],context['method_keys'])))
            selected.setdefault(d['branch'],[]).append(None)
            continue
        if resolution['resolved_span'] is None:
            resolution.update(resolved_span=deepcopy(chosen),rule='UNIQUE_EXPLICIT_SELECTED_METHOD_OCCURRENCE')
        span = validate_span(protocol,chosen)
        if not isinstance(d['name'], str) or not d['name']:
            raise ValueError('Method declaration name must be nonempty text')
        name_span, binding_rule, guards = None, 'NAME_SCOPE_UNPROVEN', []
        selected_role_established = False
        if span['quote'] == d['name']:
            name_span = dict(start=span['start'], end=span['end'], quote=d['name'])
            binding_rule = 'EXACT_METHOD_NAME_VALUE_SPAN'
        else:
            frame = re.fullmatch(r'(?:\*\*)?(?:Chosen|Selected)\s+Method(?:\*\*)?\s*:(?:\*\*)?\s*'
                + '(?P<name>' + re.escape(d['name']) + r')(?:\*\*)?\s*', span['quote'], re.I)
            if frame and frame.group('name') == d['name']:
                name_span = dict(start=span['start']+frame.start('name'), end=span['start']+frame.end('name'), quote=d['name'])
                binding_rule = 'EXPLICIT_SELECTED_METHOD_DECLARATION_V1'
        branch = branches[d['branch']]
        assertion_context_span = _method_assertion_context(protocol, span['start'], span['end'], context['method_keys'], branch)
        left = assertion_context_span['start']
        context_line = assertion_context_span['quote']
        if NEGATION.search(context_line):
            guards.append('METHOD_DECLARATION_NEGATION_CONTEXT')
        if CONDITION.search(context_line):
            guards.append('METHOD_DECLARATION_CONDITIONAL_CONTEXT')
        if re.search(r'\b(?:example|hypothetical|comparison|rejected)\b',context_line,re.I):
            guards.append('METHOD_DECLARATION_UNSELECTED_DISCUSSION_CONTEXT')
        if re.search(r'\b(?:may|might|could|would|perhaps|consider(?:ing)?)\b',context_line,re.I):
            guards.append('METHOD_DECLARATION_TENTATIVE_CONTEXT')
        if name_span is None:
            guards.append('METHOD_NAME_SCOPE_UNPROVEN')
        elif binding_rule == 'EXACT_METHOD_NAME_VALUE_SPAN':
            name = re.escape(d['name'])
            def role_at_value(pattern):
                return any(left+match.start('name')==name_span['start'] and left+match.end('name')==name_span['end']
                           for match in re.finditer(pattern,context_line,re.I))
            role_frame = role_at_value(r'(?:Chosen|Selected)\s+Method(?:\*\*)?\s*:(?:\*\*)?\s*'
                                      + '(?P<name>'+name+r')(?![A-Za-z0-9+])')
            active_use = role_at_value(r'\b(?:use|using|apply|perform|choose|select)\s+(?:the\s+)?(?:\*\*)?'
                                      + '(?P<name>'+name+r')(?![A-Za-z0-9+])(?:\*\*)?')
            title_match = re.match(r'\s*(?:\*\*)?(?P<name>' + name + r')(?:\*\*)?\s*(?::|$)',context_line,re.I)
            title = left == 0 and title_match and left+title_match.start('name')==name_span['start'] and left+title_match.end('name')==name_span['end']
            header_names = '(?:' + '|'.join(re.escape(key) for key in context['method_keys']) + ')'
            header_list = context_line.split(':',1)[0].strip().strip('*').strip()
            positive_list = left == 0 and re.fullmatch(header_names + r'(?:\s+and\s+' + header_names + r')+',header_list,re.I)
            header_end = context_line.find(':') if ':' in context_line else len(context_line)
            list_member = positive_list and left<=name_span['start']<name_span['end']<=left+header_end
            selected_role_established = bool(role_frame or active_use or title or list_member)
            if not selected_role_established:
                guards.append('SELECTED_METHOD_ROLE_NOT_ESTABLISHED')
        if binding_rule == 'EXPLICIT_SELECTED_METHOD_DECLARATION_V1':
            selected_role_established = True
        branch = branches[d['branch']]
        if branch.get('location_status')=='REVIEW_REQUIRED':
            guards.append('METHOD_DECLARATION_BRANCH_SCOPE_UNPROVEN')
        regions=branch.get('resolved_spans',branch['spans'])
        if name_span is not None and regions and not any(s['start']<=name_span['start']<name_span['end']<=s['end'] for s in regions):
            guards.append('METHOD_DECLARATION_BRANCH_SCOPE_UNPROVEN')
        selected_lines=re.finditer(r'(?im)^\s*(?:\*\*)?(?:Chosen|Selected)\s+Method(?:\*\*)?\s*:(?:\*\*)?\s*([^;\uff1b\r\n]+)',protocol)
        for declared_line in selected_lines:
            if NEGATION.search(declared_line.group()) or CONDITION.search(declared_line.group()):continue
            other_name=declared_line.group(1).strip().strip('*').strip()
            other=method_identity(other_name,context['method_keys'])
            whole=dict(start=declared_line.start(),end=declared_line.end())
            belongs=(not branch['spans'] and len(branches)==1 and branch['id']=='main') or any(
                region['start']<=whole['start']<whole['end']<=region['end'] for region in regions)
            if belongs and other.get('resolved_key')!=method_identity(d['name'],context['method_keys']).get('resolved_key'):
                guards.append('OTHER_EXPLICIT_SELECTED_METHOD_IN_BRANCH_UNRECONCILED')
        resolved = method_identity(d['name'],context['method_keys'])
        declared_keys={method_identity(v['name'],context['method_keys']).get('resolved_key') for v in declarations
                       if isinstance(v,dict) and v.get('branch')==d['branch'] and isinstance(v.get('name'),str)}
        unreconciled = _unreconciled_selected_mentions(protocol,branch,resolved.get('resolved_key'),context['method_keys'],declared_keys)
        if unreconciled:
            guards.append('OTHER_POSSIBLE_SELECTED_METHOD_IN_BRANCH_UNRECONCILED')
        details.append(dict(branch=d['branch'],name=d['name'],span=span,name_span=name_span,binding_rule=binding_rule,
                            assertion_context=context_line,assertion_context_span=assertion_context_span,guards=guards,identity=resolved,quote_resolution=resolution,selected_role_established=selected_role_established,unreconciled_selected_mentions=unreconciled))
        selected.setdefault(d['branch'],[]).append(resolved.get('resolved_key') if not guards else None)
    status = 'UNRESOLVED'
    if not declarations:
        status = 'UNDER_SPECIFIED'
    elif set(selected) != set(branches):
        status = 'UNDER_SPECIFIED'
    elif any(len(set(names))>1 and all(names) for names in selected.values()):
        status = 'VIOLATED'  # Multiple independently bound selected identities in one route.
    elif any(len(names)!=1 or not names[0] for names in selected.values()):
        status = 'UNRESOLVED'
    else:
        status = 'SATISFIED'
    header=protocol.splitlines()[0] if protocol else ''
    mentions,active_header_mentions=_header_unresolved_method_mentions(header,context['method_keys'])
    if status=='SATISFIED' and len(set(active_header_mentions))>1 and len(selected)==1:
        status='UNRESOLVED'  # Header mentions multiple methods: selected/rejected roles unproven.
    operation_conflicts=[]
    for row in extraction['steps']:
        if row['assertion']['polarity']!='AFFIRMED':continue
        operational=[key for key in context['method_keys'] if re.search(r'(?<![A-Za-z0-9])'+re.escape(key)+r'(?![A-Za-z0-9+])',row['operation'] or '',re.I)]
        chosen=selected.get(row['branch'],[])
        if any(key not in chosen for key in operational):operation_conflicts.append(row['id'])
    if status=='SATISFIED' and operation_conflicts:status='UNRESOLVED'
    return dict(status=status,branches=selected,declarations=details,header_method_mentions=mentions,active_or_unresolved_header_method_mentions=active_header_mentions,operation_method_conflicts=operation_conflicts,
                scope='EXACT_SELECTED_NAME_IDENTITY_ONLY_NOT_RECIPE_FIDELITY',selection_finality='NOT_CERTIFIED',scientific_truth=None)


def _bound_literal_equality(rule, extraction, protocol, cards, fidelity):
    """Only admit an authored literal entity-dimension-value assignment."""
    fields={'type','field','entity_field','entity','dimension','polarity','source_binding','protocol_binding'}
    if set(rule) != fields or rule['polarity'] not in {'AFFIRMED','NEGATED'}:
        raise ValueError('Literal equality requires field/entity/dimension/polarity and both bindings')
    sb,pb = rule['source_binding'],rule['protocol_binding']
    card = next(c for c in cards if c['id']==sb['source_id'])
    passage = next(p for p in card['passages'] if p['id']==sb['passage_id'])
    doc=card.get('source_document',{}).get('text')
    if not isinstance(doc,str):raise ValueError('Literal source lacks full snapshot')
    rows=[r for r in extraction[pb['collection']] if (pb.get('record_id') is not None and r.get('id')==pb['record_id']) or
                (pb['collection']=='ri' and pb.get('branch') is not None and r.get('branch')==pb['branch'])]
    if len(rows)!=1:raise ValueError('Literal selector must identify exactly one extracted record')
    row=rows[0]
    if row is None or row.get(rule['entity_field']) != rule['entity'] or row.get('assertion',{}).get('polarity')!=rule['polarity']:
        raise ValueError('Protocol literal has wrong entity or polarity')
    values=[]
    for binding,body,region in [(sb,doc,passage),(pb,protocol,None)]:
        if binding.get('polarity')!=rule['polarity']:raise ValueError('Literal polarity mismatch')
        spans={key:validate_span(body,binding[key]) for key in ['span','entity_span','dimension_span','value_span']}
        whole=spans['span']
        if region and not region['start']<=whole['start']<whole['end']<=region['end']:
            raise ValueError('Source binding outside cited passage')
        if any(not whole['start']<=s['start']<s['end']<=whole['end'] for s in spans.values()):
            raise ValueError('Binding fields outside assignment span')
        if spans['entity_span']['quote']!=rule['entity'] or spans['dimension_span']['quote']!=rule['dimension']:
            raise ValueError('Literal entity/dimension mismatch')
        value=spans['value_span']['quote']
        prefix='NOT ' if rule['polarity']=='NEGATED' else ''
        expected=prefix+rule['entity']+' '+rule['dimension']+' = '+value
        if whole['quote']!=expected:
            raise ValueError('Only exact typed literal assignments are mechanically certified')
        values.append(value)
    if row.get(rule['field'])!=values[1]:raise ValueError('Comparison is not the extracted field')
    matching=[f for f in fidelity['facts'] if f['collection']==pb['collection'] and f['branch']==row['branch'] and f['id']==row.get('id')]
    if len(matching)!=1:raise ValueError('Literal selected fact occurrence is ambiguous')
    if not _field_fact_eligible(fidelity,matching[0],[rule['field'],rule['entity_field']]):
        return dict(status='UNRESOLVED',scope='FROZEN_LITERAL_FIELD_ASSIGNMENT_NOT_SEMANTIC_ENTAILMENT',
            scientific_truth=None,field=rule['field'],entity=rule['entity'],dimension=rule['dimension'],
            polarity=rule['polarity'],source_value=values[0],protocol_value=values[1],
            extraction_dependency_status='REVIEW_REQUIRED')
    entity_support=matching[0]['fields'][rule['entity_field']]
    if not any(s['start']==pb['entity_span']['start'] and s['end']==pb['entity_span']['end'] for s in entity_support.get('spans',[])):
        raise ValueError('Entity is not bound to the selected field occurrence')
    support=matching[0]['fields'][rule['field']]
    if not any(s['start']==pb['value_span']['start'] and s['end']==pb['value_span']['end'] for s in support.get('spans',[])):
        raise ValueError('Comparison does not bind the extracted field occurrence')
    return dict(status='SATISFIED' if values[0]==values[1] else 'VIOLATED',
                scope='FROZEN_LITERAL_FIELD_ASSIGNMENT_NOT_SEMANTIC_ENTAILMENT',scientific_truth=None,
                field=rule['field'],entity=rule['entity'],dimension=rule['dimension'],polarity=rule['polarity'],
                source_value=values[0],protocol_value=values[1])


def _retrieve_cards(cards, protocol, method_keys, explicit=False):
    """Conservative declared-method retrieval, identical for every judge family."""
    policy='explicit-frozen-cards-preserved' if explicit else 'exact-declared-method-primary-sources-v1'
    names=re.findall(r'(?im)^\s*(?:\*\*)?(?:Chosen|Selected)\s+Method\s*:\s*(?:\*\*)?\s*([^;\uff1b\r\n]+)',protocol)
    if not names:
        header=protocol.splitlines()[0] if protocol else ''
        mentions=[key for key in method_keys if re.search(r'(?<![A-Za-z0-9])'+re.escape(key)+r'(?![A-Za-z0-9+])',header,re.I)]
        names=mentions if len(mentions)==1 else []
    identities=[method_identity(name.strip().strip('*').strip(),method_keys) for name in names]
    selected={i['resolved_key'] for i in identities if i['status']=='RESOLVED_SINGLE'}
    reasons=[]
    if explicit:
        keep=cards
        reasons=['EXPLICIT_CONTEXT_NOT_PRUNED']
    elif len(names)!=1 or len(selected)!=1 or any(i['status']!='RESOLVED_SINGLE' for i in identities):
        keep=cards
        reasons=['SELECTED_SINGLE_METHOD_NOT_DETERMINED']
    else:
        method=next(iter(selected))
        # Active transition to another named recipe is uncertainty, not a comparison citation.
        others=[key for key in method_keys if key!=method]
        active=[key for key in others if re.search(r'(?:then|followed by|subsequently|\u968f\u540e|\u7ee7\u800c|\u518d\u7528)\s+(?:the\s+)?'+re.escape(key)+r'(?![A-Za-z0-9+])',protocol,re.I)]
        active += [key for key in others if re.search(r'(?im)^\s*\*\*[^\n]*(?:clearing|\u900f\u660e)[^\n]*'+re.escape(key)+r'(?![A-Za-z0-9+])',protocol,re.I)]
        if active:
            keep=cards;reasons=['OTHER_ACTIVE_METHOD_RECIPE_UNCERTAIN']
        else:
            keep=[c for c in cards if method_identity(c.get('method',''),method_keys).get('resolved_key')==method]
            if not keep:
                keep=cards;reasons=['NO_EXACT_PRIMARY_SOURCE_FOR_SELECTED_METHOD']
    chosen={c['id'] for c in keep}
    inventory=[dict(id=c['id'],card_sha256=digest(c),source_sha256=c.get('source_document',{}).get('sha256'),
                    selected=c['id'] in chosen) for c in cards]
    return keep,dict(policy=policy,declared_method_names=names,resolved_methods=sorted(selected),
                     fallback_reasons=reasons,selected_source_ids=[c['id'] for c in keep],
                     unselected_source_ids=[c['id'] for c in cards if c['id'] not in chosen],source_inventory=inventory)

def build_context(question_meta, protocol, workspace=None, study_context=None):
    if not isinstance(question_meta, dict) or not isinstance(protocol, str):
        raise ValueError('Question object and unchanged protocol required')
    explicit = study_context is not None
    task = deepcopy(study_context) if explicit else {}
    if not isinstance(task, dict):
        raise ValueError('study_context must be an object')
    if task.get('protocol_sha256') not in (None, text_hash(protocol)) or task.get('question_sha256') not in (None, digest(question_meta)):
        raise ValueError('Task context belongs to another input')
    cards = task.get('cards', []) if explicit else _cards(Path(workspace or ROOT))
    method_path=Path(workspace or ROOT)/'KnowledgeBase/method_ri_ref.json'
    method_keys=list(json.loads(method_path.read_text(encoding='utf-8-sig')).get('ri_ref',{})) if method_path.exists() else ['MACS','CUBIC','SeeDB','SeeDB2','FDISCO','iDISCO+','FRUIT']
    method_keys=deepcopy(task.get('method_keys',method_keys))
    audit_cards=deepcopy(cards)
    cards,retrieval=_retrieve_cards(cards,protocol,method_keys,explicit)
    task_state = propose_task_state(question_meta, evidence_ids=[c['id'] for c in cards])
    requirements = task.get('requirements')
    if requirements is None:
        requirements = [dict(id='DECLARED_STEPS', kind='COMPLETENESS', necessary=True, evidence_ids=[],
            text='Provide explicit processing steps within the stated execution scope, without requiring completed fixation or label QC again.',
            literal_rule=dict(type='EXTRACTION_NONEMPTY', collection='steps')),
            dict(id='DECLARED_APPLICABILITY', kind='SCIENTIFIC', necessary=True, evidence_ids=[c['id'] for c in cards],
            text='Evidence supports the actual selected single method and conditions for this sample and existing labels; naming a method alone is insufficient.'),
            dict(id='SINGLE_METHOD_IDENTITY',kind='TEXT',necessary=True,evidence_ids=[],
                 text='Declare one identified clearing method per complete alternative branch; do not splice methods.',
                 literal_rule=dict(type='METHOD_IDENTITY_SINGLE'))]
        requirements += _question_requirements(question_meta)
        requirements += deepcopy(task_state['requirements'])
        for index,target in enumerate(question_meta.get('marker_query_targets', [])):
            goal=target.get('structure_or_cell_subtype') or target.get('query_path')
            if goal:
                requirements.append(dict(id='TARGET_FUNCTION_'+str(index+1),kind='SCIENTIFIC',necessary=True,
                    evidence_ids=[c['id'] for c in cards],text='Support the requested signal/function: '+str(goal)+
                    '; preserve existing QC-passed channels when stated, without automatically demanding new staining.',
                    question_metadata_path='marker_query_targets/'+str(index),origin='PROVISIONAL_TASK_FUNCTION_NOT_ALIAS_GOLD'))
        qtext=str(question_meta.get('question',''))
        if 'RI' in qtext:
            requirements.append(dict(id='RI_MEDIUM_DECLARATION',kind='COMPLETENESS',necessary=True,evidence_ids=[],
                text='Declare the final RI matching medium within the requested scope.',literal_rule=dict(type='EXTRACTION_NONEMPTY',collection='ri')))
    validate_requirements(requirements)
    validate_cards(cards)
    condition_rules = (deepcopy(task.get('source_condition_rules', {'schema_version':'source-condition-rules-v1','rules':[]}))
                       if explicit else load_rules(Path(workspace or ROOT)))
    condition_diagnostics = diagnose_source_conditions(protocol, cards, condition_rules, method_keys=method_keys)
    inventory = task.get('field_inventory')
    if inventory is not None:
        if not isinstance(inventory, list):
            raise ValueError('Field inventory must be an array')
        for item in inventory:
            if item.get('collection') not in {'labels','steps','ri'} or not isinstance(item.get('field'), str):
                raise ValueError('Inventory needs collection and field')
            validate_span(protocol, item['span'])
    context = dict(schema_version=VERSION, question_meta=deepcopy(question_meta), question_sha256=digest(question_meta),
                   protocol_sha256=text_hash(protocol), requirements=requirements, cards=cards, formula=task.get('formula'),
                   field_inventory=inventory, origin='EXPLICIT_FROZEN_TASK_CONTEXT' if explicit else 'AUTO_PROVISIONAL_NOT_DOMAIN_REVIEWED',
                   scope=deepcopy(task.get('scope', question_meta)), domain_reviewed=task.get('domain_reviewed') is True,
                   frozen_objectives=deepcopy(task.get('verified_objectives')),
                   route_methods=deepcopy(task.get('route_methods', {})),method_keys=method_keys,
                   audit_cards=audit_cards,retrieval=retrieval,field_scope_policy='diagnostic',quotation_policy='diagnostic',
                   source_condition_rules=condition_rules, source_condition_diagnostics=condition_diagnostics,
                   task_state_audit=task_state,
                   extraction_mode=task.get('extraction_mode', 'record_refs'))
    if context['extraction_mode'] not in {'record_refs','literal_fields'}:
        raise ValueError('Unknown extraction mode')
    if context['extraction_mode']=='record_refs':
        context['source_record_catalog'] = build_record_catalog(protocol)
        template = (ROOT/'prompts/oeq_scientific_record_assessment.txt').read_text(encoding='utf-8')+'\nEXTRACTION_INSTRUCTIONS\n'+RECORD_REF_PROMPT
    else:
        template = (ROOT/'prompts/oeq_scientific_assessment.txt').read_text(encoding='utf-8')
    context['prompt_template_sha256'] = text_hash(template)
    if not isinstance(context['route_methods'], dict) or any(not isinstance(v,str) or not v.strip() for v in context['route_methods'].values()):
        raise ValueError('Each route must declare one method identity, never a serial list')
    context['context_sha256'] = digest(context)
    prompt_context = deepcopy(context)
    prompt_context.pop('audit_cards')  # Full source snapshots remain in immutable audit context.
    # Locally calculated recommendation reports stay in the signed sidecar, not teacher input.
    prompt_context.pop('source_condition_diagnostics')
    prompt_context.pop('source_condition_rules')
    prompt_context.pop('task_state_audit')
    if prompt_context.get('scope')==prompt_context['question_meta']:
        prompt_context.pop('scope')  # Exact task already appears once in question_meta.
    prompt_context.pop('source_record_catalog', None)
    for requirement in prompt_context['requirements']:
        rule = requirement.get('literal_rule')
        if rule and rule.get('type')=='TASK_INITIAL_FUNCTION':
            rule.pop('state_audit', None)
    # Integrity hashes for unselected snapshots are audit metadata, not source evidence.
    prompt_context['retrieval'].pop('source_inventory', None)
    prompt_context['retrieval'].pop('unselected_source_ids', None)
    for card in prompt_context['cards']:
        doc = card.get('source_document')
        if isinstance(doc, dict):
            doc.pop('text', None)  # Full snapshots remain in hashed audit context, not duplicated in prompt.
    protocol_view = ('\nSOURCE_RECORD_VIEW\n'+json.dumps(build_compact_prompt_view(context['source_record_catalog']), ensure_ascii=False,sort_keys=True,separators=(',',':'))
                     if context['extraction_mode']=='record_refs' else '\nPROTOCOL\n'+protocol)
    context['prompt'] = template+'\nCONTEXT_JSON\n'+json.dumps(prompt_context, ensure_ascii=False,sort_keys=True,separators=(',',':'))+protocol_view
    context['prompt_sha256'] = text_hash(context['prompt'])
    return context


def _field_fact_eligible(fidelity, fact, fields):
    if any(fact['fields'][field]['status'] != 'GROUNDED' for field in fields):
        return False
    return not any(issue.get('collection') == fact['collection'] and issue.get('index') == fact['index']
                   and (issue.get('field') is None or issue.get('field') in fields)
                   for issue in fidelity['issues'])


def _requirement_fidelity(fidelity, req):
    """Keep source-domain errors local; retain a separate full extraction audit."""
    if req.get('scope', 'GLOBAL') != 'ROUTE':
        return dict(scoring_eligible=fidelity['scoring_eligible'], scope='GLOBAL',
                    issues=deepcopy(fidelity['issues']))
    rid=req['route_id']
    facts=[f for f in fidelity['facts'] if f['branch']==rid]
    indices={(f['collection'],f['index']) for f in facts}
    issues=[]
    for issue in fidelity['issues']:
        if 'branch' in issue:
            relevant=issue['branch']==rid
        elif 'collection' in issue and 'index' in issue:
            relevant=(issue['collection'],issue['index']) in indices
        else:
            # Unlocated structural errors cannot be silently assigned elsewhere.
            relevant=True
        if relevant:issues.append(deepcopy(issue))
    eligible=bool(facts) and not issues and all(
        field['status'] in {'GROUNDED','MISSING'}
        for fact in facts for field in fact['fields'].values())
    return dict(scoring_eligible=eligible, scope='ROUTE', route_id=rid,
                fact_ids=[f['id'] for f in facts], issues=issues,
                completeness_certified=False, scientific_truth=None)


def _route_method_identity(methods, route_id, extraction):
    declarations=[d for d in methods['declarations'] if d['branch']==route_id]
    names=methods['branches'].get(route_id,[])
    step_ids={row['id'] for row in extraction['steps'] if row['branch']==route_id}
    conflicts=[sid for sid in methods['operation_method_conflicts'] if sid in step_ids]
    if not declarations:
        status='UNDER_SPECIFIED'
    elif any(d['guards'] for d in declarations) or not names or not all(names) or conflicts:
        status='UNRESOLVED'
    elif len(set(names))>1:
        status='VIOLATED'
    elif len(names)!=1:
        status='UNRESOLVED'
    else:
        status='SATISFIED'
    return dict(status=status,scope='EXACT_SELECTED_NAME_IDENTITY_IN_BOUND_ROUTE_ONLY_NOT_RECIPE_FIDELITY',
                route_id=route_id,selected_methods=deepcopy(names),declarations=deepcopy(declarations),
                operation_method_conflicts=conflicts,scientific_truth=None)


def _literal(req, extraction, text, cards, method_audit, fidelity, source_scope=None):
    rule = req.get('literal_rule')
    if rule is None:
        return None
    kind = rule.get('type')
    scoped_route = req.get('route_id') if req.get('scope','GLOBAL')=='ROUTE' else None
    if source_scope is not None and source_scope['scope_status']!='RESOLVED':
        return dict(status='UNRESOLVED',scope='REQUIREMENT_SOURCE_REGION_UNRESOLVED',
                    guards=deepcopy(source_scope['guards']),scientific_truth=None)
    regions = source_scope['regions'] if source_scope is not None else [dict(start=0,end=len(text),quote=text)]
    def in_route(fact):
        return scoped_route is None or fact['branch']==scoped_route
    if kind == 'EXTRACTION_NONEMPTY':
        collection = rule['collection']
        required_fields = {'steps': ['operation'], 'ri': ['solution', 'value_text'],
                           'labels': ['target', 'probe']}[collection]
        facts = [fact for fact in fidelity['facts'] if fact['collection'] == collection and in_route(fact)]
        eligible = [fact for fact in facts if fact['assertion']['polarity'] == 'AFFIRMED'
                    and _field_fact_eligible(fidelity, fact, required_fields)]
        status = 'SATISFIED' if eligible else ('UNRESOLVED' if facts else 'UNDER_SPECIFIED')
        scope = 'AT_LEAST_ONE_GROUNDED_AFFIRMED_DECLARATION_NOT_EXECUTION_OR_COMPLETENESS_PROOF'
    elif kind == 'LITERAL_REQUIRED':
        token = rule['text']
        if not isinstance(token, str) or not token:
            raise ValueError('Empty literal requirement')
        status = 'SATISFIED' if any(token in region['quote'] for region in regions) else 'UNDER_SPECIFIED'
        scope = 'EXACT_REQUIRED_TEXT_IN_BOUND_ROUTE' if scoped_route else 'EXACT_REQUIRED_TEXT_ONLY'
    elif kind == 'SOURCE_LITERAL_EQUALITY':
        check = _bound_literal_equality(rule,extraction,text,cards,fidelity)
        binding = rule['protocol_binding']
        facts = [fact for fact in fidelity['facts'] if fact['collection'] == binding['collection']
                 and ((binding.get('record_id') is not None and fact['id'] == binding['record_id'])
                      or (binding['collection'] == 'ri' and binding.get('branch') is not None
                          and fact['branch'] == binding['branch']))]
        if len(facts) != 1 or not _field_fact_eligible(fidelity, facts[0], [rule['field'], rule['entity_field']]):
            check.update(status='UNRESOLVED', extraction_dependency_status='REVIEW_REQUIRED')
        else:
            check['extraction_dependency_status'] = 'GROUNDED'
        return check
    elif kind == 'TASK_INITIAL_FUNCTION':
        from experiments.construct_validity.task_function_presence import assess_required_function
        return assess_required_function(rule, extraction, text, fidelity,
                                        source_scope=source_scope, route_id=scoped_route)
    elif kind == 'METHOD_IDENTITY_SINGLE':
        return _route_method_identity(method_audit,scoped_route,extraction) if scoped_route else deepcopy(method_audit)
    elif kind in {'NO_REPEAT_FIXATION','NO_REPEAT_LABEL_QC','NO_OLD_SIGNAL_RECOVERY'}:
        patterns={
          'NO_REPEAT_FIXATION':r'(?:repeat(?:ed)? fixation|re-?fix|\u91cd\u590d\u56fa\u5b9a|\u518d\u6b21\u56fa\u5b9a|\u91cd\u65b0\u56fa\u5b9a)',
          'NO_REPEAT_LABEL_QC':r'(?:repeat(?:ed)? label|re-?label|\u91cd\u65b0\u67d3\u8272|\u91cd\u590d\u6807\u8bb0|\u518d\u6b21\u793a\u8e2a)',
          'NO_OLD_SIGNAL_RECOVERY':r'(?:restore old signal|recover old signal|\u6062\u590d[^\u3002]{0,10}\u65e7[^\u3002]{0,10}\u4fe1\u53f7)',
        }
        facts = [fact for fact in fidelity['facts'] if fact['collection'] == 'steps' and in_route(fact)]
        eligible = {fact['index'] for fact in facts if _field_fact_eligible(fidelity, fact, ['operation'])}
        violations = [row['id'] for index, row in enumerate(extraction['steps']) if index in eligible
                      and row['assertion']['polarity'] == 'AFFIRMED'
                      and re.search(patterns[kind], row['operation'] or '', re.I)]
        unproven = [fact['id'] for fact in facts if fact['index'] not in eligible]
        conditional = [row['id'] for index, row in enumerate(extraction['steps']) if index in eligible
                       and row['assertion']['polarity']=='CONDITIONAL'
                       and re.search(patterns[kind],row['operation'] or '',re.I)]
        status = 'VIOLATED' if violations else ('UNRESOLVED' if unproven or conditional else 'SATISFIED')
        scope='DECLARED_OPERATION_SCOPE_ONLY_NOT_FULL_SEMANTIC_OR_OMISSION_CERTIFICATION'
        return dict(status=status,scope=scope,violation_step_ids=violations,unproven_step_ids=unproven,conditional_step_ids=conditional,scientific_truth=None)
    else:
        raise ValueError('Unknown literal rule')
    return dict(status=status, scope=scope, scientific_truth=None)


def apply_assessment(raw_structured, context, protocol):
    frozen = {k:v for k,v in context.items() if k not in {'context_sha256','prompt','prompt_sha256'}}
    if context.get('schema_version') != VERSION or digest(frozen) != context.get('context_sha256') or text_hash(protocol) != context['protocol_sha256']:
        raise ValueError('Frozen context or answer changed')
    raw = parse_json(raw_structured) if isinstance(raw_structured,str) else deepcopy(raw_structured)
    if not isinstance(raw,dict) or set(raw) not in ({'extraction','assessment','objectives'}, {'extraction','assessment','objectives','method_declarations'}):
        raise ValueError('Expected extraction, assessment, objectives')
    extraction = deepcopy(raw['extraction'])
    reference_expansion = None
    if isinstance(extraction,dict) and extraction.get('schema_version')==RECORD_REF_SCHEMA:
        if context['extraction_mode']!='record_refs':
            raise ValueError('Record references were not requested by this frozen context')
        reference_expansion = expand_record_refs(extraction, protocol, catalog=context['source_record_catalog'])
        extraction = deepcopy(reference_expansion['expanded'])
    policy = context['field_scope_policy']
    validated = validate_extraction(extraction, protocol, field_scope_policy=policy)
    fidelity = deepcopy(validated['field_audit'])
    inventory, matched, missing = context['field_inventory'], [], []
    for item in inventory or []:
        found = any(f['collection']==item['collection'] and item['field'] in f['fields'] and
                    _field_fact_eligible(fidelity, f, [item['field']]) and
                    any(s['start']==item['span']['start'] and s['end']==item['span']['end'] for s in f['fields'][item['field']].get('spans',[]))
                    for f in fidelity['facts'])
        (matched if found else missing).append(deepcopy(item))
    fidelity.update(coverage_status='INVENTORY_COMPLETE' if inventory and not missing else 'PARTIAL',
                    missing_fields=missing, independently_declared_fields=inventory,
                    inventory_recall=len(matched)/len(inventory) if inventory else None,
                    completeness_certified=bool(inventory) and not missing and fidelity['scoring_eligible'],
                    inventory_scope='SUPPLIED_DECLARED_REFERENCE_ONLY_NOT_FULL_CONTENT_OR_SCIENTIFIC_GOLD')
    judged = adjudicate(_spans(raw['assessment'], protocol),context['requirements'],protocol,context['cards'],context['formula'],quotation_policy=context['quotation_policy'])
    by_id = {r['id']:r for r in context['requirements']}
    records = judged['requirements']
    methods = _method_audit(raw,validated,context,protocol)
    for record in records:
        req = by_id[record['id']]
        source_scope = resolve_scope(req,validated,protocol)
        scope_audit = audit_requirement_quotes(record,source_scope,protocol)
        binding_audit = audit_requirement_bindings(record,source_scope,protocol)
        local_fidelity = _requirement_fidelity(fidelity,req)
        record['protocol_binding_scope_audit']=binding_audit
        record['requirement_fidelity_audit']=local_fidelity
        record['source_scope']=source_scope
        record['requirement_scope_audit']=scope_audit
        check = _literal(req, extraction, protocol, context['cards'],methods,fidelity,source_scope)
        record['verification'] = check
        if req.get('literal_rule',{}).get('type')=='TASK_INITIAL_FUNCTION' and req.get('necessity_status')=='UNRESOLVED':
            record['effective_status']='UNRESOLVED'
            record['guards'].append('TASK_EXECUTION_APPLICABILITY_UNRESOLVED')
        elif check and req['kind'] != 'SCIENTIFIC':
            record['effective_status'] = check['status']
        elif req['kind'] != 'SCIENTIFIC':
            record['effective_status'] = 'UNRESOLVED'
            record['guards'].append('TEXT_SEMANTIC_PROPOSAL_NOT_INDEPENDENTLY_VERIFIED')
        if req.get('scope','GLOBAL')=='ROUTE':
            record['guards']=sorted(set(record['guards'])|set(scope_audit['guards'])|set(binding_audit['guards']))
            if source_scope['scope_status']!='RESOLVED' or binding_audit['status']!='RESOLVED':
                record['effective_status']='UNRESOLVED'
            elif record['effective_status'] in {'SATISFIED','VIOLATED'} and (scope_audit['status']!='RESOLVED' or not scope_audit['has_local_decisive_anchor']):
                record['effective_status']='UNRESOLVED'
                record['guards']=sorted(set(record['guards'])|{'REQUIREMENT_DECISION_NOT_GROUNDED_IN_ITS_ROUTE'})
        if set(record['guards']) & {'INVALID_PROTOCOL_QUOTATION','MISSING_DECISIVE_PROTOCOL_ANCHOR'} and record['effective_status'] in {'SATISFIED','VIOLATED'}:
            record['effective_status']='UNRESOLVED'
        if req['kind']=='SCIENTIFIC' and not local_fidelity['scoring_eligible'] and record['effective_status']=='SATISFIED':
            record['effective_status']='UNRESOLVED'
            record['guards'].append('EXTRACTION_FIDELITY_REVIEW_REQUIRED')
    for record in records:
        req=by_id[record['id']]
        identity=(_route_method_identity(methods,req['route_id'],extraction) if req.get('scope','GLOBAL')=='ROUTE' else methods)
        if req['kind']=='SCIENTIFIC' and record['effective_status']=='SATISFIED' and identity['status']!='SATISFIED':
            record['effective_status']='UNRESOLVED'
            record['guards'].append('SINGLE_METHOD_IDENTITY_NOT_ESTABLISHED')
    states = {r['id']:r['effective_status'] for r in records}
    overall = evaluate_formula(admissibility_formula(context['requirements'],context['formula']), states)
    routes = {}
    for req in context['requirements']:
        if req.get('scope','GLOBAL')=='ROUTE' and req['necessary']:
            routes.setdefault(req['route_id'],[]).append(req['id'])
    route_results=[]
    for rid,ids in routes.items():
        declared=context['route_methods'].get(rid)
        names=methods['branches'].get(rid,[])
        identity_ok=_route_method_identity(methods,rid,extraction)['status']=='SATISFIED' and bool(declared) and len(names)==1 and method_identity(declared,context['method_keys']).get('resolved_key')==names[0] and names[0] is not None
        status=combine([states[i] for i in ids])
        if status=='SATISFIED' and not identity_ok:status='UNRESOLVED'
        route_results.append(dict(route_id=rid,requirement_ids=ids,status=status,scope='COMPLETE_DECLARED_ROUTE',
                                  single_method=declared,single_method_identity_verified=identity_ok,
                                  guards=[] if identity_ok else ['ROUTE_METHOD_IDENTITY_NOT_ESTABLISHED']))
    if overall=='SATISFIED' and route_results and not any(r['status']=='SATISFIED' for r in route_results):overall='UNRESOLVED'
    from experiments.construct_validity.candidate_binding import audit_candidate_bindings
    candidate_binding = audit_candidate_bindings(
        context['requirements'], records, route_results, overall, protocol, validated, fidelity)
    overall, route_results = candidate_binding['overall'], candidate_binding['route_results']
    from experiments.construct_validity.answer_matching import summarize_answer_matching
    answer_matching = summarize_answer_matching(context['requirements'], records, route_results, overall,
                                               text_hash(protocol), requested_formula=context['formula'])
    science = [r for r in records if by_id[r['id']]['kind']=='SCIENTIFIC']
    text = [r for r in records if by_id[r['id']]['kind']!='SCIENTIFIC']
    source_states = [r['effective_status'] for r in records if r['verification'] and r['verification']['scope'].startswith('FROZEN_LITERAL')]
    source_states += [r['effective_status'] for r in science if r.get('evidence_audit')]
    if not isinstance(raw['objectives'],dict):
        raise ValueError('Objectives must be an object')
    objectives = dict(id=text_hash(protocol),task_id=context['question_sha256'],scenario=deepcopy(context['scope']),
                      constraints={'complete_contract':overall},objectives=deepcopy(context['frozen_objectives'] or {}),
                      proposals=deepcopy(raw['objectives']),status='FROZEN_EXTERNAL_VALUES' if context['frozen_objectives'] else 'PROPOSED_VALUES_NOT_VERIFIED',
                      scientific_validation=None)
    from oeq_quantity_audit import audit_quantity_scope
    return dict(schema_version=VERSION,context_sha256=context['context_sha256'],technical_status='VALID',
                quantity_scope_diagnostics=audit_quantity_scope(protocol),
                extraction_fidelity=fidelity,extraction=validated,
                extraction_reference_audit=({k:deepcopy(reference_expansion[k]) for k in ['raw_payload','coverage','reference_audits','length_model']} if reference_expansion else None),
                task_state_audit=deepcopy(context['task_state_audit']),method_identity=methods,requirement_results=records,route_results=route_results,overall=overall,
                candidate_binding_audit=candidate_binding['audit'],answer_matching=answer_matching,
                source_consistency_decision=dict(status=combine(source_states) if source_states else 'UNRESOLVED',scope='BOUND_SOURCE_RELATIONS_NOT_EXPERIMENTAL_SUCCESS'),
                text_completeness_decision=dict(status=combine([r['effective_status'] for r in text]) if text else 'UNRESOLVED'),
                scientific_applicability_decision=dict(status=combine([r['effective_status'] for r in science]) if science else 'UNRESOLVED',independent_scientific_validation=None),
                source_condition_diagnostics=deepcopy(context['source_condition_diagnostics']),
                experimental_success_claim=None,objectives=objectives,contract_origin=context['origin'],scientific_gold=None,
                abstention_reason=[r['id'] for r in records if r['effective_status'] in {'UNRESOLVED','UNDER_SPECIFIED'}])


def compare_assessments(a,b,*,required_constraints=None,objective_names=None):
    return compare_candidates(a['objectives'],b['objectives'],required_constraints=required_constraints,objective_names=objective_names)

def diagnose_assessment(raw_structured, protocol):
    """Failure sidecar only; never emit eligibility or effective decisions."""
    raw = parse_json(raw_structured) if isinstance(raw_structured,str) else deepcopy(raw_structured)
    if not isinstance(raw,dict):
        raise ValueError('Diagnostic expects original structured object')
    result = diagnose_extraction(raw.get('extraction'),protocol)
    result['proposal_sha256'] = digest(raw)
    declarations = raw.get('method_declarations', [])
    if isinstance(declarations,list):
        for index, declaration in enumerate(declarations):
            if not isinstance(declaration,dict):continue
            path=f'method_declarations[{index}].span'
            try:
                resolution=quote_span_candidates(protocol,declaration.get('span'))
                result['locations'].append(dict(path=path,**resolution))
                result['ambiguous_locations'] += resolution['resolved_span'] is None
            except (ValueError,TypeError) as exc:
                result['hard_errors'].append(dict(path=path,message=str(exc),type=type(exc).__name__))
    return result
