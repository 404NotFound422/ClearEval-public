"""Post-hoc target-catalog data access, without new aliases or scoring arithmetic.

Only authored recommendation targets may expose slash-separated alternatives.
Actual entity names are not split. Tissue evidence retains row scope and uses
one task-selected scope; different scopes or conflicting rows remain unresolved.
"""
from __future__ import annotations
import contextlib, copy, re
VERSION='target-catalog-role-fix-v1-posthoc'
SCOPE_KEYS={'major_category':'大类','subcategory':'亚类','structure_or_cell_subtype':'结构/细胞类型'}
MARKER_FIELDS=['推荐标志物 1','推荐标志物 2']

def target_options(target):
    name=target.get('marker_name')
    role=target.get('marker_slot')
    if not isinstance(name,str):return []
    eligible=(role in ('recommended_marker_1','recommended_marker_2') and
        isinstance(target.get('source_tissue_xlsx_row'),int) and bool(target.get('query_path')))
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
    values=children if split else [name]
    return [{**copy.deepcopy(target),'marker_name':value,
        'authored_target_parent':{'marker_name':name,'target_index':target.get('target_index'),
          'source_tissue_xlsx_row':target.get('source_tissue_xlsx_row'),'query_path':target.get('query_path'),
          'marker_slot':role},'authored_option_index':i,'option_split_applied':bool(split)} for i,value in enumerate(values)]

def expanded_targets(targets):return [c for t in targets for c in target_options(t)]

def marker_scope_lookup(runner,marker,fluor,targets):
    query=runner._expand_marker_candidates(marker)
    candidates=[]
    for index,row in enumerate(runner.TISSUE_KB):
        names=[row.get(k) for k in MARKER_FIELDS if row.get(k)]
        matched=[name for name in names if query & runner._expand_marker_candidates(name)]
        if matched:candidates.append({'row_index':index,'row':row,'matching_authored_names':matched})
    matched_targets=[t for t in expanded_targets(targets) if query & runner._expand_marker_candidates(t['marker_name'])]
    scoped=[r for r in candidates if any(all(t.get(a) and t[a]==r['row'].get(b) for a,b in SCOPE_KEYS.items()) for t in matched_targets)]
    selected=scoped if matched_targets else candidates
    column=runner._map_fluor_to_tissue_col(fluor)
    scopes={tuple(r['row'].get(k) for k in SCOPE_KEYS.values()) for r in selected}
    values=[r['row'].get(column) for r in selected] if column else []
    known={x for x in values if type(x) in (int,float) and x in (0,1)}
    if not column:status='unmapped_authored_fluor_column';value=None
    elif not selected:status='no_matching_authored_row_in_task_scope';value=None
    elif len(scopes)!=1:status='multiple_authored_scopes_unresolved';value=None
    elif len(known)>1:status='conflicting_authored_values_unresolved';value=None
    elif known:status='same_scope_authored_consistent_value';value=bool(next(iter(known)))
    else:status='authored_cells_unknown';value=None
    return {'marker':marker,'fluorophore':fluor,'status':status,'value':value,'column':column,
      'matching_target_options':matched_targets,'candidate_rows':[{'row_index':r['row_index'],'matching_authored_names':r['matching_authored_names'],
        'scope':{k:r['row'].get(k) for k in SCOPE_KEYS.values()},'cell_value':r['row'].get(column) if column else None} for r in candidates],
      'selected_row_indices':[r['row_index'] for r in selected],
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
