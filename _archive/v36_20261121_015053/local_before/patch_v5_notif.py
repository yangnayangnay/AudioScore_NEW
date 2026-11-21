# -*- coding: utf-8 -*-
"""v5-notif: bottom-right toast 3s + beep + settings modal + browser guide."""
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []
R = []

R.append((r"""'<span id="asQLog" style="cursor:pointer;font-size:12px;color:#8ab4e0">\u65e5\u5fd7</span>'+""",
          r"""'<span id="asQLog" style="cursor:pointer;font-size:12px;color:#8ab4e0">\u65e5\u5fd7</span>'+
 '<span id="asQSet" style="cursor:pointer;font-size:12px;color:#9fb0c0">\u2699 \u8bbe\u7f6e</span>'+"""))

R.append((r"""'<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
 '<label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">'+
 '<input type="checkbox" id="asChkItem">\u6bcf\u5b8c\u6210\u4e00\u9996\u7acb\u5373\u5355\u72ec\u4e0b\u8f7d</label>'+
 '<label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">'+
 '<input type="checkbox" id="asChkZip" checked>\u7ed3\u675f\u65f6\u518d\u7ed9 ZIP \u603b\u5305</label>'+
 '<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px">'+
 '\u7f6e\u4fe1\u5ea6\u2265 <input type="number" id="asThresh" min="0.05" max="0.9" '+
 'step="0.05" value="0.3" style="width:56px"></label>'+
 '</div></div>'+""",
          r"""'<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
 '<span style="font-size:11px;opacity:.55">\u63d0\u793a/\u63d0\u793a\u97f3/\u7f6e\u4fe1\u5ea6/\u4e0b\u8f7d\u9009\u9879\u5728 \u2699 \u8bbe\u7f6e\u91cc</span>'+
 '</div></div>'+"""))

R.append((r"""var chkItem=el('asChkItem'),chkZip=el('asChkZip');
chkItem.checked=ls('as_autodl')!=='0';
chkZip.checked=ls('as_zipmode')!=='0';
chkItem.onchange=function(){ls('as_autodl',chkItem.checked?'1':'0');};
chkZip.onchange=function(){ls('as_zipmode',chkZip.checked?'1':'0');};
var thrIn=el('asThresh');
if(thrIn){thrIn.value=ls('as_thresh')||'0.3';
  thrIn.onchange=function(){var v=parseFloat(thrIn.value);
    if(!(v>0))v=0.3;thrIn.value=v;ls('as_thresh',String(v));};}
function getThr(){var v=parseFloat(ls('as_thresh')||'0.3');return v>0?v:0.3;}""",
          r"""var chkItem={get checked(){return ls('as_autodl')!=='0';}};
var chkZip={get checked(){return ls('as_zipmode')!=='0';}};
function getThr(){var v=parseFloat(ls('as_thresh')||'0.3');return v>0?v:0.3;}"""))

R.append((r"""if(j.status==='done'){cur.st='done';cur.dl=DLURL(j);
          var el2=Date.now()-(cur.tStart||Date.now());
          if(el2>1000){var old=parseFloat(ls('as_avgms')||String(el2));
            ls('as_avgms',String(old*0.6+el2*0.4));}
          if(!cur.dl)cur.reason='\u5b8c\u6210\u4f46\u672a\u8bc6\u522b\u4e0b\u8f7d\u5730\u5740';
          renderQ();queueForDownload(cur);advance();return;}""",
          r"""if(j.status==='done'){cur.st='done';cur.dl=DLURL(j);
          var el2=Date.now()-(cur.tStart||Date.now());
          if(el2>1000){var old=parseFloat(ls('as_avgms')||String(el2));
            ls('as_avgms',String(old*0.6+el2*0.4));}
          if(!cur.dl)cur.reason='\u5b8c\u6210\u4f46\u672a\u8bc6\u522b\u4e0b\u8f7d\u5730\u5740';
          notify('\u300c'+(cur.oname||cur.name||'')+'\u300d\u8f6c\u6362\u5b8c\u6210');
          renderQ();queueForDownload(cur);advance();return;}"""))

R.append((r"""if(j.status==='error'){cur.st='err';
          cur.reason='\u670d\u52a1\u5668\u8f6c\u6362\u51fa\u9519\uff0c\u770b\u65e5\u5fd7';
          renderQ();advance();return;}""",
          r"""if(j.status==='error'){cur.st='err';
          cur.reason='\u670d\u52a1\u5668\u8f6c\u6362\u51fa\u9519\uff0c\u770b\u65e5\u5fd7';
          notify('\u300c'+(cur.oname||cur.name||'')+'\u300d\u8f6c\u6362\u5931\u8d25');
          renderQ();advance();return;}"""))

R.append((r"""toast('\u961f\u5217\u5168\u90e8\u5b8c\u6210');finishZip();return;}""",
          r"""notify('\u961f\u5217\u5168\u90e8\u5b8c\u6210');finishZip();return;}"""))

