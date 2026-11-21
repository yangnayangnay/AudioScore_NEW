# -*- coding: utf-8 -*-
"""v4-layout: input -> overall-bar -> queue-panel. Full script rebuild
(v8+v9 merged, badge/threshold/auto-pp kept, layout fixed)."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

V4JS = r"""<script>
(function(){
'use strict';
var QKEY='as_queue_state',PENDKEY='as_pending_dl',DLSET='as_dl_done',ARCH='as_run_archive';
var PPS=['pp1','pp2','pp3','pp4','pp5','pp6','pp7','pp8','pp9','pp10','pp11','pp12','pp13','pp14','pp15','pp16'];
function el(id){return document.getElementById(id);}
function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);
  if(v===null){localStorage.removeItem(k);return null;}localStorage.setItem(k,v);}
  catch(e){return null;}}
function jsGet(k,d){try{var v=JSON.parse(localStorage.getItem(k)||'null');
  return v==null?d:v;}catch(e){return d;}}
function jsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
function toast(m){var t=el('asToast');
  if(!t){t=document.createElement('div');t.id='asToast';
    t.style.cssText='position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'+
    'background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;z-index:10000';
    document.body.appendChild(t);}
  t.textContent=m;t.style.opacity='1';
  clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},3200);}
function DLURL(j){if(!j)return '';var c=[j.download_url,j.download,j.file_url,j.file,
  j.url,j.midi,j.midi_url,j.result_url,j.result];
  for(var i=0;i<c.length;i++)if(typeof c[i]==='string'&&c[i])return c[i];return '';}
function outName(on){var b=(on||'').replace(/\.[^.]+$/,'');if(!b)b='output';
  if(/audioscore$/i.test(b))return b+'.mid';return b+'AudioScore.mid';}
function saveBlob(url,fn,cb){fetch(url).then(function(r){return r.blob();})
  .then(function(bl){var u=URL.createObjectURL(bl);var t=document.createElement('a');
  t.href=u;t.download=fn;document.body.appendChild(t);t.click();t.remove();
  setTimeout(function(){URL.revokeObjectURL(u);},4000);if(cb)cb(true);})
  .catch(function(){if(cb)cb(false);});}
function buildZip(items){
  var CT=(function(){var t=[],c,n,k;for(n=0;n<256;n++){c=n;
    for(k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);t[n]=c>>>0;}return t;})();
  function crc32(u8){var c=0xFFFFFFFF,i;
    for(i=0;i<u8.length;i++)c=CT[(c^u8[i])&0xFF]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}
  var enc=new TextEncoder();
  function w16(v){return [v&255,(v>>>8)&255];}
  function w32(v){return [v&255,(v>>>8)&255,(v>>>16)&255,(v>>>24)&255];}
  return Promise.all(items.map(function(it){
    return it.blob.arrayBuffer().then(function(ab){
      return {name:it.name,u8:new Uint8Array(ab)};});}))
  .then(function(files){
    var parts=[],central=[],off=0;
    files.forEach(function(f){
      var n=f.u8.length,c=crc32(f.u8),nb=enc.encode(f.name);
      var lh=[].concat(w32(0x04034b50),w16(20),w16(0x0800),w16(0),w16(0),w16(0),
        w32(c),w32(n),w32(n),w16(nb.length),w16(0));
      parts.push(new Uint8Array(lh),nb,f.u8);
      var cd=[].concat(w32(0x02014b50),w16(20),w16(20),w16(0x0800),w16(0),w16(0),
        w16(0),w32(c),w32(n),w32(n),w16(nb.length),w16(0),w16(0),w16(0),w16(0),
        w32(0),w32(off));
      central.push(new Uint8Array(cd),nb);
      off+=lh.length+nb.length+n;});
    var cdSize=central.reduce(function(a,x){return a+x.length;},0);
    var eo=new Uint8Array([].concat(w32(0x06054b50),w16(0),w16(0),w16(files.length),
      w16(files.length),w32(cdSize),w32(off),w16(0)));
    return new Blob(parts.concat(central,[eo]),{type:'application/zip'});});
}
function fmtMs(ms){var s2=Math.round(ms/1000);var m=Math.floor(s2/60);s2=s2%60;
  return m>0?m+'\u5206'+(s2<10?'0':'')+s2+'\u79d2':s2+'\u79d2';}
