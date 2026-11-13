const byId=id=>document.getElementById(id);
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(v,d=2)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('en-IN',{maximumFractionDigits:d,minimumFractionDigits:d}):'—';
function badges(row){
 const values=[];const add=(condition,label)=>{if(condition)values.push(`<span class="signal-badge ${row.redwala_gira?'red':''}">${escape(label)}</span>`);};
 add(row.possible_candidate,'Possible Candidate');add(row.redwala_gira,'Redwala Gira');
 add(row.possible_candidate&&row.resistance_break,'Resistance Break');add(row.possible_candidate&&row.resistance_break_open,'Resistance Break Open');
 add(row.possible_candidate&&row.first_candle_high_break,'First Candle High Break');add(row.possible_candidate&&row.first_open_equals_low,'Open = Low');
 add(row.possible_candidate&&row.previous_day_high_cross,'Previous Day High Cross');
 add(row.redwala_gira&&row.first_candle_low_break,'First Candle Low Break');add(row.redwala_gira&&row.previous_day_low_cross,'First Candle PDL Cross');
 add(row.redwala_gira&&row.previous_day_low_cross_second_candle,'PDL Cross on 2nd Candle');
 add(row.possible_candidate&&row.previous_close>0&&row.first_candle_open>0&&Math.abs(row.first_candle_open-row.previous_close)<=row.previous_close*.035+Number.EPSILON*Math.max(row.first_candle_open,row.previous_close)*4,'under_3.5%');
 add(row.is_fno,'F&O');return values.join('');
}
let latestState=null;
byId('memberSetup').addEventListener('change',()=>{if(latestState)render(latestState);});
function render(data){
 latestState=data;
 const allRows=data.stocks||[];
 const setup=byId('memberSetup').value;
 const rows=allRows.filter(r=>setup==='possible'?r.possible_candidate:setup==='redwala'?r.redwala_gira:true);
 byId('memberPossible').textContent=allRows.filter(r=>r.possible_candidate).length;
 byId('memberRedwala').textContent=allRows.filter(r=>r.redwala_gira).length;
 byId('memberConnection').textContent=data.connected&&data.running?'Live market is running':data.running?'Live market is reconnecting':'Live market is stopped';
 byId('memberMessage').textContent=`${rows.length} visible stocks · Updated ${new Date(data.updated_at).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata'})} IST`;
 byId('memberRows').innerHTML=rows.map((r,i)=>`<tr><td>${i+1}</td><td><strong>${escape(r.symbol)}</strong><span class="stock-name">${escape(r.name)}</span><div class="member-badges">${badges(r)}</div></td><td><strong>${number(r.first_candle_turnover/10000000)} Cr</strong></td><td>${number(r.volume_multiplier)}×</td><td>${number(r.ltp)}</td><td class="${r.percent_change<0?'negative':'positive'}">${number(r.percent_change)}%</td><td>${number(r.upper_circuit_distance_percent)}%<br><small>Limit ${number(r.upper_circuit_limit)}</small></td><td>${number(r.lower_circuit_distance_percent)}%<br><small>Limit ${number(r.lower_circuit_limit)}</small></td><td>${number(r.today_opening_volume,0)}</td><td>${number(r.opening_volume_average,0)}</td><td>${number(r.previous_day_multiplier)}×</td><td>${number(r.previous_day_percent)}%</td><td>${escape(r.first_candle_color)}<br><small>O ${number(r.first_candle_open)} · C ${number(r.first_candle_close)}</small></td><td>${number(r.previous_close)}</td><td>${number(r.resistance_level)}</td></tr>`).join('')||'<tr><td colspan="15">No confirmed stocks match the selected setup yet.</td></tr>';
}
let polling=false;
async function poll(){if(polling)return;polling=true;const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
 try{const response=await fetch('/api/auth/me',{cache:'no-store',signal:controller.signal});if(response.status===401){location.replace('/login');return;}
 if(!response.ok)throw new Error('Account access could not be checked.');const user=await response.json();
 const active=user.status==='active';byId('pendingAccess').hidden=active;byId('memberDashboard').hidden=!active;
 if(!active){latestState=null;byId('memberRows').replaceChildren();return;}
 const state=await fetch('/api/member/state',{cache:'no-store',signal:controller.signal});
 if(state.status===401){location.replace('/login');return;}
 if(!state.ok)throw new Error('Dashboard access unavailable. Contact the administrator if this continues.');
 render(await state.json());byId('accountError').textContent='';
 }catch(error){latestState=null;byId('memberConnection').textContent='Live market status unavailable';byId('memberRows').replaceChildren();byId('accountError').textContent=error.message;}
 finally{clearTimeout(timeout);polling=false;}
}
window.sessionReady.then(user=>{if(user){poll();setInterval(poll,2000);}}).catch(()=>{});
