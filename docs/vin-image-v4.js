(function(root){
'use strict';
function canvas(w,h){const c=document.createElement('canvas');c.width=Math.max(1,Math.round(w));c.height=Math.max(1,Math.round(h));return c}
function crop(image,rect={x:0,y:0,w:1,h:1},turns=0){
 const iw=image.naturalWidth||image.width,ih=image.naturalHeight||image.height;
 const rw=turns%2?ih:iw,rh=turns%2?iw:ih;
 const x=Math.max(0,Math.min(.999,rect.x)),y=Math.max(0,Math.min(.999,rect.y));
 const sw=Math.max(1,Math.min(rect.w,1-x)*rw),sh=Math.max(1,Math.min(rect.h,1-y)*rh);
 const scale=Math.min(4,Math.max(1,1800/sw),3200/sw,Math.sqrt(4000000/(sw*sh)));
 const out=canvas(sw*scale,sh*scale),ctx=out.getContext('2d');
 ctx.fillStyle='#fff';ctx.fillRect(0,0,out.width,out.height);ctx.scale(scale,scale);ctx.translate(-x*rw,-y*rh);ctx.translate(rw/2,rh/2);ctx.rotate(turns*Math.PI/2);ctx.drawImage(image,-iw/2,-ih/2);return out;
}
function rotate(source,angle){if(Math.abs(angle)<.1)return source;const rad=angle*Math.PI/180;const out=canvas(source.width*Math.cos(rad)+source.height*Math.abs(Math.sin(rad)),source.height*Math.cos(rad)+source.width*Math.abs(Math.sin(rad)));const ctx=out.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,out.width,out.height);ctx.translate(out.width/2,out.height/2);ctx.rotate(rad);ctx.drawImage(source,-source.width/2,-source.height/2);return out}
function filter(source,mode='gray'){
 const out=canvas(source.width,source.height),ctx=out.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0);const im=ctx.getImageData(0,0,out.width,out.height),d=im.data,n=d.length/4;
 const gray=new Uint8Array(n),hist=new Uint32Array(256);for(let i=0;i<n;i++){const j=i*4;const v=mode==='color-clean'?Math.max(d[j],d[j+1],d[j+2]):Math.round(.299*d[j]+.587*d[j+1]+.114*d[j+2]);gray[i]=v;hist[v]++}
 let low=0,high=255,total=0;for(let v=0;v<256;v++){total+=hist[v];if(total<n*.01)low=v;if(total<n*.96)high=v}const span=Math.max(35,high-low);
 if(mode==='binary'){
  const w=out.width,h=out.height,r=Math.max(8,Math.min(35,Math.round(w/90))),means=new Float32Array(n);
  for(let y=0;y<h;y++){let sum=0;for(let x=0;x<=Math.min(r,w-1);x++)sum+=gray[y*w+x];for(let x=0;x<w;x++){means[y*w+x]=sum/(Math.min(w-1,x+r)-Math.max(0,x-r)+1);if(x-r>=0)sum-=gray[y*w+x-r];if(x+r+1<w)sum+=gray[y*w+x+r+1]}}
  for(let x=0;x<w;x++){let sum=0;for(let y=0;y<=Math.min(r,h-1);y++)sum+=means[y*w+x];for(let y=0;y<h;y++){const mean=sum/(Math.min(h-1,y+r)-Math.max(0,y-r)+1);const i=y*w+x,j=i*4,v=gray[i]<mean-17?0:255;d[j]=d[j+1]=d[j+2]=v;d[j+3]=255;if(y-r>=0)sum-=means[(y-r)*w+x];if(y+r+1<h)sum+=means[(y+r+1)*w+x]}}
 }else{for(let i=0;i<n;i++){const j=i*4,v=Math.max(0,Math.min(255,Math.round((gray[i]-low)*255/span)));d[j]=d[j+1]=d[j+2]=v;d[j+3]=255}}
 ctx.putImageData(im,0,0);return out;
}
function deskew(source){
 if(source.width/source.height<2.5)return {canvas:source,angle:0};
 const scale=Math.min(1,900/source.width),small=canvas(source.width*scale,source.height*scale),ctx=small.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0,small.width,small.height);const d=ctx.getImageData(0,0,small.width,small.height).data,points=[];
 for(let y=2;y<small.height-2;y++)for(let x=2;x<small.width-2;x++){const j=(y*small.width+x)*4;if((d[j]+d[j+1]+d[j+2])/3<100)points.push(x,y)}
 if(points.length<80)return {canvas:source,angle:0};
 let bestAngle=0,best=-1,zero=0;for(let angle=-6;angle<=6;angle+=.5){const slope=Math.tan(angle*Math.PI/180),rows=new Uint32Array(small.height+200);for(let i=0;i<points.length;i+=2){const row=Math.round(points[i+1]+slope*(points[i]-small.width/2))+100;if(row>=0&&row<rows.length)rows[row]++}let score=0;for(const count of rows)score+=count*count;if(angle===0)zero=score;if(score>best){best=score;bestAngle=angle}}
 if(best<zero*1.04)bestAngle=0;return {canvas:rotate(source,bestAngle),angle:bestAngle};
}
function locate(data,width,height){
 const lines=data.lines||[];let selected=null;
 for(const line of lines){if(/КУЗ|РАМ[АЫ]|\bVIN\b|CHASSIS|BODY/i.test(line.text||'')){selected=line;break}}
 if(!selected)selected=lines.find(line=>/[A-Z0-9АВЕКМНОРСТУХ]{14,22}/i.test((line.text||'').replace(/[\s-]/g,'')));
 if(!selected?.bbox)return null;
 const words=selected.words||[];const token=words.find(word=>{const text=(word.text||'').replace(/[^A-Z0-9АВЕКМНОРСТУХ]/gi,'');return text.length>=14&&text.length<=22});
 let box=token?.bbox||selected.bbox;
 if(!token&&/КУЗ|РАМ[АЫ]|VIN|CHASSIS|BODY/i.test(selected.text||'')&&selected.bbox.x1-selected.bbox.x0<width*.4){const next=lines.find(l=>l!==selected&&l.bbox&&l.bbox.y0>=selected.bbox.y1&&l.bbox.y0-selected.bbox.y1<(selected.bbox.y1-selected.bbox.y0)*2);if(next&&/[A-Z0-9]{10}/i.test((next.text||'').replace(/\s/g,'')))box=next.bbox}
 const pad=Math.max(6,(box.y1-box.y0)*.5),x=Math.max(0,box.x0-pad),y=Math.max(0,box.y0-pad);
 return {x:x/width,y:y/height,w:(Math.min(width,box.x1+pad)-x)/width,h:(Math.min(height,box.y1+pad)-y)/height};
}
root.VinImage={crop,rotate,filter,deskew,locate};
})(typeof window==='undefined'?globalThis:window);
