# -*- coding: utf-8 -*-
"""v10-dlfix: capture MIDI bytes at job-completion instant (BLOBS cache);
downloads & ZIP use cache instead of re-fetching (possibly overwritten) URL;
unique names for same-name files; jid collision detect; URL collision warn."""
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []

R = []

# R1: capture blob at completion instant
R.append((r"""notify('\u300c'+(cur.oname||cur.name||'')+'\u300d\u8f6c\u6362\u5b8c\u6210');
          renderQ();queueForDownload(cur);advance();return;}""",
r"""notify('\u300c'+(cur.oname||cur.name||'')+'\u300d\u8f6c\u6362\u5b8c\u6210');
          captureBlob(cur);renderQ();queueForDownload(cur);advance();return;}"""))

# R2: queueForDownload -> uniqName + URL-collision warn
R.append((r"""  var rec={jid:jid,url:it.dl||'',name:outName(it.oname||it.name||'')};""",
r"""  var rec={jid:jid,url:it.dl||'',name:uniqName(outName(it.oname||it.name||''))};
  try{var same=Q.filter(function(x){return x!==it&&x.jid&&x.jid!==jid&&
    x.dl&&x.dl===it.dl;});
    if(same.length)console.warn('[AudioScore] URL collision:',jid,it.dl);}catch(e){}"""))

# R3: drainPending -> BLOBS first, URL fallback second
R.append((r"""  draining=true;
  var e=a[0];
  if(e.url){saveBlob(e.url,e.name,function(good){""",
r"""  draining=true;
  var e=a[0];
  if(BLOBS[e.jid]){saveData(BLOBS[e.jid],e.name,function(good){
    draining=false;
    if(good){dlMark(e.jid);
      pendSet(pend().filter(function(x){return x.jid!==e.jid;}));
      toast('\u5df2\u4e0b\u8f7d '+e.name);}
    else{lastFail=Date.now();}});}
  else if(e.url){saveBlob(e.url,e.name,function(good){"""))

# R4: finishZip -> BLOBS first
R.append((r"""  Promise.all(g.map(function(e){
    var got=(e.url)?Promise.resolve(e.url):""",
r"""  Promise.all(g.map(function(e){
    if(BLOBS[e.jid])return Promise.resolve({name:e.name,blob:BLOBS[e.jid]});
    var got=(e.url)?Promise.resolve(e.url):"""))

# R5: manual dl click -> BLOBS first
R.append((r"""  var row=a.closest('.asQItem');
  saveBlob(a.getAttribute('href'),outName(row?row.dataset.oname:''),function(){});});""",
r"""  var row=a.closest('.asQItem');
  var jid2=row?row.dataset.jid:'';
  var fn2=outName(row?row.dataset.oname:'');
  if(jid2&&BLOBS[jid2]){saveData(BLOBS[jid2],fn2,function(){});return;}
  saveBlob(a.getAttribute('href'),fn2,function(){});});"""))

# R6: saveBlob interior -> smartFragOn gate (consistency)
R.append((r"""    if(precMode()==='acc'){postprocBlob(bl,function(p){res(p);});}
    else res(bl);});})""",
r"""    if(smartFragOn()){postprocBlob(bl,function(p){res(p);});}
    else res(bl);});})"""))

# R7: helpers (BLOBS/uniqName/saveData/captureBlob) before queueForDownload
R.append((r"""function queueForDownload(it){""",
r"""var BLOBS={},USED={};
function uniqName(n){
  if(!USED[n]){USED[n]=1;return n;}
  var i=2,b=n.replace(/\.mid$/i,'');
  while(USED[b+' ('+i+').mid'])i++;
  USED[b+' ('+i+').mid']=1;return b+' ('+i+').mid';}
function saveData(bl,fn,cb){
  try{var u=URL.createObjectURL(bl);var t=document.createElement('a');
  t.href=u;t.download=fn;document.body.appendChild(t);t.click();t.remove();
  setTimeout(function(){URL.revokeObjectURL(u);},4000);if(cb)cb(true);}
  catch(e){if(cb)cb(false);}}
function captureBlob(it){
  try{
    if(!it||!it.dl||!it.jid)return;
    if(BLOBS[it.jid])return;
    fetch(it.dl,{cache:'no-store'}).then(function(r){
      return r.ok?r.blob():null;})
    .then(function(bl){
      if(!bl)return;
      if(smartFragOn()){postprocBlob(bl,function(p){BLOBS[it.jid]=p;});}
      else BLOBS[it.jid]=bl;
      var ks=Object.keys(BLOBS);if(ks.length>40)delete BLOBS[ks[0]];})
    .catch(function(){});}catch(e){}}
function queueForDownload(it){"""))

# R8: jid collision detect at submit phase
R.append((r"""    if(id&&id!==prevId&&cur){cur.jid=id;cur.subphase='run';
      cur.tStart=Date.now();phase='run';t0=Date.now();renderQ();return;}""",
r"""    if(id&&id!==prevId&&cur){
      var dup=Q.some(function(x){return x!==cur&&x.jid===id;});
      if(dup){cur.st='err';
        cur.reason='\u4efb\u52a1\u53f7\u51b2\u7a81\uff08\u670d\u52a1\u5668\u8fd4\u56de\u91cd\u590d ID\uff09';
        renderQ();advance();return;}
      cur.jid=id;cur.subphase='run';
      cur.tStart=Date.now();phase='run';t0=Date.now();renderQ();return;}"""))

for i,(o,n) in enumerate(R,1):
    if o in s:
        s = s.replace(o,n,1); ok.append("R%d: OK" % i)
    elif n in s:
        ok.append("R%d: SKIP (already)" % i)
    else:
        fail.append("R%d: NOT FOUND" % i)

HP.write_text(s, encoding="utf-8")
print()
print("==== V10 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
