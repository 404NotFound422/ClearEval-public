"""Joint private factory with complete reference-bound parameter phase scopes."""
from types import FunctionType,SimpleNamespace
from ..parameter_finite_requirement_domains_v1 import normal_candidate_v1 as base
from ..parameter_route_role_scope_v1 import route_scope_v1 as material,recipe_scope
from ..parameter_contract_dispatch_v1.dispatch import wrap
from ..parameter_actual_carrier_role_v1 import carrier_scope,carrier_obligation
from ..parameter_strict_source_quote_projection_v1 import private_backend,normal_candidate_v1 as quoted
from ..source_metadata_treatment_clock_20261025_v1 import count_consumers
from parameter_execution_unit_contract_20261025_v1 import normal_candidate_v9 as global_template,binding,binding_v15
from ..parameter_literal_action_scope_v1 import action_scope
from ..parameter_private_reference_scope_v1 import units as reference_scope,rebind as typed_rebind
from ..parameter_operation_variant_scope_v1 import apply as operation_variants
from ..parameter_cubic_route_scope_v1 import apply as cubic_routes

prior=base.prior


def build():
    units=reference_scope.namespace(count_consumers.source_units_namespace(prior.consumers.source_units_namespace(prior.source_units_v2)))
    core=prior.execution.template.normal.scoring_core
    support_modules=[prior.support,prior.support_v2,prior.support_v3,prior.support_v4,prior.support_v5,prior.support_v6,prior.support_v7,prior.support_v8,prior.support_v9,prior.support_v10]
    def combined_apply(binding,protocol,original_manifest,max_template_worlds=4096,source=None):
        if source is not None:
            binding=typed_rebind.rebind(binding,source,protocol)
        if binding.get('private_typed_rebind',{}).get('status')=='INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE':
            return binding
        if source is not None and cubic_routes.declared(binding):
            result=operation_variants.apply(binding,protocol,original_manifest,max_template_worlds)
            return cubic_routes.apply(result,protocol,original_manifest,max_template_worlds)
        result=carrier_scope.extend(material.apply(binding,protocol,original_manifest,max_template_worlds),protocol,original_manifest)
        return operation_variants.apply(result,protocol,original_manifest,max_template_worlds)
    def material_namespace(original):
        return SimpleNamespace(**{**vars(original),'apply':combined_apply,'VERSION':action_scope.VERSION})
    functions=((carrier_obligation.prior.decompose,carrier_obligation.decompose),)+reference_scope.binding_replacements(units)
    wrappers=((global_template._observations,quoted.wrap_observer),)
    replacements=[(binding,reference_scope.binding_namespace(binding,combined_apply)),
        (binding_v15,reference_scope.binding_namespace(binding_v15,combined_apply)),
        (core,prior.review_core_interface_v1.namespace(core)),(prior.physical,prior.facts.namespace()),
        (prior.custom1,material_namespace(prior.custom1)),(prior.custom2,material_namespace(prior.custom2))]
    for module in support_modules:
        supported=private_backend.build(module,units,external_functions=functions,function_wrappers=wrappers)
        wrapped=base.spacing.namespace(base.medium.namespace(supported))
        if hasattr(wrapped,'_source_origin'):wrapped=recipe_scope.support_namespace(wrapped)
        replacements.append((module,wrapped))
    private=private_backend.build(prior.execution,units,external_modules=tuple(replacements),
        external_functions=functions,function_wrappers=wrappers)
    backend=prior.representation._api(private);fn=prior.subset._api
    ns={**vars(prior.subset),'template':private.template,'hybrid':private.hybrid,'legacy_hybrid':private.hybrid.prior}
    builder=FunctionType(fn.__code__,ns,fn.__name__,fn.__defaults__,fn.__closure__);builder.__kwdefaults__=fn.__kwdefaults__
    return wrap(builder(backend))


parameter=build();prepare=parameter.prepare;consume=parameter.consume;apply=parameter.apply;revalidate_parameter_graph=parameter.revalidate_parameter_graph


def __getattr__(name):return getattr(parameter,name)
