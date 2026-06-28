import json
with open(r'dataset\Q+AR\model_response\clearing_time_stats.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(type(data))
if isinstance(data, dict):
    print('keys:', list(data.keys())[:20])
    for k, v in data.items():
        print(k, type(v))
        if isinstance(v, (dict, list)):
            print(json.dumps(v, indent=2, ensure_ascii=False)[:2000])
        break
elif isinstance(data, list):
    print('len:', len(data))
    print(json.dumps(data[0], indent=2, ensure_ascii=False)[:2000])
