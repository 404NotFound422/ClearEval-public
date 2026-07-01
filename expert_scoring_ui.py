"""ClearEval expert scoring UI.

A lightweight Streamlit application for reviewing Open-Ended Question (OEQ)
cases from ``dataset/Q+AR/result/Machine_vs_Human_Summary.json``.  The left
column shows the question context and the model response in a structured,
human-readable form; the right column shows and lets expert users edit the
human CCE scores.  Edits are saved to a separate file and never modify the
original evaluation JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import streamlit as st


DATA_PATH = Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
USER_SCORES_PATH = Path("dataset/Q+AR/result/human_evaluation_user_scores.json")


@st.cache_data
def load_data() -> list[dict[str, Any]]:
    """Load the Machine_vs_Human_Summary JSON."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_score_group(group: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy 'items' format to the standard score-dict format."""
    if not isinstance(group, dict):
        return {}
    if "items" in group:
        return {
            key: {"score": value} for key, value in group["items"].items()
        } | {"total_score": group.get("total_score", 0)}
    return group


def load_user_scores() -> dict[str, dict[str, Any]]:
    """Load previously saved user scores, keyed by model|question_id."""
    if not USER_SCORES_PATH.exists():
        return {}
    try:
        with open(USER_SCORES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if isinstance(data, list):
        scores = {
            f"{item['model_name']}|{item['question_id']}": item for item in data
        }
    elif isinstance(data, dict):
        scores = data
    else:
        return {}
    for record in scores.values():
        for category in ("completeness", "correctness", "effectiveness"):
            if category in record:
                record[category] = normalize_score_group(record[category])
    return scores


def save_user_scores(scores: dict[str, dict[str, Any]]) -> None:
    """Persist user scores to the separate output file."""
    USER_SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)


def record_key(record: dict[str, Any]) -> str:
    return f"{record['model_name']}|{record['question_id']}"


def parse_model_response(text: str) -> dict[str, str]:
    """Split the markdown response into labeled sections.

    The expected format uses ``**Label:** value`` headings.  If no headings are
    found, the whole response is returned under a single ``Response`` key.
    """
    sections: dict[str, str] = {}
    pattern = re.compile(r"\*\*([^*]+?)\*\*\s*(.*?)(?=\n\*\*|$)", re.DOTALL)
    for match in pattern.finditer(text):
        key = match.group(1).strip().rstrip(":")
        value = match.group(2).strip()
        if key and value:
            sections[key] = value
    if not sections:
        sections["Response"] = text.strip()
    return sections


