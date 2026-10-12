"""Locate intact diagnostic blocks inside one failed archived JSON preview.

This does not repair a score, reconstruct an extraction, or calculate Cor/Eff.
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT/'dataset/Q+AR/result/evaluation_results_gemini-3-flash_1-shot.json'
OUT = ROOT/'artifacts/cce_validation/inventory/partial_score_q29'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    original_bytes = SOURCE.read_bytes()
    rows = json.loads(original_bytes.decode('utf-8-sig'))
    record = next(r for r in rows if int(r['question_id']) == 29)
    evaluation = record['evaluation']
    preview = evaluation['_raw_content_preview']
    decoder = json.JSONDecoder()
    blocks, fields = [], []
    for name in ['completeness', 'correctness']:
        matches = list(re.finditer(r'"'+name+r'"\s*:\s*', preview))
        assert len(matches) == 1, 'Named diagnostic block is not unique'
        start = matches[0].end()
        obj, end = decoder.raw_decode(preview, start)
        assert isinstance(obj, dict)
        raw_block = preview[start:end]
        # File-level offsets refer to the JSON-escaped bytes of this raw block
        # inside the persisted preview string, not to a fabricated valid root JSON.
        encoded_options = [json.dumps(raw_block, ensure_ascii=flag)[1:-1].encode('utf-8') for flag in [False, True]]
        offsets = []
        for encoded in encoded_options:
            at = original_bytes.find(encoded)
            if at >= 0 and original_bytes.find(encoded, at+1) < 0:
                offsets.append({'start': at, 'end': at+len(encoded), 'sha256': digest(encoded)})
        assert offsets, 'Cannot bind intact block to unique persisted source bytes'
        item = {'name': name, 'json_object_decoded_successfully': True,
            'preview_unicode_offsets': [start, end],
            'preview_decoded_utf8_byte_offsets': [len(preview[:start].encode('utf-8')), len(preview[:end].encode('utf-8'))],
            'preview_block_raw_utf8_sha256': digest(raw_block.encode('utf-8')),
            'persisted_file_escaped_block_byte_span': offsets[0],
            'parsed_numeric_fields': {k: {'score': v.get('score'), 'max_score': v.get('max_score')}
                                      for k,v in obj.items() if isinstance(v,dict) and 'score' in v}}
        blocks.append(item)
        for field, value in item['parsed_numeric_fields'].items():
            current = evaluation.get('scores', {}).get(name, {}).get(field, {})
            stored = current.get('score')
            fields.append({'field': field, 'raw_block_score': value['score'], 'raw_block_max_score': value['max_score'],
                'persisted_later_layer_score': stored,
                'conflict': stored is not None and stored != value['score'],
                'usage': 'diagnostic_only_no_automatic_reconciliation'})
    assert next(f for f in fields if f['field'] == 'co_chem')['conflict']
    assert SOURCE.read_bytes() == original_bytes, 'Source was unexpectedly modified'
    result = {'status': 'intact_partial_blocks_located_conflict_unresolved',
        'question_id': 29, 'model': 'gemini-3-flash', 'source_path': str(SOURCE.resolve()),
        'source_file_sha256': digest(original_bytes), 'source_record_key': 'question_id=29/evaluation/_raw_content_preview',
        'raw_preview_sha256': digest(preview.encode('utf-8')), 'raw_preview_unicode_length': len(preview),
        'original_error': evaluation['_error'], 'blocks': blocks, 'fields': fields,
        'exact_original_question_binding_present_in_failed_record': False,
        'original_answer_hash_in_failed_record': None, 'complete_extraction_recovered': False,
        'formal_Cor': None, 'formal_Eff': None, 'formal_CCE': None,
        'source_scores_changed': False, 'new_model_requests': 0, 'expert_labels_added': 0,
        'limitations': ['A valid subobject does not repair the invalid/truncated full teacher record.',
            'Raw co_chem and the later persisted co_chem conflict; provenance must resolve which layer is scientifically interpretable.',
            'No current component is overwritten and no normalization or full Cor/Eff/CCE is inferred.',
            'The raw preview sample description is not the exact historical task text or an extraction record.'],
        'script': {'path': str(pathlib.Path(__file__).resolve()), 'sha256': digest(pathlib.Path(__file__).read_bytes())},
        'actual_command': {'executable': sys.executable, 'argv': sys.argv}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'README.md').write_text('# q29 失败记录的局部数值块审计\n\n'+
        '已定位原 JSON preview 中可完整解码的 completeness 与 correctness 两个对象；JSON 记录原文件和 preview 散列、原文件中转义块的字节范围、解码后 UTF-8 的块范围。原文件未改，0 模型请求、0 专家标签。\n\n'+
        '| 字段 | 原 preview | 后存层 | 冲突 |\n|---|---:|---:|---|\n'+
        '\n'.join('| '+r['field']+' | '+str(r['raw_block_score'])+' | '+str(r['persisted_later_layer_score'])+' | '+str(r['conflict'])+' |' for r in fields)+
        '\n\nco_chem 的原 preview 为 0，后存层为 1；不自动选择其中一层。失败记录缺少原题精确绑定及完整 extraction，因此未计算正式 Cor、Eff 或 CCE，也未将原 c_step 换算成 SR。完整对象可读仅支持局部记录恢复，不修复整个失败评价。见 [audit.json](audit.json)。\n',encoding='utf-8')
    print(json.dumps({'status': result['status'], 'intact_blocks': len(blocks),
                      'conflicting_fields': [r['field'] for r in fields if r['conflict']], 'new_model_requests': 0}))


if __name__ == '__main__':
    main()