function saveOpts(){var o={};PPS.forEach(function(id){var e=el(id);if(e)o[id]=!!e.checked;});
  var be=el('backend');if(be)o.backend=be.value;jsSet('as_opts',o);}
(function(){var o=jsGet('as_opts',{});
  PPS.forEach(function(id){var e=el(id);if(e&&(id in o))e.checked=!!o[id];});
  var be=el('backend');if(be&&o.backend)be.value=o.backend;})();
PPS.forEach(function(id){var e=el(id);if(e)e.addEventListener('change',saveOpts);});
var be=el('backend');if(be)be.addEventListener('change',saveOpts);
var input=document.querySelector('input[type="file"]');
if(input)try{input.multiple=true;}catch(e){}
var btn=null,autoPass=false,logOpen=false;
var cands=document.querySelectorAll('button,input[type="button"],input[type="submit"]');
for(var i=0;i<cands.length;i++){var t=((cands[i].textContent||'')+(cands[i].value||'')).trim();
  if(/\u5f00\u59cb|\u8f6c\u6362|\u8f6c\u5199/.test(t)){btn=cands[i];break;}}
function lockBtn(on){if(!btn)return;
  btn.style.opacity=on?'0.45':'';
  btn.style.pointerEvents=on?'none':'';
  btn.style.cursor=on?'not-allowed':'';}
var obar=document.createElement('div');obar.id='asOverallWrap';
obar.style.cssText='display:flex;align-items:center;gap:10px;margin:10px 0 6px';
obar.innerHTML='<span id="asOCount" style="font-size:12px;opacity:.65;white-space:nowrap"></span>'+
 '<div style="flex:1;height:6px;background:#2a2f3a;border-radius:3px;overflow:hidden">'+
 '<div id="asQOBar" style="height:100%;width:0;background:#5b8dd6;transition:width .4s"></div></div>'+
 '<span id="asQEta" style="font-size:12px;opacity:.6;white-space:nowrap"></span>';
var panel=document.createElement('div');panel.id='asQueuePanel';
panel.style.cssText='border:1px solid #3a3f4a;border-radius:8px;padding:8px 12px;'+
 'margin:6px 0 10px;position:sticky;top:0;z-index:500;background:rgba(16,18,24,.97);'+
 'box-shadow:0 2px 10px rgba(0,0,0,.35)';
panel.innerHTML='<div style="display:flex;align-items:center;gap:8px">'+
 '<span style="font-weight:600">\u8f6c\u6362\u961f\u5217</span>'+
 '<span id="asQFold" style="cursor:pointer;opacity:.7;padding:0 4px">\u25be</span>'+
 '<span id="asQLog" style="cursor:pointer;font-size:12px;color:#8ab4e0">\u65e5\u5fd7</span>'+
 '<span id="asQRetry" style="cursor:pointer;font-size:12px;color:#e0c98a">'+
 '\u21bb\u91cd\u8bd5\u5931\u8d25</span>'+
 '<span id="asQClear" style="cursor:pointer;font-size:12px;color:#e08a8a;margin-left:auto">'+
 '\u6e05\u7a7a</span></div>'+
 '<div id="asQBody"><div id="asQList" style="display:flex;flex-direction:column;'+
 'gap:6px;min-height:28px;margin-top:8px"></div>'+
 '<div style="display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap">'+
 '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
 '<label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">'+
 '<input type="checkbox" id="asChkItem">\u6bcf\u5b8c\u6210\u4e00\u9996\u7acb\u5373\u5355\u72ec\u4e0b\u8f7d</label>'+
 '<label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">'+
 '<input type="checkbox" id="asChkZip" checked>\u7ed3\u675f\u65f6\u518d\u7ed9 ZIP \u603b\u5305</label>'+
 '<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px">'+
 '\u7f6e\u4fe1\u5ea6\u2265 <input type="number" id="asThresh" min="0.05" max="0.9" '+
 'step="0.05" value="0.3" style="width:56px"></label>'+
 '</div></div>'+
 '<pre id="asLogBox" style="display:none;margin-top:6px;max-height:180px;overflow:auto;'+
 'background:#0d0f14;border:1px solid #2a2f3a;border-radius:6px;padding:8px;'+
 'font:11px/1.5 Consolas,monospace;color:#9fb0c0;white-space:pre-wrap"></pre>';
