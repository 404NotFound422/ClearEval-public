"""Freeze a language intervention before any new vector calculation."""
import hashlib,json,re,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b

# Author translations preserve the original scientific choices, including
# contradictions with the reference. They are not independent expert labels.
BODIES={
'R3C04':[
'Soak in 20% (vol/vol) methanol/water solution with gentle shaking.',
'Soak in 40% (vol/vol) methanol/water solution with gentle shaking.',
'Soak in 60% (vol/vol) methanol/water solution with gentle shaking.',
'Soak in 80% (vol/vol) methanol/water solution with gentle shaking.',
'Soak in 100% (vol/vol) methanol with gentle shaking.',
'Soak again in fresh 100% (vol/vol) methanol.',
'Soak in 5% H2O2 in methanol (volume ratio: 30% H2O2 : methanol = 1 : 5), protected from light.',
'Soak in 80% (vol/vol) methanol/water solution.',
'Soak in 60% (vol/vol) methanol/water solution.',
'Soak in 40% (vol/vol) methanol/water solution.',
'Soak in 20% (vol/vol) methanol/water solution.',
'Soak in 1×PBS.',
'Permeabilization solution: PBS + 0.2% (vol/vol) Triton X-100 + 20% (vol/vol) DMSO + 0.3 M Glycine, with gentle shaking.',
'Blocking solution: PBS + 0.2% Triton X-100 + 10% (vol/vol) DMSO + 6% (vol/vol) normal donkey serum (NDS), with gentle shaking.',
'Primary antibody incubation solution: PBS + 0.2% Triton X-100 + 5% DMSO + 3% NDS + 0.01% (w/v) NaN3; add NeuN (RBFOX3) primary antibody at 1:200.',
'Add β-III Tubulin (TUJ1) primary antibody at 1:300 to the same incubation solution (may be co-incubated in the same tube with 5.1).',
'Wash solution: PBS + 0.2% Triton X-100 + 0.01% NaN3; change the solution with gentle shaking.',
'Repeat 6.1 for a total of 6 times (approximately 36 hours of washing in total).',
'Secondary antibody incubation solution: PBS + 0.2% Triton X-100 + 3% NDS + 0.01% NaN3; add donkey anti-mouse/rabbit Alexa Fluor 647 secondary antibodies at 1:400, matched to the primary antibody hosts (corresponding to NeuN and TUJ1 respectively; if the two primary antibodies have different hosts, they may be co-incubated in the same tube).',
'Wash in PBS + 0.2% Triton X-100 + 0.01% NaN3, changing the solution with gentle shaking.',
'Repeat 8.1 for a total of 6 times (approximately 36 hours of washing in total).',
'TO-PRO-3 at 1–2 µM (in PBS + 0.2% Triton X-100), with gentle shaking protected from light.',
'Wash 3 times in PBS.',
'20% methanol/water.',
'40% methanol/water.',
'60% methanol/water.',
'80% methanol/water.',
'100% methanol.',
'Fresh 100% methanol.',
'Soak in a mixture of 66% (vol/vol) dichloromethane (DCM)/33% methanol.',
'Soak in 100% DCM.',
'Pre-soak in 100% dibenzyl ether (DBE, RI≈1.56).',
'Continue soaking in fresh 100% DBE until completely transparent (usually needed for a whole brain).',
'Keep the sample fully immersed in fresh 100% DBE, sealed and protected from light for storage (fill the container as much as possible to reduce oxidation).',
'Before light-sheet imaging, replace with fresh DBE once and let stand for bubble removal/settling.',
'Match the imaging medium to the objective: use a DBE-compatible imaging chamber and sealing materials for RI≈1.56; after fixing the sample to the holder, proceed directly to whole-brain light-sheet scanning.'
],
'R3C07':[
'Place the adult mouse whole brain already fixed in 4% PFA into 1× PBS and rinse thoroughly to remove residual fixative.',
'Place the brain tissue in 1× PBS containing 0.2% (vol/vol) Triton X-100 (PBST) and permeabilize with shaking.',
'Replace with fresh PBST and continue permeabilization.',
'Place the brain tissue in blocking solution (5% (vol/vol) normal donkey serum + 0.2% Triton X-100 + 0.1% (wt/vol) NaN₃ in 1× PBS) and block with shaking.',
'Place the brain tissue in a solution containing rabbit polyclonal anti-β-III Tubulin (TUJ1) antibody (1:500 diluted in blocking solution), and incubate with gentle shaking.',
'Wash with PBST to remove unbound primary antibody.',
'Place the brain tissue in a solution containing donkey anti-rabbit Alexa Fluor 647 secondary antibody (1:500 diluted in blocking solution), and incubate with shaking protected from light.',
'Wash with PBST to remove unbound secondary antibody.',
'Perform a final wash with 1× PBS.',
'Place the brain tissue in 50% (vol/vol) aqueous THF (tetrahydrofuran), adjusted with NaOH to pH 9–10 to protect fluorescent proteins, and dehydrate with shaking.',
'Place the brain tissue in 70% (vol/vol) aqueous THF (pH 9–10), and dehydrate with shaking.',
'Place the brain tissue in 80% (vol/vol) aqueous THF (pH 9–10), and dehydrate with shaking.',
'Place the brain tissue in 100% THF (anhydrous, pH 9–10, with a small amount of NaOH), and dehydrate with shaking for the first time.',
'Place the brain tissue in 100% THF (anhydrous, pH 9–10), and dehydrate with shaking for the second time (replacing with fresh THF).',
'Place the brain tissue in BABB (benzyl alcohol:benzyl benzoate = 1:2, vol/vol) with shaking to complete delipidation and begin RI matching, until completely transparent (usually 30–60 min).',
'Transfer the transparent brain tissue into fresh BABB (RI ≈ 1.56) and let equilibrate without agitation, protected from light, ensuring that the tissue is completely transparent and free of bubbles.',
'Replace with fresh BABB again, confirm complete tissue transparency, and prepare for imaging.',
'Transfer the transparent brain tissue into BABB in a light-sheet microscope sample chamber, use a refractive-index-matched immersion medium (RI = 1.56) to secure the sample position, and avoid bubbles.',
'If short-term storage is needed, seal the sample in BABB and store at 4 ℃ protected from light (imaging within 1 week is recommended to avoid fluorescent signal decay).'
]}

