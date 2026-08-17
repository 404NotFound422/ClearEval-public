# ClearEval counterfactual-validity overlay -- DATA_SUMMARY (Task 1)

- Algorithm: `seed-selector-v1` (see `seed_selector.py` module docstring for full rules)
- Split seed: `20260817` (RNG = `random.Random(split_seed)`)
- Corpus: 253 OEQ questions x 13 frozen 1-shot models (dataset/Q+AR)

All content selection is mechanical (regex/keyword/eligibility rules).
No ClearEval gold, expert labels, mutation labels, or scorer thresholds
were used to select or generate content.

## 1. Scenario strata (definition + question-level counts)

| Stratum | Definition | Questions |
|---|---|---|
| ERROR_CORRECTION | question text matches `错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在` | 60 |
| COMPLEX_GENERATION | not ERROR_CORRECTION and `len(marker_query_targets) >= 4` | 70 |
| SIMPLE_GENERATION | remaining questions | 123 |

Counts are derived per question with `derive_scenario_type(question_text, len(marker_query_targets))` over `question_final.json` (253 questions); the table is regenerated, never hardcoded.

## 2. Input files (sha256)

- `dataset/Q+AR/model_response/from_gemini-3-flash_1-shot.json` : `7fcacdf4267646af3ec7748d9ec9c60c2a02a9b0cba49164c7909ae91cce8634`
- `dataset/Q+AR/model_response/from_gemini-3-pro_1-shot.json` : `168a2fca058cdd26c213208b27fb10edc70ac079c4fefc26f0ddfc4db4c47bd9`
- `dataset/Q+AR/model_response/from_glm4.7-thinking_1-shot.json` : `b0abd6d07fd22f8baebc0bd74c77f1ddf3b9eb9998a57c340ffd22fc13d3ae09`
- `dataset/Q+AR/model_response/from_glm4.7-unthinking_1-shot.json` : `e7aa741bc595bf49e5c59108e1d7cc857022e9a5a8405f3d051260f5b30c8f91`
- `dataset/Q+AR/model_response/from_openai_claude-sonnet-4.6_1-shot.json` : `dcd4ff283d201f541ce6cba49dcd98df10d53b012a1aa7c9fa69671fe7da1bbd`
- `dataset/Q+AR/model_response/from_openai_deepseek-chat_1-shot.json` : `89d04d6e9730697f06054ca6135205fe23e9e08cd5a09537eeea1c6670e10025`
- `dataset/Q+AR/model_response/from_openai_deepseek-reasoner_1-shot.json` : `6b1662656af537a219a95cea7c1f52b01f424b536e70f8a335536fe23420cd68`
- `dataset/Q+AR/model_response/from_openai_gpt-5.2-fast_1-shot.json` : `c864dcdca8f800c64381de62146f66a0d4f0fa232bc68ce2a7686da3a5e0223e`
- `dataset/Q+AR/model_response/from_openai_gpt-5.2-thinking_1-shot.json` : `30ea221c31d9d4d5010716b8ac42e23baf5610e41da050d045bb1944b6883846`
- `dataset/Q+AR/model_response/from_openai_qwen3-14b_1-shot.json` : `74854cc357783de591e0aae720ec7f8064a62c266b3491e6bfe3b0b1af030915`
- `dataset/Q+AR/model_response/from_openai_qwen3-235b_1-shot.json` : `530263e5aca047096a6e40d7cf384ce8ea3d451a311c09f5b89dd8f6c19fd89e`
- `dataset/Q+AR/model_response/from_openai_qwen3-32b_1-shot.json` : `138663d0dd10aae4880135cda5f0ddaec7677306e8ac4706d59512abb3a13faf`
- `dataset/Q+AR/model_response/from_openai_qwen3-max_1-shot.json` : `66f980f6758fe4e125e3ccdf22c074b4eb1d8ae4f62c22b34e8c8b969d507371`
- `dataset/Q+AR/result/evaluation_results_gemini-3-flash_1-shot.json` : `4b7ff59488ad7df585d84468d6f4b591c77276ee66a6f1bfa8bcac605b3b7bcd`
- `dataset/Q+AR/result/evaluation_results_gemini-3-pro_1-shot.json` : `86ea0e1c3a2b3576ce819eb9858b00a3f7d2f678d34341631881314b44f06115`
- `dataset/Q+AR/result/evaluation_results_glm4.7-thinking_1-shot.json` : `a190b24e164124c0533d95546d70011d5a727bf4c1d2d8c8f3a162c799efa93f`
- `dataset/Q+AR/result/evaluation_results_glm4.7-unthinking_1-shot.json` : `ac3a4c01a9b963c627fe1630913adc9b2a32a7a6df06a95b201bbea80f0a48bc`
- `dataset/Q+AR/result/evaluation_results_openai_claude-sonnet-4.6_1-shot.json` : `022498debb5e93fe4a8b57173dc2c512acd313b6c7d3cb46f2a94923bae04704`
- `dataset/Q+AR/result/evaluation_results_openai_deepseek-chat_1-shot.json` : `da18a82c6086636bc994eeceb5926c9b8a4e3b24c9b18172d26f5b01f9de73d7`
- `dataset/Q+AR/result/evaluation_results_openai_deepseek-reasoner_1-shot.json` : `7e178e70ca5b2f70fff7ca6456d402d822207af4356c0aed85c89a1ff19d236b`
- `dataset/Q+AR/result/evaluation_results_openai_gpt-5.2-fast_1-shot.json` : `1a3a91975bdb64715786a18f928b760f23411692fa3b945ca84d4746dca108ea`
- `dataset/Q+AR/result/evaluation_results_openai_gpt-5.2-thinking_1-shot.json` : `44e12a289b6a2e785f87154da02636449fded9bade8dcf00fac82a9674ff0e37`
- `dataset/Q+AR/result/evaluation_results_openai_qwen3-14b_1-shot.json` : `4d460cd427ff62542e6e14255e67fd556ece1352d814e213a12eace3ec1691bf`
- `dataset/Q+AR/result/evaluation_results_openai_qwen3-235b_1-shot.json` : `cc176e58b6fc65c46478057910870c874fbc72bae69c68393a66d70d6abefb8b`
- `dataset/Q+AR/result/evaluation_results_openai_qwen3-32b_1-shot.json` : `533d757387d426c2d88891bbfb432e1dce6c91825ee6942f76a398c59de31ccc`
- `dataset/Q+AR/result/evaluation_results_openai_qwen3-max_1-shot.json` : `5137b4f5383dd13bddcaf3b731874e75de108198e121aaca91b03e2c7c882225`
- `dataset/Q+AR/src/question_final.json` : `487c62e32e7096bf5963edbbf1af8ba2fa9d5a371702675a836b309a8cecbd9b`