if(input&&input.parentNode){
  input.parentNode.insertBefore(obar,input.nextSibling);
  input.parentNode.insertBefore(panel,obar.nextSibling);
}else{document.body.appendChild(obar);document.body.appendChild(panel);}
var chkItem=el('asChkItem'),chkZip=el('asChkZip');
chkItem.checked=ls('as_autodl')!=='0';
chkZip.checked=ls('as_zipmode')!=='0';
chkItem.onchange=function(){ls('as_autodl',chkItem.checked?'1':'0');};
chkZip.onchange=function(){ls('as_zipmode',chkZip.checked?'1':'0');};
var thrIn=el('asThresh');
if(thrIn){thrIn.value=ls('as_thresh')||'0.3';
  thrIn.onchange=function(){var v=parseFloat(thrIn.value);
    if(!(v>0))v=0.3;thrIn.value=v;ls('as_thresh',String(v));};}
function getThr(){var v=parseFloat(ls('as_thresh')||'0.3');return v>0?v:0.3;}
var list=el('asQList'),body=el('asQBody'),fold=el('asQFold');
try{if(ls('as_qfold')==='1'){body.style.display='none';fold.textContent='\u25b8';}}catch(e){}
fold.onclick=function(){var open=body.style.display!=='none';
  body.style.display=open?'none':'';fold.textContent=open?'\u25b8':'\u25be';
  ls('as_qfold',open?'1':'0');};
el('asQLog').onclick=function(){var box=el('asLogBox');
  logOpen=(box.style.display==='none');
  box.style.display=logOpen?'':'none';
  if(logOpen)fetchLog();};
