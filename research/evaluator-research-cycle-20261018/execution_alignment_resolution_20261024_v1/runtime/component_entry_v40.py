"""Normal composition for complete reference-bound parameter evidence."""
from contextlib import contextmanager
from endpoint_execution import clone_namespace
from . import component_entry_v39 as prior
from .component40_reference_scope_v1.router import parameter

VERSION = 'normal-source-bound-component-composition-v40-reference-operation-scope'
component_evidence = clone_namespace(prior.component_evidence, {'parameter': parameter})
_ns = clone_namespace(prior, {
    'parameter': parameter,
    'component_evidence': component_evidence,
    'VERSION': VERSION,
})

source_entry = _ns.source_entry
bio = _ns.bio
steps = _ns.steps
time = _ns.time
correctness = _ns.correctness
labels = _ns.labels
generic_labels = _ns.generic_labels
empty_steps = _ns.empty_steps
aggregates = _ns.aggregates
digest = _ns.digest
apply_steps = _ns.apply_steps
coverage_certificate = _ns.coverage_certificate
finalize_aggregates = _ns.finalize_aggregates
apply_components = _ns.apply_components
attach = _ns.attach
@contextmanager
def prepare_branch(job, provider_output, **consumers):
    with source_entry.prepare_branch(job, provider_output) as branch:
        if job.get('spec_path'):
            branch = {**branch, 'coverage_source_context': {
                'reference_spec': source_entry.dispatch.read(job['spec_path'])}}
        yield attach(branch, **consumers)


@contextmanager
def prepare_bound(*args, **kwargs):
    consumers = {key: kwargs.pop(key) for key in (
        'bio_evidence', 'step_evidence', 'time_policy', 'parameter_review', 'correctness_policy') if key in kwargs}
    with source_entry.prepare_bound(*args, **kwargs) as branch:
        yield attach(branch, **consumers)


@contextmanager
def prepare_job(job, **consumers):
    with source_entry.prepare_job(job) as branch:
        yield attach(branch, **consumers)


def __getattr__(name):
    return getattr(source_entry, name)
