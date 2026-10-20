import { remaining, resetText, duration, stale, eligible, expiryText } from './usage.js';
const $ = id => document.getElementById(id);
let key = localStorage.getItem('headroom-pair') || '';
const hash = new URLSearchParams(location.hash.slice(1));
if(hash.has('pair')){ key = hash.get('pair'); localStorage.setItem('headroom-pair', key); history.replaceState(null,'',location.pathname); }
let accounts = [], activeId = null, connected = false, busy = false;
try { accounts = JSON.parse(localStorage.getItem('headroom-snapshots') || '[]'); } catch {}
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
function empty(i){return `<article class="account empty"><div class="account-top"><div class="account-title"><span class="avatar">${i+1}</span><h2>Account ${i+1}</h2></div><span class="badge">Not connected</span></div><div class="big-label">Usage unavailable</div><div class="reading"><div class="number">—<small>%</small></div></div><p class="empty-note">Connect an account to view limits and resets.</p><button class="empty-action" data-connect>Connect account ＋</button></article>`;}
function render(){
 const expanded = new Set([...document.querySelectorAll('.reset-inventory[open]')].map(el=>el.dataset.account));
 $('accounts').innerHTML = accounts.map((a,i)=>{
 const bucket=getBucket(a),primary=bucket.primary, secondary=bucket.secondary, r=remaining(primary);
 const status=a.error?'Refresh failed':!connected||stale(a)?'Saved reading':activeId===a.id?'Desktop account':'Connected';
 return `<article class="account"><div class="account-top"><div class="account-title"><span class="avatar">${escape((a.email || `Account ${i+1}`)[0].toUpperCase())}</span><div><h2>${escape(accountName(a,i))} <button class="rename" data-rename="${escape(a.id)}" aria-label="Rename ${escape(accountName(a,i))}" title="Rename account">✎</button></h2><p class="identity">${escape(a.email || 'ChatGPT account')} / ${escape(a.plan || bucket.planType || 'Plan unavailable')}</p></div></div><span class="badge">${status}</span></div><div class="big-label">${escape(duration(primary?.windowDurationMins))}</div><div class="reading"><div class="number">${r??'—'}<small>${r!==null?'%':''}</small></div><span>remaining</span></div>${meter(primary,true)}${resetLine(primary)}${secondary?weekly(secondary):'<div class="weekly"><p class="empty-note">No second usage window returned by Codex.</p></div>'}${Object.entries(a.buckets||{}).filter(([id])=>id!==(bucket.limitId||'codex')).map(([id,b])=>`<details class="extra"><summary>${escape(b.limitName||id)}</summary>${b.primary?weekly(b.primary):''}${b.secondary?weekly(b.secondary):''}</details>`).join('')}<div class="account-bottom"><span>${a.error?escape(a.error):''}</span><span>Updated ${age(a.updatedAt)}</span></div>${bankedResets(a,expanded)}</article>`;
 }).join('') + Array.from({length:Math.max(0,2-accounts.length)},(_,i)=>empty(accounts.length+i)).join('');
 document.querySelectorAll('[data-connect]').forEach(b=>b.onclick=connectAccount);
 document.querySelectorAll('[data-rename]').forEach(b=>b.onclick=()=>{
   const id=b.dataset.rename, i=accounts.findIndex(a=>a.id===id);
   renameId=id;
   $('account-name').value=accountName(accounts[i],i);
   $('rename-error').textContent='';
   $('rename-dialog').showModal();
   $('account-name').focus();$('account-name').select();
 });
 const upcoming=[];
 accounts.forEach((a,i)=>Object.entries(a.buckets||{}).forEach(([id,b])=>{if(!b)return;[b.primary,b.secondary].filter(Boolean).forEach(w=>{if(w.resetsAt)upcoming.push({a,i,id,b,w});});}));
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
 try{const data=await request('/usage'); accounts=data.accounts;activeId=data.activeId;connected=true;localStorage.setItem('headroom-snapshots',JSON.stringify(accounts));$('status').textContent=data.login?.running?'Finish signing in in the opened browser':data.login?.error?data.login.error:data.errors?.length?'Some readings failed · see account details':`Connected to this Mac / Updated ${new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}`;}
 catch(e){connected=false;$('status').textContent=e.message.includes('fetch')||e.name==='TimeoutError'?'Connector unavailable · start it on this Mac':e.message;}
 finally{busy=false;$('refresh').disabled=false;render();}
}
async function connectAccount(){
 if(!key||!connected){openConnection();return;}
 const popup=window.open('about:blank','_blank');
 try{const data=await request('/login','POST');if(popup){popup.opener=null;popup.location.href=data.url;}else toast('Allow pop-ups, then finish the account sign-in.');$('status').textContent='Finish signing in in the opened browser';setTimeout(sync,5000);}
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
$('connection').onclick=openConnection;$('how').onclick=openConnection;$('add').onclick=connectAccount;
$('pair').onclick=()=>{const value=$('key').value.trim();if(value.length<20){$('dialog-message').textContent='Enter the pairing key created by your local connector.';return;}key=value;localStorage.setItem('headroom-pair',key);$('key').value='';$('dialog').close();sync();};
$('refresh').onclick=()=>key?sync():openConnection();
render();sync();setInterval(()=>{render();if($('auto').checked&&!document.hidden)sync();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$('auto').checked)sync();});
