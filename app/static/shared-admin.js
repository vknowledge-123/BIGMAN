// Server preferences are authoritative. Legacy localStorage never controls member visibility.
let sharedLoaded=false, sharedRevision=-1, displayDirty=false, displaySending=false, displayPending=null, displayTimer;
const sharedControls=['dashboardVolumeEnabled','dashboardVolumeMin','dashboardPriceEnabled','dashboardPriceMax','dashboardCircuitEnabled','setupFilter'];
const displayStatus=document.getElementById('sharedDisplayStatus');
for(const id of sharedControls)document.getElementById(id).disabled=true;
window.syncSharedDisplay=function(payload){
 if(!payload||displayDirty||payload.revision<=sharedRevision)return;
 sharedLoaded=true;sharedRevision=payload.revision;const s=payload.settings;
 dashboardVolumeFilter={enabled:s.volume_enabled,minimum:s.volume_min};
 dashboardPriceFilter={enabled:s.price_enabled,maximum:s.price_max};dashboardCircuitEnabled=s.circuit_enabled;
 els.dashboardVolumeEnabled.checked=s.volume_enabled;els.dashboardVolumeMin.value=s.volume_min;
 els.dashboardPriceEnabled.checked=s.price_enabled;els.dashboardPriceMax.value=s.price_max;
 els.dashboardCircuitEnabled.checked=s.circuit_enabled;els.setupFilter.value=s.setup;
 for(const id of sharedControls)document.getElementById(id).disabled=false;
 displayStatus.textContent='Shared settings saved. Approved members receive the same visibility rules.';
};
function sharedDraft(){
 const rawVolume=els.dashboardVolumeMin.value.trim(),rawPrice=els.dashboardPriceMax.value.trim();
 const volume=Number(rawVolume),price=Number(rawPrice);
 if(!rawVolume||!rawPrice||!Number.isSafeInteger(volume)||volume<0||!Number.isFinite(price)||price<0)return null;
 return {volume_enabled:els.dashboardVolumeEnabled.checked,volume_min:volume,
  price_enabled:els.dashboardPriceEnabled.checked,price_max:price,
  circuit_enabled:els.dashboardCircuitEnabled.checked,setup:els.setupFilter.value||'all'};
}
async function saveShared(){
 if(displaySending||!displayPending)return;
 displaySending=true;let failed=false;
 try{
  while(displayPending){const value=displayPending;displayPending=null;
   displayStatus.textContent='Saving shared display settings…';
   const result=await api('/api/display-settings',{method:'POST',body:JSON.stringify(value)},10000);
   if(!displayPending){displayDirty=false;window.syncSharedDisplay(result);}
  }
  document.getElementById('retryDisplaySave').hidden=true;
  await refreshState();
 }catch(error){failed=true;displayStatus.textContent=`Not shared yet: ${error.message}`;document.getElementById('retryDisplaySave').hidden=false;}
 finally{displaySending=false;if(displayPending&&!failed)saveShared();}
}
function queueShared(immediate){
 if(!sharedLoaded)return;
 const draft=sharedDraft();if(!draft){displayStatus.textContent='Enter valid display limits before sharing the change.';return;}
 displayDirty=true;displayPending=draft;clearTimeout(displayTimer);displayStatus.textContent='Saving shared display settings...';
 if(immediate)saveShared();else displayTimer=setTimeout(saveShared,350);
}
for(const id of sharedControls){const el=document.getElementById(id);el.addEventListener('input',()=>queueShared(false));el.addEventListener('change',()=>queueShared(true));}
document.getElementById('retryDisplaySave').addEventListener('click',()=>queueShared(true));
async function loadMembers(){
 const output=document.getElementById('membersMessage');
 try{
  const data=await api('/api/admin/users');
  document.getElementById('memberAccounts').innerHTML=data.users.map(u=>`<tr><td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.role)}</td><td>${escapeHtml(u.status)}</td><td>${u.mfa?'Ready':'Not enrolled'}</td><td>${u.role==='admin'?'Administrator':`<button type="button" class="secondary" data-member="${escapeHtml(u.id)}" data-status="${u.status==='active'?'suspended':'active'}" ${!u.mfa&&u.status!=='active'?'disabled':''}>${u.status==='active'?'Suspend':u.status==='suspended'?'Restore access':'Approve'}</button>`}</td></tr>`).join('')||'<tr><td colspan="6">No accounts yet.</td></tr>';
  output.textContent='';
 }catch(error){output.textContent=error.message;}
}
document.getElementById('refreshMembers').addEventListener('click',loadMembers);
document.getElementById('memberAccounts').addEventListener('click',async event=>{
 const button=event.target.closest('button[data-member]');if(!button||button.disabled)return;
 button.disabled=true;
 try{await api('/api/admin/users/'+encodeURIComponent(button.dataset.member),{method:'POST',body:JSON.stringify({status:button.dataset.status})});await loadMembers();}
 catch(error){document.getElementById('membersMessage').textContent=error.message;button.disabled=false;}
});
window.addEventListener('load',async()=>{
 try{window.syncSharedDisplay(await api('/api/display-settings'));if(lastLiveState)renderState(lastLiveState);await loadMembers();}
 catch(error){displayStatus.textContent='Shared settings unavailable: '+error.message;}
});

window.addEventListener('beforeunload',event=>{if(displayDirty){event.preventDefault();event.returnValue='';}});
