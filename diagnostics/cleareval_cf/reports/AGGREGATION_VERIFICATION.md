# AGGREGATION VERIFICATION -- production oeq aggregation unchanged

- recomputed rows: 13  frozen rows: 13
- all_exact       : True
- max abs diff    : 0.0
- tolerance       : 1e-09 (Exact equality is expected: the recommutation uses the same per-sub-metric mean + MAX_SCORES normalization over the same frozen eval files that produced oeq_stats_260223.jsonl (results/aggregate_oeq.py).  The 1e-9 slack only absorbs JSON float round-trip noise; anything larger signals drift in the frozen data or stats file.)

| model_name | sample_count_match | max_abs_diff | exact |
|---|---|---|---|
| gemini-3-flash | True | 0.00e+00 | True |
| gemini-3-pro | True | 0.00e+00 | True |
| glm4.7-thinking | True | 0.00e+00 | True |
| glm4.7-unthinking | True | 0.00e+00 | True |
| openai_claude-sonnet-4.6 | True | 0.00e+00 | True |
| openai_deepseek-chat | True | 0.00e+00 | True |
| openai_deepseek-reasoner | True | 0.00e+00 | True |
| openai_gpt-5.2-fast | True | 0.00e+00 | True |
| openai_gpt-5.2-thinking | True | 0.00e+00 | True |
| openai_qwen3-14b | True | 0.00e+00 | True |
| openai_qwen3-235b | True | 0.00e+00 | True |
| openai_qwen3-32b | True | 0.00e+00 | True |
| openai_qwen3-max | True | 0.00e+00 | True |
