"""Post-hoc target-catalog data access, without new aliases or scoring arithmetic.

Only authored recommendation targets may expose slash-separated alternatives.
Actual entity names are not split. Tissue evidence retains row scope. Each
applicable scope must independently support the same value; missing or
conflicting scope-specific evidence remains unresolved.
"""
from __future__ import annotations
import contextlib, copy, re
VERSION='target-catalog-role-fix-v2-posthoc'
SCOPE_KEYS={'major_category':'大类','subcategory':'亚类','structure_or_cell_subtype':'结构/细胞类型'}
MARKER_FIELDS=['推荐标志物 1','推荐标志物 2']

def recommendation_names(name,eligible):
    if not isinstance(name,str):return [],False
    # Delimiters inside parenthetical labels and numeric wavelengths are not
    # alternate biological recommendation items.
    children=[];start=0;depth=0
    for match in re.finditer(r'[()（）]|\s+/\s+',name):
        token=match.group()
        if token in ('(','（'):depth+=1
        elif token in (')','）'):depth=max(0,depth-1)
        elif depth==0:
            children.append(name[start:match.start()].strip());start=match.end()
    children.append(name[start:].strip())
    split=eligible and len(children)>1 and all(re.search(r'[A-Za-z\u0370-\u03ff\u4e00-\u9fff]',x) for x in children)
    return (children if split else [name]),bool(split)

def target_options(target):
    name=target.get('marker_name');role=target.get('marker_slot')
    eligible=(role in ('recommended_marker_1','recommended_marker_2') and
        isinstance(target.get('source_tissue_xlsx_row'),int) and bool(target.get('query_path')))
    values,split=recommendation_names(name,eligible)
    return [{**copy.deepcopy(target),'marker_name':value,
        'authored_target_parent':{'marker_name':name,'target_index':target.get('target_index'),
          'source_tissue_xlsx_row':target.get('source_tissue_xlsx_row'),'query_path':target.get('query_path'),
          'marker_slot':role},'authored_option_index':i,'option_split_applied':bool(split)} for i,value in enumerate(values)]

def expanded_targets(targets):return [c for t in targets for c in target_options(t)]

def marker_scope_lookup(runner,marker,fluor,targets):
    query=runner._expand_marker_candidates(marker)
    candidates=[]
    for index,row in enumerate(runner.TISSUE_KB):
        matches=[]
        for field in MARKER_FIELDS:
            name=row.get(field);options,split=recommendation_names(name,True)
            for option in options:
                if query & runner._expand_marker_candidates(option):matches.append({'field':field,'authored_name':name,'option':option,'option_split_applied':split})
        if matches:candidates.append({'row_index':index,'row':row,'matching_authored_names':matches})
    matched_targets=[t for t in expanded_targets(targets) if query & runner._expand_marker_candidates(t['marker_name'])]
    scoped=[r for r in candidates if any(all(t.get(a) and t[a]==r['row'].get(b) for a,b in SCOPE_KEYS.items()) for t in matched_targets)]
    selected=scoped if matched_targets else candidates
    column=runner._map_fluor_to_tissue_col(fluor)
    scopes={tuple(r['row'].get(k) for k in SCOPE_KEYS.values()) for r in selected}
    per_scope=[]
    for scope in sorted(scopes):
        scoped_rows=[r for r in selected if tuple(r['row'].get(k) for k in SCOPE_KEYS.values())==scope]
        values=[r['row'].get(column) for r in scoped_rows] if column else []
        known={x for x in values if type(x) in (int,float) and x in (0,1)}
        state='conflicting_authored_values' if len(known)>1 else 'authored_unknown' if not known else 'consistent_authored_value'
        per_scope.append({'scope':dict(zip(SCOPE_KEYS.values(),scope)),'row_indices':[r['row_index'] for r in scoped_rows],
          'all_cell_values':values,'state':state,'value':next(iter(known)) if len(known)==1 else None})
    values={r['value'] for r in per_scope if r['value'] is not None}
    if not column:status='unmapped_authored_fluor_column';value=None
    elif not selected:status='no_matching_authored_row_in_task_scope';value=None
    elif any(r['state']=='conflicting_authored_values' for r in per_scope):status='conflicting_authored_values_unresolved';value=None
    elif any(r['value'] is None for r in per_scope):status='applicable_scope_unknown';value=None
    elif len(values)>1:status='applicable_scopes_disagree';value=None
    else:status='all_applicable_scopes_have_same_authored_value';value=bool(next(iter(values)))
    return {'marker':marker,'fluorophore':fluor,'status':status,'value':value,'column':column,
      'matching_target_options':matched_targets,'candidate_rows':[{'row_index':r['row_index'],'matching_authored_names':r['matching_authored_names'],
        'scope':{k:r['row'].get(k) for k in SCOPE_KEYS.values()},'cell_value':r['row'].get(column) if column else None} for r in candidates],
      'selected_row_indices':[r['row_index'] for r in selected],'per_scope_evidence':per_scope,
      'row_selection_uses_scores':False,'different_scopes_merged':False,'new_alias_or_KB_value':False}

@contextlib.contextmanager
def using_target_catalog_fix(runner,targets):
    """Temporarily install two data-access helpers in one synchronous scorer."""
    oldmatch=runner._match_marker_to_targets;oldcompat=runner._get_marker_fluor_compat
    trace={'version':VERSION,'target_options':expanded_targets(targets),'target_match_calls':[],'compatibility_calls':[]}
    def match(marker,query_targets,fluor_name=None):
        before=oldmatch(marker,query_targets,fluor_name=fluor_name)
        options=expanded_targets(query_targets)
        after=oldmatch(marker,options,fluor_name=fluor_name)
        trace['target_match_calls'].append({'marker':marker,'fluorophore':fluor_name,'original_match':before,'candidate_match':after,
          'authored_targets':copy.deepcopy(query_targets),'option_targets':options})
        return after
    def compat(marker,fluor):
        row=marker_scope_lookup(runner,marker,fluor,targets)
        row['original_last_row_lookup']=oldcompat(marker,fluor)
        trace['compatibility_calls'].append(row);return row['value']
    runner._match_marker_to_targets=match;runner._get_marker_fluor_compat=compat
    try:yield trace
    finally:runner._match_marker_to_targets=oldmatch;runner._get_marker_fluor_compat=oldcompat

def score_label_occurrences(original,projection,runner,quantitative,demand,targets):
    with using_target_catalog_fix(runner,targets) as trace:
        result=original(projection,runner,quantitative,demand,targets)
    result['target_catalog_role_fix']=trace
    return result
