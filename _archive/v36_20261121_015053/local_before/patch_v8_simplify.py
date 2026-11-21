# -*- coding: utf-8 -*-
"""v8-simplify: 16 pp toggles -> 7 core + 6 advanced collapsed;
postprocBlob key off smart-frag; preset dropdown keeps working."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []

# ---------- 1. postprocBlob switch from precMode to smartFrag ----------
C_OLD = r"""function precMode(){return ls('as_prec')||'std';}
function postprocBlob(blob,cb){
  if(precMode()!=='acc'){cb(blob);return;}"""
C_NEW = r"""function precMode(){return ls('as_prec')||'std';}
function smartFragOn(){return ls('as_g_smartfrag')!=='0';}
function postprocBlob(blob,cb){
  if(!smartFragOn()){cb(blob);return;}"""
if C_OLD in s: s = s.replace(C_OLD, C_NEW, 1); ok.append("C: postprocBlob -> smartFragOn")
elif "smartFragOn" in s: ok.append("C: SKIP")
else: fail.append("C: NOT FOUND")

D_OLD = r"""        .then(function(bl){return new Promise(function(res){
          if(precMode()==='acc'){postprocBlob(bl,function(p){res({name:e.name,blob:p});});}
          else res({name:e.name,blob:bl});});})"""
D_NEW = r"""        .then(function(bl){return new Promise(function(res){
          if(smartFragOn()){postprocBlob(bl,function(p){res({name:e.name,blob:p});});}
          else res({name:e.name,blob:bl});});})"""
if D_OLD in s: s = s.replace(D_OLD, D_NEW, 1); ok.append("D: ZIP postproc -> smartFragOn")
elif "smartFragOn()){postprocBlob" in s: ok.append("D: SKIP")
else: fail.append("D: NOT FOUND")

# ---------- 2. simplify UI ----------
MARK = "/* ==AS_SIMPLIFY== */"
if MARK in s:
    ok.append("UI: SKIP (already simplified)")
else:
    JS = r"""<script>
/* ==AS_SIMPLIFY== v1: 16 pp toggles -> 7 core + 6 advanced collapsed */
(function(){
'use strict';
var PPS=['pp1','pp2','pp3','pp4','pp5','pp6','pp7','pp8','pp9','pp10',
         'pp11','pp12','pp13','pp14','pp15','pp16'];
function el(id){return document.getElementById(id);}
function ls(k,v){try{
  if(v===undefined)return localStorage.getItem(k);
  if(v===null){localStorage.removeItem(k);return null;}
  localStorage.setItem(k,v);}catch(e){return null;}}

var GROUPS=[
 {key:'smartfrag',label:'\u667a\u80fd\u53bb\u788e\uff08\u8fc7\u6ee4\u788e\u97f3\u7b26 + \u5408\u5e76\u8de8\u7247\u4f2a\u5f71\uff0c\u5fc5\u5f00\uff09',ids:['pp1','pp2'],def:true},
 {key:'separate',label:'\u97f3\u8272\u9884\u5206\u79bb\uff08Demucs\uff0c\u591a\u4e50\u5668\u5f3a\u63a8\uff0c\u72ec\u594f\u5efa\u8bae\u5173\uff09',ids:['pp4'],def:true},
 {key:'instr',label:'\u667a\u80fd\u4e50\u5668\u8bc6\u522b\uff08\u8054\u52a8\u5206\u79bb\u4e0eguided\uff09',ids:['pp5'],def:false},
 {key:'vel',label:'\u529b\u5ea6\u91cd\u5efa\uff08\u80fd\u91cf\u5305\u7edc\uff0c\u4f4e\u98ce\u9669\u9ad8\u6536\u76ca\uff09',ids:['pp3'],def:true},
 {key:'silent',label:'\u9759\u97f3\u7559\u767d\uff08\u957f\u95f4\u9699\u8865\u4f11\u6b62\uff0c\u53ef\u8bfb\u6027\uff09',ids:['pp11'],def:true},
 {key:'meter',label:'\u62cd\u53f7\u5199\u5165\uff084/4 3/4 6/8\uff0c\u96f6\u98ce\u9669\uff09',ids:['pp10'],def:true},
 {key:'quant',label:'\u8282\u62cd\u91cf\u5316\uff08\u542b\u4e92\u89e3/\u65f6\u503c\uff0c\u89c4\u6574\u66f2\u98ce\u624d\u5f00\uff09',ids:['pp7','pp9','pp15'],def:false}
];
var ADV=[
 {key:'harm',label:'\u8c10\u6ce2\u91cd\u5206\u914d\uff08\u8bef\u5224\u7387\u9ad8\uff0c\u4e0d\u5efa\u8bae\u5f00\uff09',ids:['pp6'],def:false},
 {key:'voice',label:'\u58f0\u90e8\u5206\u79bb\uff08\u4e0d\u63d0\u5347\u7cbe\u5ea6\uff0cDAW\u53ef\u505a\uff09',ids:['pp8'],def:false},
 {key:'onset',label:'\u8d77\u97f3\u7cbe\u5316\uff08librosa \u5f31\u4e8e\u6a21\u578b\uff0c\u4e0d\u5efa\u8bae\u5f00\uff09',ids:['pp12'],def:false},
 {key:'decay',label:'\u8870\u51cf\u65f6\u503c\uff08\u53ea\u5f71\u54cd\u5c3e\u97f3\uff09',ids:['pp13'],def:false},
 {key:'dyn',label:'\u52a8\u6001\u9608\u503c\uff08\u6a21\u578b\u5185\u90e8\u5df2\u8fc7\u6ee4\uff0c\u53cc\u91cd\u52b3\u52a8\uff09',ids:['pp14'],def:false},
 {key:'dtw',label:'DTW\u5bf9\u9f50\u8bca\u65ad\uff08\u7eaf\u6392\u9519\u7528\uff09',ids:['pp16'],def:false}
];

// 1. hide original pp checkboxes (find wrapping label)
PPS.forEach(function(id){
  var e=el(id);if(!e)return;
  var p=e.parentElement;
  if(p&&p.tagName==='LABEL')p.style.display='none';
  else if(p){var gp=p.parentElement;
    if(gp&&gp.tagName==='LABEL')gp.style.display='none';
    else e.style.display='none';}});

function waitFor(fn,cb){
  var t=setInterval(function(){var r=fn();if(r){clearInterval(t);cb(r);}},100);
  setTimeout(function(){clearInterval(t);},10000);}

waitFor(function(){return document.getElementById('asQBody');},function(body){
  var wrap=document.createElement('div');
  wrap.style.cssText='display:flex;flex-direction:column;gap:6px;margin-top:8px;'+
    'padding:10px;background:#141820;border:1px solid #2a3140;border-radius:6px';
  var row=document.createElement('div');
  row.style.cssText='display:flex;flex-wrap:wrap;gap:10px 16px';
  var advRow=document.createElement('div');
  advRow.style.cssText='display:none;flex-wrap:wrap;gap:10px 16px;'+
    'padding-top:8px;border-top:1px dashed #2a3140';
  var advBtn=document.createElement('span');
  advBtn.textContent='\u25b8 \u9ad8\u7ea7\uff08\u4e0d\u5efa\u8bae\u52a8\uff09';
  advBtn.style.cssText='cursor:pointer;font-size:11px;color:#8ab4e0;'+
    'user-select:none;width:100%';
  advBtn.onclick=function(){
    var open=advRow.style.display==='none';
    advRow.style.display=open?'flex':'none';
    advBtn.textContent=(open?'\u25be':'\u25b8')+' \u9ad8\u7ea7\uff08\u4e0d\u5efa\u8bae\u52a8\uff09';};

  function makeCheckbox(g){
    var lab=document.createElement('label');
    lab.style.cssText='display:inline-flex;align-items:center;gap:6px;'+
      'font-size:12px;color:#dfe6ee;cursor:pointer;max-width:100%';
    var cb=document.createElement('input');cb.type='checkbox';
    var first=el(g.ids[0]);
    var saved=ls('as_g_'+g.key);
    cb.checked=(saved!=null)?(saved==='1'):
      (first?first.checked:g.def);
    if(first)first.checked=cb.checked;
    g.ids.slice(1).forEach(function(id){
      var e=el(id);if(e)e.checked=cb.checked;});
    cb.dataset.g=g.key;
    cb.onchange=function(){
      g.ids.forEach(function(id){var e=el(id);if(e)e.checked=cb.checked;});
      ls('as_g_'+g.key,cb.checked?'1':'0');
      if(typeof saveOpts==='function')saveOpts();};
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(g.label));
    return lab;}

  GROUPS.forEach(function(g){row.appendChild(makeCheckbox(g));});
  ADV.forEach(function(g){advRow.appendChild(makeCheckbox(g));});
  wrap.appendChild(advBtn);
  wrap.appendChild(row);
  wrap.appendChild(advRow);
  body.appendChild(wrap);

  // reverse-sync: preset dropdown (applyPrec) sets original pp checkboxes
  // programmatically -> poll them and mirror to new UI
  setInterval(function(){
    GROUPS.concat(ADV).forEach(function(g){
      var cb=wrap.querySelector('[data-g='+g.key+']');
      if(!cb)return;
      var first=el(g.ids[0]);
      if(first&&first.checked!==cb.checked){
        cb.checked=first.checked;
        ls('as_g_'+g.key,cb.checked?'1':'0');}});
  },500);
});
})();
</script>"""
    if "</body>" in s:
        s = s.replace("</body>", JS + "\n</body>", 1)
        ok.append("UI: simplify script injected")
    else:
        fail.append("UI: </body> not found")

HP.write_text(s, encoding="utf-8")
print()
print("==== V8-SIMPLIFY RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
