const state = { profile: null, opportunities: [], assessments: new Map(), selected: null, pack: null, watch: [] };
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
function toast(message){ const el=$('#toast'); el.textContent=message; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),2200); }
async function api(path, options={}){ const res=await fetch(path,{headers:{'content-type':'application/json',...(options.headers||{})},...options}); if(!res.ok){const body=await res.text();throw new Error(`${res.status}: ${body}`)} return res.json(); }
function money(value){ const v=value.maximum ?? value.minimum; if(!v)return 'Undisclosed'; return `${new Intl.NumberFormat('en-GB',{maximumFractionDigits:0}).format(v)} ${value.currency}`; }
function deadlineText(date){ if(!date)return 'Unverified'; const days=Math.ceil((new Date(date+'T23:59:59Z')-new Date())/86400000); if(days<0)return 'Closed'; if(days===0)return 'Today'; if(days===1)return '1 day'; return `${days} days`; }
function sourceBadge(o){ return o.sourceType==='fixture'?'DEMO FIXTURE':o.sourceType.toUpperCase(); }
function requirementStatement(r){ return typeof r==='string'?r:r.statement; }
function intel(o){ return o.intelligence||{}; }
function changeText(o){ const changes=intel(o).changeSummary||[]; return changes.length?changes.join(' · '):'No recorded changes'; }
function feedInsight(o,a){
  const requirements=o.requirements||[];
  const verified=a?.gaps?.filter(g=>g.status==='verified').length||0;
  const critical=a?.gaps?.find(g=>['missing','unknown','failed'].includes(g.status));
  const strongest=a?.strongEvidence?.[0]||'No verified match yet';
  return `${a?.hardEligibility||'not assessed'} eligibility · ${verified}/${requirements.length} requirements evidenced · strongest proof: ${strongest}${critical?` · critical gap: ${critical.requirement}`:''}`;
}
async function init(){
  try{
    const [health, profile, feed, watch] = await Promise.all([api('/health'),api('/api/profile'),api('/api/feed',{method:'POST',body:'{}'}),api('/api/watch')]);
    state.profile=profile; state.opportunities=feed.items; state.watch=watch.items;
    $('#service-status').textContent=health.status==='ok'?'Service ready':'Service degraded';
    $('#payment-mode').textContent=`${health.paymentMode} payment mode`;
    renderProfile(); renderFeed(); renderWatch(); updateMetrics();
    if(state.opportunities.length) await selectOpportunity(state.opportunities[0].id);
  }catch(error){ console.error(error); $('#service-status').textContent='Service unavailable'; toast('Could not load Norn'); }
}
function verifiedReadiness(){ const claims=[...state.profile.skills,...state.profile.projects]; if(!claims.length)return 0; const evidenceIds=new Set(state.profile.evidence.filter(e=>e.status==='verified'&&(e.url||e.digest)).map(e=>e.id)); const proven=claims.filter(c=>c.status==='verified'&&(c.evidenceIds||[]).some(id=>evidenceIds.has(id))); return Math.round(proven.length/claims.length*100); }
function updateMetrics(){ $('#metric-readiness').textContent=`${verifiedReadiness()}%`; $('#metric-feed').textContent=state.opportunities.length; const scores=[...state.assessments.values()].map(a=>a.score); $('#metric-score').textContent=scores.length?Math.max(...scores):'—'; $('#metric-watch').textContent=state.watch.filter(w=>!['archived','lost'].includes(w.status)).length; }
function renderFeed(filter='all'){
  const list=$('#feed-list'); list.classList.remove('skeleton');
  const items=state.opportunities.filter(o=>filter==='all'||o.type===filter);
  list.innerHTML=items.map((o,i)=>{ const a=state.assessments.get(o.id); const x=intel(o); const title=[x.programme,x.track].filter(Boolean).join(' / ')||o.title; return `<article class="opportunity ${state.selected?.id===o.id?'selected':''}" data-id="${o.id}">
    <div class="rank">${String(i+1).padStart(2,'0')}</div>
    <div class="opp-title"><span class="opp-type">${o.type} · ${sourceBadge(o)} · v${x.version||1}</span><h3>${title}</h3><p>${o.issuer} — ${o.summary}</p><small>${feedInsight(o,a)}</small><br><small>${changeText(o)}</small></div>
    <div class="opp-meta"><p>${Math.round((x.completeness||0)*100)}% complete<br>${Math.round((x.sourceQuality||0)*100)}% source quality<br>${x.dossierStatus||'draft'}</p></div>
    <div class="deadline"><small>DEADLINE</small><strong>${deadlineText(o.deadline)}</strong><small>${x.freshness||'unknown'}</small></div>
    <div class="score-badge">${a?a.score:'—'}</div>
  </article>`}).join('') || '<div class="empty">No opportunities in this category.</div>';
  $$('.opportunity').forEach(el=>el.addEventListener('click',()=>selectOpportunity(el.dataset.id)));
}
async function selectOpportunity(id){ state.selected=state.opportunities.find(o=>o.id===id); if(!state.selected)return; if(!state.assessments.has(id)){ const assessment=await api('/api/score',{method:'POST',body:JSON.stringify({profile:state.profile,opportunity:state.selected})}); state.assessments.set(id,assessment); } renderFeed($('.chip.active')?.dataset.filter||'all'); renderAssessment(); renderGaps(); updateMetrics(); }
function renderAssessment(){ const a=state.assessments.get(state.selected.id); $('#score-value').textContent=a.score; $('#score-opportunity').textContent=`${state.selected.issuer} / ${state.selected.title}`; $('#score-recommendation').textContent=a.recommendation.replaceAll('_',' '); $('#score-summary').textContent=a.rationale.join(' '); $('#criteria-list').innerHTML=a.criteria.map(c=>`<div class="criterion" title="${c.reason}"><label>${c.label}</label><div class="bar"><i style="width:${c.score/c.maximum*100}%"></i></div><b>${Math.round(c.score)}/${c.maximum}</b></div>`).join(''); }
function renderGaps(){ const a=state.assessments.get(state.selected.id); $('#gaps-list').innerHTML=a.gaps.map(g=>`<div class="gap-row"><div class="gap-status ${g.status}">${g.status}</div><strong>${g.requirement}</strong><p>${g.recommendedAction||g.reason}</p></div>`).join('')||'<div class="empty">No explicit requirements supplied.</div>'; }
function renderProfile(){ $('#profile-name').value=state.profile.displayName; $('#profile-bio').value=state.profile.biography; $('#profile-preferences').value=state.profile.preferredOpportunities.join(', '); $('#skills-list').innerHTML=state.profile.skills.map(s=>`<div class="claim-row"><span>${s.name}</span><span class="tag ${s.status}">${s.status}</span></div>`).join(''); $('#projects-list').innerHTML=state.profile.projects.map(p=>`<div class="claim-row"><span><strong>${p.name}</strong><br><small>${p.summary}</small></span><span class="tag ${p.status}">${p.status}</span></div>`).join(''); $('#evidence-count').textContent=`${state.profile.evidence.length} records`; $('#evidence-list').innerHTML=state.profile.evidence.map(e=>`<div class="evidence-row"><span>${e.label}<br><small>${e.kind}</small></span><span class="tag ${e.status}">${e.status}</span></div>`).join('')||'<div class="empty">No verified evidence yet.</div>'; }
async function saveProfile(){ state.profile.displayName=$('#profile-name').value.trim(); state.profile.biography=$('#profile-bio').value.trim(); state.profile.preferredOpportunities=$('#profile-preferences').value.split(',').map(x=>x.trim()).filter(Boolean); state.profile=await api('/api/profile',{method:'PUT',body:JSON.stringify(state.profile)}); state.assessments.clear(); renderProfile(); renderFeed(); updateMetrics(); toast('Norn Profile saved'); }
async function generatePack(){ if(!state.selected)return toast('Select an opportunity first'); const assessment=state.assessments.get(state.selected.id); state.pack=await api('/api/packs',{method:'POST',body:JSON.stringify({profile:state.profile,opportunity:state.selected,assessment})}); $('#pack-content').textContent=state.pack.content; $('#pack-digest').textContent=`sha256 ${state.pack.digest.slice(0,18)}…`; toast('Draft Norn Pack generated'); }
function renderWatch(){ $('#watch-list').innerHTML=state.watch.map(w=>`<article class="watch-item"><div class="watch-date">${w.deadline||'No date'}</div><div><h3>${w.title}</h3><p>${w.nextAction}</p></div><div class="watch-state ${w.status}">${w.status}</div></article>`).join('')||'<div class="empty">No watched opportunities.</div>'; }
async function runBrief(){ const button=$('#run-brief'); button.disabled=true; button.textContent='Evaluating…'; try{ const result=await api('/api/v1/opportunity-brief',{method:'POST',body:JSON.stringify({profile:state.profile,opportunities:state.opportunities,includePackForTopOpportunity:true,maximumResults:5})}); result.ranked.forEach(r=>state.assessments.set(r.opportunity.id,r.assessment)); if(result.topPack){state.pack=result.topPack;$('#pack-content').textContent=result.topPack.content;$('#pack-digest').textContent=`sha256 ${result.topPack.digest.slice(0,18)}…`;} renderFeed(); await selectOpportunity(result.ranked[0].opportunity.id); toast(result.summary); } catch(error){ console.error(error); toast('Paid endpoint is not available in this mode'); } finally{button.disabled=false;button.innerHTML='Run opportunity brief <span>↗</span>';} }
$$('.nav').forEach(btn=>btn.addEventListener('click',()=>{ $$('.nav').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); $$('.view').forEach(v=>v.classList.remove('active')); $(`#view-${btn.dataset.view}`).classList.add('active'); window.scrollTo({top:300,behavior:'smooth'}); }));
$$('.chip').forEach(btn=>btn.addEventListener('click',()=>{$$('.chip').forEach(b=>b.classList.remove('active'));btn.classList.add('active');renderFeed(btn.dataset.filter)}));
$('#save-profile').addEventListener('click',saveProfile); $('#generate-pack').addEventListener('click',generatePack); $('#run-brief').addEventListener('click',runBrief);
init();
