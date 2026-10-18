"""Bounded source-literal consistency repair. No model, source recipe or question IDs.

Runs AFTER legacy extraction verification; preserves the old assertion in audit.
Only explicit section roles, terminal nominal purpose, parenthetical condition,
and separately checked replacement count are recognized. Unknown stays unknown.
"""
from copy import deepcopy
import re
VERSION='literal-consistency-v2-unestablished-scope'
CONDITION=re.compile(r'必要时|如有必要|视需要|\bif\s+(?:needed|required|necessary|desired)\b',re.I)
# These literal markers can only demote, never establish that a trigger is true.
# A marker inside quoted prose/negation may therefore conservatively abstain.
UNESTABLISHED_SCOPE=re.compile(
    r'\b(?:if|unless|provided\s+that|in\s+case|optional(?:ly)?|'
    r'as\s+(?:needed|required|necessary|desired))\b|'
    r'必要时|如有必要|视需要|按需|可选|如果|若|仅当|待确认', re.I)

RATIONALE=re.compile(r'^(?:justification|rationale|explanation|理由|选择理由|原理说明)\s*[:：]?$',re.I)
EVENT=r'(?:oxidation|degradation|damage|loss|decay|corrosion|quenching)'
PURPOSE=re.compile(r'to\s+prevent\s+(?:[A-Za-z-]+\s+){0,2}'+EVENT+r'(?:\s+and\s+(?:[A-Za-z-]+\s+){0,2}'+EVENT+r')?',re.I)

def _span(protocol, text, parent):
    start=protocol.find(text,parent['start'],parent['end'])
    if start<0:raise ValueError('Consistency clause is not a source substring')
    return dict(start=start,end=start+len(text),quote=text)

def _assert(row, polarity, reason, directive=None, restrictions=()):
    a=deepcopy(row.get('assertion',{}));a.update(polarity=polarity,scope='MAIN_DIRECTIVE' if directive else 'UNRESOLVED',scope_policy=VERSION,scope_reason=reason,directive_span=directive,restriction_spans=list(restrictions),parameter_bindings={})
    row['assertion']=a

