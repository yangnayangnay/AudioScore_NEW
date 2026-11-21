# ==AS_LIVE_TEE== auto v1
try:
    import as_live as _as_live
    _as_live.install_tee()
except Exception as _ase:
    print("[as_live] tee failed:", _ase)
﻿# -*- coding: utf-8 -*-
"""v7: per-item download on each completion AND zip at end (both, not either/or)
+ start.bat uses system default browser."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []
FULL_PPS = ",".join("'pp%d'" % k for k in range(1, 17))

def splice(text, marker, new_block):
    i = text.find(marker)
    if i < 0:
        return text, False
    start = text.rfind("<script>", 0, i)
    end = text.find("</script>", i)
    if start < 0 or end < 0:
        return text, False
    return text[:start] + new_block + text[end + 9:], True

HELPERS = r"""
  function DLURL(j){if(!j)return '';var c=[j.download_url,j.download,j.file_url,
    j.file,j.url,j.midi,j.midi_url,j.result_url,j.result];
    for(var i=0;i<c.length;i++)if(typeof c[i]==='string'&&c[i])return c[i];return '';}
  function outName(on){var b=(on||'').replace(/\.[^.]+$/,'');if(!b)b='output';
    if(/audioscore$/i.test(b))return b+'.mid';return b+'AudioScore.mid';}
  function saveBlob(url,fn,cb){fetch(url).then(function(r){return r.blob();})
    .then(function(bl){var u=URL.createObjectURL(bl);var t=document.createElement('a');
    t.href=u;t.download=fn;document.body.appendChild(t);t.click();t.remove();
    setTimeout(function(){URL.revokeObjectURL(u);},4000);if(cb)cb(true);})
    .catch(function(){if(cb)cb(false);});}
  function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);
    if(v===null){localStorage.removeItem(k);return null;}
    localStorage.setItem(k,v);}catch(e){return null;}}
  function jsGet(k,d){try{var v=JSON.parse(localStorage.getItem(k)||'null');
    return v==null?d:v;}catch(e){return d;}}
  function jsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
  function buildZip(items){
    var CT=(function(){var t=[],c,n,k;for(n=0;n<256;n++){c=n;
      for(k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);t[n]=c>>>0;}return t;})();
    function crc32(u8){var c=0xFFFFFFFF,i;
      for(i=0;i<u8.length;i++)c=CT[(c^u8[i])&0xFF]^(c>>>8);
      return (c^0xFFFFFFFF)>>>0;}
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
      var cdSize=central.reduce(function(acc,x){return acc+x.length;},0);
      var eo=new Uint8Array([].concat(w32(0x06054b50),w16(0),w16(0),
        w16(files.length),w16(files.length),w32(cdSize),w32(off),w16(0)));
      return new Blob(parts.concat(central,[eo]),{type:'application/zip'});});
  }
