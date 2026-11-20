'use strict';
const $ = (id) => document.getElementById(id);
const state = { source: 'file', selected: null, status: null, media: [], lastJob: null, busy: false };
const escapeHTML = (v) => String(v).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = (b) => b >= 1024*1024*1024 ? `${(b/1024/1024/1024).toFixed(2)} GB` : b>=1024*1024 ? `${(b/1024/1024).toFixed(1)} MB` : `${(b/1024).toFixed(0)} KB`;
const api = async (path, options={}) => {
  const res = await fetch(path, options);
  let body;
  try { body = await res.json(); } catch { body = {}; }
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
};
const jsonPost = (path, payload) => api(path,{ method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload) });
function notice(text, type='') {
  $('feedback').textContent = text;
  $('feedback').className = 'feedback ' + type;
}
function setBusy(value) {
  state.busy = !!value;
  ['startBtn','fetchYoutube','uploadZone'].forEach((id) => $(id).disabled = value);
}
function setSource(source) {
  state.source = source;
  for (const item of ['file','youtube','test']) {
    const active = item === source;
    $('source'+item[0].toUpperCase()+item.slice(1)).classList.toggle('selected', active);
    $('source'+item[0].toUpperCase()+item.slice(1)).setAttribute('aria-selected', String(active));
    $(item+'Content').classList.toggle('hidden', !active);
  }
  if (source === 'test') notice('Built-in color bars selected.');
  if (source === 'file') $('selectedVideo').textContent = state.selected || 'None — upload or pick from library';
}
function updateFrequency() {
  const ch = $('channel').value;
  $('monitorChannel').innerHTML = `CH 0${ch} <span class="separator">/</span> ${ch === '3' ? '61.25' : '67.25'} MHz`;
}
function updateOutputNotice() {
  const rf = $('outputMode').value === 'rf';
  $('rfCheck').classList.toggle('hidden', !rf);
  $('outputNotice').classList.toggle('warning', rf);
  $('outputNotice').innerHTML = rf ? '<span class="notice-mark">!</span><span>HACKRF TX — Must be an authorized RF setup with a properly attenuated, DC-isolated connection. Amplifier stays OFF and TX gain stays at 0 dB.</span>' : '<span class="notice-mark">i</span><span>PREVIEW MODE — No RF signal is transmitted. The video plays in this browser.</span>';
}
function populateMedia() {
  const el = $('library');
  $('mediaCount').textContent = `${state.media.length} ITEM${state.media.length === 1 ? '' : 'S'}`;
  if (!state.media.length) {
    el.innerHTML = '<div class="empty-library">No media added yet. Upload an MP4 or paste a YouTube link.</div>';
    return;
  }
  el.innerHTML = state.media.map(f => `<div class="media-row ${f.name===state.selected ? 'selected':''}" data-select="${escapeHTML(f.name)}"><div class="media-icon">▶</div><div class="media-desc"><strong title="${escapeHTML(f.name)}">${escapeHTML(f.name)}</strong><small>${bytes(f.size)} · ${new Date(f.modified).toLocaleDateString()}</small></div><button class="delete-media" data-delete="${escapeHTML(f.name)}" title="Delete ${escapeHTML(f.name)}" aria-label="Delete ${escapeHTML(f.name)}">✕</button></div>`).join('');
}
async function refreshLibrary() {
  const res = await api('/api/media');
  state.media = res.items;
  if (state.selected && !state.media.some(x=>x.name===state.selected)) state.selected=null;
  if (!state.selected && state.media.length) state.selected=state.media[0].name;
  populateMedia();
  $('selectedVideo').textContent = state.selected || 'None — upload or pick from library';
}
function chooseVideo(filename) {
  state.selected=filename;
  setSource('file');
  populateMedia();
  notice(`Selected: ${filename}`,'success');
}
async function uploadFile(file) {
  if (!file) return;
  setBusy(true);
  notice(`Uploading ${file.name}…`);
  try {
    const result = await api('/api/upload?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    await refreshLibrary();
    chooseVideo(result.item.name);
    notice(`Uploaded ${file.name}. Click START to preview.`,'success');
  } catch (e) { notice(e.message,'error'); }
  finally { setBusy(false); $('filePicker').value=''; }
}
async function fetchYoutube() {
  const url = $('youtubeUrl').value.trim();
  if (!url) return notice('Paste a YouTube URL first.','error');
  setBusy(true);
  notice('Starting download…');
  try {
    const result = await jsonPost('/api/youtube',{url});
    state.lastJob = result.job.id;
    notice('Downloading. You can keep using the interface.');
  } catch(e) { notice(e.message,'error'); }
  finally { setBusy(false); }
}
function showMonitor(active) {
  const video = $('videoPreview');
  const bars = $('colorbars');
  const center = $('screenCenter');
  const stamp = $('screenStamp');
  if (!active) {
    video.pause();video.hidden=true;video.removeAttribute('src');video.load();
    bars.classList.remove('visible');center.classList.remove('hidden');
    stamp.textContent='PREVIEW ONLY';
    $('playSummary').textContent='Load a source to begin';
    $('stateTag').textContent='IDLE';$('stateTag').classList.remove('playing');
    return;
  }
  $('stateTag').textContent=active.mode==='rf'?'TX ACTIVE':'PREVIEW';
  $('stateTag').classList.add('playing');
  $('playSummary').textContent=active.source==='test'?'Built-in color bars':active.name;
  stamp.textContent=active.mode==='rf'?'HACKRF TRANSMITTING':'BROWSER PREVIEW';
  if (active.source === 'test') {
    video.pause();video.hidden=true;video.removeAttribute('src');video.load();
    bars.classList.add('visible');center.classList.add('hidden');
  } else {
    const path='/media/'+encodeURIComponent(active.name);
    if (video.getAttribute('src')!==path) {
      video.src=path;video.loop=active.repeat;video.muted=true;
      video.play().catch(()=>{});
    }
    video.hidden=false;bars.classList.remove('visible');center.classList.add('hidden');
  }
}
let lastActiveKey='';
function paintStatus(data) {
  state.status=data;
  const a=data.active;
  const nextKey=a?`${a.started_at}/${a.name}/${a.mode}`:'';
  if(lastActiveKey!==nextKey){ showMonitor(a);lastActiveKey=nextKey; }
  $('headDot').classList.toggle('busy',!!a);
  $('headerStatus').textContent=a?(a.mode==='rf'?'TRANSMITTING':'PREVIEWING'):'SYSTEM READY';
  $('headerMode').textContent=data.rf_enabled?'RF AVAILABLE':'PREVIEW MODE';
  $('txLabel').textContent=data.rf_enabled?'ENABLED':'LOCKED';
  $('txLabel').classList.toggle('enabled',data.rf_enabled);
  const statusMark = (found) => found?'<span class="diag-dot yes"></span> READY':'<span class="diag-dot" style="background:#eaa591"></span> MISSING';
  $('hacktvStatus').innerHTML=statusMark(data.hacktv_found);
  $('ffmpegStatus').innerHTML=statusMark(data.ffmpeg_found);
  $('ytdlpStatus').innerHTML=statusMark(data.yt_dlp_found);
  $('rfStatus').textContent=data.rf_enabled?'UNLOCKED':'LOCKED';
  $('rfStatus').classList.toggle('locked',!data.rf_enabled);
  $('logsView').textContent=(data.recent_logs||[]).join('\n')||'(No log entries yet)';
  if (state.lastJob) {
    const job=data.jobs.find(j=>j.id===state.lastJob);
    if(job?.state==='done') {
      state.lastJob=null;
      refreshLibrary().then(()=>{chooseVideo(job.name);notice('YouTube video saved! Ready to start.','success');}).catch(()=>{});
    } else if(job?.state==='failed') {
      state.lastJob=null;
      notice('YouTube download failed: '+job.error,'error');
    }
  }
}
async function refreshStatus() {
  try { paintStatus(await api('/api/status')); }
  catch (e) { $('headerStatus').textContent='OFFLINE';$('headDot').classList.add('busy');notice('Server unavailable: '+e.message,'error'); }
}
async function start() {
  const source=state.source==='test'?'test':'file';
  if(state.source==='youtube')return notice('Save a YouTube video first; it will appear in your library.','error');
  if(source==='file'&&!state.selected)return notice('Upload or select a local video first.','error');
  const mode=$('outputMode').value;
  if(mode==='rf' && !$('benchConfirmed').checked) return notice('Confirm the lawful, isolated RF bench connection first.','error');
  setBusy(true);notice('Starting…');
  try {
    await jsonPost('/api/play',{
      source,name:source==='file'?state.selected:null,mode,
      channel:$('channel').value,repeat:$('repeat').checked,
      bench_confirmed:$('benchConfirmed').checked
    });
    await refreshStatus();notice(mode==='rf'?'HackTV started. Check the Quasar tuner.':'Browser preview started. No RF emitted.','success');
  } catch(e){notice(e.message,'error');await refreshStatus();}
  finally{setBusy(false);}
}
async function stop() {
  try{await jsonPost('/api/stop',{});await refreshStatus();notice('Stopped.','success');}
  catch(e){notice(e.message,'error');}
}
$('filePicker').addEventListener('change',e=>uploadFile(e.target.files[0]));
$('uploadZone').addEventListener('click',()=>$('filePicker').click());
$('uploadZone').addEventListener('dragover',e=>{e.preventDefault();$('uploadZone').classList.add('drag');});
$('uploadZone').addEventListener('dragleave',()=>$('uploadZone').classList.remove('drag'));
$('uploadZone').addEventListener('drop',e=>{e.preventDefault();$('uploadZone').classList.remove('drag');uploadFile(e.dataTransfer.files[0]);});
for(const el of document.querySelectorAll('.source-tab'))el.addEventListener('click',()=>setSource(el.dataset.source));
$('channel').addEventListener('change',updateFrequency);
$('outputMode').addEventListener('change',updateOutputNotice);
$('startBtn').addEventListener('click',start);$('stopBtn').addEventListener('click',stop);
$('fetchYoutube').addEventListener('click',fetchYoutube);
$('refreshBtn').addEventListener('click',()=>refreshLibrary().catch(e=>notice(e.message,'error')));
$('diagRefresh').addEventListener('click',refreshStatus);
$('logsToggle').addEventListener('click',()=>{
  const hidden=$('logsView').classList.toggle('hidden');$('logsToggle').textContent=hidden?'SHOW':'HIDE';
});
$('library').addEventListener('click',async(e)=>{
  const deleteBtn=e.target.closest('[data-delete]');
  if(deleteBtn){
    const name=deleteBtn.dataset.delete;
    if(!window.confirm(`Delete ${name}?`))return;
    try{await api('/api/media/'+encodeURIComponent(name),{method:'DELETE'});await refreshLibrary();notice('Deleted '+name,'success');}
    catch(err){notice(err.message,'error');}
    return;
  }
  const item=e.target.closest('[data-select]'); if(item)chooseVideo(item.dataset.select);
});
function clock(){ $('monitorTime').textContent=new Date().toLocaleTimeString('en-GB',{hour12:false}); }
clock();setInterval(clock,1000);updateFrequency();updateOutputNotice();
Promise.all([refreshLibrary(),refreshStatus()]).catch(e=>notice(e.message,'error'));
setInterval(refreshStatus,3000);
