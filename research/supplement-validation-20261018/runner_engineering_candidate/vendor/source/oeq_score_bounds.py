"""Read-only mathematical diagnostics, not replacement benchmark point scores.

Uses the existing 0..6 label scale, min label, arithmetic-mean normalized E,
I_A=min(Com,Cor,Eff), and nonnegative HV=Com*Cor*Eff. Unknown bounds are
possible values, not imputed scores, confidence intervals, or probabilities.
"""
import math

VERSION='label-uncertainty-bounds-diagnostic-v3-specification-penalty'


class BoundsInputError(ValueError):
    """A diagnostic limitation, distinct from an out-of-scale numerical value."""
    def __init__(self, code, field, reason, fields=None):
        super().__init__(reason)
        self.code, self.field = code, field
        self.fields = fields or [field]


def _number(value,low,high,name):
    if value is None:
        raise BoundsInputError('MISSING_INPUT', name, name+' is unknown; label-only bounds require this input')
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise BoundsInputError('INVALID_INPUT_TYPE', name, name+' must be numeric')
    if not math.isfinite(value):
        raise BoundsInputError('NONFINITE_INPUT', name, name+' is not finite')
    if not low<=value<=high:
        raise BoundsInputError('OUT_OF_SCALE', name, name+' outside its existing finite scale')
    return float(value)


def label_bounds(components, specification_penalty=None):
    required={'task_coverage','necessary_signal_distinction','method_fluor_compatibility'}
    if set(components)!=required:raise ValueError('Expected the three revised label components')
    applicable=[];known=[];unknown=[];excluded=[];missing_spec=[]
    for name,row in components.items():
        status=row['status'];score=row['score']
        if row.get('disposition')=='NOT_ASSESSED_MISSING_SPEC':
            if name!='necessary_signal_distinction' or status!='UNKNOWN' or score is not None or row.get('assessability_reason')!='MISSING_SPEC':
                raise ValueError('Invalid missing-spec disposition')
            missing_spec.append(name);continue
        if status=='NOT_APPLICABLE':
            if score is not None:raise ValueError('N/A must not carry a score')
            excluded.append(name);continue
        if status=='UNKNOWN':
            if score is not None:raise ValueError('Unknown must not carry a score')
            applicable.append((0.,6.));unknown.append(name);continue
        if status not in {'SATISFIED','FAILED','TABLE_REPORTED'}:raise ValueError('Unrecognized component status')
        score=_number(score,0,6,name)
        if status=='SATISFIED' and score!=6:raise ValueError('Satisfied categorical endpoint must be 6')
        if status=='FAILED' and score!=0:raise ValueError('Failed categorical endpoint must be 0')
        applicable.append((score,score));known.append((name,score))
    if not applicable:raise ValueError('No applicable label criterion; aggregate N/A policy is undefined')
    bounds=[min(x[0] for x in applicable),min(x[1] for x in applicable)]
    pre_penalty_bounds=list(bounds)
    deduction=0.0
    if specification_penalty is not None:
        from oeq_practical_scoring import ALEXA_MISSING_MODEL_POLICY
        if specification_penalty.get('policy_version') != ALEXA_MISSING_MODEL_POLICY:
            raise ValueError('Unknown specification penalty policy')
        deduction=_number(specification_penalty.get('deduction'),0,1,'specification_penalty')
        if deduction not in (0,1):raise ValueError('Expected once-per-answer unit deduction')
        bounds=[max(0.0,x-deduction) for x in bounds]
    return {'bounds':bounds, 'pre_penalty_bounds':pre_penalty_bounds,
        'specification_deduction':deduction,'identified_value':bounds[0] if bounds[0]==bounds[1] else None,
        'observed_only_min':min(x[1] for x in known) if known else None,
        'observed_min_scope':'DIAGNOSTIC_ONLY_NOT_FULL_S_LABEL',
        'assessed_count':len(known),'applicable_count':len(applicable),
        'assessed_components':[x[0] for x in known],'unknown_components':unknown,
        'not_applicable_components':excluded,'missing_spec_components':missing_spec,
        'task_relevant_count':len(applicable)+len(missing_spec),
        'bounds_scope':'Conditional on missing-spec exclusion policy' if missing_spec else 'All applicable criteria',
        'coverage_meaning':'criterion count only; not reliability, probability, or a weighting factor'}


def diagnostic_bounds(record):
    raw=record['raw_scores'];calculated=record['calculated_scores']
    diagnostics=record['effectiveness_input']['label_diagnostics']
    label=label_bounds(diagnostics['components'],diagnostics.get('specification_penalty'))
    missing=[k for values,keys in [(raw,['s_method','s_trans','s_time']),
        (calculated,['Com','Cor'])] for k in keys if values.get(k) is None]
    if missing:
        raise BoundsInputError('MISSING_NONLABEL_COMPONENTS',missing[0],
            'Label-only bounds require known non-label inputs: '+', '.join(missing),missing)
    method=_number(raw['s_method'],-2.5,2.5,'s_method')
    trans=_number(raw['s_trans'],0,3,'s_trans');time=_number(raw['s_time'],0,3,'s_time')
    com=_number(calculated['Com'],0,1+0.4*8*2**-23,'Com')
    cor=_number(calculated['Cor'],0,1,'Cor')
    # Original signed method normalization and fixed four-way E average.
    constant=((method/2.5+1)/2+trans/3+time/3)/4
    eff=[constant+x/24 for x in label['bounds']]
    ia=[min(com,cor,x) for x in eff]
    hv=[com*cor*x for x in eff]
    return {'schema_version':VERSION,'question_id':record.get('question_id'),
        'label':label,'Eff_bounds':eff,'IA_bounds':ia,'HV_bounds':hv,
        'Eff_identified':eff[0] if eff[0]==eff[1] else None,
        'IA_identified':ia[0] if ia[0]==ia[1] else None,
        'HV_identified':hv[0] if hv[0]==hv[1] else None,
        'original_point_values_unchanged':{k:calculated.get(k) for k in ['Com','Cor','Eff','IA','HV']},
        'mathematical_basis':{'label':'min is coordinatewise nondecreasing on [0,6]',
            'Eff':'fixed nonnegative normalized average; label coefficient 1/24',
            'IA':'min is coordinatewise nondecreasing; equal endpoint minima identify value',
            'HV':'Com*Cor is nonnegative, so product is nondecreasing in Eff'},
        'scope':'Possible-score bounds conditional on retained judgments and existing numerical formulas; not statistical uncertainty or scientific certification',
        'scientific_certified':False,'replaces_point_scores':False}