## 3. Eligibility pre-filter (mechanical) and pool

Eligibility rules (a)-(e) as documented in `seed_selector.py` rule 4:
- (a) response record exists for (model, question_id);
- (b) response_text non-empty after strip;
- (c) evaluation record exists;
- (d) usable totals present for completeness AND correctness AND effectiveness;
- (e) `correctness.critical_warnings` empty or absent.

- Candidate pairs tried: `3289` (13 x 253)
- Eligible: `71`
- Rejected: `3218` by reason:

| Rejection reason | Count |
|---|---|
| critical_warnings_present | 3216 |
| missing_cc_score_totals | 1 |
| missing_response_record | 1 |

Eligible pool per model:

| Model | Eligible candidates |
|---|---|
| gemini-3-flash | 5 |
| gemini-3-pro | 5 |
| glm4.7-thinking | 6 |
| glm4.7-unthinking | 6 |
| openai_claude-sonnet-4.6 | 4 |
| openai_deepseek-chat | 3 |
| openai_deepseek-reasoner | 2 |
| openai_gpt-5.2-fast | 22 |
| openai_gpt-5.2-thinking | 15 |
| openai_qwen3-14b | 0 |
| openai_qwen3-235b | 0 |
| openai_qwen3-32b | 0 |
| openai_qwen3-max | 3 |

Eligible pool per stratum:

| Stratum | Eligible candidates |
|---|---|
| SIMPLE_GENERATION | 38 |
| COMPLEX_GENERATION | 20 |
| ERROR_CORRECTION | 13 |

