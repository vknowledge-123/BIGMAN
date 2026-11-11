window.sessionReady = (async()=>{
  const response=await fetch('/api/auth/me',{cache:'no-store',credentials:'same-origin'});
  if(response.status===401){location.replace('/login');return null;}
  if(!response.ok)throw new Error('Could not load your account. Refresh to try again.');
  const user=await response.json();window.sessionUser=user;
  const label=document.getElementById('accountName');if(label)label.textContent=`${user.name} · ${user.role==='admin'?'Administrator':'Member'}`;
  return user;
})();
window.sessionReady.catch(error=>{const el=document.getElementById('accountError');if(el)el.textContent=error.message;});
document.getElementById('logoutButton')?.addEventListener('click',async()=>{
  try{const user=await window.sessionReady;if(!user)return;
    const response=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':user.csrf,'Content-Type':'application/json'},body:'{}'});
    if(response.ok||response.status===401)location.replace('/login');else throw new Error('Sign-out failed. Please try again.');
  }catch(error){const el=document.getElementById('accountError');if(el)el.textContent=error.message;}
});