R.append((r"""busy=true;phase='gap';t0=0;archSet([]);tryWake();lockBtn(true);renderQ();},true);""",
          r"""busy=true;phase='gap';t0=0;archSet([]);tryWake();ensureAC();lockBtn(true);renderQ();},true);"""))

for i,(o,n) in enumerate(R,1):
    if o in s:
        s = s.replace(o,n,1); ok.append("R%d: OK" % i)
    elif n in s:
        ok.append("R%d: SKIP (already)" % i)
    else:
        fail.append("R%d: NOT FOUND" % i)

TAIL_OLD = r"""renderQ();
})();
</script>"""
TAIL_NEW = r"""renderQ();
/* ==== notifications + beep + settings modal + browser guide ==== */
var AC=null;
function ensureAC(){try{
  var C=window.AudioContext||window.webkitAudioContext;if(!C)return;
  if(!AC)AC=new C();
  if(AC.state==='suspended')AC.resume();}catch(e){}}
function beep(){try{ensureAC();if(!AC||AC.state!=='running')return;
  var o=AC.createOscillator(),g=AC.createGain();
  o.connect(g);g.connect(AC.destination);
  o.type='sine';o.frequency.setValueAtTime(880,AC.currentTime);
  g.gain.setValueAtTime(0.0001,AC.currentTime);
  g.gain.exponentialRampToValueAtTime(0.25,AC.currentTime+0.02);
  g.gain.exponentialRampToValueAtTime(0.0001,AC.currentTime+0.45);
  o.start();o.stop(AC.currentTime+0.5);}catch(e){}}
function browserGuide(){
  try{var ua=navigator.userAgent;
    if(/edg\//i.test(ua))return 'edge://settings/content/automaticDownloads';
    if(/opera|opr/i.test(ua))return 'opera://settings/content/automaticDownloads';
    if(/brave/i.test(ua))return 'brave://settings/content/automaticDownloads';
    if(/vivaldi/i.test(ua))return 'vivaldi://settings/content/automaticDownloads';
    if(/chrome|crios/i.test(ua))return 'chrome://settings/content/automaticDownloads';
    if(/firefox/i.test(ua))return 'about:preferences (\u5e38\u89c4\u2192\u6587\u4ef6\u4e0e\u5e94\u7528)';
    return '\u6d4f\u89c8\u5668\u8bbe\u7f6e\u2192\u7ad9\u70b9\u6743\u9650\u2192\u81ea\u52a8\u4e0b\u8f7d';}catch(e){
    return '\u6d4f\u89c8\u5668\u8bbe\u7f6e';}}
function notify(msg){
  if(ls('as_notify')==='0')return;
  var w=el('asNotifyWrap');
  if(!w){w=document.createElement('div');w.id='asNotifyWrap';
    w.style.cssText='position:fixed;right:16px;bottom:16px;z-index:10001;'+
    'display:flex;flex-direction:column;gap:8px;align-items:flex-end';
    document.body.appendChild(w);}
  var t=document.createElement('div');
  t.style.cssText='background:#2a3140;color:#e6ecf2;padding:10px 14px;'+
  'border-radius:6px;border:1px solid #4a5464;'+
  'box-shadow:0 4px 12px rgba(0,0,0,.4);font-size:13px;max-width:280px;'+
  'opacity:0;transition:opacity .25s';
  t.textContent=msg;w.appendChild(t);
  setTimeout(function(){t.style.opacity='1';},10);
  setTimeout(function(){t.style.opacity='0';
    setTimeout(function(){t.remove();},300);},3000);
  if(ls('as_sound')!=='0')beep();
  try{if(ls('as_sysnotify')==='1'&&window.Notification&&
      Notification.permission==='granted'){
    var nn=new Notification('AudioScore',{body:msg});
    setTimeout(function(){try{nn.close();}catch(e){}},3000);}}catch(e){}}
var modal=document.createElement('div');modal.id='asModal';
modal.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);'+
 'z-index:10002;align-items:center;justify-content:center';
modal.innerHTML='<div style="background:#1a1f28;color:#e6ecf2;border-radius:10px;'+
 'padding:16px 20px;min-width:300px;max-width:400px;'+
 'box-shadow:0 8px 24px rgba(0,0,0,.5)">'+
 '<div style="font-weight:600;margin-bottom:12px">\u2699 \u901a\u7528\u8bbe\u7f6e</div>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;'+
 'font-size:13px;cursor:pointer"><input type="checkbox" id="asChkNotify">'+
 '\u6bcf\u9996\u5b8c\u6210/\u5931\u8d25\u65f6\u53f3\u4e0b\u89d2\u5f39\u7a97\u63d0\u793a</label>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;'+
 'font-size:13px;cursor:pointer"><input type="checkbox" id="asChkSound">'+
 '\u63d0\u793a\u97f3 <span id="asPreview" style="cursor:pointer;color:#8ab4e0;'+
 'text-decoration:underline">\u8bd5\u542c</span></label>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;'+
 'font-size:13px;cursor:pointer"><input type="checkbox" id="asChkSys">'+
 '\u540c\u65f6\u53d1\u7cfb\u7edf\u901a\u77e5 <span id="asPermHint" '+
 'style="font-size:11px;opacity:.6"></span></label>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;'+
 'font-size:13px;cursor:pointer"><input type="checkbox" id="asChkItem2">'+
 '\u6bcf\u5b8c\u6210\u4e00\u9996\u7acb\u5373\u5355\u72ec\u4e0b\u8f7d</label>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;'+
 'font-size:13px;cursor:pointer"><input type="checkbox" id="asChkZip2">'+
 '\u7ed3\u675f\u65f6\u518d\u7ed9 ZIP \u603b\u5305</label>'+
 '<label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;'+
 'font-size:13px;flex-wrap:wrap">\u4e50\u5668\u7f6e\u4fe1\u5ea6\u2265 '+
 '<input type="number" id="asThresh2" min="0.05" max="0.9" step="0.05" '+
 'value="0.3" style="width:56px">'+
 '<span style="font-size:11px;opacity:.6">\u8d85\u8fc7\u5219\u53c2\u4e0e pp4/pp5 \u81ea\u52a8\u5224\u65ad</span></label>'+
 '<div style="background:#10141a;border:1px solid #2a3140;border-radius:6px;'+
 'padding:8px 10px;margin-bottom:12px;font-size:11px;color:#9fb0c0;line-height:1.6">'+
 '<b>\u81ea\u52a8\u4e0b\u8f7d\u4e0d\u88ab\u62e6\u622a\u7684\u8bbe\u7f6e\u8def\u5f84:</b><br>'+
 '<span id="asGuidePath"></span><br>'+
 '\u628a\u4e0a\u9762\u8def\u5f84\u7c98\u5230\u5730\u5740\u680f\u2192\u628a http://localhost:8000 \u52a0\u5165\u201c\u5141\u8bb8\u201d\u5217\u8868</div>'+
 '<div style="display:flex;justify-content:flex-end">'+
 '<button id="asModalClose" style="cursor:pointer;padding:4px 14px">\u5173\u95ed</button></div>'+
 '</div>';
document.body.appendChild(modal);
modal.addEventListener('click',function(e){
  if(e.target===modal)modal.style.display='none';});
el('asModalClose').onclick=function(){modal.style.display='none';};
el('asQSet').onclick=function(){modal.style.display='flex';};
var chkN=el('asChkNotify'),chkS=el('asChkSound'),chkSys=el('asChkSys'),
    chkI2=el('asChkItem2'),chkZ2=el('asChkZip2'),thr2=el('asThresh2');
function syncModal(){
  chkN.checked=ls('as_notify')!=='0';
  chkS.checked=ls('as_sound')!=='0';
  chkSys.checked=ls('as_sysnotify')==='1';
  chkI2.checked=ls('as_autodl')!=='0';
  chkZ2.checked=ls('as_zipmode')!=='0';
  thr2.value=ls('as_thresh')||'0.3';
  var h=el('asPermHint');
  try{h.textContent=(!window.Notification)?'(\u4e0d\u652f\u6301)':
    (Notification.permission==='granted'?'\u5df2\u6388\u6743':
     Notification.permission==='denied'?'\u5df2\u62d2\u7edd':'\u672a\u7533\u8bf7');}
  catch(e){h.textContent='';}
  el('asGuidePath').textContent=browserGuide();}
chkN.onchange=function(){ls('as_notify',chkN.checked?'1':'0');};
chkS.onchange=function(){ls('as_sound',chkS.checked?'1':'0');};
chkSys.onchange=function(){ls('as_sysnotify',chkSys.checked?'1':'0');
  if(chkSys.checked){ensureAC();
    try{if(window.Notification&&Notification.permission!=='granted'
      &&Notification.permission!=='denied')
      Notification.requestPermission().then(syncModal);}catch(e){}}};
chkI2.onchange=function(){ls('as_autodl',chkI2.checked?'1':'0');};
chkZ2.onchange=function(){ls('as_zipmode',chkZ2.checked?'1':'0');};
thr2.onchange=function(){var v=parseFloat(thr2.value);
  if(!(v>0))v=0.3;thr2.value=v;ls('as_thresh',String(v));};
el('asPreview').onclick=function(ev){ev.stopPropagation();ensureAC();beep();};
el('asQSet').addEventListener('click',syncModal);
syncModal();
})();
</script>"""
if TAIL_OLD in s:
    s = s.replace(TAIL_OLD, TAIL_NEW, 1); ok.append("TAIL: modal/notify injected")
elif TAIL_NEW in s:
    ok.append("TAIL: SKIP (already)")
else:
    fail.append("TAIL: not found")

HP.write_text(s, encoding="utf-8")
print()
print("==== V5 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
