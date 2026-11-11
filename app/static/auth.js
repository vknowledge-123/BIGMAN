const $ = id => document.getElementById(id);
const signup = location.pathname === '/signup';
let challenge = null;
if (signup) {
  $('formTitle').textContent = 'Create your account';
  $('formKicker').textContent = 'YOUR MARKET VIEW STARTS HERE';
  $('formIntro').textContent = 'Join the dashboard. Set up your authenticator, then request administrator approval.';
  for (const id of ['nameField','confirmField','signupHelp']) $(id).hidden = false;
  $('name').required = $('confirmPassword').required = true;
  $('password').minLength = 12;
  $('password').autocomplete = 'new-password';
  $('identitySubmit').firstChild.textContent = 'Create account ';
  $('switchLink').replaceChildren(document.createTextNode('Already registered? '));
  const link = document.createElement('a'); link.href='/login'; link.textContent='Sign in'; $('switchLink').append(link);
}
async function send(path, data) {
  const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Requested-With':'scanner'},body:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'Please check your inputs and try again.');
    return result;
  } finally {clearTimeout(timer);}
}
$('identityForm').addEventListener('submit',async event=>{
  event.preventDefault(); if($('identitySubmit').disabled)return;
  $('authMessage').textContent='';
  if(signup && $('password').value!==$('confirmPassword').value){$('authMessage').textContent='Passwords do not match.';return;}
  $('identitySubmit').disabled=true;
  try {
    const payload={email:$('email').value,password:$('password').value};
    if(signup)payload.name=$('name').value;
    const result=await send(signup?'/api/auth/signup':'/api/auth/login',payload);
    challenge=result.challenge;
    $('password').value=$('confirmPassword').value='';
    $('identityForm').hidden=$('switchLink').hidden=true;
    $('otpForm').hidden=false;
    $('formTitle').textContent=result.enrollment?'Set up your authenticator':'Confirm it’s you';
    $('formIntro').textContent=result.enrollment?'Connect Google Authenticator to protect your account.':'Enter the current code from Google Authenticator.';
    $('enrollment').hidden=!result.enrollment;
    if(result.enrollment){$('qr').src=result.qr;$('setupKey').textContent=result.secret;}
    $('otp').focus();
  }catch(error){$('authMessage').textContent=error.name==='AbortError'?'Request timed out. If you signed up, try signing in to finish setup.':error.message;}
  finally{$('identitySubmit').disabled=false;}
});
$('otpForm').addEventListener('submit',async event=>{
  event.preventDefault(); if($('otpSubmit').disabled)return;
  $('otpSubmit').disabled=true;$('authMessage').textContent='';
  try {await send('/api/auth/verify',{challenge,code:$('otp').value});challenge=null;$('setupKey').textContent='';location.replace('/');}
  catch(error){$('authMessage').textContent=error.name==='AbortError'?'Verification timed out. Try opening the dashboard before signing in again.':error.message;}
  finally{$('otpSubmit').disabled=false;}
});
