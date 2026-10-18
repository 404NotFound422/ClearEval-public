#!/usr/bin/env python3
"""Opt-in OpenAI-compatible chat-completions transport; never invoked by prepare/tests.
Endpoint, existing credential environment variable and model must be explicitly configured.
No credential is persisted, echoed, created or included in the retained response.
"""
import json,os,sys,urllib.request,urllib.parse

def main():
    request=json.load(sys.stdin)
    endpoint=os.environ.get('CLEAREVAL_JUDGE_ENDPOINT','')
    parsed=urllib.parse.urlsplit(endpoint)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('An explicit HTTPS API endpoint without embedded credentials is required')
    key_env=os.environ.get('CLEAREVAL_JUDGE_KEY_ENV','')
    if not key_env or not os.environ.get(key_env):raise ValueError('Existing credential environment variable is unavailable')
    params=request['parameters']
    if set(params)-{'temperature','top_p','max_tokens','seed','response_format'}:raise ValueError('Unsupported judge parameters')
    if type(params.get('max_tokens')) is not int or not 1<=params['max_tokens']<=32768:raise ValueError('Bounded max_tokens required')
    body={'model':request['model'],'messages':[{'role':'user','content':request['prompt']}],**params}
    if params.get('response_format')=='json_schema':
        body['response_format']={'type':'json_schema','json_schema':{'name':'cleareval_output','strict':False,'schema':request['schema']}}
    elif params.get('response_format')=='json_object':body['response_format']={'type':'json_object'}
    elif 'response_format' in params:raise ValueError('Unknown response format')
    req=urllib.request.Request(endpoint,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ[key_env],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=int(os.environ.get('CLEAREVAL_JUDGE_TIMEOUT','600'))) as response:
        result=json.loads(response.read(64*1024*1024))
    choice=result['choices'][0]
    if choice.get('finish_reason') not in ['stop',None]:raise ValueError('Provider response incomplete: '+str(choice.get('finish_reason')))
    text=choice['message']['content']
    if not isinstance(text,str):raise ValueError('Provider returned no textual response')
    json.dump({'model':result['model'],'provider_request_id':result['id'],'text':text,'usage':result.get('usage'),'provider_response':result},sys.stdout,ensure_ascii=False)
if __name__=='__main__':main()
