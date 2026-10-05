"""Standalone Chinese review form; no network or hidden expected labels."""
import json
from pathlib import Path
from .contract import read

def create_html(package):
    package=Path(package)
    data=json.dumps({"packet":read(package/"public/cases.json"),"template":read(package/"public/ratings_template.json")},ensure_ascii=False).replace("<","\\u003c")
    html=r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>匿名方案独立审阅</title><style>
body{font:16px/1.7 system-ui,'Microsoft YaHei',sans-serif;background:#f3f6f8;color:#183243;margin:0}main{max-width:980px;margin:auto;padding:24px}
section,.item{background:white;border:1px solid #dbe4ea;border-radius:8px;padding:18px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 monospace;background:#f4f7f9;padding:12px}
input,textarea,select{font:inherit;width:100%;box-sizing:border-box;padding:8px;margin:5px 0 12px;border:1px solid #9aaebc;border-radius:4px}textarea{min-height:70px}label{display:block}
button{padding:10px 18px;background:#176d87;color:white;border:0;border-radius:4px;font:inherit;margin-right:8px;cursor:pointer}.bar{position:sticky;top:0;background:#f3f6f8f5;padding:12px}details{margin:10px 0}summary{cursor:pointer}h1{font-size:28px}h2{font-size:20px}h3{font-size:17px}
</style><main><h1>匿名方案独立审阅</h1>
<p>请按任务、原文和可核验文献独立判断。未确认的项目可暂不填写；本页完全在本机运行，不会自动发送内容。请勿在初评前查看自动评分或其他评阅者标签。</p>
<div class="bar"><span id="progress"></span><br><button id="download">下载审阅 JSON</button><button id="save">保存本机草稿</button><span id="message"></span></div>
<section><h2>评阅者信息</h2><div id="background"></div></section>
<section><h2>判定说明</h2><p>满足：本项有支持。违反：有明确矛盾的行为或错误身份/符合性声明。信息不足：必要操作或细节缺失，包括明确省略。证据未决：科学支持或适用性不足、冲突。可对暂定要求提出异议，无需迎合它。</p></section>
<div id="cases"></div></main><script id="data" type="application/json">DATAHERE</script><script>
const data=JSON.parse(document.getElementById('data').textContent),key='cleareval-review-'+data.template.package_sha256;
let form=data.template;
try{const old=JSON.parse(localStorage.getItem(key));if(old&&old.package_sha256===form.package_sha256)form=old;}catch(e){}
function el(tag,text,parent){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(parent)parent.appendChild(x);return x;}
function field(parent,label,value,setter,type='textarea'){const l=el('label',label,parent),x=el(type,undefined,l);x.value=value??'';x.oninput=()=>{setter(x.value);progress();};}
function choice(parent,label,value,setter,options){const l=el('label',label,parent),s=el('select',undefined,l);for(const [v,t] of options){const o=el('option',t,s);o.value=v;}s.value=value??'';s.onchange=()=>{setter(s.value||null);progress();};}
const bg=document.getElementById('background');
for(const [k,l] of [['id','评阅者代号'],['expertise','领域经验'],['method_familiarity','方法熟悉程度']])field(bg,l,form.reviewer[k],v=>form.reviewer[k]=v,'input');
for(const [k,l] of [['participated_in_task_design','是否参与本组任务设计'],['saw_automatic_judgments','是否已看过本组自动判定'],['saw_other_raters','是否已看过其他评阅者判定']])
choice(bg,l,form.reviewer[k]===null?'':String(form.reviewer[k]),v=>form.reviewer[k]=v===null?null:v==='true',[['','请选择'],['false','否'],['true','是']]);
const states=[['','尚未填写'],['SATISFIED','满足'],['VIOLATED','违反'],['UNDER_SPECIFIED','信息不足'],['UNRESOLVED','证据未决']];
for(const c of data.packet.cases){
const box=el('section',undefined,document.getElementById('cases'));el('h2',c.review_id,box);
const q=el('details',undefined,box);el('summary','任务',q);el('pre',c.question,q);
const p=el('details',undefined,box);p.open=true;el('summary','方案原文',p);el('pre',c.protocol,p);
const sources=el('details',undefined,box);el('summary','核查文献目录',sources);
for(const s of c.sources){
const x=el('p',undefined,sources),sourceUrl=s.identity?.url||s.url;
if(sourceUrl&&/^https?:\/\//.test(sourceUrl)){const a=el('a',s.source||s.id,x);a.href=sourceUrl;a.target='_blank';a.rel='noopener noreferrer';}
else el('span',s.source||s.id,x);
const locator=typeof s.locator==='object'?JSON.stringify(s.locator):s.locator;
el('span',' '+(locator||'')+(s.identity?.version?' [version '+s.identity.version+']':''),x);
for(const passage of s.passages||[]){const d=el('details',undefined,sources);el('summary','Primary passage '+passage.id,d);el('pre',passage.quote,d);}
for(const correction of s.identity?.correction_chain||[]){const d=el('details',undefined,sources);el('summary','Correction '+correction.version,d);el('pre',correction.text,d);}
}
for(const req of c.requirements){
const r=form.ratings.find(x=>x.review_id===c.review_id&&x.requirement_id===req.id),item=el('div',undefined,box);item.className='item';el('h3',req.id+' · '+req.text,item);
choice(item,'判定',r.status,v=>r.status=v,states);
field(item,'理由',r.reason,v=>r.reason=v);
field(item,'方案原文引文（每行一段，逐字复制）',r.protocol_quotes.join('\n'),v=>r.protocol_quotes=v.split('\n').filter(x=>x.trim()));
field(item,'文献链接（每行一个）',r.evidence_urls.join('\n'),v=>r.evidence_urls=v.split('\n').filter(x=>x.trim()));
field(item,'对要求本身的异议或适用限制（可选）',r.requirement_dispute,v=>r.requirement_dispute=v||null);
}}
function progress(){document.getElementById('progress').textContent='已填判定与理由 '+form.ratings.filter(r=>r.status&&r.reason&&r.reason.trim()).length+' / '+form.ratings.length+' 项';}
document.getElementById('save').onclick=()=>{localStorage.setItem(key,JSON.stringify(form));document.getElementById('message').textContent='已保存';};
document.getElementById('download').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(form,null,2)+'\n'],{type:'application/json;charset=utf-8'}));a.download='ratings_'+(form.reviewer.id||'draft')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};progress();
</script></html>"""
    (package/"public/review.html").write_text(html.replace("DATAHERE",data),encoding="utf-8")