function esc(x){return String(x).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
var Q=[],busy=false,cur=null,phase='idle',t0=0,prevId='',dragIdx=-1,
    draining=false,lastFail=0;
(function(){var sv=jsGet(QKEY,null);if(!sv)return;
  sv.forEach(function(x){x.file=null;
    if(x.st==='queued'||x.st==='run'){x.st='err';x.lost=true;
      x.reason='\u9875\u9762\u5237\u65b0\u540e\u6587\u4ef6\u4e22\u5931\uff0c\u8bf7\u91cd\u65b0\u6dfb\u52a0';}
    Q.push(x);});})();
function persist(){jsSet(QKEY,Q.map(function(x){return{name:x.name,oname:x.oname,
  size:x.size,st:x.st,dl:x.dl,jid:x.jid,reason:x.reason,lost:!!x.lost};}));}
function creep(it){var e=Date.now()-(it.tStart||Date.now());
  return 12+73*(1-Math.exp(-e/60000));}
function renderQ(){
  list.innerHTML='';var dn=0,rem=0;
  Q.forEach(function(it,ix){
    if(it.st==='queued'&&it.file)rem++;
    if(it.st==='done')dn++;
    var row=document.createElement('div');
    row.className='asQItem';row.draggable=true;row.dataset.i=ix;
    row.dataset.oname=it.oname||it.name||'';row.dataset.jid=it.jid||'';
    row.style.cssText='display:flex;flex-direction:column;gap:2px;padding:6px 8px;'+
      'border:1px solid #3a3f4a;border-radius:6px;cursor:grab';
    var stt={queued:'\u5f85\u8f6c\u6362',run:'',done:'\u5b8c\u6210',
      err:'\u5931\u8d25'}[it.st]||'';
    var stc={queued:'#8ab4e0',run:'#e0c98a',done:'#8ad0a0',err:'#e08a8a'}[it.st]||'#999';
    if(it.st==='run'){
      var e=Date.now()-(it.tStart||Date.now());
      var mm=Math.floor(e/60000),ss=Math.floor(e/1000)%60;
      stt=(it.subphase==='submit')?('\u63d0\u4ea4\u4e2d '+mm+':'+(ss<10?'0':'')+ss):
        ((it.realPct!=null)?('\u63a8\u7406 '+it.realPct+'% '+mm+':'+(ss<10?'0':'')+ss):
         ('\u63a8\u7406\u4e2d '+mm+':'+(ss<10?'0':'')+ss));}
    var rt=it.reason||'';
    var badge='';
    if(it.instr===null)badge='<span style="font-size:11px;color:#7fa6d9;'+
      'white-space:nowrap">\u8bc6\u522b\u4e2d\u2026</span>';
    else if(it.instr&&it.instr.length)badge='<span style="font-size:11px;'+
      'color:#7fa6d9;white-space:nowrap">'+
      esc(it.instr.map(function(x){return x.n+' '+x.c.toFixed(2);}).join(' \u00b7 '))+
      '</span>';
    else if(it.instr&&it.instrSrc==='fail')badge='<span style="font-size:11px;'+
      'opacity:.5;white-space:nowrap">\u8bc6\u522b\u5931\u8d25</span>';
    var retry=(it.st==='err'&&!it.lost)?
      '<span class="asQR" data-x="'+ix+'" style="cursor:pointer;color:#e0c98a" '+
      'title="'+esc(rt)+'">\u21bb</span>':'';
    var l1='<div style="display:flex;align-items:center;gap:8px">'+
      '<span style="opacity:.5">\u2195</span>'+
      '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '+
      'title="'+esc(rt||it.oname||it.name)+'">'+esc(it.oname||it.name||'')+'</span>'+
      badge+
      (it.dl?'<a href="'+it.dl+'" class="asQDl" style="font-size:12px;color:#8ad0a0">'+
       esc(outName(it.oname||it.name||''))+'</a>':'')+
      '<span style="font-size:12px;color:'+stc+'" title="'+esc(rt)+'">'+stt+'</span>'+
      retry+'<span class="asQX" data-x="'+ix+'" style="cursor:pointer;color:#e08a8a;'+
      'font-weight:700">\u00d7</span></div>';
    var l2='';
    if(it.st==='run'){
      var p=(it.realPct!=null)?(12+73*it.realPct/100):creep(it);
      l2='<div style="display:flex;align-items:center;gap:8px">'+
        '<div style="flex:1;height:4px;background:#2a2f3a;border-radius:2px;'+
        'overflow:hidden"><div style="height:100%;width:'+p.toFixed(1)+'%;'+
        'background:#5b8dd6;transition:width .5s"></div></div></div>';}
    else if(it.st==='done'){
      l2='<div style="display:flex"><div style="flex:1;height:3px;background:#2a3a2f;'+
        'border-radius:2px;overflow:hidden"><div style="height:100%;width:100%;'+
        'background:#8ad0a0"></div></div></div>';}
    row.innerHTML=l1+l2;
    list.appendChild(row);});
  el('asOCount').textContent=Q.length?('\u5b8c\u6210 '+dn+'/'+Q.length):'';
  el('asQOBar').style.width=Q.length?(dn/Q.length*100+'%'):'0';
  var avg=parseFloat(ls('as_avgms')||'0');
  el('asQEta').textContent=(busy&&rem&&avg)?('\u5269\u7ea6 '+fmtMs(avg*rem)):'';
  lockBtn(busy);
  persist();}
function detectItems(from){
  for(var k=from;k<Q.length;k++)(function(it){
    if(!it.file)return;it.instr=null;renderQ();
    var fd=new FormData();fd.append('file',it.file,it.name);
    fetch('/api/instruments',{method:'POST',body:fd})
      .then(function(r){return r.json();})
      .then(function(j){it.instr=(j&&j.instruments)||[];
        it.instrSrc=(j&&j.model)||'';renderQ();})
      .catch(function(){it.instr=[];it.instrSrc='fail';renderQ();});})(Q[k]);}
el('asQAdd').onclick=function(){
  if(!input||!input.files||!input.files.length){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6');return;}
  var from=Q.length;
  for(var k=0;k<input.files.length;k++)
    Q.push({file:input.files[k],name:input.files[k].name,oname:input.files[k].name,
      size:input.files[k].size,st:'queued',dl:'',jid:'',reason:'',realPct:null,
      instr:null,instrSrc:''});
  try{input.value='';}catch(e){}
  renderQ();detectItems(from);};
list.addEventListener('click',function(e){
  var x=e.target.closest&&e.target.closest('.asQX');
  if(x){var i=+x.dataset.x;if(busy&&cur===Q[i]){toast('\u8f6c\u6362\u4e2d\u4e0d\u53ef\u5220');return;}
    Q.splice(i,1);renderQ();return;}
  var r=e.target.closest&&e.target.closest('.asQR');
  if(r){var j=+r.dataset.x,it=Q[j];
    if(it&&it.st==='err'&&it.file){it.st='queued';it.reason='';it.dl='';it.jid='';
      renderQ();toast('\u5df2\u91cd\u65b0\u6392\u961f\uff0c\u70b9\u5f00\u59cb\u8f6c\u6362');}
    else if(it&&it.lost)toast('\u6587\u4ef6\u5df2\u4e22\u5931\uff0c\u8bf7\u91cd\u65b0\u6dfb\u52a0');}});
el('asQRetry').onclick=function(){var n=0;
  Q.forEach(function(x){if(x.st==='err'&&x.file){x.st='queued';x.reason='';x.dl='';x.jid='';n++;}});
  renderQ();if(n)toast('\u91cd\u65b0\u6392\u961f '+n+' \u4e2a\uff0c\u70b9\u5f00\u59cb\u8f6c\u6362');};
el('asQClear').onclick=function(){if(busy){toast('\u8f6c\u6362\u4e2d\u4e0d\u53ef\u6e05\u7a7a');return;}
  Q=[];renderQ();};
list.addEventListener('dragstart',function(e){
  var it=e.target.closest&&e.target.closest('.asQItem');if(!it)return;
  dragIdx=+it.dataset.i;});
list.addEventListener('dragover',function(e){e.preventDefault();});
list.addEventListener('drop',function(e){e.preventDefault();
  var it=e.target.closest&&e.target.closest('.asQItem');if(!it||dragIdx<0)return;
  var to=+it.dataset.i;if(to===dragIdx)return;
  var m=Q.splice(dragIdx,1)[0];Q.splice(to,0,m);dragIdx=-1;renderQ();});
function recordId(id){if(id)ls('as_last_job',id);}
try{var _f=window.fetch;
  window.fetch=function(u,o){return _f.apply(this,arguments).then(function(r){
    try{var s2=(typeof u==='string')?u:(u&&u.url)||'';
      if(s2.indexOf('/api/jobs')>=0&&o&&(o.method||'GET').toUpperCase()==='POST'){
        r.clone().json().then(function(j){recordId(j&&(j.id||j.job_id));}).catch(function(){});
        try{var fi=document.querySelector('input[type="file"]');
          if(fi&&fi.files&&fi.files[0])ls('as_last_name',fi.files[0].name);}catch(e){}}}
    catch(e){}return r;});};}catch(e){}
try{var _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;
    return _o.apply(this,arguments);};
  XMLHttpRequest.prototype.send=function(){var x=this;
    try{if(x.__m&&String(x.__m).toUpperCase()==='POST'&&
        String(x.__u).indexOf('/api/jobs')>=0){
      x.addEventListener('load',function(){
        try{var j=JSON.parse(x.responseText);recordId(j&&(j.id||j.job_id));}
        catch(e){ls('as_post_status',String(x.status||'ERR'));}});}}
    catch(e){}
    return _s.apply(this,arguments);};}catch(e){}
function setFiles(f){try{var dt=new DataTransfer();dt.items.add(f);
  input.files=dt.files;return true;}catch(e){return false;}}
function submitNext(){
  var nxt=null;Q.forEach(function(x){if(!nxt&&x.st==='queued'&&x.file)nxt=x;});
  if(!nxt){busy=false;phase='idle';releaseWake();lockBtn(false);renderQ();
    toast('\u961f\u5217\u5168\u90e8\u5b8c\u6210');finishZip();return;}
  cur=nxt;cur.st='run';cur.subphase='submit';cur.reason='';cur.dl='';cur.jid='';
  cur.realPct=null;
  (function(it){var c=it.instr||[];if(!c.length)return;
    var thr=getThr(),above=c.filter(function(x){return x.c>=thr;});
    var p4=el('pp4'),p5=el('pp5');
    if(p4)p4.checked=above.length>=2;
    if(p5&&above.length)p5.checked=true;
    saveOpts();})(cur);
  renderQ();
  prevId=ls('as_last_job')||'';
  if(!input||!setFiles(cur.file)){cur.st='err';
    cur.reason='\u65e0\u6cd5\u5199\u5165\u6587\u4ef6\u8f93\u5165\u6846';
    renderQ();cur=null;phase='gap';t0=Date.now();return;}
  ls('as_last_name',cur.oname||cur.name||'');
  autoPass=true;btn.click();setTimeout(function(){autoPass=false;},0);
  phase='submit';t0=Date.now();}
function advance(){cur=null;phase='gap';t0=Date.now();}
var logInflight=false;
function fetchLog(){
  if(logInflight)return;logInflight=true;
  fetch('/api/as/logs?n=16',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){logInflight=false;
    if(j&&cur&&j.progress!=null&&(j.now-j.progress_at)<15)cur.realPct=j.progress;
    var box=el('asLogBox');if(!box||box.style.display==='none')return;
    var txt=(j&&j.lines||[]).map(function(x){
      return x.t+' '+(x.s==='err'?'!':'>')+' '+x.l;}).join('\n');
    var atB=box.scrollTop+box.clientHeight>=box.scrollHeight-10;
    box.textContent=txt||'(\u6682\u65e0\u65e5\u5fd7)';
    if(atB)box.scrollTop=box.scrollHeight;})
  .catch(function(){logInflight=false;});}
