import pandas as pd

df = pd.read_csv('results/clearing_time_analysis/extraction_comparison.csv')
for model in ['openai_qwen3-14b', 'openai_claude-sonnet-4.6', 'glm4.7-thinking']:
    sub = df[df['model'] == model]
    cond = (
        (sub['original_hours'].isna() != sub['fixed_hours'].isna())
        | (sub['original_hours'].notna() & sub['fixed_hours'].notna()
           & ((sub['original_hours'] - sub['fixed_hours']).abs() > 0.01))
    )
    changed = sub[cond]
    print(f"\n{model}: {len(changed)} changed")
    print(changed.head(10).to_string(index=False))
