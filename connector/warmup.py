#!/usr/bin/env python3
"""Per-account warmup planning owned by Headroom's local connector."""
import hashlib, json, time, math, uuid
from receipts import write_receipt, capture, update, record_event
from pathlib import Path
from server import DATA, Rpc

GRACE = 30

def atomic_save(path, value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value));tmp.chmod(0o600);tmp.replace(path)

def read_account(rpc, expected):
    account=rpc.call('account/read', {'refreshToken':False}).get('account')
    limits=rpc.call('account/rateLimits/read')
    if not account or account.get('type')!='chatgpt':raise RuntimeError('ChatGPT sign-in required; no API-key fallback.')
    identity=limits.get('accountId') or account.get('email')
    if not identity or hashlib.sha256(identity.encode()).hexdigest()[:20]!=expected:
        raise RuntimeError('Account identity changed. Sign into the original account; nothing was sent.')
    bucket=(limits.get('rateLimitsByLimitId') or {}).get('codex') or limits.get('rateLimits') or {}
    return bucket

def plan(bucket, previous, now):
    primary=bucket.get('primary') or {}; weekly=bucket.get('secondary') or {}
    reset=primary.get('resetsAt');used=primary.get('usedPercent')
    if primary.get('windowDurationMins')!=300 or not isinstance(reset,(int,float)) or reset<=0 or not isinstance(used,(int,float)) or not math.isfinite(reset) or not math.isfinite(used) or not 0 <= used <= 100:
        return False,None,now+900,'Five-hour window unavailable'
    if not isinstance(weekly.get('usedPercent'), (int,float)) or not math.isfinite(weekly['usedPercent']) or not 0 <= weekly['usedPercent'] <= 100:
        return False,None,now+60,'Weekly quota unavailable'
    if weekly['usedPercent']>=100:
        end=weekly.get('resetsAt')
        return False,None,max(now+900,end+GRACE if isinstance(end,(int,float)) else 0),'Weekly limit exhausted'
    anchor=previous.get('nextReset',reset)
    expired=reset+GRACE<=now
    unstarted=used==0 and reset>=now+300*60-120
    due=expired or (anchor+GRACE<=now and unstarted)
    key=reset if expired else anchor
    attempted=previous.get('attemptedReset')
    if due and attempted is not None and (abs(attempted-key)<120 or previous.get('outcome') in ('pending','uncertain') and key <= attempted+300*60):
        return False,key,now+1800,'Already attempted this reset; no duplicate sent'
    return due,key,max(now+120,reset+GRACE), 'Due' if due else 'Current window is already active'