function tick(){
  if(!busy){drainPending();finishZip();return;}
  if(phase==='gap'){if(Date.now()-t0>600)submitNext();return;}
  if(phase==='submit'){
    var id=ls('as_last_job')||'';
    if(id&&id!==prevId&&cur){cur.jid=id;cur.subphase='run';
      cur.tStart=Date.now();phase='run';t0=Date.now();renderQ();return;}
    if(Date.now()-t0>20000&&cur){
      cur.st='err';cur.reason='20\u79d2\u672a\u6355\u83b7\u4efb\u52a1\u53f7(HTTP '+
        (ls('as_post_status')||'?')+')\uff0c\u770b\u670d\u52a1\u5668\u65e5\u5fd7';
      renderQ();advance();return;}
    return;}
  if(phase==='run'){
    if(cur&&cur.jid){
      fetch('/api/jobs/'+cur.jid,{cache:'no-store'}).then(function(r){
        return r.ok?r.json():null;}).then(function(j){
        if(!j||!busy||phase!=='run'||!cur)return;
        if(j.status==='done'){cur.st='done';cur.dl=DLURL(j);
          var el2=Date.now()-(cur.tStart||Date.now());
          if(el2>1000){var old=parseFloat(ls('as_avgms')||String(el2));
            ls('as_avgms',String(old*0.6+el2*0.4));}
          if(!cur.dl)cur.reason='\u5b8c\u6210\u4f46\u672a\u8bc6\u522b\u4e0b\u8f7d\u5730\u5740';
          renderQ();queueForDownload(cur);advance();return;}
        if(j.status==='error'){cur.st='err';
          cur.reason='\u670d\u52a1\u5668\u8f6c\u6362\u51fa\u9519\uff0c\u770b\u65e5\u5fd7';
          renderQ();advance();return;}}).catch(function(){});}
    fetchLog();
    renderQ();}}
