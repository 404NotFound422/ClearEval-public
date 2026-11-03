"""Bind conditions to a section or a single execution event, preserving source text."""
import re

NUMBER = r'\d+(?:\.\d+)?'
TIME = re.compile(r'(?<![\d.])(' + NUMBER + r')(?:\s*[-–—~至]\s*(' + NUMBER + r'))?\s*(hours?|hrs?|h|minutes?|mins?|min|days?|d|seconds?|secs?|s)\b', re.I)


def normalized(text):
    for old, new in [('小时', ' hours'), ('分钟', ' minutes'), ('秒', ' seconds'), ('天', ' days')]:
        text = text.replace(old, new)
    return text


def explicit_count(text,allow_sequence=False):
    """Total count of a directly declared repeated operation, not repeat-additions."""
    if re.search(r'\brepeat|重复|换液', text, re.I):
        return None
    for word,value in [('one',1),('two',2),('three',3),('four',4),('five',5),('six',6),('seven',7),('eight',8),('nine',9),('ten',10)]:
        text=re.sub(r'\b'+word+r'\b(?=\s+(?:times|changes|washes)\b)',str(value),text,flags=re.I)
    for pattern in [r'(?<![\d.])(\d+)\s*[×x]\s*(?=\d)', r'(?<![\d.])(\d+)\s*(?:times\b|changes\b|washes\b|次)']:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m[1])
    if re.search(r'\btwice\b', text, re.I):
        return 2
    if re.search(r'\bonce\b', text, re.I):
        return 1
    # Explicit percentage sequence with "each step" supplies an arithmetic count
    # even where the frozen structural parser kept it as a single written group.
    if allow_sequence and re.search(r'each\s+step|per\s+step|每步',text,re.I):
        sequence=re.search(r'(?:'+NUMBER+r'\s*%\s*(?:[,/、，]\s*(?:and\s*)?|and\s+)){1,}'+NUMBER+r'\s*%',text,re.I)
        if sequence:return len(re.findall(NUMBER,sequence[0]))
    return None


def each_duration(text):
    hits = []
    for match in TIME.finditer(normalized(text)):
        t = normalized(text)
        before, after = t[max(0, match.start()-30):match.start()], t[match.end():match.end()+24]
        if re.search(r'(?:each(?:\s+(?:step|time|wash|incubation))?(?:\s+for)?|per\s+step|每次|每步)\s*$', before, re.I) or re.match(r'\s*(?:each\b|per\s+(?:step|wash)\b|/步)', after, re.I):
            factor = 1440 if match[3].lower().startswith('d') else 60 if match[3].lower().startswith('h') else 1/60 if match[3].lower().startswith('s') else 1
            hits.append(dict(value=[float(match[1])*factor, float(match[2] or match[1])*factor], kind='interval', literal=match[0]))
    return hits


def duration(text, step, parse, legacy):
    original = step.get('original_text', text)
    per = each_duration(text)
    if not per:
        return parse(text, 'duration', legacy)
    values = [p['value'] for p in per]
    if any(v != values[0] for v in values):
        return dict(value=None, kind='conflict', evidence_text=text, reason='conflicting_per_event_durations')
    count = len(step['gradient_values']) if 'gradient_index' in step else explicit_count(original,allow_sequence=True)
    result = dict(value=values[0], kind='interval', evidence_text=text, ownership='per_execution_event', event_count=count)
    tagged = re.search(r'(?:Time|时间)\s*[:：]\s*([^;)）]+)', normalized(text), re.I)
    if not tagged:
        return result
    label = legacy(tagged[1], 'duration')
    if label.get('value') is None or not isinstance(label['value'], list):
        return result
    # A label explicitly marked each/per belongs to the same event.
    label_is_each = bool(each_duration(tagged[1]))
    explicit_total = bool(re.search(r'\btotal\b|总计|累计|合计|总时', tagged[1], re.I))
    if label_is_each or (label['value'] == result['value'] and not explicit_total):
        return result
    if count:
        expected = [v*count for v in result['value']]
        result['total_minutes'] = label['value']
        if all(abs(a-b)<1e-7 for a,b in zip(expected, label['value'])):
            result['total_consistency'] = 'PASS'
            return result
        return dict(value=None, kind='conflict', reason='per_event_count_total_disagree', assertions=[result, label], evidence_text=text)
    # Do not guess how many events a summary duration includes.
    return dict(value=None, kind='unresolved_total', reason='total_count_not_explicit', evidence_text=text)


def agitation_text(step, agitation):
    local = step['text']
    parsed = agitation(local)
    if parsed['positive'] or parsed['negative']:
        return local, 'operation'
    heading = step.get('heading', '')
    # Unresolved exceptions/conditional headings do not apply to every child.
    if re.search(r'\bexcept\b|\bunless\b|\bif\b|除.*外|若|如果', heading, re.I):
        return local, 'conditional_section_unresolved'
    hp = agitation(heading)
    if hp['positive'] or hp['negative']:
        return heading, 'numbered_section'
    return local, 'not_stated_in_operation_or_section'
