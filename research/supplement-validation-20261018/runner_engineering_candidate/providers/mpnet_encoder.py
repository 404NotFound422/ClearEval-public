#!/usr/bin/env python3
"""Real local MPNet provider. Requires independently verified preinstalled artifacts.
This script has NOT been executed in the candidate preparation stage.
"""
import hashlib,importlib.metadata,json,os,pathlib,platform,sys
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false')
HERE=pathlib.Path(__file__).resolve().parent

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    import numpy as np,torch
    from sentence_transformers import SentenceTransformer
    manifest=json.loads((HERE/'artifacts/model_manifest.json').read_text());lock=HERE/'requirements.lock.txt'
    if manifest['model_id']!='sentence-transformers/all-mpnet-base-v2':raise ValueError('Unexpected encoder model')
    packages={}
    for line in lock.read_text().splitlines():
        if line and not line.startswith('#'):
            name,version=line.split('==');packages[name]=importlib.metadata.version(name)
            if packages[name]!=version:raise ValueError('Package lock mismatch')
    snapshot=pathlib.Path(manifest['snapshot_path'])
    for item in manifest['files']:
        if sha(snapshot/item['path'])!=item['sha256']:raise ValueError('Model artifact mismatch')
    weights=next(r for r in manifest['files'] if r['path']=='model.safetensors')
    request=json.load(sys.stdin);texts=request['texts']
    if not texts or any(not isinstance(t,str) for t in texts):raise ValueError('Expected ordered text list')
    torch.set_num_threads(1);torch.manual_seed(0)
    model=SentenceTransformer(str(snapshot),device='cpu',local_files_only=True,trust_remote_code=False)
    model.max_seq_length=384;model.float();model.eval()
    with torch.no_grad():emb=model.encode(texts,batch_size=32,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    emb=np.asarray(emb,dtype=np.float32);cos=emb@emb.T;norms=np.linalg.norm(emb,axis=1)
    runtime={'model_id':manifest['model_id'],'model_revision':manifest['revision'],'dtype':'float32','normalization':'L2','dimensions':768,
       'max_seq_length':384,'device':'cpu','encoder_script_sha256':sha(__file__),'model_weights_sha256':weights['sha256'],
       'package_lock_sha256':sha(lock),'python':platform.python_version(),'packages':packages,'batch_size':32,'torch_num_threads':1}
    json.dump({'texts':texts,'ordered_texts_sha256':digest(texts),'embeddings':emb.tolist(),'cosine_similarity':cos.tolist(),'norms':norms.tolist(),'runtime':runtime},sys.stdout,ensure_ascii=False,allow_nan=False)
if __name__=='__main__':main()
