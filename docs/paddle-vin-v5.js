(function(root){
'use strict';
function tensor(source){
 const h=48,scaled=Math.max(16,Math.min(2048,Math.round(source.width/source.height*h))),w=Math.max(320,Math.ceil(scaled/32)*32);
 const c=document.createElement('canvas');c.width=scaled;c.height=h;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,scaled,h);ctx.drawImage(source,0,0,scaled,h);const rgba=ctx.getImageData(0,0,scaled,h).data;
 const data=new Float32Array(3*w*h),plane=w*h;for(let y=0;y<h;y++)for(let x=0;x<scaled;x++){const i=(y*scaled+x)*4,j=y*w+x;data[j]=(rgba[i+2]/255-.5)/.5;data[plane+j]=(rgba[i+1]/255-.5)/.5;data[plane*2+j]=(rgba[i]/255-.5)/.5}return {data,width:w};
}
function trim(source){
 const c=document.createElement('canvas');c.width=source.width;c.height=source.height;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0);const im=ctx.getImageData(0,0,c.width,c.height),w=c.width,h=c.height,rows=new Float32Array(h);
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4;if(Math.max(im.data[i],im.data[i+1],im.data[i+2])<115)rows[y]++}
 const max=Math.max(...rows);if(max<10)return source;let best=null,start=-1;
 for(let y=0;y<=h;y++){const active=y<h&&rows[y]>max*.18;if(active&&start<0)start=y;if((!active||y===h)&&start>=0){const end=y;let sum=0;for(let j=start;j<end;j++)sum+=rows[j];if(!best||sum>best.sum)best={top:start,bottom:end,sum};start=-1}}
 if(!best||best.bottom-best.top<h*.12)return source;
 const pad=Math.max(3,Math.round((best.bottom-best.top)*.2)),top=Math.max(0,best.top-pad),bottom=Math.min(h,best.bottom+pad);
 return VinImage.crop(source,{x:0,y:top/h,w:1,h:(bottom-top)/h});
}
function create(progress=()=>{}){
 const worker=new Worker('paddle-worker-v5.js');let next=0,closed=false;const pending=new Map();
 function rejectAll(message){for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error(message))}pending.clear()}
 worker.onmessage=e=>{if(e.data.type==='progress'){progress(e.data.message);return}const p=pending.get(e.data.id);if(!p)return;clearTimeout(p.timer);pending.delete(e.data.id);e.data.error?p.reject(Error(e.data.error)):p.resolve(e.data.result)};
 worker.onerror=()=>rejectAll('PaddleOCR не запустился. Проверьте интернет и поддержку WebAssembly в браузере.');
 function call(type,payload={},transfer=[]){if(closed)return Promise.reject(Error('Распознавание отменено'));return new Promise((resolve,reject)=>{const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(Error('OCR не ответил вовремя. Попробуйте ещё раз.'));worker.terminate();closed=true;rejectAll('OCR остановлен.')},180000);pending.set(id,{resolve,reject,timer});worker.postMessage({id,type,...payload},transfer)})}
 const ready=call('init').catch(e=>{worker.terminate();closed=true;throw e});
 return {ready,recognize:async source=>{const input=tensor(source);return call('recognize',input,[input.data.buffer])},terminate:async()=>{closed=true;worker.terminate();rejectAll('Распознавание отменено')}};
}
root.PaddleVin={tensor,trim,create};
})(typeof window==='undefined'?globalThis:window);
