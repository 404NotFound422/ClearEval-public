# Vestigial scoring-prompt module.
#
# The ACTIVE teacher evaluation prompt is prompts/eval_oeq_teacher_rubric.txt,
# which evaluate_response_with_teacher() loads and fills directly. This module
# exists only to satisfy the non-empty guard in load_prompt_method_generate();
# the historical `{{protocol_content}}` substitution that consumed `prompt` is
# commented out in evaluate_response_with_teacher(). Keep this file present so
# the grading pipeline starts.
prompt = "See prompts/eval_oeq_teacher_rubric.txt for the active teacher rubric."
