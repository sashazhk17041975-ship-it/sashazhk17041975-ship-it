(function(root){
'use strict';
const lookalikes={'А':'A','В':'B','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P','С':'C','Т':'T','У':'Y','Х':'X'};
const label=/(?:\bVIN\b|КУЗ[АО][ВЎУY]?\s*(?:\([^)]*\))?\s*[№N:#.]*|РАМ[АЫ]\s*[№N:#.]*|\bCHASSIS\b|\bBODY\b)/i;
function scanSegment(segment){
 const text=segment.toUpperCase().replace(/[АВЕКМНОРСТУХ]/g,c=>lookalikes[c]);
 const found=[];
 for(const token of text.split(/[^A-Z0-9]+/))if(/^[A-HJ-NPR-Z0-9]{17}$/.test(token))found.push(token);
 const compact=text.trim().replace(/^[№:#*\s]+/,'').replace(/[\s\-*]+/g,'');
 if(/^[A-HJ-NPR-Z0-9]{17}$/.test(compact))found.push(compact);
 return found;
}
function extract(text){
 const lines=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
 const targeted=[],general=[];
 for(let i=0;i<lines.length;i++){
  const m=label.exec(lines[i]);
  if(m){const tail=lines[i].slice(m.index+m[0].length).replace(/^[\s№:#.]+/,'');targeted.push(...scanSegment(tail));if(i+1<lines.length)targeted.push(...scanSegment(lines[i+1]));}
  general.push(...scanSegment(lines[i]));
 }
 return [...new Set([...targeted,...general])];
}
root.VinParser={extract};
})(typeof window==='undefined'?globalThis:window);