"""

QUEUE = r"""<script>
(function(){
  var QKEY='as_queue_state',PENDKEY='as_pending_dl',DLSET='as_dl_done',
      ARCHKEY='as_run_archive';
  var PPS=[__PPS__];
  function el(id){return document.getElementById(id);}
  function toast(msg){var t=el('asToast');
    if(!t){t=document.createElement('div');t.id='asToast';
      t.style.cssText='position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'+
      'background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;z-index:10000';
      document.body.appendChild(t);}
    t.textContent=msg;t.style.opacity='1';
    clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},3200);}
  __HELPERS__
  function saveOpts(){var o={};PPS.forEach(function(id){var e=el(id);if(e)o[id]=!!e.checked;});
    var be=el('backend');if(be)o.backend=be.value;jsSet('as_opts',o);}
  (function(){var o=jsGet('as_opts',{});
    PPS.forEach(function(id){var e=el(id);if(e&&(id in o))e.checked=!!o[id];});
    var be=el('backend');if(be&&o.backend)be.value=o.backend;})();
  PPS.forEach(function(id){var e=el(id);if(e)e.addEventListener('change',saveOpts);});
  var be=el('backend');if(be)be.addEventListener('change',saveOpts);
  var input=document.querySelector('input[type="file"]');
  if(input)try{input.multiple=true;}catch(e){}
  var btn=null,autoPass=false;
  var cands=document.querySelectorAll('button,input[type="button"],input[type="submit"]');
  for(var i=0;i<cands.length;i++){var t=((cands[i].textContent||'')+(cands[i].value||'')).trim();
    if(/\u5f00\u59cb|\u8f6c\u6362|\u8f6c\u5199/.test(t)){btn=cands[i];break;}}
  var panel=document.createElement('div');panel.id='asQueue';
  panel.style.cssText='border:1px solid #3a3f4a;border-radius:8px;padding:8px 12px;'+
    'margin:10px 0;position:sticky;top:0;z-index:500;background:rgba(16,18,24,.97);'+
    'box-shadow:0 2px 10px rgba(0,0,0,.35)';
  panel.innerHTML='<div style="display:flex;align-items:center;gap:8px">'+
    '<span style="font-weight:600">\u8f6c\u6362\u961f\u5217</span>'+
    '<span id="asQCount" style="opacity:.6;font-size:12px"></span>'+
    '<span id="asQFold" style="cursor:pointer;opacity:.7;padding:0 4px">\u25be</span>'+
    '<span id="asQRetry" style="cursor:pointer;font-size:12px;color:#e0c98a">'+
    '\u21bb\u91cd\u8bd5\u5931\u8d25</span>'+
    '<span id="asQClear" style="cursor:pointer;font-size:12px;color:#e08a8a;margin-left:auto">'+
    '\u6e05\u7a7a</span></div>'+
    '<div id="asQBody"><div id="asQList" style="display:flex;flex-direction:column;'+
    'gap:6px;min-height:28px;margin-top:8px"></div>'+
    '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">'+
    '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
    '<span style="font-size:12px;opacity:.6">\u6bcf\u5b8c\u6210\u4e00\u9996\u7acb\u5373\u5355\u72ec\u4e0b\u8f7d'+
    '\uff1b\u7ed3\u675f\u65f6\u518d\u81ea\u52a8\u7ed9 ZIP \u603b\u5305\u5151\u5e95</span></div></div>';
  if(input&&input.parentNode&&input.nextSibling)
    input.parentNode.insertBefore(panel,input.nextSibling);
  else document.body.appendChild(panel);
  var list=el('asQList'),body=el('asQBody'),fold=el('asQFold');
  try{if(ls('as_qfold')==='1'){body.style.display='none';fold.textContent='\u25b8';}}catch(e){}
  fold.onclick=function(){var open=body.style.display!=='none';
    body.style.display=open?'none':'';fold.textContent=open?'\u25b8':'\u25be';
    ls('as_qfold',open?'1':'0');};
  function esc(x){return String(x).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  var Q=[];
  (function(){var sv=jsGet(QKEY,null);if(!sv)return;
    sv.forEach(function(x){x.file=null;
      if(x.st==='queued'||x.st==='run'){x.st='err';
        x.reason='\u9875\u9762\u5237\u65b0\u5bfc\u81f4\u6587\u4ef6\u4e22\u5931\uff0c\u8bf7\u91cd\u65b0\u6dfb\u52a0';x.lost=true;}
      Q.push(x);});})();
  function persist(){jsSet(QKEY,Q.map(function(x){return{name:x.name,oname:x.oname,
    size:x.size,st:x.st,dl:x.dl,jid:x.jid,reason:x.reason,lost:!!x.lost};}));}
  function renderQ(){
    list.innerHTML='';
    var qc=0;
    Q.forEach(function(it,ix){
      if(it.st==='queued'&&it.file)qc++;
      var row=document.createElement('div');
      row.className='asQItem';row.draggable=true;row.dataset.i=ix;
      row.dataset.oname=it.oname||it.name||'';row.dataset.jid=it.jid||'';
      row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 8px;'+
        'border:1px solid #3a3f4a;border-radius:6px;cursor:grab';
      var stt={queued:'\u5f85\u8f6c\u6362',run:'\u8f6c\u6362\u4e2d\u2026',
               done:'\u5b8c\u6210',err:'\u5931\u8d25'}[it.st]||'';
      var stc={queued:'#8ab4e0',run:'#e0c98a',done:'#8ad0a0',err:'#e08a8a'}[it.st]||'#999';
      var rt=(it.reason||'');
      var retry=(it.st==='err'&&!it.lost)?
        '<span class="asQR" data-x="'+ix+'" style="cursor:pointer;color:#e0c98a" '+
        'title="'+esc(rt)+'">\u21bb</span>':'';
      row.innerHTML='<span style="opacity:.5">\u2195</span>'+
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '+
        'title="'+esc(rt||it.oname||it.name)+'">'+esc(it.oname||it.name||'')+'</span>'+
        (it.dl?'<a href="'+it.dl+'" class="asQDl" style="font-size:12px;color:#8ad0a0">'+
         esc(outName(it.oname||it.name||''))+'</a>':'')+
        '<span style="font-size:12px;color:'+stc+'" title="'+esc(rt)+'">'+stt+'</span>'+
        retry+'<span class="asQX" data-x="'+ix+'" style="cursor:pointer;color:#e08a8a;'+
        'font-weight:700">\u00d7</span>';
      list.appendChild(row);});
    el('asQCount').textContent=Q.length?('('+Q.length+')'):'';
    if(btn)btn.disabled=(!busy&&qc===0);
    persist();}
  el('asQAdd').onclick=function(){
    if(!input||!input.files||!input.files.length){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6');return;}
    for(var k=0;k<input.files.length;k++)
      Q.push({file:input.files[k],name:input.files[k].name,oname:input.files[k].name,
              size:input.files[k].size,st:'queued',dl:'',jid:'',reason:''});
    try{input.value='';}catch(e){}
    renderQ();};
  var busy=false,cur=null,phase='idle',t0=0,prevId='',dragIdx=-1;
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
  function setFiles(f){try{var dt=new DataTransfer();dt.items.add(f);
    input.files=dt.files;return true;}catch(e){return false;}}
  function recordId(id){if(id)ls('as_last_job',id);}
  try{var _f=window.fetch;
    window.fetch=function(u,o){return _f.apply(this,arguments).then(function(r){
      try{var s2=(typeof u==='string')?u:(u&&u.url)||'';
        if(s2.indexOf('/api/jobs')>=0&&o&&(o.method||'GET').toUpperCase()==='POST'){
          r.clone().json().then(function(j){recordId(j&&(j.id||j.job_id));}).catch(function(){});
          try{var fi=document.querySelector('input[type="file"]');
            if(fi&&fi.files&&fi.files[0])ls('as_last_name',fi.files[0].name);}catch(e){}}}
      catch(e){}return r;});};}catch(e){}
  try{var _o=XMLHttpRequest.prototype.open,_s2=XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;
      return _o.apply(this,arguments);};
    XMLHttpRequest.prototype.send=function(){var x=this;
      try{if(x.__m&&String(x.__m).toUpperCase()==='POST'&&
          String(x.__u).indexOf('/api/jobs')>=0){
        try{var fi=document.querySelector('input[type="file"]');
          if(fi&&fi.files&&fi.files[0])ls('as_last_name',fi.files[0].name);}catch(e){}
        x.addEventListener('load',function(){
          try{var j=JSON.parse(x.responseText);recordId(j&&(j.id||j.job_id));}
          catch(e){ls('as_post_status',String(x.status||'ERR'));}});}}
      catch(e){}
      return _s2.apply(this,arguments);};}catch(e){}
  function submitNext(){
    var nxt=null;Q.forEach(function(x){if(!nxt&&x.st==='queued'&&x.file)nxt=x;});
    if(!nxt){busy=false;phase='idle';releaseWake();renderQ();
      toast('\u961f\u5217\u5168\u90e8\u5b8c\u6210');drainPending();finishZip();return;}
    cur=nxt;cur.st='run';cur.reason='';cur.dl='';cur.jid='';renderQ();
    prevId=ls('as_last_job')||'';
    if(!input||!setFiles(cur.file)){cur.st='err';
      cur.reason='\u65e0\u6cd5\u5199\u5165\u6587\u4ef6\u8f93\u5165\u6846';
      renderQ();cur=null;phase='gap';t0=Date.now();return;}
    ls('as_last_name',cur.oname||cur.name||'');
    autoPass=true;btn.click();setTimeout(function(){autoPass=false;},0);
    phase='submit';t0=Date.now();}
  function advance(){cur=null;phase='gap';t0=Date.now();}
  function tick(){
    if(!busy){drainPending();finishZip();return;}
    if(phase==='gap'){if(Date.now()-t0>600)submitNext();return;}
    if(phase==='submit'){
      var id=ls('as_last_job')||'';
      if(id&&id!==prevId&&cur){cur.jid=id;phase='run';t0=Date.now();return;}
      if(Date.now()-t0>20000&&cur){
        var ps=ls('as_post_status')||'?';
        cur.st='err';cur.reason='20\u79d2\u672a\u6355\u83b7\u4efb\u52a1\u53f7(HTTP '+
          ps+')\uff0c\u770b\u670d\u52a1\u5668\u65e5\u5fd7';
        renderQ();advance();return;}
      return;}
    if(phase==='run'&&cur&&cur.jid){
      fetch('/api/jobs/'+cur.jid,{cache:'no-store'}).then(function(r){
        return r.ok?r.json():null;}).then(function(j){
        if(!j||!busy||phase!=='run'||!cur)return;
        console.log('AS queue job:',cur.jid,j);
        if(j.status==='done'){cur.st='done';cur.dl=DLURL(j);
          if(!cur.dl)cur.reason='\u5b8c\u6210\u4f46\u672a\u8bc6\u522b\u4e0b\u8f7d\u5730\u5740';
          renderQ();queueForDownload(cur);advance();return;}
        if(j.status==='error'){cur.st='err';
          cur.reason='\u670d\u52a1\u5668\u8f6c\u6362\u51fa\u9519\uff0c\u770b\u670d\u52a1\u9ed1\u7a97\u53e3\u65e5\u5fd7';
          renderQ();advance();return;}}).catch(function(){});}
  }
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
  /* ---- downloads: per-item immediately + zip of whole run at end ---- */
  function dlHas(jid){return jid&&jsGet(DLSET,[]).indexOf(jid)>=0;}
  function dlMark(jid){if(!jid)return;var a=jsGet(DLSET,[]);
    if(a.indexOf(jid)<0){a.push(jid);jsSet(DLSET,a);}}
  function pend(){return jsGet(PENDKEY,[]);}
  function pendSet(a){jsSet(PENDKEY,a);}
  function arch(){return jsGet(ARCHKEY,[]);}
  function archSet(a){jsSet(ARCHKEY,a);}
  function queueForDownload(it){
    if(ls('as_autodl')==='0')return;
    var jid=it.jid||'';
    if(dlHas(jid))return;
    var rec={jid:jid,url:it.dl||'',name:outName(it.oname||it.name||'')};
    var a=pend();a.push(rec);pendSet(a);
    var g=arch();g.push(rec);archSet(g);
    if(document.hidden)toast('\u5b8c\u6210\uff0c\u56de\u5230\u9875\u9762\u540e\u8865\u4e0b\u8f7d');}
  var draining=false,lastFail=0;
  function drainPending(){
    if(document.hidden||ls('as_autodl')==='0')return;
    if(draining)return;
    if(Date.now()-lastFail<8000)return;
    var a=pend();if(!a.length)return;
    a=a.filter(function(e){return !dlHas(e.jid);});
    if(!a.length){pendSet([]);return;}
    draining=true;
    var e=a[0];
    if(e.url){saveBlob(e.url,e.name,function(good){
      draining=false;
      if(good){dlMark(e.jid);
        pendSet(pend().filter(function(x){return x.jid!==e.jid;}));
        toast('\u5df2\u4e0b\u8f7d '+e.name);}
      else{lastFail=Date.now();toast('\u5355\u72ec\u4e0b\u8f7d\u5931\u8d25\uff0c'+
        '\u7ed3\u675f\u65f6\u7684 ZIP \u603b\u5305\u4f1a\u5151\u5e95');}});}
    else{fetch('/api/jobs/'+e.jid,{cache:'no-store'}).then(function(r){
      return r.json();}).then(function(j){var u=DLURL(j);
      if(u){e.url=u;var b3=pend();b3[0]=e;pendSet(b3);}
      draining=false;}).catch(function(){draining=false;});}}
  function finishZip(){
    if(document.hidden||ls('as_autodl')==='0')return;
    if(ls('as_zipmode')==='0')return;
    if(draining)return;
    var g=arch();if(!g.length)return;
    draining=true;
    var stamp=new Date();
    function p2(x){return (x<10?'0':'')+x;}
    var zname='AudioScore_'+stamp.getFullYear()+p2(stamp.getMonth()+1)+
      p2(stamp.getDate())+'_'+p2(stamp.getHours())+p2(stamp.getMinutes())+
      '_'+g.length+'\u9996.zip';
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
      items=items.filter(Boolean);
      draining=false;
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
    busy=true;phase='gap';t0=0;archSet([]);tryWake();renderQ();},true);
  renderQ();
})();
</script>"""
QUEUE = QUEUE.replace("__PPS__", FULL_PPS).replace("__HELPERS__", HELPERS)
s2, did = splice(s, "asQAdd", QUEUE)
if did: s = s2; ok.append("queue v7: per-item on completion + zip of whole run at end")
else: fail.append("queue splice failed")

AUTO = r"""<script>
(function(){
  function on(k,d){var v=null;try{v=localStorage.getItem(k);}catch(e){}
    return v==null?d:v;}
  function mk(key,dflt,txt){
    var lab=document.createElement('label');
    lab.style.cssText='display:inline-flex;align-items:center;gap:6px;font-size:12px;'+
      'cursor:pointer;margin-right:14px';
    var cb=document.createElement('input');cb.type='checkbox';
    cb.checked=on(key,dflt)==='1';
    cb.onchange=function(){try{localStorage.setItem(key,cb.checked?'1':'0');}catch(e){}};
    lab.appendChild(cb);lab.appendChild(document.createTextNode(txt));
    return lab;}
  var panel=document.getElementById('asQueue');
  var box=document.createElement('div');
  box.style.cssText='margin-top:8px';
  box.appendChild(mk('as_autodl','1','\u6bcf\u5b8c\u6210\u4e00\u9996\u7acb\u5373\u5355\u72ec\u4e0b\u8f7d'));
  box.appendChild(mk('as_zipmode','1',
    '\u7ed3\u675f\u65f6\u518d\u6253\u5305 ZIP \u603b\u5305\uff08\u5151\u5e95\uff0c\u63a8\u8350\uff09'));
  if(panel)panel.appendChild(box);else document.body.appendChild(box);
})();
</script>"""
s2, did = splice(s, "as_autodl", AUTO)
if did: s = s2; ok.append("autodl v6: two independent checkboxes")
else: fail.append("autodl splice failed")

HP.write_text(s, encoding="utf-8")

# ---- start.bat: use system default browser (remove hardcoded chrome/msedge) ----
BROWSERS = re.compile(r"(chrome|msedge|firefox|iexplore)\.exe", re.I)
OPENER = 'start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"\r\n'
for sbname in ("start.bat", "run.bat", "启动.bat"):
    SB = ROOT / sbname
    if not SB.exists():
        continue
    tb = SB.read_text(encoding="utf-8", errors="ignore")
    lines = [l for l in tb.splitlines() if not BROWSERS.search(l)]
    pyidx = -1
    for i, l in enumerate(lines):
        if re.search(r"python|uvicorn|\.py", l, re.I):
            pyidx = i
            break
    at = pyidx if pyidx >= 0 else 0
    lines.insert(at, OPENER.rstrip("\r\n"))
    new = "\r\n".join(lines) + "\r\n"
    bak = Path(str(SB) + ".bak")
    if not bak.exists():
        bak.write_text(tb, encoding="utf-8", errors="ignore")
    SB.write_text(new, encoding="utf-8")
    ok.append("%s: hardcoded browser removed -> system default browser" % sbname)
    break

print()
print("==== V7 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
print("  markers: finishZip=%s ARCHKEY=%s" % (
    "function finishZip" in s, "as_run_archive" in s))