details={r['anonymous_answer_id']:r for r in b.read(R3/'confirmation_inputs_01/selected_step_details.json')}
cases={r['anonymous_answer_id']:r for r in b.read(R3/'confirmation_qwen_01/cases.json')['cases']}
records=[];checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
# Unicode digits and reference-step numbers are retained, not normalized away.
numbers=lambda text:Counter(re.findall(r'\d+(?:\.\d+)?',text))
for aid,bodies in BODIES.items():
    d,c=details[aid],cases[aid]
    check('step_count:'+aid,len(bodies)==len(d['generated_steps']))
    check('original_answer:'+aid,hashlib.sha256(c['model_response'].encode('utf-8')).hexdigest()==c['answer_sha256'])
    for i,(source,body) in enumerate(zip(d['generated_steps'],bodies)):
        split=source['text'].index('(Temperature:');original_body=source['text'][:split];suffix=source['text'][split:]
        translated=body+suffix
        check('numeric_tokens:'+aid+':'+str(i),numbers(source['text'])==numbers(translated))
        check('metadata_verbatim:'+aid+':'+str(i),translated[translated.index('(Temperature:'):]==suffix)
        check('source_span:'+aid+':'+str(i),source['text'] in c['model_response'][source['start']:source['end']])
        records.append({'answer_id':aid,'step_index':i,'source':source,'english_body_original_metadata':translated,
            'original_body':original_body,'metadata_suffix':suffix,'question_id':c['question_id'],
            'source_answer_sha256':c['answer_sha256'],'translation_author':'current assistant',
            'expert_verified':False,'no_new_model_request':True})
