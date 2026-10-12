"""Accept an explicit Chinese selected-method header alongside the saved judgment.

The method must already be the single selected, source-bound model mention.
This candidate does not infer a method from reagents or choose the highest score.
"""
import re
import cce_scoped_midpoint_scorer_v1 as b
VERSION='selected-method-Chinese-header-v1.1'


def chinese_selection_header(context,name):
    first=context.splitlines()[0]
    before,separator,after=first.partition('：')
    if not separator:before,separator,after=first.partition(':')
    if not separator or name not in after:return False
    if not re.search(r'(?:所选(?:用)?|选定|已选).*(?:方法|方案)',before):return False
    if re.search(r'未选|不选|非所选|备选|候选|可选|示例|例如',before):return False
    # Check the method's value segment rather than an unrelated label alternative.
    pos=after.index(name)
    local=after[max(0,pos-12):]
    if re.search(r'不采用|不选择|未使用|不用|备选|可选|或|\bor\b|\bnot\b|\balternative\b',local,re.I):return False
    return True


def selected_method(conversion,doc):
    old=conversion['legacy_projection']['extraction']['method_name']
    if old is not None:return {'method_name':old,'changed':False,'basis':'existing_projection'}
    mentions=[m for m in conversion['source_audit']['resolved']['method_mentions'] if m['usage']=='selected']
    names={m['name']['quote'] for m in mentions}
    if len(names)!=1:return {'method_name':None,'changed':False,'basis':'no_unique_selected_method'}
    name=next(iter(names));evidence=[]
    for mention in mentions:
        span=mention['name'];b.verify_span(doc['text'],span)
        if (mention['name_binding']['atomicity']['projection_eligible_provisional'] and
                chinese_selection_header(span['context'],name)):
            evidence.append({'model_mention_id':mention['id'],'raw_usage':mention['usage'],
                'name_span':span,'selection_context':mention['supporting_evidence']})
    return {'method_name':name if evidence else None,'changed':bool(evidence),'version':VERSION,
        'basis':'single_model_selected_method_with_explicit_Chinese_header','evidence':evidence,
        'source_text_and_saved_judgment_unchanged':True}