try{var b=new Blob(['setInterval(function(){postMessage(1)},1000);'],
    {type:'text/javascript'});
  var w=new Worker(URL.createObjectURL(b));
  w.onmessage=function(){tick();};}catch(e){setInterval(tick,1000);}
var wl=null;
function tryWake(){try{if(navigator.wakeLock&&navigator.wakeLock.request)
  navigator.wakeLock.request('screen').then(function(l){wl=l;}).catch(function(){});}
  catch(e){}}
function releaseWake(){try{if(wl){wl.release();wl=null;}}catch(e){}}
document.addEventListener('visibilitychange',function(){
  if(!document.hidden){if(busy)tryWake();drainPending();finishZip();}});
function dlHas(jid){return jid&&jsGet(DLSET,[]).indexOf(jid)>=0;}
function dlMark(jid){if(!jid)return;var a=jsGet(DLSET,[]);
  if(a.indexOf(jid)<0){a.push(jid);if(a.length>200)a=a.slice(-200);jsSet(DLSET,a);}}
function pend(){return jsGet(PENDKEY,[]);}
function pendSet(a){jsSet(PENDKEY,a);}
function arch(){return jsGet(ARCH,[]);}
function archSet(a){jsSet(ARCH,a);}
function queueForDownload(it){
  if(!chkItem.checked)return;
  var jid=it.jid||'';
  if(dlHas(jid))return;
  var rec={jid:jid,url:it.dl||'',name:outName(it.oname||it.name||'')};
  var a=pend();a.push(rec);pendSet(a);
  var g=arch();g.push(rec);archSet(g);
  if(document.hidden)toast('\u5b8c\u6210\uff0c\u56de\u5230\u9875\u9762\u540e\u8865\u4e0b\u8f7d');}