- CCE total range over eligible pool: `[9.2963, 26.2710]`
- Bucket boundaries (equal-width thirds): LOW `< 14.9545`, MID `< 20.6128`, HIGH `>= 20.6128`

## 4. Derivation rules (see `seed_selector.py` docstring for full tables)

**clearing_method_family** -- first match wins over question text:

`CUBIC, PEGASOS, iDISCO, FDISCO, uDISCO, 3DISCO, DISCO, MACS, eFLASH, CLARITY, SHANEL, SeeDB, Scale (ScaleS/Scale), SWITCH, SOLVENT_BASED (甲醇/有机溶剂), UNKNOWN`

**labeling_requirement** -- text keywords + marker-name fallback:

transgenic signal = text `转基因|荧光蛋白|报告基因|遗传标记|外源基因|GFP|YFP|Thy1|tdTomato|Ai14|Cre|AAV` or any marker_name matching `GFP|YFP|Thy1|tdTomato|Ai14|reporter|Cre`; immuno signal = text `抗体|免疫`.  MIXED if transgenic signal and (immuno signal or `n_targets >= 4`); else TRANSGENIC / IMMUNOLABELING / UNKNOWN.

## 5. Selection algorithm (greedy round-robin, RNG-free)

Per stratum, 8 rounds; round r is led by dimension `DIMENSIONS[r % 5]` (`sample_tier, source_model, clearing_method_family, labeling_requirement, cce_bucket`).  Each round picks the unselected candidate with the smallest `(count[lead], sum(counts over other dims), question_id, source_model)` lexicographic key.  seed_ids are then assigned `SEED-001..024` sorted by (stratum rank, question_id, source_model).

## 6. Chosen seeds (24; 8 per stratum)

### SIMPLE_GENERATION (8 seeds)

| seed_id | qid | model | sample_tier | method_family | labeling | n_targets | cce_bucket | cce_total |
|---|---|---|---|---|---|---|---|---|
| SEED-001 | 1 | openai_gpt-5.2-fast | T04_WHOLE_MOUSE_BRAIN_5_12MM | UNKNOWN | UNKNOWN | 2 | HIGH | 23.5555 |
| SEED-002 | 29 | openai_gpt-5.2-fast | T01_THIN_SLICE_LE500UM | UNKNOWN | TRANSGENIC | 2 | HIGH | 25.6381 |
| SEED-003 | 30 | glm4.7-thinking | T01_THIN_SLICE_LE500UM | UNKNOWN | TRANSGENIC | 2 | MID | 19.2439 |
| SEED-004 | 79 | openai_gpt-5.2-thinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | UNKNOWN | IMMUNOLABELING | 2 | HIGH | 23.0062 |
| SEED-005 | 107 | openai_deepseek-chat | T05_MOUSE_SOFT_ORGAN_5_20MM | UNKNOWN | UNKNOWN | 2 | LOW | 14.6504 |
| SEED-006 | 137 | openai_gpt-5.2-thinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | UNKNOWN | MIXED | 2 | MID | 19.5341 |
| SEED-007 | 166 | glm4.7-thinking | T06_LONG_CNS_OR_TUBULAR_15_80MM | UNKNOWN | IMMUNOLABELING | 2 | LOW | 11.1563 |
| SEED-008 | 244 | gemini-3-flash | T02_THICK_SLICE_0P5_3MM | UNKNOWN | UNKNOWN | 2 | HIGH | 22.8400 |

### COMPLEX_GENERATION (8 seeds)

