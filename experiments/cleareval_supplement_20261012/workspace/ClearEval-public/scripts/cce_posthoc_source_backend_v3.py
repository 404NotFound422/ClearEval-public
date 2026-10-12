"""One isolated source environment for name, relation and attached records."""
import cce_posthoc_name_boundary_v2 as previous
import cce_label_source_syntax_fix_v1 as syntax
import cce_attached_operation_parameters_v1 as attached

_backend=attached.build_backend(syntax.build_backend(previous))
for _key,_value in vars(_backend).items():
    if not _key.startswith('__'):globals()[_key]=_value
POSTHOC_BACKEND_VERSION='uniform-posthoc-source-backend-v3'
assert _environment['relation_policy'] is syntax.relation_policy
assert _environment['name_atomicity'] is syntax.name_atomicity
