"""Versioned judge guidance, not an automatic biological-validity classifier.

No keyword scoring, new wet-lab procedures, or changes to archived decisions.
Sources support scoped scientific premises; score bands are benchmark policy.
"""
from copy import deepcopy
from pathlib import Path
from evaluation_contract import json_hash

VERSION = 'sample-marker-applicability-v4-20261015'
SOURCES = [
    {'id': 'hardtissue-idisco-cne25582',
     'url': 'https://onlinelibrary.wiley.com/doi/full/10.1002/cne.25582',
     'alternate_url': 'https://pubmed.ncbi.nlm.nih.gov/38289188/',
     'title': 'Using tissue clearing and light sheet fluorescence microscopy for the three-dimensional analysis of sensory and sympathetic nerve endings that innervate bone and dental tissue of mice',
     'source_type': 'PRIMARY_RESEARCH',
     'summary': 'A modified iDISCO/iDISCO+ study of mouse bone and dental innervation identifies mineral as a barrier to optical transparency and uses decalcification. It supports a hard-tissue applicability concern for an explicitly non-decalcified iDISCO route, not a universal rule for every clearing method.',
     'limits': 'Successful decalcified tissue imaging does not establish preservation of native mineral or intact enamel; preservation of gross shape and preservation of mineral are different endpoints.'},
    {'id': 'brp-nc82-wagh2006', 'url': 'https://pubmed.ncbi.nlm.nih.gov/16543132/',
     'title': 'Bruchpilot, a protein with homology to ELKS/CAST, is required for structural integrity and function of synaptic active zones in Drosophila',
     'source_type': 'PRIMARY_RESEARCH',
     'summary': 'The study identifies the Drosophila nc82 antigen as Bruchpilot, an active-zone protein with homology to ELKS/CAST.',
     'limits': 'Homology alone does not establish antibody cross-reactivity, expression, or equivalent target identity in another species or tissue.'},
    {'id': 'prostate-p63-pmid11597556', 'url': 'https://pubmed.ncbi.nlm.nih.gov/11597556/',
     'title': 'p63 protein expression is rare in prostate adenocarcinoma: implications for cancer diagnosis and carcinogenesis',
     'source_type': 'PRIMARY_RESEARCH',
     'summary': 'p63 staining identified basal epithelial cells in benign prostate and was absent from most examined adenocarcinomas, supporting a contextual basal-cell marker role.',
     'limits': 'The observation is not an infallible cancer classifier or a validation of any clearing pipeline.'},
    {'id': 'prostate-amacr-2003', 'url': 'https://pubmed.ncbi.nlm.nih.gov/12883245/',
     'title': 'Alpha-methylacyl-CoA racemase: a variably sensitive immunohistochemical marker for the diagnosis of small prostate cancer foci on needle biopsy',
     'source_type': 'PRIMARY_RESEARCH',
     'summary': 'The study finds variable AMACR sensitivity and explains why absent basal-cell staining alone is not necessarily diagnostic of cancer.',
     'limits': 'AMACR is not uniquely mandatory and no marker panel here certifies clinical diagnosis.'},
]

def applicability_context():
    """Fresh independent evidence/policy payload for the production score request."""
    context = {'version': VERSION, 'kind': 'SCOPED_EVIDENCE_AND_BENCHMARK_POLICY',
        'assessment_axes': ['target_identity', 'species_or_clone_reactivity',
            'tissue_cell_expression_and_specificity', 'sample_physical_properties',
            'task_required_function', 'processing_and_preservation_scope'],
        'evidence_states': ['SUPPORTED_FUNCTIONAL_ALTERNATIVE', 'OBSERVED_CONTRADICTION',
            'CONCRETE_LIMITED_APPLICABILITY', 'MISSING_RELEVANT_EVIDENCE', 'OUT_OF_SCOPE'],
        'co_method_bands': {'2': 'Functional applicable method or supported alternative',
            '1': 'Concrete limited applicability with useful function retained',
            '0': 'Established incompatibility or loss of a task-critical function',
            'null': 'Material unresolved applicability, not an automatic failure'},
        'sources': deepcopy(SOURCES), 'automatic_score_override': False,
        'changes_reference_or_sr': False, 'changes_alexa_policy': False,
        'scientific_or_clinical_certification': False}
    context['content_sha256'] = json_hash(context)
    return context

def applicability_prompt():
    return (Path(__file__).parent/'prompts/oeq_sample_marker_applicability_v4.txt').read_text()
