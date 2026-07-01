"""
使用本地 Ollama 模型重新生成 user preference vector，并验证改进后的 S_method
与专家评分的吻合程度。

用法：
    python validate_smethod_ollama.py --model qwen3:8b --output smethod_validation.json

需要 Ollama 服务已启动，并且本地有指定的模型。
"""

import argparse
import json
import pathlib
import numpy as np
import requests
from scipy import stats
from collections import Counter

from OEQ_run_grading_new import calculate_method_suitability
from prompts.parse_user_preference_vector import USER_PREFERENCE_PROMPT


def parse_pref_vector(raw: str):
    """从模型输出中解析 user_input_vectors JSON。"""
    text = raw.strip()
    # 去掉 markdown fence
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        data = json.loads(text)
        return data.get("user_input_vectors", {})
    except Exception:
        return {}


def generate_pref_vector(model: str, question_text: str):
    """通过 Ollama REST API 生成用户偏好向量。"""
    prompt = USER_PREFERENCE_PROMPT.replace("{user_text}", question_text)
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0},
            },
            timeout=300,
        )
        resp.raise_for_status()
        return parse_pref_vector(resp.json().get("response", ""))
    except Exception as e:
        print(f"[WARN] Ollama generation failed: {e}")
        return {}


def icc_2_1(y: np.ndarray) -> float:
    """Two-way random, single measure ICC."""
    n, k = y.shape
    ms = np.var(y.mean(axis=1), ddof=0) * k
    mw = np.var(y, axis=1, ddof=0).mean()
    if ms + (k - 1) * mw == 0:
        return 0.0
    return float((ms - mw) / (ms + (k - 1) * mw))


def quadratic_weighted_kappa(y1, y2, scores):
    """简化版 QWK，用于连续得分离散化到 bins 后。"""
    n = len(scores)
    # 将连续值映射到最近的 bin index
    def to_bin(x):
        idx = int(np.round((x / 5.0) * (n - 1)))
        return max(0, min(n - 1, idx))

    a = [to_bin(v) for v in y1]
    b = [to_bin(v) for v in y2]

    # observed agreement
    o = sum(1 for x, y in zip(a, b) if x == y) / len(a)

    # expected agreement (marginals)
    ca = Counter(a)
    cb = Counter(b)
    e = sum((ca[i] / len(a)) * (cb[i] / len(b)) for i in range(n))

    if e == 1:
        return 1.0
    return float((o - e) / (1 - e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--output", default="results/smethod_validation_ollama.json")
    parser.add_argument("--max-items", type=int, default=0, help="用于测试的最大样本数，0 表示全部")
    args = parser.parse_args()

    data_path = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
    ms_path = pathlib.Path("dataset/Q+AR/src/model_space.json")

    data = json.loads(data_path.read_text(encoding="utf-8"))
    model_space = json.loads(ms_path.read_text(encoding="utf-8"))

    if args.max_items > 0:
        data = data[:args.max_items]

    # 按 question_id 缓存 preference vector
    pref_cache = {}

    records = []
    for idx, item in enumerate(data):
        qid = item["question_id"]
        qtext = item.get("specific_question", "")

        if qid not in pref_cache:
            pref_cache[qid] = generate_pref_vector(args.model, qtext)
            print(f"[{idx+1}/{len(data)}] qid={qid} pref_vector generated")
        else:
            print(f"[{idx+1}/{len(data)}] qid={qid} pref_vector cached")

        user_pref = pref_cache[qid]

        method_name = item["machine_evaluation"]["meta_data"].get("target_method", "")
        method_vector_dict = {}
        found = False
        if method_name:
            mn_low = method_name.lower()
            for key, val in model_space.get("methods", {}).items():
                kl = key.lower()
                if (mn_low in kl or kl in mn_low) and min(len(mn_low), len(kl)) >= 3:
                    method_vector_dict = val
                    found = True
                    break

        if not found:
            new_score = 0.0
        else:
            new_score = calculate_method_suitability(user_pref, method_vector_dict, sigma=0.4)

        human_score = item["human_evaluation"]["effectiveness"]["s_method"]["score"]
        old_score = item["machine_evaluation"]["scores"]["effectiveness"]["s_method"]["score"]

        records.append({
            "model_name": item["model_name"],
            "question_id": qid,
            "method": method_name,
            "human_smethod": human_score,
            "old_machine_smethod": old_score,
            "new_machine_smethod": new_score,
            "user_pref_vector": user_pref,
        })

    # 计算指标
    human = np.array([r["human_smethod"] for r in records])
    old_machine = np.array([r["old_machine_smethod"] for r in records])
    new_machine = np.array([r["new_machine_smethod"] for r in records])

    def metrics(y_pred, y_true):
        r, rp = stats.pearsonr(y_pred, y_true)
        rho, _ = stats.spearmanr(y_pred, y_true)
        icc = icc_2_1(np.column_stack([y_pred, y_true]))
        qwk = quadratic_weighted_kappa(y_pred, y_true, [0, 1, 2, 3, 4, 5])
        return {
            "pearson_r": float(r),
            "pearson_p": float(rp),
            "spearman_rho": float(rho),
            "icc_2_1": float(icc),
            "qwk_approx": float(qwk),
            "mean_pred": float(y_pred.mean()),
            "std_pred": float(y_pred.std()),
        }

    summary = {
        "model_used": args.model,
        "n_records": len(records),
        "old_metrics": metrics(old_machine, human),
        "new_metrics": metrics(new_machine, human),
        "human": {"mean": float(human.mean()), "std": float(human.std()), "min": float(human.min()), "max": float(human.max())},
        "records": records,
    }

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Summary ===")
    print(f"Records: {len(records)}")
    print(f"Old (cosine) metrics: {json.dumps(summary['old_metrics'], ensure_ascii=False, indent=2)}")
    print(f"New (weighted Euclidean) metrics: {json.dumps(summary['new_metrics'], ensure_ascii=False, indent=2)}")
    print(f"Saved to: {out_path}")


if __name__ == "__main__":
    main()
