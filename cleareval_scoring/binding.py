"""Pilot argument binding refinement; preserves raw spans and frozen baseline.

Distinguish principal contact from removal purpose. Mask material names and
embedded alphanumeric tokens for numeric parsing without changing offsets.
"""
from copy import deepcopy
import re

from .operations import TIME, TEMP, parameter, phase


def bound_parameter(text, name, material_spans):
    masked = list(text)
    for span in material_spans:
        masked[span['start']:span['end']] = ' ' * (span['end'] - span['start'])
    # Unit-like suffixes inside identifiers (e.g. X7D) are not durations.
    regex = TIME if name == 'duration' else TEMP
    for hit in regex.finditer(text):
        if hit.start() and re.match(r'[A-Za-z0-9_]', text[hit.start() - 1]):
            masked[hit.start():hit.end()] = ' ' * (hit.end() - hit.start())
    result = parameter(''.join(masked), name)
    if result.get('evidence'):
        evidence = result['evidence']
        evidence['text'] = text[evidence['start']:evidence['end']]
    return result


def bind_operation(node):
    op = deepcopy(node['typed'])
    text = node['text']
    op['binding_changes'] = []
    for name in ('duration', 'temperature'):
        value = bound_parameter(text, name, op['material_spans'])
        if value != op[name]:
            op['binding_changes'].append(name + '_entity_boundary')
        op[name] = value
    leading_contact = re.search(r'^\s*(?:incubat\w*|immerse\w*)\b', text, re.I)
    removal_purpose = re.search(r'\bto (?:wash|remove)\b|洗去|去除', text, re.I)
    destination = re.search(r'\b(?:transfer|transition)\b.*\binto\b|转入', text, re.I)
    op['removal_goal'] = text[removal_purpose.start():] if removal_purpose else None
    if op['primary_materials'] and op['action'] not in ('store', 'mount') and (
        leading_contact and removal_purpose or destination
    ):
        op['action'] = 'incubate'
        op['action_origin'] = 'principal_contact_separated_from_removal_goal'
        op['phase'] = phase(text, node.get('heading', ''), set(op['primary_materials']), op['action'])
        op['binding_changes'].append('principal_contact_and_phase')
    return op
