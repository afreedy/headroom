import test from 'node:test';
import assert from 'node:assert/strict';
import { remaining, resetText, duration, stale, eligible, expiryText } from '../public/usage.js';
test('remaining uses used percentage and preserves unavailable values',()=>{
 assert.equal(remaining({usedPercent:10}),90);assert.equal(remaining({usedPercent:120}),0);assert.equal(remaining({usedPercent:-10}),100);assert.equal(remaining(null),null);assert.equal(remaining({usedPercent:null}),null);assert.equal(remaining({usedPercent:NaN}),null);
});
test('reset countdown never fabricates renewed quota',()=>{assert.match(resetText(1,2000),/refresh to confirm/);assert.equal(resetText(3660,0),'1h 1m');assert.equal(resetText(null),'Reset time unavailable');assert.equal(duration(300),'5-hour limit');assert.equal(duration(10080),'7-day limit');});
test('stale, exhausted, errored, unknown or passed-reset accounts are not recommended',()=>{
 const now=2000000000; const a={updatedAt:now/1000,buckets:{codex:{primary:{usedPercent:10,resetsAt:now/1000+10}}}};
 assert.equal(eligible(a,now),true);assert.equal(stale({...a,updatedAt:0},now),true);assert.equal(eligible({...a,error:'offline'},now),false);assert.equal(eligible(a,now+11000),false);assert.equal(eligible({...a,buckets:{}},now),false);assert.equal(eligible({...a,buckets:{codex:{primary:{usedPercent:100}}}},now),false);
});

test('reset expiry handles missing, future and elapsed timestamps honestly',()=>{assert.equal(expiryText(null),'Expiry not provided');assert.equal(expiryText(1,2000),'Expired · refresh to confirm');assert.equal(expiryText(3660,0),'1h 1m left');});

test('failed, disconnected and stale readings are never shown as current', async () => {
 const {freshReading}=await import('../public/usage.js');
 const a={updatedAt:1000};
 assert.equal(freshReading(a,true,1000000),true);
 assert.equal(freshReading({...a,error:'offline'},true,1000000),false);
 assert.equal(freshReading({...a,needsLogin:true},true,1000000),false);
 assert.equal(freshReading(a,false,1000000),false);
 assert.equal(freshReading(a,true,1400000),false);
});

test('a passed reset hides the old percentage until a new window is returned', async () => {
 const {currentWindow}=await import('../public/usage.js');
 const old={usedPercent:48,resetsAt:1000};
 assert.equal(remaining(currentWindow(old,1000001)),null);
 assert.equal(remaining(currentWindow({...old,resetsAt:2000},1000001)),52);
 assert.equal(old.usedPercent,48);
});
