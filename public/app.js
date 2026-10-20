import { remaining, resetText, duration, stale, eligible, expiryText, freshReading, currentWindow } from './usage.js';
const $ = id => document.getElementById(id);
let key = localStorage.getItem('headroom-pair') || '';
const hash = new URLSearchParams(location.hash.slice(1));
if(hash.has('pair')){ key = hash.get('pair'); localStorage.setItem('headroom-pair', key); history.replaceState(null,'',location.pathname); }
let accounts = [], activeId = null, connected = false, busy = false;
try { accounts = JSON.parse(localStorage.getItem('headroom-snapshots') || '[]'); } catch {}
let histories = {};
let names = {};
try { names = JSON.parse(localStorage.getItem('headroom-names') || '{}'); } catch {}
const accountName = (a,i) => names[a.id] || `Account ${i+1}`;
const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fullDate = ts => Number.isFinite(ts) && ts > 0 ? new Date(ts*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Unavailable';
const age = ts => !ts ? 'Never synced' : Date.now()-ts*1000 < 60000 ? 'Just now' : `${Math.floor((Date.now()-ts*1000)/60000)}m ago`;
function toast(text){ $('toast').textContent=text; $('toast').style.display='block'; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').style.display='none',6500); }
function openConnection(){ $('dialog').showModal(); }
function getBucket(a){ return a.buckets?.codex || Object.values(a.buckets || {}).find(Boolean) || {}; }
function meter(w, large=false){ const r=remaining(w);return large? `<div class="segments" aria-hidden="true">${Array.from({length:40},(_,i)=>`<i class="${r!==null && i<Math.round(r/2.5)?'filled':''}"></i>`).join('')}</div>`:`<div class="bar" aria-hidden="true"><span style="width:${r??0}%"></span></div>`; }
function resetLine(w){return `<div class="reset-line"><span>${w?.resetsAt?'Resets '+escape(fullDate(w.resetsAt)):'Reset time unavailable'}</span><time>${escape(resetText(w?.resetsAt))}</time></div>`;}
function weekly(w){return `<div class="weekly"><div class="weekly-top"><span>${escape(duration(w?.windowDurationMins))}</span><strong>${remaining(w)??'—'}${remaining(w)!==null?'%':''} left</strong></div>${meter(w)}${resetLine(w)}</div>`;}
function bankedResets(a, expanded){
 const count = a.resetCredits;
 if(count === null || count === undefined) return '';
 if(count === 0) return '<div class="reset-inventory"><span>No banked resets available</span></div>';
 const credits=a.resetCreditDetails;
 return `<details class="reset-inventory" data-account="${escape(a.id)}" ${expanded.has(a.id)?'open':''}><summary>${escape(count)} banked reset${count===1?'':'s'} <span>View expiry dates ＋</span></summary><div class="reset-list">${credits?.length?credits.map((c,i)=>`<div class="credit-row"><div><strong>${escape(c.title || `Banked reset ${i+1}`)}</strong><span>${c.expiresAt?'Expires '+escape(fullDate(c.expiresAt)):'Expiry not provided by Codex'}</span></div><span>${escape(expiryText(c.expiresAt))}</span></div>`).join(''):'<p>Codex returned the available count without individual expiry details.</p>'}${credits?.length && credits.length < count?'<p>Only '+credits.length+' of '+escape(count)+' reset details were returned by Codex.</p>':''}</div></details>`;
}
const preciseDate = ts => ts ? new Date(ts*1000).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'long'}) : 'Not retained';
function historyMarkup(a, expanded){
 const runs=histories[a.id];
 return `<details class="warmup-history" data-history="${escape(a.id)}" ${expanded.has(a.id)?'open':''}><summary>Warmup runs <span>${a.warmup?.latestRun?escape(a.warmup.latestRun.status)+' · ':''}View evidence ＋</span></summary><div class="run-list">${!runs?'<p>Loading recorded runs…</p>':runs.error?`<p class="error">${escape(runs.error)}</p>`:!runs.length?'<p>No warmup attempts recorded yet.</p>':runs.map(r=>`<details class="run" data-run-id="${escape(r.id)}"><summary><strong>${escape(r.evidence==='legacy'?'Legacy completion · limited evidence':r.status)}</strong><span>${escape(preciseDate(r.startedAt||r.completedAt))}</span></summary>${r.notice?`<p class="error">${escape(r.notice)}</p>`:''}<dl><dt>Trigger</dt><dd>${escape(r.trigger||'Automatic reset warmup')}</dd><dt>Model</dt><dd>${escape(r.model||'Not retained')}${r.routedModel?' → '+escape(r.routedModel):''}</dd><dt>Reasoning effort</dt><dd>${escape(r.reasoningEffort||'Not retained')}</dd><dt>Started</dt><dd>${escape(preciseDate(r.startedAt))}</dd><dt>Completed</dt><dd>${escape(preciseDate(r.completedAt))}</dd><dt>Duration</dt><dd>${r.durationMs!==undefined?escape((r.durationMs/1000).toFixed(3))+' seconds':'Not retained'}</dd><dt>Thread ID</dt><dd>${escape(r.threadId||'Not retained')}</dd><dt>Turn ID</dt><dd>${escape(r.turnId||'Not retained')}</dd><dt>Runtime status</dt><dd>${escape(r.completionStatus||'Not retained')}</dd></dl><div class="transcript"><strong>Exact request</strong><pre>${escape(r.request??'Not retained')}</pre><strong>Exact response</strong><pre>${escape(r.response??(r.status==='pending'?'Waiting for response':'Not retained'))}</pre></div>${r.error||r.completionError||r.quotaRefreshError?`<p class="error">${escape(r.error||r.completionError?.message||r.quotaRefreshError)}</p>`:''}${r.tokenUsage?`<p class="run-tokens">Reported tokens: ${escape(r.tokenUsage.last?.inputTokens??'—')} input · ${escape(r.tokenUsage.last?.outputTokens??'—')} output · ${escape(r.tokenUsage.last?.cachedInputTokens??'—')} cached input</p>`:''}<details data-receipt-id="${escape(r.id)}"><summary>Full receipt · quota snapshots and events</summary><pre class="receipt-json">${escape(JSON.stringify(r,null,2))}</pre></details><button class="outline-button" data-download="${escape(a.id)}" data-run="${escape(r.id)}">Download receipt JSON</button></details>`).join('')}</div></details>`;
}
async function loadHistory(id){
 try{histories[id]=(await request('/runs?account='+encodeURIComponent(id))).runs;}
 catch(e){histories[id]={error:e.message};}
 render();
}
function empty(i){return `<article class="account empty"><div class="account-top"><div class="account-title"><span class="avatar">${i+1}</span><h2>Account ${i+1}</h2></div><span class="badge">Not connected</span></div><div class="big-label">Usage unavailable</div><div class="reading"><div class="number">—<small>%</small></div></div><p class="empty-note">Connect an account to view limits and resets.</p><button class="empty-action" data-connect>Connect account ＋</button></article>`;}
function render(){
 const historyExpanded=new Set([...document.querySelectorAll('.warmup-history[open]')].map(el=>el.dataset.history));
 const openReceipts=new Set([...document.querySelectorAll('[data-receipt-id][open]')].map(el=>el.dataset.receiptId));
 const openRuns=new Set([...document.querySelectorAll('.run[open]')].map(el=>el.dataset.runId));
 const expanded = new Set([...document.querySelectorAll('.reset-inventory[open]')].map(el=>el.dataset.account));
 $('accounts').innerHTML = accounts.map((a,i)=>{
 const fresh=freshReading(a,connected),bucket=fresh?getBucket(a):{},primary=currentWindow(bucket.primary), secondary=currentWindow(bucket.secondary), r=remaining(primary);
 const status=a.needsLogin?'Sign-in required':a.error?'Refresh failed':!fresh?'Saved reading':'Connected';
 return `<article class="account"><div class="account-top"><div class="account-title"><span class="avatar">${escape((a.email || `Account ${i+1}`)[0].toUpperCase())}</span><div><h2>${escape(accountName(a,i))} <button class="rename" data-rename="${escape(a.id)}" aria-label="Rename ${escape(accountName(a,i))}" title="Rename account">✎</button></h2><p class="identity">${escape(a.email || 'ChatGPT account')} / ${escape(a.plan || bucket.planType || 'Plan unavailable')}</p></div></div><span class="badge">${status}</span></div><div class="big-label">${fresh?escape(duration(primary?.windowDurationMins)):'Current usage unavailable'}</div><div class="reading"><div class="number">${r??'—'}<small>${r!==null?'%':''}</small></div><span>remaining</span></div>${meter(primary,true)}${resetLine(primary)}${secondary?weekly(secondary):'<div class="weekly"><p class="empty-note">No second usage window returned by Codex.</p></div>'}${Object.entries(fresh?a.buckets||{}:{}).filter(([id])=>id!==(bucket.limitId||'codex')).map(([id,b])=>`<details class="extra"><summary>${escape(b.limitName||id)}</summary>${b.primary?weekly(b.primary):''}${b.secondary?weekly(b.secondary):''}</details>`).join('')}<div class="account-bottom"><span>${a.error?escape(a.error):!fresh?'Reconnect to refresh; previous readings are hidden.':''}</span><span>Updated ${age(a.updatedAt)}</span></div>${a.needsLogin?`<button class="outline-button" data-reconnect="${escape(a.id)}">Reconnect account</button>`:''}<div class="account-bottom"><span>Warmup: ${escape(a.needsLogin?'Sign-in required':a.warmup?.status||'Waiting for connector')}</span><span>${(a.warmup?.latestRun?.completedAt||a.warmup?.lastCompletedAt)?'Last hi '+escape(fullDate(a.warmup.latestRun?.completedAt||a.warmup.lastCompletedAt)):''}</span></div><div class="account-bottom"><span>Last check ${escape(preciseDate(a.warmup?.checkedAt))}</span><span>Next check ${escape(preciseDate(a.warmup?.nextCheckAt))}</span></div>${historyMarkup(a,historyExpanded)}${fresh?bankedResets(a,expanded):'<div class="reset-inventory">Banked resets unavailable until refresh succeeds</div>'}</article>`;
 }).join('') + Array.from({length:Math.max(0,2-accounts.length)},(_,i)=>empty(accounts.length+i)).join('');
 document.querySelectorAll('[data-receipt-id]').forEach(el=>{if(openReceipts.has(el.dataset.receiptId))el.open=true;});
 document.querySelectorAll('.run').forEach(el=>{if(openRuns.has(el.dataset.runId))el.open=true;});
 document.querySelectorAll('[data-history]').forEach(el=>el.ontoggle=()=>{if(el.open&&!histories[el.dataset.history])loadHistory(el.dataset.history);});
 document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>{
   const r=histories[b.dataset.download]?.find(r=>r.id===b.dataset.run);
   if(!r)return;const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));
   const a=document.createElement('a');a.href=url;a.download='headroom-run-'+r.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 document.querySelectorAll('[data-connect]').forEach(b=>b.onclick=()=>connectAccount());
 document.querySelectorAll('[data-reconnect]').forEach(b=>b.onclick=()=>connectAccount(b.dataset.reconnect));
 document.querySelectorAll('[data-rename]').forEach(b=>b.onclick=()=>{
   const id=b.dataset.rename, i=accounts.findIndex(a=>a.id===id);
   renameId=id;
   $('account-name').value=accountName(accounts[i],i);
   $('rename-error').textContent='';
   $('rename-dialog').showModal();
   $('account-name').focus();$('account-name').select();
 });
 const upcoming=[];
 accounts.forEach((a,i)=>Object.entries(freshReading(a,connected)?a.buckets||{}:{}).forEach(([id,b])=>{if(!b)return;[b.primary,b.secondary].filter(Boolean).forEach(w=>{if(w.resetsAt)upcoming.push({a,i,id,b,w});});}));
 upcoming.sort((a,b)=>a.w.resetsAt-b.w.resetsAt);
 $('schedule').innerHTML=upcoming.length?upcoming.slice(0,6).map(({a,i,id,b,w})=>`<div class="schedule-row"><div><strong>${escape(accountName(a,i))}</strong><small>${escape(id==='codex'?duration(w.windowDurationMins):(b.limitName||id)+' / '+duration(w.windowDurationMins))}</small></div><span>${escape(fullDate(w.resetsAt))}</span><strong>${escape(resetText(w.resetsAt))}</strong></div>`).join(''):'<p class="schedule-empty">Your next resets will appear after you connect an account.</p>';
 const ready=accounts.filter(a=>connected&&eligible(a));
 $('advice').textContent=ready.length?`${ready.length} account${ready.length===1?' has':'s have'} capacity in all reported windows.`:accounts.length?'Refresh both accounts before choosing your next session. A reset passing does not confirm that an allowance has renewed.':'Connect an account to view limits and resets.';
 $('dot').className='dot '+(connected?'connected':'');
 $('timezone').textContent=Intl.DateTimeFormat().resolvedOptions().timeZone+' / '+new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
}
async function request(path,method='GET'){
 const response=await fetch('http://127.0.0.1:4318'+path,{method,headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(120000)});
 const body=await response.json(); if(!response.ok)throw new Error(body.error||'Connector request failed.');return body;
}
async function sync(){
 if(busy)return;if(!key){$('status').textContent='Connect your Mac to see real usage';return;}
 busy=true;$('refresh').disabled=true;$('status').textContent='Reading account limits…';
 try{const data=await request('/usage'); accounts=data.accounts;activeId=data.activeId;connected=true;if(data.login?.running)setTimeout(sync,3000);localStorage.setItem('headroom-snapshots',JSON.stringify(accounts));$('status').textContent=data.login?.running?'Finish signing in in the opened browser':data.login?.error?data.login.error:data.errors?.length?'Some readings failed · see account details':`Connected to this Mac / Updated ${new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}`;}
 catch(e){connected=false;$('status').textContent=e.message.includes('fetch')||e.name==='TimeoutError'?'Connector unavailable · start it on this Mac':e.message;}
 finally{busy=false;$('refresh').disabled=false;render();}
}
async function connectAccount(expected=null){
 if(!key||!connected){openConnection();return;}
 const popup=window.open('about:blank','_blank');
 try{const data=await request('/login'+(expected?'?account='+encodeURIComponent(expected):''),'POST');if(popup){popup.opener=null;popup.location.href=data.url;}else toast('Allow pop-ups, then finish the account sign-in.');$('status').textContent='Finish signing in in the opened browser';setTimeout(sync,5000);}
 catch(e){popup?.close();toast(e.message);}
}
let renameId=null;
$('rename-close').onclick=$('rename-cancel').onclick=()=>$('rename-dialog').close();
$('rename-form').onsubmit=e=>{
 e.preventDefault();const value=$('account-name').value.trim();
 if(!value || value.length>60){$('rename-error').textContent='Enter a name with 1–60 characters.';return;}
 names[renameId]=value;localStorage.setItem('headroom-names',JSON.stringify(names));
 $('rename-dialog').close();render();
};
$('command').textContent=`python3 "${'connector/server.py'}" --origin ${location.origin} --open`;
$('connection').onclick=openConnection;$('how').onclick=openConnection;$('add').onclick=()=>connectAccount();
$('pair').onclick=()=>{const value=$('key').value.trim();if(value.length<20){$('dialog-message').textContent='Enter the pairing key created by your local connector.';return;}key=value;localStorage.setItem('headroom-pair',key);$('key').value='';$('dialog').close();sync();};
$('refresh').onclick=()=>key?sync():openConnection();
render();sync();setInterval(()=>{render();if($('auto').checked&&!document.hidden)sync();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$('auto').checked)sync();});

setInterval(()=>{document.querySelectorAll('.warmup-history[open]').forEach(el=>loadHistory(el.dataset.history));},5000);