def repair_record(row,protocol):
    """Return literal rows; no unchanged row is rewritten, including metadata."""
    from experiments.construct_validity.fidelity import (_PROCEDURE_HEAD,_DIRECTIVE,
        _ASSERTION_NEGATION,_SCOPE_COMPLEX,_MAIN_CLAUSE_BOUNDARY,
        _nominal_main_annotations,_sole_main_action)
    original=deepcopy(row);r=deepcopy(row);parent=r['source']
    if protocol[parent['start']:parent['end']]!=r['raw_text']:
        raise ValueError('Consistency input raw text does not match source')
    audit=dict(version=VERSION,original_assertion=deepcopy(r.get('assertion')),source_span=deepcopy(parent))
    heading=re.sub(r'[*#_]', '', r.get('phase','')).strip()
    if RATIONALE.fullmatch(heading):
        r['statement_mode']='CONTEXT_OR_CAPABILITY';audit['rule']='EXPLICIT_RATIONALE_SECTION';r['representation_consistency']=audit
        return [r]
    t=r['operation'];conditionals=list(re.finditer(r'\([^()]*\)|（[^（）]*）',t))
    conditionals=[m for m in conditionals if CONDITION.match(m.group()[1:-1].strip())]
    if conditionals:
        # Do not promote fused mixed-scope text to an asserted treatment. Keep
        # exact component spans; main is not silently assigned the group's time.
        audit['rule']='EXPLICIT_PARENTHETICAL_CONDITION';audit['scoped_components']=[]
        for m in conditionals:
            audit['scoped_components'].append({'polarity':'CONDITIONAL','span':_span(protocol,m.group()[1:-1],parent)})
        remainder=t
        for m in reversed(conditionals):remainder=remainder[:m.start()]+remainder[m.end():]
        audit['main_text']=remainder
        cursor=0;segments=[]
        for m in conditionals:
            if t[cursor:m.start()].strip(' .。'):
                segments.append(_span(protocol,t[cursor:m.start()],parent))
            cursor=m.end()
        if t[cursor:].strip(' .。'):segments.append(_span(protocol,t[cursor:],parent))
        audit['main_spans']=segments
        audit['main_polarity']='UNRESOLVED' if _ASSERTION_NEGATION.search(remainder) or CONDITION.search(remainder) else r.get('assertion',{}).get('polarity','UNKNOWN')
        audit['main_status']='RETAINED_FOR_REVIEW_NOT_WHOLE_ROW_AFFIRMED'
        _assert(r,'UNKNOWN','MIXED_SCOPE_COMPONENTS_RETAINED',restrictions=[x['span'] for x in audit['scoped_components']])
        r['representation_consistency']=audit;return [r]
    # No execution-context proof is accepted here. Preserve existing conditional
    # and prohibited labels; never promote a condition based on world knowledge.
    body_markers=list(UNESTABLISHED_SCOPE.finditer(t))
    heading_markers=list(UNESTABLISHED_SCOPE.finditer(r.get('phase','')))
    if (body_markers or heading_markers) and r.get('assertion',{}).get('polarity') not in {'CONDITIONAL','NEGATED'}:
        audit['rule']='UNESTABLISHED_LITERAL_OPTIONAL_OR_CONDITIONAL_SCOPE'
        audit['trigger_status']='NOT_ESTABLISHED_NO_CONTEXT_INFERENCE'
        spans=[_span(protocol,m.group(),parent) for m in body_markers]
        audit['body_marker_spans']=spans
        # Phase is retained verbatim, not treated as a reconstructed source span.
        # from_catalog supplies its literal heading; direct callers may not.
        audit['heading_text']=r.get('phase','')
        audit['heading_markers']=[dict(start=m.start(),end=m.end(),quote=m.group()) for m in heading_markers]
        _assert(r,'UNKNOWN',audit['rule'],restrictions=spans)
        r['representation_consistency']=audit
        return [r]
    # A terminal prevention purpose is a nominal event, not a negated action.
    # Main must be a single bounded imperative and the whole purpose must match.
    if r.get('assertion',{}).get('polarity')=='UNKNOWN':
        core=t.rstrip().rstrip('.');m=re.search(r'\bto\s+prevent\b',core,re.I)
        if m:
            main=core[:m.start()].rstrip(' ,');purpose=core[m.start():]
            nominal=PURPOSE.fullmatch(purpose)
            # Gerund acceptance is ONLY terminal event head "quenching";
            # other action words/conditional clauses still fail closed.
            safe_purpose=not re.search(r'\b(?:if|unless|after|before|not|no|without|use|add|remove|store|incubate|stop|start|do|[a-z]+ing)\b', re.sub(r'\bquenching\b','',purpose,flags=re.I),re.I)
            if (nominal and safe_purpose and (_PROCEDURE_HEAD.match(main) or _DIRECTIVE.match(main))
                and not _ASSERTION_NEGATION.search(main) and not _SCOPE_COMPLEX.search(main)
                and not _MAIN_CLAUSE_BOUNDARY.search(main) and _nominal_main_annotations(main)
                and _sole_main_action(main) and not re.search(r'[.:;!?]',re.sub(r'(?<=\d)\.(?=\d)','',main))):
                audit['rule']='TERMINAL_NOMINAL_PREVENTION_PURPOSE'
                _assert(r,'AFFIRMED',audit['rule'],_span(protocol,main,parent),[_span(protocol,purpose,parent)])
                r['representation_consistency']=audit
    return [r] if r!=original else [original]

def explicit_replacement_count(row):
    """One initial treatment plus a literal unconditional parenthetical replacement.

    A replacement count is not total repetitions. No quantity/recipe inferred.
    Conflicting explicit total remains unresolved, not guessed.
    """
    t=row['operation'];m=re.search(r'\(\s*replace\s+(once|twice|\d+\s+times)\s*\)',t,re.I)
    if not m:return None
    count={'once':1,'twice':2}.get(m[1].lower())
    if count is None:count=int(m[1].split()[0])
    if count<1 or count>100:return None
    # Require exactly one independently stated treatment; avoid coordinated acts.
    main=t[:m.start()].strip()
    if not re.match(r'^(?:delipidation|incubation|incubate|wash|rinse|soak|dehydration)\s+(?:in|with)\s+\S',main,re.I):return None
    if re.search(r'\b(?:and|or|then|if|unless|optional|not|never|without)\b|[;；]',main,re.I):return None
    if t[m.end():].strip(' .'):return None
    # Multiplier is corroboration only; incompatible count cannot be asserted.
    explicit_totals=re.findall(r'\b(\d+)\s+(?:times|washes)\b',main,re.I)
    if re.search(r'\b(?:twice|thrice)\b',main,re.I) or explicit_totals:
        return {'status':'CONFLICTING_OR_MULTIPLE_COUNT_SCOPES','count':None,'quote':m.group()}
    multipliers=re.findall(r'\b(\d+)\s*[×x]\s*\d',row['raw_text'],re.I)
    if multipliers and any(int(n)!=count+1 for n in multipliers):return {'status':'CONFLICTING_EXPLICIT_COUNT','count':None,'quote':m.group()}
    return {'status':'EXPLICIT_REPLACEMENT_PLUS_INITIAL','count':count+1,'quote':m.group()}