def send_hi(rpc, workspace, receipt=None, persist=None):
    models=rpc.call('model/list', {'limit':100,'includeHidden':False}).get('data',[])
    model=next((m for m in models if m.get('model')=='gpt-6-luna'),None) or next((m for m in models if m.get('isDefault')),None)
    if not model:raise RuntimeError('No supported Codex model returned.')
    efforts=[e.get('reasoningEffort') for e in model.get('supportedReasoningEfforts',[])]
    effort=next((e for e in ('minimal','low','medium') if e in efforts),model.get('defaultReasoningEffort','low'))
    if receipt is not None:
        update(DATA,receipt,model=model['model'], reasoningEffort=effort, request='hi', instructions='Reply exactly hi. Do not use tools.', sandbox='read-only', ephemeral=True)
        persist()
    thread=rpc.call('thread/start', {'model':model['model'],'cwd':str(workspace),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only','baseInstructions':'Reply exactly hi. Do not use tools.','developerInstructions':'','config':{'model_reasoning_effort':effort,'model_verbosity':'low'}})
    if receipt is not None:
        update(DATA,receipt,threadId=thread['thread']['id'],requestedModel=model['model'],reportedModel=thread.get('model'));persist()
        def event(method, params):
            record_event(DATA,receipt,method,params)
        rpc.capture_event=event
    started=rpc.call('turn/start', {'threadId':thread['thread']['id'],'input':[{'type':'text','text':'hi'}],'effort':effort,'summary':'none'})
    if receipt is not None:
        update(DATA,receipt,turnId=(started.get('turn') or {}).get('id',receipt.get('turnId')));persist()
    if not rpc.turn_done.wait(90):raise RuntimeError('Message completion uncertain; no automatic resend for this reset.')
    turn=rpc.turn_result
    if receipt is not None:
        if not receipt.get('completionStatus'):
            record_event(DATA,receipt,'turn/completed',{'threadId':receipt['threadId'],'turn':turn})
    if turn.get('status')!='completed':raise RuntimeError((turn.get('error') or {}).get('message') or 'Message did not complete.')
    return model['model']

def process_account(rpc, row, state, state_path):
    """Uses a fresh identity-checked snapshot; persist intent before any inference."""
    ident = row['id']; previous = state.get(ident, {})
    bucket = (row.get('buckets') or {}).get('codex') or {}
    now = time.time(); due, anchor, next_check, reason = plan(bucket, previous, now)
    entry = dict(previous)
    if previous.get('outcome') not in ('pending','uncertain'): entry.pop('error', None)
    if previous.get('outcome') in ('pending','uncertain') and reason.startswith('Already attempted'):
        reason = 'Completion uncertain; no resend for this window'
    entry.update(checkedAt=now, nextCheckAt=next_check, status=reason)
    state[ident] = entry
    if not due:
        reset = (bucket.get('primary') or {}).get('resetsAt')
        if isinstance(reset, (int,float)) and reset > now and reason == 'Current window is already active':
            entry['nextReset'] = reset
        atomic_save(state_path, state)
        return
    workspace = DATA/'warmup-workspace'; workspace.mkdir(exist_ok=True, mode=0o700)
    entry.update(attemptedReset=anchor, outcome='pending', attemptedAt=now, status='Sending hi')
    atomic_save(state_path, state)
    try:
        receipt={'id':uuid.uuid4().hex,'accountId':ident,'startedAt':now,'resetDueAt':anchor,
                 'status':'pending','evidence':'recorded','request':'hi','response':None,'before':bucket}
        entry['lastRunId']=receipt['id']
        atomic_save(state_path,state)
        def persist(): write_receipt(DATA,receipt)
        persist()
        model = send_hi(rpc, workspace, receipt, persist)
    except Exception as error:
        if 'receipt' in locals():
            update(DATA,receipt,status='failed' if receipt.get('completionStatus')=='failed' else 'uncertain',error=str(error),finishedAt=time.time());persist()
        entry.update(outcome='uncertain', status='Warmup needs attention; no resend for this window', error=str(error), nextCheckAt=time.time()+1800)
        atomic_save(state_path, state)
        return
    completed=time.time()
    update(DATA,receipt,status='completed',completedAt=completed,durationMs=round((completed-now)*1000));persist()
    entry.update(outcome='completed', lastCompletedAt=completed, model=model, status='hi completed')
    # Record completion before the follow-up read; quota failure must not undo it.
    atomic_save(state_path, state)
    try:
        after = read_account(rpc, ident)
        row['buckets']['codex'] = after; row['updatedAt'] = time.time()
        update(DATA,receipt,after=after);persist()
        reset = (after.get('primary') or {}).get('resetsAt')
        if isinstance(reset, (int,float)) and reset > time.time():
            entry.update(nextReset=reset, nextCheckAt=reset+GRACE)
        else:
            entry.update(status='hi completed; reset time unconfirmed', nextCheckAt=time.time()+60)
    except Exception as error:
        update(DATA,receipt,quotaRefreshError=str(error));persist()
        entry.update(status='hi completed; quota refresh failed', error=str(error), nextCheckAt=time.time()+60)
    atomic_save(state_path, state)

if __name__ == '__main__':
    raise SystemExit('Warmups are managed by the Headroom connector. Start server.py instead.')
