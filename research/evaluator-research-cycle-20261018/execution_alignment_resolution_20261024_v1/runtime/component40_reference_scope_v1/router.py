"""Route complete reference-scope evidence through partial and multi-origin consumers."""
from ..component39_joint_scope_v1.router import namespace
from ...parameter_joint_reference_scope_v1 import normal_candidate as joint
from ...parameter_partial_transport_subset_v1 import normal_adapter as partial_adapter, reader as partial_reader
from ...parameter_atomic_multisource_v2 import normal_adapter as multi_adapter, reader as multi_reader
from ...parameter_contract_dispatch_v1 import dispatch

VERSION = 'normal-reference-operation-scope-parameter-origin-policy-router-v1'
native = joint.parameter.native_backend
partial = partial_adapter.namespace(native, declared_policy_version=partial_reader.VERSION)
multi = multi_adapter.namespace(partial, declared_policy_version=multi_reader.VERSION)
parameter = dispatch.wrap(namespace(native, partial, multi))
