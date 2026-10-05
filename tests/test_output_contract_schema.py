"""Static schema declarations and production source-only extraction controls.
Full JSON Schema validation is optional; no dependency is installed by this test.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

from experiments.construct_validity.compact_grounding import build_record_catalog, expand_record_refs

SCHEMA_PATH=Path(__file__).resolve().parents[1]/'prompts/oeq_record_output.schema.json'


def representative_payload():
    text='1. Move generic object\n2. Leave generic object\nRI generic_medium = 1.51\n'
    def support(value):
        if value is None:
            return dict(kind='MISSING',raw_value=None,spans=[])
        start=text.index(value)
        return dict(kind='EXPLICIT',raw_value=value,transform='IDENTITY',
                    spans=[dict(start=start,end=start+len(value),quote=value)])
    catalog=build_record_catalog(text)
    ri=dict(branch='main',solution='generic_medium',value_text='1.51',
            quote='RI generic_medium = 1.51',assertion={'polarity':'AFFIRMED'},
            field_support=dict(solution=support('generic_medium'),value_text=support('1.51')))
    payload=dict(extraction=dict(schema_version='extraction-record-refs-v1',
        protocol_sha256=catalog['protocol_sha256'],branches=[dict(id='main',mode='SERIAL',sample_id='synthetic',spans=[])],
        labels=[],steps=[dict(id='S1',record_id=catalog['records'][0]['record_id'],branch='main')],
        ri=[ri],limitations='Synthetic only.'),assessment=dict(schema_version='judgment-grounding-v2',
        requirements=[dict(id='R1',status='UNRESOLVED',basis='MISSING',evidence_ids=[],quotes=[],
                           reason='Synthetic unknown.',evidence_checks=[])],limitations='No scientific assertion.'),objectives={})
    return text,payload


class OutputContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=json.loads(SCHEMA_PATH.read_text(encoding='utf-8-sig'))
        cls.defs=cls.schema['$defs']

    def test_RI_only_uses_required_original_offset_spans(self):
        for field in ['solution','value_text']:
            self.assertEqual(self.defs['riSupports']['properties'][field],{'$ref':'#/$defs/strictRIFieldSupport'})
        strict=self.defs['strictRIFieldSupport']
        self.assertEqual(strict['properties']['spans']['items'],{'$ref':'#/$defs/originalOffsetSpan'})
        required=set(self.defs['originalOffsetSpan']['required'])
        self.assertEqual(required,{'start','end','quote'})
        self.assertFalse(required.issubset({'quote'}))
        self.assertFalse(self.defs['originalOffsetSpan']['additionalProperties'])

    def test_defined_EXPLICIT_supports_require_raw_value_and_IDENTITY_transform(self):
        for name in ['fieldSupport','strictRIFieldSupport']:
            branches=self.defs[name]['anyOf']
            explicit=next(branch for branch in branches if branch['properties']['kind'].get('const')=='EXPLICIT')
            self.assertEqual(set(explicit['required']),{'raw_value','transform'})
            self.assertEqual(explicit['properties']['raw_value'],{'type':'string','minLength':1})
            self.assertEqual(explicit['properties']['transform'],{'const':'IDENTITY'})
            old_support=dict(kind='EXPLICIT',spans=[{'quote':'generic_medium'}])
            self.assertEqual(set(explicit['required'])-set(old_support),{'raw_value','transform'})
            others=next(branch for branch in branches if 'enum' in branch['properties']['kind'])
            self.assertNotIn('EXPLICIT',others['properties']['kind']['enum'])

    def test_generic_branch_method_and_label_span_forms_remain_unchanged(self):
        self.assertEqual(set(self.defs['originalSpan']['anyOf'][0]['required']),{'quote'})
        self.assertEqual(self.defs['branch']['properties']['spans']['items'],{'$ref':'#/$defs/originalSpan'})
        self.assertEqual(self.defs['methodDeclaration']['properties']['span'],{'$ref':'#/$defs/originalSpan'})
        self.assertEqual(self.defs['labelSupports']['properties']['probe'],{'$ref':'#/$defs/fieldSupport'})
        self.assertEqual(self.defs['fieldSupport']['properties']['spans']['items'],{'$ref':'#/$defs/originalSpan'})

    def test_canonical_RI_source_payload_passes_core_and_preserves_coverage_gap(self):
        text,payload=representative_payload()
        before=deepcopy(payload)
        result=expand_record_refs(payload['extraction'],text)
        self.assertEqual(payload,before)
        self.assertTrue(result['validated']['scoring_eligible'])
        self.assertEqual(result['expanded']['ri'][0]['value_text'],'1.51')
        self.assertTrue(result['coverage']['omitted_record_ids'])
        self.assertFalse(result['coverage']['extraction_completeness_certified'])
        self.assertFalse(result['coverage']['scientific_steps_certified'])

    def test_MISSING_nullable_RI_remains_supported(self):
        text,payload=representative_payload()
        row=payload['extraction']['ri'][0]
        row['value_text']=None
        row['field_support']['value_text']=dict(kind='MISSING',raw_value=None,spans=[])
        result=expand_record_refs(payload['extraction'],text)
        self.assertIsNone(result['expanded']['ri'][0]['value_text'])
        self.assertEqual(self.defs['ri']['properties']['value_text']['type'],['string','null'])
        others=self.defs['strictRIFieldSupport']['anyOf'][1]
        self.assertIn('MISSING',others['properties']['kind']['enum'])
        self.assertNotIn('raw_value',others.get('required',[]))

    def test_raw_quote_only_and_missing_raw_value_have_distinct_core_errors(self):
        text,payload=representative_payload()
        quote_only=deepcopy(payload['extraction'])
        support=quote_only['ri'][0]['field_support']['solution']
        support['spans']=[{'quote':support['spans'][0]['quote']}]
        with self.assertRaisesRegex(ValueError,'Span needs start, end and quote'):
            expand_record_refs(quote_only,text)
        missing_raw=deepcopy(payload['extraction'])
        del missing_raw['ri'][0]['field_support']['solution']['raw_value']
        with self.assertRaisesRegex(ValueError,'Field value has no bound original text'):
            expand_record_refs(missing_raw,text)

    @unittest.skipUnless(importlib.util.find_spec('jsonschema') is not None,
                         'jsonschema unavailable: static declarations/core checks are not formal schema validation')
    def test_formal_schema_if_existing_jsonschema_is_available(self):
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(self.schema)
        validator=Draft202012Validator(self.schema)
        _,payload=representative_payload()
        validator.validate(payload)
        for missing in ['raw_value','transform']:
            changed=deepcopy(payload)
            del changed['extraction']['ri'][0]['field_support']['solution'][missing]
            self.assertTrue(list(validator.iter_errors(changed)))
        changed=deepcopy(payload)
        changed['extraction']['ri'][0]['field_support']['solution']['spans']=[{'quote':'generic_medium'}]
        self.assertTrue(list(validator.iter_errors(changed)))
        changed=deepcopy(payload)
        changed['extraction']['ri'][0]['value_text']=None
        changed['extraction']['ri'][0]['field_support']['value_text']=dict(kind='MISSING',raw_value=None,spans=[])
        validator.validate(changed)


if __name__=='__main__':
    unittest.main()
