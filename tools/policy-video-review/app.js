'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {bottle_verb:'Verb · Bottle', pick_diverse_object:'Noun · Pick diverse object', attribute_select:'Attribute select', arm_select:'Arm select v2', stack_sequence:'Stack sequence', place_relative:'Place relative', grasp_cube_approach:'Grasp approach · 已归档'};
const verdictNames = {unreviewed:'未复核', agree:'与自动一致', false_positive:'疑似误报成功', false_negative:'疑似漏判成功', uncertain:'待确认', stale:'源文件已更新', unscored:'自动判定无效'};
const labelNames = {success:'Success', failure:'Fail', uncertain:'待确认', unreviewed:'未复核', error:'Error'};
const S = {rows:[], visible:[], id:null, detail:null, dirty:false, saving:false, serial:0, page:0, pageSize:40, tab:'compare', view:'all', loaded:false};
const video = $('#video');
let toastTimer;

function toast(message, error=false) {
  $('#toast').textContent=message; $('#toast').className='toast'+(error?' error':'');
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),error?6500:2400);
}
async function api(path, payload) {
  const options = payload === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':S.token},body:JSON.stringify(payload)};
  const response=await fetch(path,options); const data=await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function current(){return S.rows.find(r=>r.id===S.id);}
function allowNavigate(){return !S.saving && (!S.dirty || window.confirm('观察记录尚未保存，是否放弃这些修改？'));}
function time(t){if(!Number.isFinite(t))return '0:00';return `${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`;}
function setOptions(selector, values, initial) {
  const el=$(selector), old=el.value;
  el.innerHTML=`<option value="">${escape(initial)}</option>`+values.map(([v,n])=>`<option value="${escape(v)}">${escape(n)}</option>`).join('');
  if(values.some(([v])=>String(v)===old))el.value=old;
}
function populateFilters(){
  const scope=S.rows.filter(r=>$('#archived').checked || !r.archived);
  setOptions('#policy',Object.entries(S.policies).filter(([p])=>scope.some(r=>r.policy===p)),'全部 policies');
  const tasks=[...new Set(scope.map(r=>r.task))];
  setOptions('#task',tasks.map(t=>[t,names[t] || t]),'全部任务');
  const subset=scope.filter(r=>!$('#task').value || r.task===$('#task').value);
  setOptions('#mode',[...new Set(subset.map(r=>r.mode).filter(Boolean))].sort().map(m=>[m,m]),'全部模式');
  setOptions('#block',[...new Set(subset.map(r=>r.block).filter(b=>b!==null))].sort((a,b)=>a-b).map(b=>[String(b),`B${String(b+1).padStart(2,'0')} · index ${b}`]),'全部 blocks');
}
function matches(r){
  if(r.archived && !$('#archived').checked)return false;
  for(const [key,id] of [['policy','policy'],['task','task'],['automatic','automatic'],['mode','mode'],['block','block']]){
    if($('#'+id).value && String(r[key])!==$('#'+id).value)return false;
  }
  const f=$('#review-filter').value;
  if(f==='disagreements' && !['false_positive','false_negative'].includes(r.verdict))return false;
  if(['success','failure'].includes(f) && (r.review?.label!==f || r.verdict==='stale'))return false;
  if(f && !['disagreements','success','failure'].includes(f) && r.verdict!==f)return false;
  const q=$('#search').value.trim().toLowerCase();
  return !q || `${r.policy} ${r.task} ${r.seed} ${r.instruction} ${r.mode} ${r.review?.notes || ''}`.toLowerCase().includes(q);
}
function updateStats(){
  const rows=S.rows.filter(r=>$('#archived').checked || !r.archived);
  const reviewed=rows.filter(r=>['agree','false_positive','false_negative','unscored'].includes(r.verdict)).length;
  $('#total').textContent=rows.length.toLocaleString(); $('#reviewed').textContent=reviewed.toLocaleString();
  $('#review-progress').textContent=`${rows.length?(100*reviewed/rows.length).toFixed(1):0}% 已复核 · ${rows.filter(r=>r.verdict==='uncertain').length} 待确认`;
  $('#scope-count').textContent=`${new Set(rows.map(r=>r.task)).size} 任务 · ${new Set(rows.map(r=>r.policy)).size} policies`;
  $('#fp').textContent=rows.filter(r=>r.verdict==='false_positive').length;
  $('#fn').textContent=rows.filter(r=>r.verdict==='false_negative').length;
}
function renderQueue(){
  S.visible=S.rows.filter(matches);
  S.page=Math.max(0,Math.min(S.page,Math.ceil(S.visible.length/S.pageSize)-1));
  const page=S.visible.slice(S.page*S.pageSize,(S.page+1)*S.pageSize);
  $('#queue-count').textContent=`${S.visible.length} episodes`;
  $('#episode-list').innerHTML=page.length?page.map(r=>`<button class="episode-row${r.id===S.id?' active':''}" data-id="${escape(r.id)}" aria-current="${r.id===S.id?'true':'false'}">
    ${r.image_url?`<img loading="lazy" src="${escape(r.image_url)}" alt="初始场景">`:''}<div class="row-content"><div class="row-top"><strong><i class="dot ${r.automatic}"></i>${escape(S.policies[r.policy])}</strong><span class="review-dot ${r.verdict.startsWith('false_')?'disagrees':''}">${r.verdict==='unreviewed'?'○':escape(verdictNames[r.verdict])}</span></div><div class="row-bottom"><span class="row-seed">${r.seed}</span> · ${escape(r.mode || r.task)}${r.block!==null?` · B${r.block+1}`:''}</div><div class="row-bottom">${escape(r.instruction)}</div></div></button>`).join(''):'<p class="hint" style="padding:18px">没有匹配的回合。</p>';
  $('#page-label').textContent=S.visible.length?`${S.page+1} / ${Math.ceil(S.visible.length/S.pageSize)}`:'0 / 0';
  $('#page-prev').disabled=S.page===0; $('#page-next').disabled=(S.page+1)*S.pageSize>=S.visible.length;
  $$('.episode-row').forEach(el=>el.onclick=()=>{if(allowNavigate())select(el.dataset.id);});
  const active=$('.episode-row.active'), list=$('#episode-list');
  if(active){
    const a=active.getBoundingClientRect(), box=list.getBoundingClientRect();
    if(a.top<box.top)list.scrollTop-=box.top-a.top;
    else if(a.bottom>box.bottom)list.scrollTop+=a.bottom-box.bottom;
  }
  const position=S.visible.findIndex(r=>r.id===S.id);
  $('#previous').disabled=S.saving || position<=0; $('#next').disabled=S.saving || position>=S.visible.length-1 || !S.visible.length;
  updateStats();
}
function changeFilters(){
  if(!allowNavigate())return;
  populateFilters(); S.page=0; renderQueue();
  if(!S.visible.some(r=>r.id===S.id))select(S.visible[0]?.id || null);
}
function paintReview(){
  $$('.filters input,.filters select,#archived,#show-fp,#show-fn,#clear-filters').forEach(el=>el.disabled=S.saving);
  const row=current(); if(!row)return;
  const label=row.review?.label || 'unreviewed';
  $$('[data-label]').forEach(b=>{b.classList.toggle('selected',b.dataset.label===label);b.disabled=S.saving;});
  $('#save-notes').disabled=S.saving; $('#reset-review').disabled=S.saving;
  $('#notes').disabled=S.saving;
  $('#save-status').textContent=S.saving?'正在保存…':S.dirty?'记录未保存':row.review?'已保存 · '+labelNames[label]:'未复核';
  const state=row.verdict, box=$('#disagreement');
  box.classList.toggle('hidden',!['false_positive','false_negative','stale','unscored'].includes(state));
  box.textContent=state==='false_positive'?'疑似误报成功：自动 Success，人工 Fail。建议检查成功判定逻辑。':state==='false_negative'?'疑似漏判成功：自动 Fail，人工 Success。建议检查成功阈值或终止条件。':state==='stale'?'源文件已更新，旧标注暂不计入分歧。请重新观看并判定。':'该回合没有有效自动成功/失败判定，人工标签单独保留。';
}
function markDirty(){S.dirty=true;paintReview();}
function setView(view){
  const views=S.detail?.data?.diagnostics?.video_views || [];
  if(view!=='all' && !views[Number(view)])view='all';
  S.view=view; const stage=$('#video-stage'); stage.classList.toggle('cropped',view!=='all');
  const width=S.detail?.video?.width, height=S.detail?.video?.height;
  stage.style.aspectRatio=width && height ? String((view==='all'?width:width/Math.max(1,views.length))/height):'3';
  video.style.width=view==='all'?'100%':`${views.length*100}%`;
  video.style.transform=view==='all'?'':`translateX(-${Number(view)*100/views.length}%)`;
  $$('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.disabled=b.dataset.view!=='all' && !views[Number(b.dataset.view)];});
}
function pauseCompare(){ $$('#compare-grid video').forEach(v=>v.pause()); }
async function select(identifier){
  const serial=++S.serial; S.id=identifier; S.detail=null; S.dirty=false;
  video.pause(); pauseCompare(); video.removeAttribute('src'); video.load();
  $('#review-workspace').classList.toggle('hidden',!identifier); $('#empty').classList.toggle('hidden',!!identifier);
  if(!identifier){renderQueue();return;}
  const row=current(); if(!row)return;
  const index=S.visible.findIndex(r=>r.id===identifier); if(index>=0)S.page=Math.floor(index/S.pageSize);
  renderQueue();
  const url=new URL(location.href);url.searchParams.set('episode',identifier);history.replaceState(null,'',url);
  $('#episode-title').textContent=names[row.task] || row.task;
  $('#episode-meta').textContent=`${S.policies[row.policy]} / SEED ${row.seed} / ${row.block===null?'无 block':`BLOCK ${row.block+1} (index ${row.block})`} / ${row.mode || 'raw task'}`;
  $('#instruction').textContent=row.instruction || '未记录指令';
  $('#auto-badge').className='badge '+row.automatic; $('#auto-badge').textContent='自动判定 · '+labelNames[row.automatic];
  $('#notes').value=row.review?.notes || ''; paintReview();
  $('#step-info').textContent=`actions ${row.steps ?? '—'} / ${row.step_limit ?? '—'}`;
  $('#termination-info').textContent=row.termination || ''; $('#video-info').textContent='读取视频信息…';
  $('#details-json').textContent='读取记录…'; $('#artifacts').innerHTML=''; $('#history-panel').textContent='读取历史…';
  $('#video-message').classList.toggle('hidden',!!row.video_url); $('#video-message').textContent='此回合没有可用视频，原始记录仍可查看。';
  $('#frame-prev').disabled=$('#frame-next').disabled=true;
  if(row.video_url){video.src=row.video_url;video.playbackRate=Number($('#speed').value);}
  setView('all'); renderCompare(false);
  try{
    const detail=await api('/api/episode?id='+encodeURIComponent(identifier));
    if(serial!==S.serial)return;
    S.detail=detail;setView('all');
    const fps=detail.video.fps;
    $('#frame-prev').disabled=$('#frame-next').disabled=!(fps>0 && row.video_url);
    $('#video-info').textContent=fps?`${detail.video.width} × ${detail.video.height} · ${fps.toFixed(2)} fps`:'未探测到编码帧率，逐帧按钮不可用';
    $('#details-json').textContent=JSON.stringify({result:detail.data.result,summary:detail.data.summary,oracle:detail.data.oracle,diagnostics:detail.data.diagnostics,provenance:detail.data.provenance},null,2);
    $('#artifacts').innerHTML=Object.entries(detail.artifacts).map(([key,url])=>`<a href="${escape(url)}" target="_blank" rel="noopener">${escape(key)} ↗</a>`).join('');
    renderHistory(detail.history);
  }catch(err){if(serial===S.serial){$('#video-info').textContent='诊断读取失败';toast(err.message,true);}}
}
function renderHistory(rows){
  $('#history-panel').innerHTML=rows.length?rows.map(r=>`<div class="history-item"><small>${escape(r.updated_at)} · revision ${r.revision}</small><strong>${escape(labelNames[r.label])}</strong><p>${escape(r.notes || '无备注')}</p></div>`).join(''):'<p class="hint">还没有人工标注。清除判定后，历史仍会保留。</p>';
}
function renderCompare(load){
  pauseCompare();const row=current(); if(!row)return;
  const peers=S.rows.filter(r=>r.task===row.task && r.seed===row.seed);
  $('#load-compare').textContent=load?'收起视频':'加载对比视频';$('#load-compare').dataset.loaded=load?'1':'0';
  $('#compare-grid').innerHTML=peers.map(r=>`<article class="compare-item"><header><strong>${escape(S.policies[r.policy])}</strong><span class="badge ${r.automatic}">${labelNames[r.automatic]}</span></header>${load && r.video_url?`<video src="${escape(r.video_url)}" ${r.image_url?`poster="${escape(r.image_url)}"`:''} controls muted playsinline preload="metadata"></video>`:r.image_url?`<img src="${escape(r.image_url)}" loading="lazy" alt="${escape(S.policies[r.policy])} 初始场景">`:'<div class="missing">无初始画面</div>'}${!r.video_url?'<div class="missing">视频缺失</div>':''}<button data-peer="${escape(r.id)}">${r.id===S.id?'当前回合':`复核此回合 · ${escape(verdictNames[r.verdict])}`}</button></article>`).join('');
  $$('[data-peer]').forEach(b=>b.onclick=()=>{if(allowNavigate())select(b.dataset.peer);});
}
async function save(label, advance){
  if(S.saving || !S.id)return;
  const row=current(), oldList=S.visible.map(r=>r.id), position=oldList.indexOf(S.id);
  const notes=$('#notes').value;
  S.saving=true;paintReview();
  try{
    const data=await api('/api/review',{id:row.id,label,notes,revision:row.review?.revision || 0,source_signature:row.source_signature});
    row.review=data.review;row.verdict=data.verdict;S.dirty=false;
    if(S.detail){S.detail.history.unshift(data.review);renderHistory(S.detail.history);}
    toast('已保存 · '+labelNames[label]+(row.verdict.startsWith('false_')?' · 已记录判定分歧':''));
    renderQueue();
    if(advance && $('#auto-next').checked){
      const next=oldList.slice(position+1).find(id=>S.visible.some(r=>r.id===id));
      if(next)await select(next);
      else if(S.visible.length && !S.visible.some(r=>r.id===row.id))await select(S.visible[0].id);
      else if(!S.visible.length)await select(null);
      else toast('已保存，已到当前队列末尾。');
    }
  }catch(err){S.dirty=true;toast(err.message,true);}
  finally{S.saving=false;paintReview();renderQueue();}
}
function navigate(direction){
  if(!allowNavigate())return;
  const index=S.visible.findIndex(r=>r.id===S.id), next=S.visible[index+direction];
  if(next)select(next.id);
}
function seek(seconds){if(Number.isFinite(video.duration)){video.pause();video.currentTime=Math.min(Math.max(0,seconds),Math.max(0,video.duration-.0001));}}
function frame(direction){const fps=S.detail?.video?.fps;if(fps>0)seek((Math.round(video.currentTime*fps)+direction)/fps);}
function switchTab(tab){
  S.tab=tab; $$('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  for(const t of ['compare','details','history'])$('#'+t+'-panel').classList.toggle('hidden',t!==tab);
  if(tab!=='compare')pauseCompare();
}
async function load(initial=false){
  const data=await api('/api/episodes');
  S.rows=data.episodes;S.policies=data.policies;S.token=data.token;
  const tasks=[...data.tasks,...new Set(S.rows.map(r=>r.task).filter(t=>!data.tasks.includes(t)))];
  S.rows.sort((a,b)=>tasks.indexOf(a.task)-tasks.indexOf(b.task) || a.seed-b.seed || Object.keys(S.policies).indexOf(a.policy)-Object.keys(S.policies).indexOf(b.policy));
  $('#run-name').textContent=data.run;$('#run-name').title=data.run_path;
  $('#save-path').textContent='标注保存于 '+data.review_path; $('#save-path').title=data.review_path;
  $('#global-error').classList.toggle('hidden',!data.warnings.length);
  $('#global-error').textContent=data.warnings.length?`${data.warnings.length} 个文件无法索引：${data.warnings.slice(0,3).join('；')}`:'';
  const requested=initial?new URL(location.href).searchParams.get('episode'):S.id;
  if(initial && S.rows.find(r=>r.id===requested)?.archived)$('#archived').checked=true;
  populateFilters();renderQueue();
  await select(S.rows.some(r=>r.id===requested)?requested:S.visible[0]?.id || null);
  S.loaded=true;
}

$$('#policy,#task,#automatic,#review-filter,#mode,#block,#archived').forEach(el=>el.addEventListener('change',changeFilters));
$('#search').addEventListener('input',()=>{if(!S.dirty && !S.saving){S.page=0;renderQueue();if(!S.visible.some(r=>r.id===S.id))select(S.visible[0]?.id || null);}});
$('#clear-filters').onclick=()=>{if(!allowNavigate())return;$$('.filters select,.filters input').forEach(e=>e.value='');changeFilters();};
$('#page-prev').onclick=()=>{S.page--;renderQueue();$('#episode-list').scrollTop=0;};$('#page-next').onclick=()=>{S.page++;renderQueue();$('#episode-list').scrollTop=0;};
$('#previous').onclick=()=>navigate(-1);$('#next').onclick=()=>navigate(1);
$$('[data-label]').forEach(b=>b.onclick=()=>save(b.dataset.label,true));
$('#save-notes').onclick=()=>save(current()?.review?.label || 'unreviewed',false);
$('#reset-review').onclick=()=>save('unreviewed',false);
$('#notes').oninput=markDirty;
$$('[data-note]').forEach(b=>b.onclick=()=>{if(S.saving)return;$('#notes').value+=($('#notes').value?'；':'')+b.dataset.note;markDirty();});
$('#record-frame').onclick=()=>{if(S.saving)return;const fps=S.detail?.video?.fps;$('#notes').value+=($('#notes').value?'；':'')+`[${video.currentTime.toFixed(3)}s${fps?` / frame ${Math.round(video.currentTime*fps)} (0-based)`:''}] `;markDirty();};
$('#play').onclick=()=>{if(video.paused)video.play().catch(err=>toast('无法播放：'+err.message,true));else video.pause();};
video.onplay=()=>$('#play').textContent='Ⅱ';video.onpause=()=>$('#play').textContent='▶';
video.ontimeupdate=()=>{$('#timeline').value=video.currentTime;$('#timecode').textContent=`${time(video.currentTime)} / ${time(video.duration)}`;};
video.onloadedmetadata=()=>{$('#timeline').max=video.duration;video.playbackRate=Number($('#speed').value);video.ontimeupdate();};
video.onerror=()=>{$('#video-message').textContent='视频无法播放。可在「诊断与原始记录」中打开原视频检查。';$('#video-message').classList.remove('hidden');};
$('#timeline').oninput=e=>seek(Number(e.target.value));$('#speed').onchange=e=>video.playbackRate=Number(e.target.value);
$('#frame-prev').onclick=()=>frame(-1);$('#frame-next').onclick=()=>frame(1);
$('#last-seconds').onclick=()=>seek(video.duration-2);$('#last-frame').onclick=()=>seek(video.duration-(S.detail?.video?.fps?1/S.detail.video.fps:.05));
$('#fullscreen').onclick=()=>$('#video-stage').requestFullscreen().catch(()=>toast('浏览器不支持全屏',true));
$$('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$$('[data-tab]').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
$('#load-compare').onclick=()=>renderCompare($('#load-compare').dataset.loaded!=='1');
$('#show-fp').onclick=()=>{if(allowNavigate()){$('#review-filter').value='false_positive';changeFilters();}};
$('#show-fn').onclick=()=>{if(allowNavigate()){$('#review-filter').value='false_negative';changeFilters();}};
$('#refresh').onclick=async()=>{if(!allowNavigate())return;$('#refresh').disabled=true;try{await api('/api/refresh',{});await load();toast('已刷新归档和标注');}catch(err){toast(err.message,true);}finally{$('#refresh').disabled=false;}};
$('#export-csv').onclick=()=>{location.href='/api/export.csv?archived='+Number($('#archived').checked);};
$('#export-diff').onclick=()=>{location.href='/api/export.csv?only=disagreements&archived='+Number($('#archived').checked);};
window.addEventListener('beforeunload',event=>{if(S.dirty || S.saving){event.preventDefault();event.returnValue='';}});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey || event.metaKey) && event.key==='Enter'){event.preventDefault();$('#save-notes').click();return;}
  if(event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,textarea,select') || !S.id || S.saving)return;
  const key=event.key.toLowerCase();
  if(['1','2','3'].includes(key)){event.preventDefault();save({'1':'success','2':'failure','3':'uncertain'}[key],true);}
  else if(key==='n')navigate(1);else if(key==='p')navigate(-1);
  else if(key===' '){event.preventDefault();$('#play').click();}
  else if(key==='arrowleft'){event.preventDefault();frame(-1);}else if(key==='arrowright'){event.preventDefault();frame(1);}
});
load(true).catch(err=>{$('#global-error').classList.remove('hidden');$('#global-error').textContent='读取失败：'+err.message;$('#run-name').textContent='请检查服务日志与 --run-dir 路径。';});