| seed_id | qid | model | sample_tier | method_family | labeling | n_targets | cce_bucket | cce_total |
|---|---|---|---|---|---|---|---|---|
| SEED-009 | 21 | openai_claude-sonnet-4.6 | T02_THICK_SLICE_0P5_3MM | UNKNOWN | MIXED | 4 | HIGH | 22.1778 |
| SEED-010 | 127 | openai_qwen3-max | T12_WHOLE_EYE_OR_RETINA | UNKNOWN | UNKNOWN | 4 | HIGH | 23.1019 |
| SEED-011 | 135 | openai_deepseek-chat | T10_LIPID_OR_PIGMENT_RICH | UNKNOWN | UNKNOWN | 4 | HIGH | 20.9194 |
| SEED-012 | 143 | openai_gpt-5.2-fast | T03_SMALL_WHOLE_SAMPLE_1_5MM | UNKNOWN | UNKNOWN | 4 | MID | 16.0738 |
| SEED-013 | 145 | gemini-3-pro | T11_PLANT_WHOLE_SEEDLING | UNKNOWN | MIXED | 4 | HIGH | 23.2942 |
| SEED-014 | 146 | openai_gpt-5.2-thinking | T11_PLANT_WHOLE_SEEDLING | UNKNOWN | MIXED | 4 | MID | 17.8710 |
| SEED-015 | 235 | gemini-3-flash | T05_MOUSE_SOFT_ORGAN_5_20MM | UNKNOWN | UNKNOWN | 4 | MID | 15.3675 |
| SEED-016 | 240 | glm4.7-thinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | UNKNOWN | UNKNOWN | 4 | MID | 19.2090 |

### ERROR_CORRECTION (8 seeds)

| seed_id | qid | model | sample_tier | method_family | labeling | n_targets | cce_bucket | cce_total |
|---|---|---|---|---|---|---|---|---|
| SEED-017 | 8 | openai_gpt-5.2-fast | T06_LONG_CNS_OR_TUBULAR_15_80MM | UNKNOWN | UNKNOWN | 2 | MID | 18.4072 |
| SEED-018 | 76 | glm4.7-thinking | T09_HUMAN_DENSE_CLINICAL_BLOCK | SOLVENT_BASED | UNKNOWN | 2 | LOW | 9.2963 |
| SEED-019 | 116 | openai_claude-sonnet-4.6 | T10_LIPID_OR_PIGMENT_RICH | iDISCO | IMMUNOLABELING | 2 | HIGH | 23.5326 |
| SEED-020 | 140 | glm4.7-unthinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | UNKNOWN | TRANSGENIC | 2 | HIGH | 24.0473 |
| SEED-021 | 148 | gemini-3-pro | T11_PLANT_WHOLE_SEEDLING | UNKNOWN | MIXED | 4 | LOW | 14.8942 |
| SEED-022 | 160 | openai_gpt-5.2-thinking | T04_WHOLE_MOUSE_BRAIN_5_12MM | SWITCH | MIXED | 4 | MID | 20.5108 |
| SEED-023 | 212 | openai_gpt-5.2-fast | T05_MOUSE_SOFT_ORGAN_5_20MM | SOLVENT_BASED | IMMUNOLABELING | 6 | MID | 17.3784 |
| SEED-024 | 236 | openai_gpt-5.2-fast | T05_MOUSE_SOFT_ORGAN_5_20MM | CUBIC | IMMUNOLABELING | 4 | LOW | 13.2810 |

## 7. Development / blind split (seeds only)

- RNG drew stratum order: `ERROR_CORRECTION, SIMPLE_GENERATION, COMPLEX_GENERATION`
- The first two drawn strata keep 6 development seeds each; the third (`COMPLEX_GENERATION`) keeps 4.

| Stratum | development | blind |
|---|---|---|
| SIMPLE_GENERATION | 6 | 2 |
| COMPLEX_GENERATION | 4 | 4 |
| ERROR_CORRECTION | 6 | 2 |

**development_seed_ids** (16):

`SEED-002, SEED-003, SEED-004, SEED-005, SEED-007, SEED-008, SEED-011, SEED-012, SEED-014, SEED-016, SEED-017, SEED-018, SEED-019, SEED-021, SEED-023, SEED-024`

**blind_seed_ids** (8):

`SEED-001, SEED-006, SEED-009, SEED-010, SEED-013, SEED-015, SEED-020, SEED-022`

## 8. Output files (sha256)

- `seed_candidates.jsonl` : `8962ae94c3c1164f11658e4a8911293b97a29f48f5362a07adf574e1beb2c9d8`
- `split_manifest.json` : `a8cbe5471fb3236a92be8c300059d35adc4f4139ee21d2826c86ea5d278621ed`
