"""Original-record source recommendations; never scientific failure labels.

This parser proves limited surface relations in explicit operation records.
Unproved relation/scope is retained for review, never silently called compliant.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from evaluator_integrity import method_identity
from .contract import digest
from .fidelity import text_hash, validate_span

VERSION = 'source-condition-diagnostics-v5'
RULE_SCHEMA = 'source-condition-rules-v1'
_CELSIUS = r'(?:\u2103|\u00b0\s*C|C)'
_TEMP = re.compile(r'(?<![\w.+-])(?P<n>[+-]?\d+(?:\.\d+)?)\s*' + _CELSIUS + r'(?!\w)', re.I)
_TEMP_FIELD = re.compile(r'(?:Temperature|\u6e29\u5ea6)\s*[:\uff1a]\s*(?P<v>[^,;\uff0c\uff1b()\n]+)', re.I)
_MEDIUM = re.compile(r'CUBIC\s*[-\u2013]\s*R\s*\+\s*(?:\(\s*[MN]\s*\))?', re.I)
_STORAGE = re.compile(r'\b(?:store|stored|storage|keep|kept|leave|left)\b|\u4fdd\u5b58|\u50a8\u5b58|\u5b58\u50a8', re.I)
_CONDITION = re.compile(r'\b(?:if|unless|may|might|could|would|optional|consider)\b|\u5982\u679c|\u5047\u5982|\u82e5|\u53ef\u9009|\u5fc5\u8981\u65f6|\u53ef\u4ee5|\u8003\u8651|\u6309\u9700|\u5982\u9700|\u89c6\u60c5\u51b5|\bas\s+(?:needed|required)\b|\bwhen\s+(?:needed|required)\b', re.I)
_NEG_STORAGE = re.compile(r'(?:do\s+not|don.t|never|avoid|not)\s+(?:\w+\s+){0,4}(?:stor\w*|keep|leave)|(?:\u4e0d\u5f97|\u4e0d\u8981|\u4e0d\u5e94|\u4e0d\u80fd|\u7981\u6b62|\u907f\u514d|\u4e0d)[^\uff0c\u3002;\uff1b]{0,24}(?:\u4fdd\u5b58|\u50a8\u5b58|\u5b58\u50a8)', re.I)
_DECLARATION = re.compile(r'(?m)^[ \t]*(?:\*\*)?Chosen\s+Method\s*[:\uff1a](?:\*\*)?\s*(?P<name>[^;\uff1b\n]+)', re.I)
_MULTI_ACTION = re.compile(r'(?<!\d)\.(?!\d)\s+\S|;|\uff1b|\u3002|\b(?:then|instead|replace|remove)\b|\u968f\u540e|\u79fb\u9664|\u66ff\u6362|\u53d6\u51fa|\u7ee7\u800c', re.I)

_SAMPLE_OBJECT = re.compile(r'\b(?:samples?|specimens?|organs?|tissues?|brains?|nodes?)\b|\u6837\u672c|\u7ec4\u7ec7|\u5668\u5b98|\u900f\u660e', re.I)
_FOREIGN_OBJECT = re.compile(r'\b(?:reagent|stock|buffer|solution|bottle|vial)\b|\u8bd5\u5242|\u50a8\u5907\u6db2|\u50a8\u5b58\u6db2|\u6eb6\u6db2', re.I)
_NEG_CONTEXT = re.compile(r'\b(?:do\s+not|never|avoid|rejected|discarded)\b|\u4e0d\u5f97|\u4e0d\u8981|\u7981\u6b62|\u4e0d\u6267\u884c|\u907f\u514d', re.I)
_NEG_RECORD = re.compile(r'(?:do\s+not|never|avoid)\s+(?:perform|execute|carry\s+out)|\bnot\s+(?:performed|executed|carried\s+out)\b|\b(?:rejected|discarded)\b|\u672a\u6267\u884c|\u672a\u5b9e\u65bd|\u4e0d\u6267\u884c|\u4e0d\u5b9e\u65bd|\u4e0d\u8981\u8fdb\u884c', re.I)


def load_rules(workspace):
    workspace = Path(workspace).resolve()
    path = workspace / 'KnowledgeBase/source_condition_rules.json'
    if not path.exists():
        return {'schema_version': RULE_SCHEMA, 'rules': []}
    if not path.resolve().is_relative_to(workspace):
        raise ValueError('Condition rules escape workspace')
    result = json.loads(path.read_text(encoding='utf-8-sig'))
    if result.get('schema_version') != RULE_SCHEMA or not isinstance(result.get('rules'), list):
        raise ValueError('Unknown source condition rules')
    result['file_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _storage_source_proof(rule, cards):
    if (rule.get('type') != 'AUTHOR_RECOMMENDATION'
            or rule.get('condition_type') != 'EXPLICIT_IMMERSED_STORAGE_TEMPERATURE'
            or rule.get('decision_policy') != 'ADVISORY_ONLY_NEVER_CHANGE_REQUIREMENT_STATE'
            or rule.get('medium_family') != 'CUBIC-R+' or rule.get('method_key') != 'CUBIC'):
        raise ValueError('Unsupported scientific meaning in recommendation rule')
    card = next((c for c in cards if c.get('id') == rule.get('source_id')), None)
    if card is None:
        return None
    doc, identity = card.get('source_document', {}), card.get('identity', {})
    text = doc.get('text')
    if (not isinstance(text, str) or text_hash(text) != rule.get('source_sha256')
            or doc.get('sha256') != rule['source_sha256']
            or identity.get('version') != rule.get('source_version')):
        raise ValueError('Recommendation source snapshot/version mismatch')
    passage_map = {p['id']: p for p in card.get('passages', [])}
    ids = rule.get('source_passage_ids')
    if not isinstance(ids, list) or not ids or any(i not in passage_map for i in ids):
        raise ValueError('Recommendation primary passages unbound')
    passages = [validate_span(text, {k:passage_map[i][k] for k in ('start','end','quote')}) for i in ids]
    guidance = validate_span(text, rule.get('source_guidance_span'))
    if not any(p['start'] <= guidance['start'] and guidance['end'] <= p['end'] for p in passages):
        raise ValueError('Guidance outside declared primary passages')
    avoid = re.search(r'Avoid\s+storage\s+at\s+(?P<t>[+-]?\d+(?:\.\d+)?\s*' + _CELSIUS + r')', guidance['quote'], re.I)
    if not avoid or float(_TEMP.fullmatch(avoid['t']).group('n')) != rule.get('avoid_temperature_C'):
        raise ValueError('Avoided temperature not stated in primary recommendation')
    if 'CUBIC-R+' not in re.sub(r'\s+', '', guidance['quote']):
        raise ValueError('Guidance medium family unbound')
    return {'source_id': card['id'], 'source_sha256': doc['sha256'],
            'source_version': identity['version'], 'guidance_span': guidance,
            'source_passage_ids': list(ids), 'publication_status': identity.get('publication_status', 'UNKNOWN'),
            'scope': rule['source_procedure_scope'], 'scope_limit': rule['source_scope_limit']}


_SEED_CONTRACTS = {
    'SEEDB2_PROTOCOL_2018': ('f7a504425ee9b28b41dc57939894a83dfeb9261bf08d1455158b7886185f7aa0',
        'Bio-protocol 8(20):e3046; corrected by e3095', 'PAGE12', 26311, 28764,
        '901cf7f9da0af795428b2c886bcdd993ad2ff0c192487e5fd4315ef3cdf479bf'),
    'SEEDB2_CORRECTION_2018': ('b5e7998e271a1372d7ed42f9ce576207944a9f5e48230d0f73c5a442c285aa75',
        'Bio-protocol 8(21):e3095; 2018-11-05', 'PAGE1', 0, 1353,
        'b5e7998e271a1372d7ed42f9ce576207944a9f5e48230d0f73c5a442c285aa75')}
_SEED_SPAN_CONTRACTS = {
    'guidance': (26635,26840,'0c832d4e49cfc22a25a65228f19750e6b6dca3985cb4c3634ecc875923a2aad8'),
    'recipe': (26608,27558,'8c9196e7329c061f9011390710068f2ec86915616de56610defa03ba7a35b6fc'),
    'correction': (696,1173,'0d6426b1e19f8269b1e55429ad3e9a3bc4d68ea600950fdc51728b1ff3fa533f')}
_SEED_MEDIUM = re.compile(r'(?<![\w])SeeDB2(?:S|G)?(?![\w])', re.I)
_PBS = re.compile(r'(?<![\w])PBS(?![\w])', re.I)
_NEG_PREPARATION = re.compile(r'\b(?:do\s+not|never|avoid)\s+(?:\w+\s+){0,3}(?:use|prepare|dilute|dissolve|add)\b|\bnot\s+(?:prepared|diluted|used)\b|(?:\u4e0d\u8981|\u4e0d\u5f97|\u4e0d\u5e94|\u7981\u6b62|\u4e0d\u4f7f\u7528)[^\u3002;\uff1b]{0,30}(?:\u7a00\u91ca|\u914d\u5236|\u6eb6\u89e3|\u4f7f\u7528|PBS)', re.I)


def _seed_bind(binding, cards, source_id):
    expected_hash, version, pid, start, end, page_hash = _SEED_CONTRACTS[source_id]
    if (binding.get('source_id'),binding.get('source_sha256'),binding.get('source_version')) != (source_id,expected_hash,version):
        raise ValueError('SeeDB2 immutable source identity/hash/version mismatch')
    if binding.get('source_passage_ids') != [pid]:
        raise ValueError('SeeDB2 full primary page binding required')
    selected=[c for c in cards if c.get('id')==source_id]
    if len(selected)>1:
        raise ValueError('Duplicate SeeDB2 source cards')
    if not selected:
        return None
    card=selected[0]; doc=card.get('source_document',{}); identity=card.get('identity',{})
    text=doc.get('text')
    if (not isinstance(text,str) or text_hash(text)!=expected_hash or doc.get('sha256')!=expected_hash
            or doc.get('version')!=version or identity.get('version')!=version):
        raise ValueError('SeeDB2 source snapshot/version mismatch')
    candidates=[p for p in card.get('passages',[]) if p.get('id')==pid]
    if len(candidates)!=1:
        raise ValueError('SeeDB2 primary page missing or duplicated')
    page=validate_span(text,{k:candidates[0][k] for k in ('start','end','quote')})
    if ((page['start'],page['end'])!=(start,end) or text_hash(page['quote'])!=page_hash
            or candidates[0].get('sha256')!=page_hash):
        raise ValueError('SeeDB2 full primary page shortened or changed')
    return card,text,page


def _seed_span(text, supplied, kind):
    start,end,sha=_SEED_SPAN_CONTRACTS[kind]
    span=validate_span(text,supplied)
    if (span['start'],span['end'])!=(start,end) or text_hash(span['quote'])!=sha:
        raise ValueError('SeeDB2 complete recipe/correction scope changed')
    return span


def _source_proof(rule,cards):
    kind=rule.get('condition_type')
    if kind=='EXPLICIT_IMMERSED_STORAGE_TEMPERATURE':
        return _storage_source_proof(rule,cards)
    if (kind!='EXPLICIT_SEEDB2S_PBS_PREPARATION_ROLE' or rule.get('type')!='AUTHOR_SOURCE_RELATION'
            or rule.get('method_key')!='SeeDB2' or rule.get('medium_family')!='SeeDB2S'
            or rule.get('decision_policy')!='ADVISORY_ONLY_NEVER_CHANGE_REQUIREMENT_STATE'
            or rule.get('corrected_by')!='SEEDB2_CORRECTION_2018'):
        raise ValueError('Unsupported source condition meaning')
    main=_seed_bind(rule,cards,'SEEDB2_PROTOCOL_2018')
    cb=rule.get('correction_binding',{})
    if cb.get('corrects_source_id')!='SEEDB2_PROTOCOL_2018':
        raise ValueError('SeeDB2 correction relation unbound')
    correction=_seed_bind(cb,cards,'SEEDB2_CORRECTION_2018')
    if main is None or correction is None:
        return None
    card,text,page=main
    guidance=_seed_span(text,rule.get('source_guidance_span'),'guidance')
    recipe=_seed_span(text,rule.get('source_recipe_span'),'recipe')
    corrected=_seed_span(correction[1],cb.get('source_guidance_span'),'correction')
    if not (page['start']<=recipe['start']<=guidance['start']<guidance['end']<=recipe['end']<=page['end']):
        raise ValueError('SeeDB2 recipe outside PAGE12')
    return {'source_id':card['id'],'source_sha256':rule['source_sha256'],'source_version':rule['source_version'],
        'source_passage_ids':['PAGE12'],'guidance_span':guidance,'recipe_span':recipe,'primary_page_span':page,
        'publication_status':card['identity'].get('publication_status','UNKNOWN'),
        'scope':rule['source_procedure_scope'],'scope_limit':rule['source_scope_limit'],
        'correction_binding':{'source_id':cb['source_id'],'source_sha256':cb['source_sha256'],
            'source_version':cb['source_version'],'source_passage_ids':['PAGE1'],
            'corrects_source_id':cb['corrects_source_id'],'guidance_span':corrected}}


def _seed_operation(line):
    # Full-match supported syntax; unknown composition/operation stays reviewable.
    op=re.sub(r'\s*\(\s*(?:Temperature|\u6e29\u5ea6)\s*[:\uff1a][^()]*\)\s*$','',line,flags=re.I)
    op=re.sub(r'^\s*\d+(?:\.\d+)*[.)\u3001]?\s+','',op).strip().rstrip('.\u3002').strip()
    medium=r'SeeDB2(?P<variant>S|G)'
    expressions=[
        (r'Dilute\s+(?:(?:pre-made|premade|existing|stock)\s+)*'+medium+r'(?:\s+(?:stock|solution|working solution))?\s+(?:with|using)\s+(?:1x\s+)?PBS','DILUTE_EXISTING_SOLUTION','DILUENT'),
        (r'(?:\u5c06|\u628a)(?P<sample>[^\uff0c\u3002;\uff1b\n]{1,30}?)\u6d78\u5165\s*\d+(?:\.\d+)?\s*vol%\s*'+medium+r'\s*\u5de5\u4f5c\u6db2\uff08\u4ee5\s*PBS\s*\u7a00\u91ca(?:\uff1bSeeDB2S\s*\u4e3a\s*iohexol\s*\u57fa\u9ad8\u6298\u5c04\u7387\u4ecb\u8d28)?\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8','DILUTE_EXISTING_SOLUTION','DILUENT'),
        (r'Prepare\s+'+medium+r'\s+from\s+Histodenz\s+powder\s+(?:using|with)\s+(?:1x\s+)?PBS','PREPARE_FROM_HISTODENZ_POWDER','PREPARATION_BUFFER'),
        (r'Dissolve\s+Histodenz\s+powder\s+in\s+(?:1x\s+)?PBS\s+to\s+prepare\s+'+medium,'PREPARE_FROM_HISTODENZ_POWDER','PREPARATION_BUFFER'),
        (r'\u7528\s*PBS\s*\u6eb6\u89e3\s*Histodenz\s*\u7c89\u672b\u914d\u5236\s*'+medium,'PREPARE_FROM_HISTODENZ_POWDER','PREPARATION_BUFFER'),
        (r'Wash\s+(?:the\s+)?(?:sample|tissue)\s+in\s+PBS\s+before\s+'+medium+r'\s+clearing','WASH_TISSUE','WASH_BUFFER')]
    for expression,kind,role in expressions:
        match=re.fullmatch(expression,op,re.I)
        if match:
            if 'sample' in match.groupdict() and not re.search(r'\u6837\u672c|\u810a\u9ad3\u6bb5|\u8111\u5757|\u7ec4\u7ec7',match['sample']):
                return None
            return {'operation':kind,'variant':'SeeDB2'+match['variant'].upper(),'pbs_role':role,
                'proof':'FULL_RECORD_EXPLICIT_OPERATION_ARGUMENTS','stock_origin':'NOT_PROVEN'}
    return None


def _seed_findings(protocol,lines,declarations,method_keys,rule,proof):
    findings=[]
    for start,end,line in lines:
        mediums,pbs=list(_SEED_MEDIUM.finditer(line)),list(_PBS.finditer(line))
        if not mediums or not pbs:
            continue
        declaration=next((d for d in declarations if d['region']['start']<=start<d['region']['end']),None)
        reasons=[]
        if not declaration or declaration['method']!=rule['method_key']:
            reasons.append('SELECTED_METHOD_OR_REGION_UNPROVEN')
        reasons.extend(_context_guards(protocol,declaration,start,method_keys))
        first = _DECLARATION.search(protocol)
        prefix = protocol[:first.start()] if first else ''
        if declaration:
            prefix += '\n' + protocol[declaration['region']['start']:start]
        for preceding in prefix.splitlines():
            heading = preceding.strip().strip('*').strip()
            is_heading = heading.endswith((':', '\uff1a')) or re.match(r'^\s*#{1,6}\s+|^\s*\*\*.*\*\*\s*$', preceding)
            if is_heading and _NEG_PREPARATION.search(heading):
                reasons.append('PRECEDING_NEGATED_PREPARATION_SCOPE_UNPROVEN')
        if _CONDITION.search(line):
            reasons.append('CONDITIONAL_OPERATION')
        if _NEG_PREPARATION.search(line) or _NEG_RECORD.search(line):
            reasons.append('NEGATED_OR_REJECTED_PREPARATION')
        if len({m.group().upper() for m in mediums})!=1:
            reasons.append('MULTIPLE_OR_GENERIC_VARIANT_REFERENCES')
        if any(name!='SeeDB2' and re.search(r'(?<![\w+])'+re.escape(name)+r'(?![\w+])',line,re.I) for name in method_keys):
            reasons.append('OTHER_METHOD_IN_OPERATION_RECORD')
        relation=_seed_operation(line)
        if relation is None:
            reasons.append('S_VARIANT_OPERATION_PBS_ARGUMENT_UNPROVEN')
        if reasons:
            status,typed='REVIEW_REQUIRED','SCOPE_INSUFFICIENT'
        elif relation['variant']!='SeeDB2S' or relation['operation']=='WASH_TISSUE':
            status,typed='CONDITION_NOT_MATCHED',None
        elif relation['operation']=='PREPARE_FROM_HISTODENZ_POWDER':
            status,typed='AUTHOR_RECIPE_NONCONFORMANCE','AUTHOR_RECIPE_EXPLICIT_PROHIBITION'
        else:
            status,typed='LOCAL_SOURCE_POTENTIAL_RISK','LOCAL_POTENTIAL_RISK'
        findings.append({'rule_id':rule['id'],'condition_type':rule['condition_type'],'status':status,'typed_relation':typed,
            'record_span':_span(protocol,start,end),'medium_spans':[_span(protocol,start+m.start(),start+m.end()) for m in mediums],
            'pbs_spans':[_span(protocol,start+m.start(),start+m.end()) for m in pbs],
            'method_declaration':deepcopy(declaration),'relation_proof':relation,'relation_guards':sorted(set(reasons)),
            'source_proof':deepcopy(proof),'source_scope_guards':['POWDER_PROHIBITION_NOT_UNIVERSAL_DILUTION_PROOF',
                'LONG_TERM_STORAGE_THRESHOLD_UNSPECIFIED','CURRENT_PRECIPITATION_AND_IMAGING_FAILURE_UNPROVEN',
                'STOCK_COMPOSITION_AND_ORIGIN_NOT_PROVEN'],
            'interpretation':'Local author recipe relation only; dilution risk transfers a powder-preparation concern. Neither relation predicts precipitation or scientific failure; absent warnings do not establish compliance.',
            'changes_requirement_states':False,'scientific_failure':None})
    return findings


def _span(protocol, start, end):
    return validate_span(protocol, {'start': start, 'end': end, 'quote': protocol[start:end]})


def _declarations(protocol, method_keys):
    found = list(_DECLARATION.finditer(protocol))
    result = []
    for index, m in enumerate(found):
        raw = m['name'].strip().strip('*').strip()
        start = m.start('name') + m['name'].find(raw)
        result.append({'method': method_identity(raw, method_keys).get('resolved_key'),
                       'method_span': _span(protocol, start, start + len(raw)),
                       'region': {'start': m.start(), 'end': found[index + 1].start() if index + 1 < len(found) else len(protocol)},
                       'scope': 'EXPLICIT_CHOSEN_DECLARATION_REGION_NOT_COMPLETE_BRANCH_PROOF'})
    return result


def _relation(operation, medium_match):
    """A storage verb with this medium as explicit prepositional argument."""
    medium = re.escape(medium_match.group()).replace(r'\ ', r'\s*')
    english = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?(?:store|keep|leave)\s+(?P<sample>[^.;\n]{1,65}?)\s+(?:fully\s+)?(?:immersed\s+)?in\s+(?:fresh\s+)?(?:100\s*%\s+)?' + medium + r'(?:\s|[,.)]|$)', re.I)
    chinese = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)\u3001]?\s*)?(?:\u5c06|\u628a)(?P<sample>[^,\uff0c\u3002;\uff1b\n]{1,35}?)(?:\u5b8c\u5168)?(?:\u6d78\u6ca1|\u653e\u7f6e|\u7f6e|\u6d78\u6ce1)(?:\u4e8e|\u5165)(?:\u65b0\u9c9c\s*)?(?:100\s*%\s*)?' + medium + r'\s*\u4e2d?[,\uff0c\s]*(?:\u907f\u5149|\u5bc6\u5c01|\u4f4e\u6e29|\u51b7\u85cf|\s)*(?:\u4fdd\u5b58|\u50a8\u5b58|\u5b58\u50a8)\s*[.\u3002]?\s*$', re.I)
    match = english.search(operation) or chinese.search(operation)
    if not match:
        return None
    return {'sample_text': match['sample'], 'rule': 'EXPLICIT_STORAGE_VERB_WITH_MEDIUM_ARGUMENT'}


def _context_guards(protocol, declaration, record_start, method_keys):
    """Only abstain on unresolved earlier scope cues; never infer branch closure."""
    if not declaration:
        return []
    first = _DECLARATION.search(protocol)
    prelude = protocol[:first.start()] if first else ''
    prefix = prelude + '\n' + protocol[declaration['region']['start']:record_start]
    guards = []
    for raw_line in prefix.splitlines():
        if _DECLARATION.match(raw_line):
            continue
        heading = raw_line.strip().strip('*').strip()
        # A conditional sentence with unresolved scope may govern following records.
        if _CONDITION.search(heading):
            guards.append('PRECEDING_CONDITIONAL_SCOPE_UNPROVEN')
        # Recognize prohibited operations, without treating avoidance of light as rejection.
        is_heading = (heading.endswith((':', '\uff1a')) or re.match(r'^\s*#{1,6}\s+|^\s*\*\*.*\*\*\s*$', raw_line) is not None)
        if is_heading:
            negative_scope = (_NEG_RECORD.search(heading) or _NEG_STORAGE.search(heading)
                              or re.search(r'\bavoid\s+(?:the\s+)?(?:following|route|method|operations?)\b', heading, re.I))
            if negative_scope:
                guards.append('PRECEDING_CONDITIONAL_OR_NEGATED_SCOPE_UNPROVEN')
            if _FOREIGN_OBJECT.search(heading):
                guards.append('PRECEDING_REAGENT_OR_STOCK_SCOPE_UNPROVEN')
        if is_heading or re.search(r'\b(?:alternative|route|method)\b|\u65b9\u6cd5|\u8def\u7ebf|\u5907\u9009', heading, re.I):
            for name in method_keys:
                if name != declaration['method'] and re.search(r'(?<![\w+])' + re.escape(name) + r'(?![\w+])', heading, re.I):
                    guards.append('PRECEDING_OTHER_METHOD_SCOPE_UNPROVEN')
    return sorted(set(guards))


def diagnose(protocol, cards, rule_set, *, method_keys):
    if not isinstance(protocol, str) or rule_set.get('schema_version') != RULE_SCHEMA:
        raise ValueError('Original protocol and versioned rules required')
    rules = rule_set.get('rules')
    if not isinstance(rules, list) or len({r.get('id') for r in rules}) != len(rules):
        raise ValueError('Invalid/duplicate recommendation rules')
    declarations = _declarations(protocol, method_keys)
    result = {'version': VERSION, 'protocol_sha256': text_hash(protocol), 'rule_set_sha256': digest(rule_set),
              'rules_file_sha256': rule_set.get('file_sha256'), 'findings': [], 'rule_audits': [],
              'scope': 'LOCAL_SOURCE_RECOMMENDATIONS_NOT_HARD_CONSTRAINTS_OR_WET_LAB_SUCCESS',
              'scientific_validation': None, 'independent_scientific_truth': None}
    offset = 0
    lines = []
    for line in protocol.splitlines(keepends=True):
        end = offset + len(line.rstrip('\r\n'))
        lines.append((offset, end, protocol[offset:end]))
        offset += len(line)
    for rule in rules:
        proof = _source_proof(rule, cards)
        result['rule_audits'].append({'id': rule['id'], 'source_available': proof is not None,
                                     'status': 'SOURCE_BOUND' if proof else 'SOURCE_NOT_SELECTED', 'type': rule['type'],
                                     'condition_type':rule['condition_type']})
        if rule['condition_type'] == 'EXPLICIT_SEEDB2S_PBS_PREPARATION_ROLE':
            if proof is not None:
                result['findings'].extend(_seed_findings(protocol, lines, declarations, method_keys, rule, proof))
            continue
        if proof is None:
            continue
        for start, end, line in lines:
            mediums = list(_MEDIUM.finditer(line))
            if not mediums or not _STORAGE.search(line):
                continue
            reasons = []
            declaration = next((d for d in declarations if d['region']['start'] <= start < d['region']['end']), None)
            if not declaration or declaration['method'] != rule['method_key']:
                reasons.append('SELECTED_METHOD_OR_REGION_UNPROVEN')
            reasons.extend(_context_guards(protocol, declaration, start, method_keys))
            field = _TEMP_FIELD.search(line)
            temp = _TEMP.fullmatch(field['v'].strip()) if field else None
            temp_start = field.start('v') + len(field['v']) - len(field['v'].lstrip()) if field else None
            operation = line[:field.start()] if field else line
            operation = operation.rstrip().rstrip('(').rstrip().rstrip('.\u3002').rstrip()
            if not temp:
                matches = list(_TEMP.finditer(operation))
                if len(matches) == 1:
                    temp = matches[0];temp_start = temp.start()
            if not temp:
                reasons.append('STORAGE_TEMPERATURE_RELATION_UNPROVEN')
            if len(mediums) != 1:
                reasons.append('MULTIPLE_MEDIUM_REFERENCES')
            # Preserve restrictions after metadata; the whole original record matters.
            if _CONDITION.search(line):
                reasons.append('CONDITIONAL_OPERATION')
            if _NEG_STORAGE.search(line) or _NEG_RECORD.search(line):
                reasons.append('NEGATED_OR_REJECTED_STORAGE')
            suffix = line[field.end():].lstrip(' ,\uff0c)') if field else ''
            if _MULTI_ACTION.search(operation) or _MULTI_ACTION.search(suffix.rstrip().rstrip('.\u3002')):
                reasons.append('MULTIPLE_OPERATION_CLAUSES')
            temperatures = list(_TEMP.finditer(line))
            if len(temperatures) > 1 or (temp and re.search(r'\b(?:room\s+temperature|RT)\b|\u5ba4\u6e29', operation, re.I)):
                reasons.append('MULTIPLE_OR_CONFLICTING_TEMPERATURE_REFERENCES')
            relation = _relation(operation, mediums[0]) if len(mediums) == 1 else None
            if not relation:
                reasons.append('SAMPLE_MEDIUM_STORAGE_ARGUMENT_UNPROVEN')
            elif not _SAMPLE_OBJECT.search(relation['sample_text']) or _FOREIGN_OBJECT.search(relation['sample_text']):
                reasons.append('TISSUE_SAMPLE_OBJECT_UNPROVEN')
            if temp and float(temp['n']) != rule['avoid_temperature_C']:
                status = 'CONDITION_NOT_MATCHED' if not reasons else 'REVIEW_REQUIRED'
            else:
                status = 'POTENTIAL_AUTHOR_GUIDANCE_CONFLICT' if not reasons else 'REVIEW_REQUIRED'
            findings = {'rule_id': rule['id'], 'status': status, 'record_span': _span(protocol, start, end),
                        'medium_spans': [_span(protocol, start + m.start(), start + m.end()) for m in mediums],
                        'temperature_span': _span(protocol, start + temp_start, start + temp_start + len(temp.group())) if temp and temp_start is not None else None,
                        'method_declaration': deepcopy(declaration), 'relation_proof': relation,
                        'relation_guards': sorted(set(reasons)), 'source_proof': deepcopy(proof),
                        'source_scope_guards': ['NON_GEL_SOURCE_SCOPE_NOT_FULLY_ESTABLISHED', 'LABEL_SPECIFIC_SHELF_LIFE_UNPROVEN'],
                        'interpretation': 'Author-guidance warning for the bound local operation; not guaranteed crystallization or experimental failure',
                        'changes_requirement_states': False}
            result['findings'].append(findings)
    result['potential_conflict_count'] = sum(f['status'] == 'POTENTIAL_AUTHOR_GUIDANCE_CONFLICT' for f in result['findings'])
    result['local_risk_count'] = sum(f.get('typed_relation') == 'LOCAL_POTENTIAL_RISK' for f in result['findings'])
    result['author_recipe_nonconformance_count'] = sum(f.get('typed_relation') == 'AUTHOR_RECIPE_EXPLICIT_PROHIBITION' for f in result['findings'])
    result['absence_of_warning_interpretation'] = 'NO_WARNING_IS_NOT_SCIENTIFIC_COMPLIANCE_OR_SUCCESS'
    result['review_required_count'] = sum(f['status'] == 'REVIEW_REQUIRED' for f in result['findings'])
    return result
