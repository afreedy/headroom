"""Local warmup receipts. Only explicit warmup evidence is retained."""
import json, time, threading
LOCK=threading.RLock()
from pathlib import Path

def write_receipt(data, receipt):
    folder=Path(data)/'warmup-runs'/receipt['accountId']
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(receipt['id']+'.json')
    with LOCK:
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(receipt));temp.chmod(0o600);temp.replace(path)

def history(data, account, state):
    folder=Path(data)/'warmup-runs'/account
    runs=[json.loads(p.read_text()) for p in folder.glob('*.json')]
    # Old ephemeral turns did not retain transcript or RPC identifiers.
    completed=state.get('lastCompletedAt')
    if completed and not any(r.get('completedAt')==completed for r in runs):
        legacy={'id':'legacy-'+str(completed),'accountId':account,'startedAt':state.get('attemptedAt'),
                     'completedAt':completed,'model':state.get('model'),'status':'completed',
                     'evidence':'legacy','request':None,'response':None,
                     'notice':'Legacy ledger records completion and model only. Exact request, response, thread ID and turn ID were not retained.'}
        write_receipt(data,legacy);runs.append(legacy)
    return sorted(runs,key=lambda r:r.get('startedAt') or r.get('completedAt') or 0,reverse=True)

def capture(receipt, method, params):
    """Allowlist answer events; never retain auth messages or reasoning traces."""
    if params.get('threadId') and params['threadId'] != receipt.get('threadId'):return
    receipt.setdefault('events',[])
    event={'at':time.time(),'method':method}
    if method=='item/completed':
        item=params.get('item') or {}
        if item.get('type')=='agentMessage':
            messages=receipt.setdefault('messages',{})
            messages[item['id']]={'text':item.get('text',''),'phase':item.get('phase')}
            receipt['response']='\n'.join(m['text'] for m in messages.values())
            event['item']={k:item.get(k) for k in ('id','type','text','phase')}
        else:
            event['item']={k:item.get(k) for k in ('id','type','status')}
    elif method=='thread/tokenUsage/updated':
        receipt['tokenUsage']=params.get('tokenUsage');event['tokenUsage']=receipt['tokenUsage']
    elif method=='model/rerouted':
        event.update({k:params.get(k) for k in ('fromModel','toModel','reason')})
        receipt['routedModel']=params.get('toModel')
    elif method=='turn/completed':
        turn=params.get('turn') or {};receipt['turnId']=turn.get('id',receipt.get('turnId'))
        receipt['completionStatus']=turn.get('status');receipt['completionError']=turn.get('error')
        event['turn']={k:turn.get(k) for k in ('id','status','error')}
    else:return
    receipt['events'].append(event)

def update(data, receipt, **changes):
    with LOCK:
        receipt.update(changes);write_receipt(data,receipt)

def record_event(data, receipt, method, params):
    with LOCK:
        capture(receipt,method,params);write_receipt(data,receipt)