def get_score(group: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Return a numeric score from a score group."""
    value = group.get(key, {})
    if isinstance(value, dict):
        return float(value.get("score", default))
    return float(value) if value is not None else default


def render_score_editor(
    container: Any,
    title: str,
    group: dict[str, Any],
    keys: list[str],
    prefix: str,
) -> dict[str, Any]:
    """Render editable score inputs for one CCE group and return updates."""
    container.markdown(f"#### {title}")
    updates: dict[str, Any] = {}
    cols = container.columns(len(keys))
    for col, key in zip(cols, keys):
        current = get_score(group, key)
        updates[key] = col.number_input(
            key,
            value=current,
            step=0.25,
            key=f"{prefix}_{key}",
        )
    total = sum(updates.values())
    container.metric(label=f"{title} Total", value=total)
    return {key: {"score": value} for key, value in updates.items()} | {"total_score": total}


def main() -> None:
    """Run the expert scoring UI."""
    st.set_page_config(
        page_title="ClearEval Expert Scoring UI",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("ClearEval Expert Scoring UI")

    records = load_data()
    if not records:
        st.error("No records found in the data source.")
        return

    user_scores = load_user_scores()

    # Sidebar navigation
    model_names = sorted({r["model_name"] for r in records})

    with st.sidebar:
        st.header("Navigation")

        selected_model = st.selectbox("Model", model_names)
        model_question_ids = sorted(
            {r["question_id"] for r in records if r["model_name"] == selected_model},
            key=lambda x: int(x),
        )

        index_key = f"qid_index_{selected_model}"
        if index_key not in st.session_state:
            st.session_state[index_key] = 0

        current_index = st.session_state[index_key]
        selected_qid = st.selectbox(
            "Question ID",
            model_question_ids,
            index=current_index,
            key=f"qid_select_{selected_model}",
        )
        st.session_state[index_key] = model_question_ids.index(selected_qid)

        col_prev, col_next = st.columns(2)
        if col_prev.button("← Previous", use_container_width=True):
            new_index = max(0, st.session_state[index_key] - 1)
            st.session_state[index_key] = new_index
            st.rerun()
        if col_next.button("Next →", use_container_width=True):
            new_index = min(len(model_question_ids) - 1, st.session_state[index_key] + 1)
            st.session_state[index_key] = new_index
            st.rerun()

        st.divider()
        st.caption(f"Total cases: {len(records)}")

    # Locate selected record
    try:
        record = next(
            r
            for r in records
            if r["model_name"] == selected_model and r["question_id"] == selected_qid
        )
    except StopIteration:
        st.error("Selected record not found.")
        return

    key = record_key(record)
    saved = user_scores.get(key, {})
    baseline = record.get("human_evaluation", {})

    # Use saved values if present, otherwise fall back to the original scores.
    current = {
        "grader_name": saved.get("grader_name", baseline.get("grader_name", "")),
        "grading_time": saved.get("grading_time", baseline.get("grading_time", "")),
        "overall_comment": saved.get(
            "overall_comment", baseline.get("overall_comment", "")
        ),
        "completeness": saved.get("completeness", baseline.get("completeness", {})),
        "correctness": saved.get("correctness", baseline.get("correctness", {})),
        "effectiveness": saved.get("effectiveness", baseline.get("effectiveness", {})),
    }

    col_left, col_right = st.columns([3, 2])

    # Left column: readable case content
    with col_left:
        st.subheader(f"{record['model_name']} — Question {record['question_id']}")

        with st.expander("Question Context", expanded=True):
            st.markdown(record["specific_question"])

        st.divider()

        sections = parse_model_response(record["model_response"])
        for title, body in sections.items():
            st.markdown(f"### {title}")
            st.markdown(body)

    # Right column: editable human scores
    with col_right:
        st.subheader("Human Evaluation")

        completeness = render_score_editor(
            st.container(),
            "Completeness",
            current["completeness"],
            ["c_step", "c_param"],
            prefix=f"{key}_completeness",
        )
        correctness = render_score_editor(
            st.container(),
            "Correctness",
            current["correctness"],
            ["co_order", "co_method", "co_param", "co_chem"],
            prefix=f"{key}_correctness",
        )
        effectiveness = render_score_editor(
            st.container(),
            "Effectiveness",
            current["effectiveness"],
            ["s_method", "s_label", "s_trans", "s_time"],
            prefix=f"{key}_effectiveness",
        )

        overall_total = (
            completeness["total_score"]
            + correctness["total_score"]
            + effectiveness["total_score"]
        )
        st.metric("Overall Total", overall_total)

        grader_name = st.text_input(
            "Grader Name",
            value=current["grader_name"],
            key=f"{key}_grader_name",
        )
        grading_time = st.text_input(
            "Grading Time",
            value=current["grading_time"],
            key=f"{key}_grading_time",
        )
        overall_comment = st.text_area(
            "Overall Comment",
            value=current["overall_comment"],
            key=f"{key}_overall_comment",
        )

        if st.button("💾 Save Human Scores", type="primary", use_container_width=True):
            user_scores[key] = {
                "model_name": record["model_name"],
                "question_id": record["question_id"],
                "grader_name": grader_name,
                "grading_time": grading_time,
                "overall_comment": overall_comment,
                "completeness": completeness,
                "correctness": correctness,
                "effectiveness": effectiveness,
                "overall_total_score": overall_total,
            }
            save_user_scores(user_scores)
            st.success(f"Saved to {USER_SCORES_PATH}")

        if saved:
            st.caption("✏️ This case has user-edited scores.")

    # Footer: machine scores for cross-reference
    with st.expander("Machine Evaluation (reference)"):
        me = record.get("machine_evaluation")
        if me:
            st.json(me)
        else:
            st.info("No machine evaluation available for this case.")


if __name__ == "__main__":
    main()
