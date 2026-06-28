import json
from collections import Counter
with open(r'dataset\Q+AR\src\question_final.json', 'r', encoding='utf-8') as f:
    questions = json.load(f)
labels = []
for q in questions:
    th = q.get('tissue_hierarchy_from_tissue_xlsx', {})
    label = th.get('tissue_tier_label')
    if label:
        labels.append(label)
print('Total questions:', len(questions))
print('Unique tissue labels:', len(set(labels)))
for label, count in Counter(labels).most_common():
    print(f'{count:4d}  {label}')