# The original truncated answer is the fixed negative example, not a synthetic
# replacement of a complete step; it keeps the identical frozen candidate pool.
negative=details['R3C03'];check('truncated_example_one_step',len(negative['generated_steps'])==1)
freeze={'created_utc':datetime.now(timezone.utc).isoformat(),'representation_conditions':['original','english_body_original_metadata'],
    'translated_answers':['R3C04','R3C07'],'translated_steps':len(records),'negative_answer':'R3C03',
    'negative_step':negative['generated_steps'][0],
    'thresholds':[.6,.7,.8],'primary_threshold':.7,'reference_pool':'exact original task/method-compatible whole-reference candidates',
    'selection':'maximum SR, same-reference SP, fixed order','encoder':'exact original local all-mpnet-base-v2',
    'new_evaluator_requests_allowed':0,'new_local_embedding_vectors':'only the 55 frozen translated steps if absent in cache',
    'no_threshold_selection':True,'scientific_errors_preserved':['C07 BABB retained, not replaced with reference DBE',
        'C07 NaOH and pH 9–10 retained, not changed to triethylamine pH 9.0','original durations retained, not corrected to reference'],
    'fidelity_checks':['55 numeric-token multisets','55 exact Temperature/Time metadata suffixes','55 original source spans'],
    'primary_outcomes':['per-reference maximum and best matching source text','SR/SP and reference selection','UNK counts and truncation',
        'changed reference hits with explicit solvent/duration conflicts retained for inspection'],
    'hypotheses':{'H_language':'English re-expression may alter matching without changing scientific choices; direction and magnitude reported unscreened',
        'H_not_sufficient':'Improved match coverage does not prove solvent/parameter discrimination or correct ordering',
        'H_negative':'Lowering threshold can give positive coverage to the already truncated generic clause; reproduce existing scores'},
    'success_criteria':'source-faithful intervention and falsifiable mechanism evidence; no requirement that all translated scores improve',
    'exposure':'already exposed development answers; no independent accuracy claim','expert_review_budget_unchanged':'one expert 5+15',
    'evaluation_scope':'step representation only; no fresh full-pipeline judge or revised Cor',
    'literature':[{'title':'Making Monolingual Sentence Embeddings Multilingual using Knowledge Distillation','url':'https://aclanthology.org/2020.emnlp-main.365/','use':'motivates cross-language alignment; no multilingual model installed or trained here'},
        {'title':'Beyond Accuracy: Behavioral Testing of NLP Models with CheckList','url':'https://aclanthology.org/2020.acl-main.442/','use':'same-content language intervention plus incomplete-clause negative example'}]}
assert not (OUT/'frozen_inputs.json').exists()
b.save(OUT/'translations.json',records);b.save(OUT/'plan.json',freeze)
b.save(OUT/'translation_checks.json',{'checks_passed':len(checks),'checks':checks,'not_independent_semantic_verification':True})
sourcefiles=[Path(__file__),OUT/'translations.json',OUT/'plan.json',R3/'confirmation_inputs_01/selected_step_details.json',
    R3/'confirmation_qwen_01/cases.json',R3/'confirmation_qwen_01/steps.json',ROOT/'scripts/cce_validation.py']
ledger=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
b.save(OUT/'frozen_inputs.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'inputs':[b.bind(p) for p in sourcefiles],
    'ledger':b.bind(ledger),'request_count':len(ledger.read_text('utf-8').splitlines()),'pre_vector_calculation':True,
    'command':[sys.executable,*sys.argv]})
print(json.dumps({'translated_steps':len(records),'checks':len(checks),'new_evaluator_requests':0,'freeze_written':True}))
