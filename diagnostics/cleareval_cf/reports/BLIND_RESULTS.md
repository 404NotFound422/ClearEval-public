# BLIND_RESULTS -- blind-split evaluator results

**No blind results yet.** The blind split has 8 seeds / 24 pairs. Running it requires (a) a frozen prompt revision (`split_manifest.frozen_prompt_sha256` is currently null), (b) judge runs (online or fixtures), and (c) expert-reviewed gold + adjudication. Until then every blind number is pending.

Once the blind run exists, this report will show metrics 9.1-9.7 computed on the blind pairs only, with the prompt revision hash and the run metadata. No prompt tuning happens after blind results.

## Blind split (frozen)

| seed_id | qid | source_model | sample_tier | cce_total |
|---|---|---|---|---|
| SEED-001 | 1 | openai_gpt-5.2-fast | T04_WHOLE_MOUSE_BRAIN_5_12MM | 23.555546787157326 |
| SEED-006 | 137 | openai_gpt-5.2-thinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | 19.534100000000002 |
| SEED-009 | 21 | openai_claude-sonnet-4.6 | T02_THICK_SLICE_0P5_3MM | 22.1778 |
| SEED-010 | 127 | openai_qwen3-max | T12_WHOLE_EYE_OR_RETINA | 23.1019 |
| SEED-013 | 145 | gemini-3-pro | T11_PLANT_WHOLE_SEEDLING | 23.2942 |
| SEED-015 | 235 | gemini-3-flash | T05_MOUSE_SOFT_ORGAN_5_20MM | 15.367505849709836 |
| SEED-020 | 140 | glm4.7-unthinking | T03_SMALL_WHOLE_SAMPLE_1_5MM | 24.047290707753785 |
| SEED-022 | 160 | openai_gpt-5.2-thinking | T04_WHOLE_MOUSE_BRAIN_5_12MM | 20.5108 |

pending metrics: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7