function drainPending(){
  if(document.hidden||!chkItem.checked||draining)return;
  if(Date.now()-lastFail<8000)return;
  var a=pend().filter(function(e){return !dlHas(e.jid);});
  if(!a.length){pendSet([]);return;}
  draining=true;
  var e=a[0];
  if(e.url){saveBlob(e.url,e.name,function(good){
    draining=false;
    if(good){dlMark(e.jid);
      pendSet(pend().filter(function(x){return x.jid!==e.jid;}));
      toast('\u5df2\u4e0b\u8f7d '+e.name);}
    else{lastFail=Date.now();
      toast('\u5355\u72ec\u4e0b\u8f7d\u5931\u8d25\uff0c\u7ed3\u675f\u65f6 ZIP \u603b\u5305\u5151\u5e95');}});}
  else{fetch('/api/jobs/'+e.jid,{cache:'no-store'}).then(function(r){
    return r.json();}).then(function(j){var u=DLURL(j);
    if(u){e.url=u;var b3=pend();b3[0]=e;pendSet(b3);}
    draining=false;}).catch(function(){draining=false;});}}
function finishZip(){
  if(document.hidden||!chkZip.checked||draining)return;
  var g=arch();if(!g.length)return;
  draining=true;
  var d=new Date();function p2(x){return (x<10?'0':'')+x;}
  var zname='AudioScore_'+d.getFullYear()+p2(d.getMonth()+1)+p2(d.getDate())+
    '_'+p2(d.getHours())+p2(d.getMinutes())+'_'+g.length+'\u9996.zip';
  toast('\u6b63\u5728\u6253\u5305\u603b\u5305 '+g.length+' \u4e2a MIDI ...');
  Promise.all(g.map(function(e){
    var got=(e.url)?Promise.resolve(e.url):
      fetch('/api/jobs/'+e.jid,{cache:'no-store'}).then(function(r){
        return r.json();}).then(function(j){return DLURL(j);})
        .catch(function(){return '';});
    return got.then(function(u){
      if(!u)return null;
      return fetch(u).then(function(r){return r.blob();})
        .then(function(bl){return {name:e.name,blob:bl};})
        .catch(function(){return null;});});}))
  .then(function(items){
    items=items.filter(Boolean);draining=false;
    if(!items.length){toast('\u6253\u5305\u5931\u8d25\uff0c\u6587\u4ef6\u4ecd\u5728\u670d\u52a1\u5668\u78c1\u76d8');return;}
    return buildZip(items).then(function(zb){
      var u=URL.createObjectURL(zb);
      var t=document.createElement('a');t.href=u;t.download=zname;
      document.body.appendChild(t);t.click();t.remove();
      setTimeout(function(){URL.revokeObjectURL(u);},6000);
      archSet([]);
      toast('\u5df2\u81ea\u52a8\u4e0b\u8f7d '+zname);});})
  .catch(function(){draining=false;
    toast('\u6253\u5305\u5f02\u5e38\uff0c\u6587\u4ef6\u4ecd\u5728\u670d\u52a1\u5668\u78c1\u76d8');});}
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('.asQDl');
  if(!a)return;e.preventDefault();
  var row=a.closest('.asQItem');
  saveBlob(a.getAttribute('href'),outName(row?row.dataset.oname:''),function(){});});
document.addEventListener('click',function(e){
  if(!btn)return;var t=e.target;
  if(!(t===btn||(btn.contains&&btn.contains(t))))return;
  if(autoPass){autoPass=false;return;}
  e.preventDefault();e.stopPropagation();
  if(busy){toast('\u961f\u5217\u8f6c\u6362\u4e2d');return;}
  var qc=Q.filter(function(x){return x.st==='queued'&&x.file;}).length;
  if(qc===0){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6\u5e76\u70b9\u201c\uff0b\u52a0\u5165\u961f\u5217\u201d');return;}
  busy=true;phase='gap';t0=0;archSet([]);tryWake();lockBtn(true);renderQ();},true);
renderQ();
})();
</script>"""

blocks = re.findall(r"<script\b[^>]*>[\s\S]*?</script>", s)
tgt = [b for b in blocks if "asQueuePanel" in b]
if len(tgt) >= 1:
    for b in tgt: s = s.replace(b, "", 1)
    s = s.replace("</body>", V4JS + "\n</body>", 1)
    print("PASS: old script x%d removed, v4-layout injected" % len(tgt))
    HP.write_text(s, encoding="utf-8")
else:
    print("FAIL: no queue script found - paste F12 Console errors to me")
