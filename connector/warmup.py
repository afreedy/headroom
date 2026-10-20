#!/usr/bin/env python3
"""One reset-aware pass; called by the Headroom heartbeat, not a polling LLM."""
import argparse, fcntl, hashlib, json, math, time
from datetime import datetime
from zoneinfo import ZoneInfo
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
    if primary.get('windowDurationMins')!=300 or not isinstance(reset,(int,float)) or reset<=0 or not isinstance(used,(int,float)):
        return False,None,now+900,'Five-hour window unavailable'
    if weekly.get('usedPercent',0) is not None and weekly.get('usedPercent',0)>=100:
        end=weekly.get('resetsAt')
        return False,None,max(now+900,end+GRACE if isinstance(end,(int,float)) else 0),'Weekly limit exhausted'
    anchor=previous.get('nextReset',reset)
    expired=reset+GRACE<=now
    unstarted=used==0 and reset>=now+300*60-120
    due=expired or (anchor+GRACE<=now and unstarted)
    key=reset if expired else anchor
    attempted=previous.get('attemptedReset')
    if due and attempted is not None and abs(attempted-key)<120:
        return False,key,now+1800,'Already attempted this reset; no duplicate sent'
    return due,key,max(now+120,reset+GRACE), 'Due' if due else 'Current window is already active'

def send_hi(rpc, workspace):
    models=rpc.call('model/list', {'limit':100,'includeHidden':False}).get('data',[])
    model=next((m for m in models if m.get('model')=='gpt-6-luna'),None) or next((m for m in models if m.get('isDefault')),None)
    if not model:raise RuntimeError('No supported Codex model returned.')
    efforts=[e.get('reasoningEffort') for e in model.get('supportedReasoningEfforts',[])]
    effort=next((e for e in ('minimal','low','medium') if e in efforts),model.get('defaultReasoningEffort','low'))
    thread=rpc.call('thread/start', {'model':model['model'],'cwd':str(workspace),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only','baseInstructions':'Reply exactly hi. Do not use tools.','developerInstructions':'','config':{'model_reasoning_effort':effort,'model_verbosity':'low'}})
    rpc.call('turn/start', {'threadId':thread['thread']['id'],'input':[{'type':'text','text':'hi'}],'effort':effort,'summary':'none'})
    if not rpc.turn_done.wait(90):raise RuntimeError('Message completion uncertain; no automatic resend for this reset.')
    turn=rpc.turn_result
    if turn.get('status')!='completed':raise RuntimeError((turn.get('error') or {}).get('message') or 'Message did not complete.')
    return model['model']

def run(execute=False, probe=None):
    targets=json.loads((DATA/'warmup-targets.json').read_text());state_path=DATA/'warmup-state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    workspace=DATA/'warmup-workspace';workspace.mkdir(exist_ok=True,mode=0o700)
    results=[];checks=[]
    for target in targets:
        ident=target['id'];previous=state.get(ident,{})
        if probe and probe!=ident:continue
        rpc=None
        try:
            rpc=Rpc(target.get('home'));bucket=read_account(rpc,ident);now=time.time()
            due,anchor,next_check,reason=plan(bucket,previous,now)
            entry=dict(previous);entry.pop('error',None)
            if due and execute or probe:
                # Persist intent before inference: a crash must not repeat a possibly completed request.
                if not probe:
                    entry.update(attemptedReset=anchor,outcome='pending',attemptedAt=now);state[ident]=entry;atomic_save(state_path,state)
                model=send_hi(rpc,workspace)
                after=read_account(rpc,ident);reset=(after.get('primary') or {}).get('resetsAt')
                confirmed=isinstance(reset,(int,float)) and reset>time.time()+60
                entry.update(outcome='completed' if confirmed else 'completed_reset_unconfirmed',lastCompletedAt=time.time(),model=model)
                if isinstance(reset,(int,float)):
                    entry['nextReset']=reset;next_check=max(time.time()+120,reset+GRACE)
                reason='hi completed; '+('reset timestamp read' if confirmed else 'new reset not confirmed')
            elif not due:
                reset=(bucket.get('primary') or {}).get('resetsAt')
                if isinstance(reset,(int,float)) and reset>now and reason!='Weekly limit exhausted':entry['nextReset']=reset
                entry.setdefault('outcome','waiting')
            entry['checkedAt']=time.time();state[ident]=entry
            results.append({'accountId':ident,'status':reason,'sendDue':due,'sent':bool((due and execute) or probe),'nextCheckAt':next_check})
            checks.append(next_check)
        except Exception as error:
            entry=state.get(ident,{})
            entry.update(error=str(error),checkedAt=time.time());state[ident]=entry
            results.append({'accountId':ident,'error':str(error),'sent':None if entry.get('outcome')=='pending' else False});checks.append(time.time()+900)
        finally:
            if rpc:rpc.close()
    atomic_save(state_path,state)
    next_at=math.ceil(max(time.time()+120,min(checks,default=time.time()+900))/60)*60
    local=datetime.fromtimestamp(next_at,ZoneInfo('Asia/Singapore'))
    return {'accounts':results,'nextCheckLocal':local.isoformat(),'rrule':f'RRULE:FREQ=DAILY;BYHOUR={local.hour};BYMINUTE={local.minute};BYSECOND=0'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--probe');args=p.parse_args()
    with (DATA/'warmup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        print(json.dumps(run(args.execute,args.probe)))
if __name__=='__main__':main()
