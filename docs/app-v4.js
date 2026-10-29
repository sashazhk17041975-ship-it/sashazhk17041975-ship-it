'use strict';
const $=id=>document.getElementById(id);
const DEMO='WBA3A5C50DF123456';
const groups=['Все детали','Двигатель','Тормоза','Подвеска','Фильтры'];
const parts=[{id:1,name:'Масляный фильтр',oem:'11 42 7 953 129',group:'Фильтры'},{id:2,name:'Воздушный фильтр',oem:'13 71 7 599 285',group:'Фильтры'},{id:3,name:'Комплект передних колодок',oem:'34 11 6 859 066',group:'Тормоза'},{id:4,name:'Передний тормозной диск',oem:'34 11 6 794 427',group:'Тормоза'},{id:5,name:'Свеча зажигания',oem:'12 12 0 039 664',group:'Двигатель'},{id:6,name:'Передний амортизатор',oem:'31 31 6 860 237',group:'Подвеска'}];
function read(key,fallback){try{return JSON.parse(localStorage.getItem(key))||fallback}catch{return fallback}}
let history=read('vin-oem-history',[]),saved=read('vin-oem-saved',[]),group='Все детали';
if(!Array.isArray(history))history=[];if(!Array.isArray(saved))saved=[];
history=history.filter(x=>x&&typeof x.vin==='string'&&/^[A-HJ-NPR-Z0-9]{17}$/.test(x.vin)&&typeof x.date==='number');saved=saved.filter(id=>parts.some(p=>p.id===id));
function persist(){try{localStorage.setItem('vin-oem-history',JSON.stringify(history));localStorage.setItem('vin-oem-saved',JSON.stringify(saved))}catch{toast('Браузер не разрешил сохранить данные')}updateCounts()}
function updateCounts(){$('history-count').textContent=history.length;$('saved-count').textContent=saved.length}
let toastTimer;function toast(message){$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),3200)}
function normalize(value){return value.toUpperCase().replace(/\s/g,'')}
function vinError(value){if(value.length!==17)return 'VIN должен содержать ровно 17 символов.';if(!/^[A-HJ-NPR-Z0-9]{17}$/.test(value))return 'Используйте латинские буквы и цифры. Буквы I, O, Q недопустимы.';return ''}
function updateInput(){$('vin').value=normalize($('vin').value);$('counter').textContent=$('vin').value.length+' / 17';$('error').textContent='';$('vin').removeAttribute('aria-invalid');$('catalog-links').hidden=true;$('results').hidden=true;$('copy-status').textContent=''}
$('vin').addEventListener('input',updateInput);$('clear').onclick=()=>{$('vin').value='';updateInput();$('vin').focus();$('results').hidden=true};
function lookup(){const vin=normalize($('vin').value);$('vin').value=vin;updateInput();const error=vinError(vin);if(error){$('error').textContent=error;$('vin').setAttribute('aria-invalid','true');$('vin').focus();return}history=[{vin,date:Date.now()},...history.filter(x=>x.vin!==vin)].slice(0,20);persist();$('catalog-vin').textContent=vin;$('catalog-links').hidden=false;if(vin!==DEMO){$('results').hidden=true;$('catalog-links').scrollIntoView({behavior:'smooth',block:'start'});return}$('results').hidden=false;group='Все детали';renderFilters();renderParts();$('catalog-links').scrollIntoView({behavior:'smooth',block:'start'})}
$('vin-form').onsubmit=e=>{e.preventDefault();lookup()};$('example').onclick=()=>{$('vin').value=DEMO;lookup()};
function setView(view){document.querySelectorAll('main>section').forEach(s=>s.hidden=s.id!==view+'-view');document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));if(view==='history')renderHistory();if(view==='saved')renderSaved()}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));document.querySelector('.brand').onclick=e=>{e.preventDefault();setView('search')};
function renderFilters(){$('filters').replaceChildren(...groups.map(name=>{const b=document.createElement('button');b.textContent=name;b.className=name===group?'active':'';b.onclick=()=>{group=name;renderFilters();renderParts()};return b}))}
function partCard(part){const el=document.createElement('article');el.className='part';el.innerHTML='<div class="part-top"><span>'+part.group.toUpperCase()+'</span><span>ПРИМЕР OEM</span></div><h3>'+part.name+'</h3><code>'+part.oem+'</code><div class="part-actions"><button class="copy">Копировать ↗</button><button class="save '+(saved.includes(part.id)?'saved':'')+'">'+(saved.includes(part.id)?'Сохранено ✓':'Сохранить ◇')+'</button></div>';el.querySelector('.copy').onclick=async()=>{try{await navigator.clipboard.writeText(part.oem);toast('OEM-номер скопирован')}catch{toast('Копирование недоступно. Выделите OEM-номер вручную.')}};el.querySelector('.save').onclick=()=>{saved=saved.includes(part.id)?saved.filter(x=>x!==part.id):[...saved,part.id];persist();renderParts();renderSaved()};return el}
function renderParts(){$('parts').replaceChildren(...parts.filter(p=>group==='Все детали'||p.group===group).map(partCard))}
function empty(message){const el=document.createElement('div');el.className='empty';el.textContent=message;return el}
function renderSaved(){const selected=parts.filter(p=>saved.includes(p.id));$('saved-list').replaceChildren(...(selected.length?selected.map(partCard):[empty('Пока нет сохранённых деталей. Откройте демопример и добавьте деталь в список.')]));}
function renderHistory(){$('history-list').replaceChildren(...(history.length?history.map(x=>{const el=document.createElement('div');el.className='history-row';const info=document.createElement('div');const code=document.createElement('code');code.textContent=x.vin;const date=document.createElement('p');date.textContent=new Date(x.date).toLocaleString('ru-RU')+(x.vin===DEMO?' · Демопример':' · Поиск во внешнем каталоге');info.append(code,date);const button=document.createElement('button');button.className='secondary';button.textContent='Открыть →';button.onclick=()=>{setView('search');$('vin').value=x.vin;lookup()};el.append(info,button);return el}):[empty('Здесь появятся VIN после первого поиска.')]));$('clear-history').hidden=!history.length}
$('clear-history').onclick=()=>{history=[];persist();renderHistory();toast('История очищена')};
$('help').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();
let stream=null,scanActive=false,scanEpoch=0,ocrBusy=false;
function stopCamera(){scanActive=false;scanEpoch++;if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;$('video').srcObject=null;$('camera-placeholder').hidden=false;$('capture-vin').hidden=true}
$('scan').onclick=()=>{$('scan-dialog').showModal();$('scan-status').textContent='Текст VIN: включите камеру и нажмите «Снять и распознать» или загрузите фото. Штрихкод сканируется автоматически, если браузер это поддерживает.'};
$('close-scan').onclick=()=>$('scan-dialog').close();$('scan-dialog').addEventListener('close',stopCamera);
function acceptVin(vin){if(vinError(vin))return false;stopCamera();$('scan-dialog').close();setView('search');$('vin').value=vin;updateInput();$('vin').focus();toast('VIN перенесён. Сверьте все 17 символов с документом.');return true}
function acceptScan(text){const candidates=VinParser.extract(text);return candidates.length===1&&acceptVin(candidates[0])}
function showCandidates(text,ranked=null,counts=new Map(),suggestions=new Map()){
 $('ocr-text').value=text;$('ocr-review').hidden=false;
 const candidates=ranked?.length?ranked:VinParser.extract(text);
 $('ocr-vin-edit').value=candidates[0]||'';
 $('vin-candidates').replaceChildren(...candidates.map(vin=>{const b=document.createElement('button');b.className='secondary';b.type='button';b.textContent=vin+(suggestions.has(vin)?' · OCR: '+suggestions.get(vin):counts.get(vin)>=2?' · совпало в '+counts.get(vin)+' проходах':' · проверьте')+' →';b.onclick=()=>acceptVin(vin);return b}));
 $('scan-status').textContent=candidates.length?'Сверьте каждый символ с документом. Совпадение нескольких проходов не гарантирует точность.':'VIN не найден. Проверьте распознанный текст ниже. Сфотографируйте крупнее строку «Кузаў (рама) №» и VIN после неё.';
}
$('start-camera').onclick=async()=>{
 if(ocrBusy)return;stopCamera();const epoch=scanEpoch;
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw Error('Камера недоступна. Нажмите «Сделать фото телефоном» или загрузите фото.');
  const newStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:3840},height:{ideal:2160}},audio:false});
  if(epoch!==scanEpoch||!$('scan-dialog').open){newStream.getTracks().forEach(t=>t.stop());return}
  stream=newStream;const track=stream.getVideoTracks?.()[0];try{if(track?.getCapabilities?.().focusMode?.includes('continuous'))await track.applyConstraints({advanced:[{focusMode:'continuous'}]})}catch{}$('video').srcObject=stream;await $('video').play();
  if(epoch!==scanEpoch)return;
  $('camera-placeholder').hidden=true;$('capture-vin').hidden=false;scanActive=true;
  $('scan-status').textContent='Наведите камеру на строку «Кузаў (рама) №» и VIN рядом с ней. Нажмите «Снять и распознать».';
  if(!('BarcodeDetector' in window))return;
  let detector;try{const supported=await BarcodeDetector.getSupportedFormats();const formats=['code_39','code_128','qr_code','data_matrix','pdf417'].filter(f=>supported.includes(f));if(!formats.length)return;detector=new BarcodeDetector({formats})}catch{return}
  const tick=async()=>{if(!scanActive||epoch!==scanEpoch)return;try{const codes=await detector.detect($('video'));if(epoch!==scanEpoch)return;for(const code of codes)if(acceptScan(code.rawValue))return}catch{}if(scanActive&&epoch===scanEpoch)setTimeout(tick,350)};tick();
 }catch(e){if(epoch!==scanEpoch)return;stopCamera();$('scan-status').textContent=e.name==='NotAllowedError'?'Камера запрещена. Разрешите доступ в настройках телефона либо нажмите «Сделать фото телефоном».':e.message}
};
let ocrPromise;
function loadOCR(){if(window.Tesseract)return Promise.resolve();if(!ocrPromise)ocrPromise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';script.onload=resolve;script.onerror=()=>{script.remove();ocrPromise=null;reject(Error('Не удалось загрузить OCR. Проверьте интернет и повторите.'))};document.head.append(script)});return ocrPromise}
function setBusy(value){ocrBusy=value;for(const id of ['photo-button','start-camera','take-photo','capture-vin','run-ocr','reset-crop','rotate-photo'])$(id).disabled=value;$('cancel-ocr').hidden=!value}
let activeWorker=null,ocrEpoch=0,loadedPhoto=null,photoTurns=0,photoRect={x:0,y:0,w:1,h:1},dragOrigin=null;
async function cancelOCR(){ocrEpoch++;if(activeWorker){const w=activeWorker;activeWorker=null;await w.terminate().catch(()=>{})}setBusy(false);$('scan-status').textContent='Распознавание отменено. Можно уточнить область VIN и повторить.'}
$('cancel-ocr').onclick=cancelOCR;$('scan-dialog').addEventListener('close',()=>{if(ocrBusy)cancelOCR();loadedPhoto=null;$('photo-editor').hidden=true;const c=$('photo-preview');c.width=1;c.height=1});
function drawPhoto(){
 if(!loadedPhoto)return;const c=$('photo-preview'),iw=loadedPhoto.naturalWidth,ih=loadedPhoto.naturalHeight,rw=photoTurns%2?ih:iw,rh=photoTurns%2?iw:ih,scale=Math.min(1,760/rw,560/rh);c.width=Math.round(rw*scale);c.height=Math.round(rh*scale);const ctx=c.getContext('2d');ctx.save();ctx.translate(c.width/2,c.height/2);ctx.rotate(photoTurns*Math.PI/2);ctx.drawImage(loadedPhoto,-iw*scale/2,-ih*scale/2,iw*scale,ih*scale);ctx.restore();const x=photoRect.x*c.width,y=photoRect.y*c.height,w=photoRect.w*c.width,h=photoRect.h*c.height;ctx.fillStyle='rgba(0,0,0,.5)';ctx.beginPath();ctx.rect(0,0,c.width,c.height);ctx.rect(x,y,w,h);ctx.fill('evenodd');ctx.strokeStyle='#c6f566';ctx.lineWidth=3;ctx.strokeRect(x,y,w,h);
 $('crop-description').textContent=photoRect.w*photoRect.h>.95?'Выбран весь снимок. Для лучшего результата обведите только VIN, оставив немного места вокруг букв.':'Выбрана область VIN. Убедитесь, что все 17 символов попали в рамку.';
}
function photoPoint(e){const r=$('photo-preview').getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}}
$('photo-preview').onpointerdown=e=>{if(ocrBusy||!loadedPhoto)return;e.preventDefault();dragOrigin=photoPoint(e);$('photo-preview').setPointerCapture(e.pointerId)};
$('photo-preview').onpointermove=e=>{if(!dragOrigin||ocrBusy)return;const p=photoPoint(e);photoRect={x:Math.min(p.x,dragOrigin.x),y:Math.min(p.y,dragOrigin.y),w:Math.abs(p.x-dragOrigin.x),h:Math.abs(p.y-dragOrigin.y)};drawPhoto()};
function endCrop(){if(!dragOrigin)return;dragOrigin=null;if(photoRect.w<.04||photoRect.h<.008){photoRect={x:0,y:0,w:1,h:1};drawPhoto()}}
$('photo-preview').onpointerup=endCrop;$('photo-preview').onpointercancel=endCrop;
$('reset-crop').onclick=()=>{photoRect={x:0,y:0,w:1,h:1};drawPhoto()};$('rotate-photo').onclick=()=>{photoTurns=(photoTurns+1)%4;photoRect={x:0,y:0,w:1,h:1};drawPhoto()};
async function openPhoto(file){
 if(!file||ocrBusy)return;if(file.size>15*1024*1024){$('scan-status').textContent='Выберите фото до 15 МБ.';return}stopCamera();$('scan-status').textContent='Открываю фото…';let url;
 try{url=URL.createObjectURL(file);const image=new Image();image.src=url;await image.decode();if(!$('scan-dialog').open)return;loadedPhoto=image;photoTurns=0;photoRect={x:0,y:0,w:1,h:1};$('ocr-review').hidden=true;$('photo-editor').hidden=false;drawPhoto();$('scan-status').textContent='Обведите пальцем только строку VIN и нажмите «Распознать выделенное». Если оставить весь снимок, приложение попробует найти строку автоматически.';$('photo-editor').scrollIntoView({behavior:'smooth',block:'nearest'})}catch{$('scan-status').textContent='Не удалось открыть изображение. Выберите JPG/PNG или сделайте новое фото.'}finally{if(url)URL.revokeObjectURL(url)}
}
async function runOCR(){
 if(!loadedPhoto||ocrBusy)return;stopCamera();setBusy(true);$('ocr-review').hidden=true;const epoch=++ocrEpoch;let worker;let stage='Подготовка';const readings=[];
 const progress=m=>{if(epoch!==ocrEpoch||!$('scan-dialog').open)return;$('scan-status').textContent=stage+': '+Math.round((m.progress||0)*100)+'%'};
 async function create(langs,accurate){
  const w=await Tesseract.createWorker(langs,1,{workerPath:'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js',corePath:'https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1',langPath:accurate?'https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/4.0.0_best_int':'https://cdn.jsdelivr.net/gh/tesseract-ocr/tessdata_fast@4.1.0',gzip:accurate,cachePath:accurate?'vin-best-v4':'vin-locate-v4',logger:progress},accurate?{load_system_dawg:'0',load_freq_dawg:'0',load_number_dawg:'0',load_punc_dawg:'0'}:{});
  if(epoch!==ocrEpoch){await w.terminate();return null}activeWorker=w;return w;
 }
 async function release(){if(worker){if(activeWorker===worker)activeWorker=null;await worker.terminate().catch(()=>{});worker=null}}
 try{
  let region=VinImage.crop(loadedPhoto,photoRect,photoTurns);await loadOCR();if(epoch!==ocrEpoch)return;
  let lineMode=region.width/region.height>=2.5;
  if(!lineMode){stage='Ищу строку «Кузаў (рама) №»';worker=await create(['eng','rus'],false);if(!worker)return;await worker.setParameters({tessedit_pageseg_mode:'11',preserve_interword_spaces:'1'});const located=await worker.recognize(region);if(epoch!==ocrEpoch)return;readings.push(located.data.text);const roi=VinImage.locate(located.data,region.width,region.height);await release();if(roi){region=VinImage.crop(region,roi);lineMode=region.width/region.height>=2.5}}
  if(epoch!==ocrEpoch)return;
  stage='Загружаю точную модель VIN';worker=await create('eng',true);if(!worker)return;
  const angle=VinImage.deskew(VinImage.filter(region,'gray')).angle;const aligned=VinImage.rotate(region,angle);
  const passes=lineMode?[['gray','7'],['binary','7'],['color-clean','13'],['gray','6']]:[['gray','11'],['binary','11'],['color-clean','6']];
  const counts=new Map();
  for(let i=0;i<passes.length;i++){
   if(epoch!==ocrEpoch)return;stage='Точный проход '+(i+1)+' / '+passes.length;
   await worker.setParameters({tessedit_pageseg_mode:passes[i][1],tessedit_char_whitelist:'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',preserve_interword_spaces:'1',user_defined_dpi:'300'});
   const result=await worker.recognize(VinImage.filter(aligned,passes[i][0]));if(epoch!==ocrEpoch)return;readings.push(result.data.text);
   for(const vin of VinParser.extract(result.data.text))counts.set(vin,(counts.get(vin)||0)+1);
   // Require agreement between different image treatments before finishing early.
   if([...counts.values()].some(votes=>votes>=2))break;
  }
  if(epoch===ocrEpoch&&$('scan-dialog').open){const ranked=[...counts].sort((a,b)=>b[1]-a[1]).map(x=>x[0]);const suggestions=new Map();for(const item of VinParser.suggest(readings.join('\n'))){if(!counts.has(item.vin)){suggestions.set(item.vin,item.note);if(!ranked.includes(item.vin))ranked.push(item.vin)}}showCandidates(readings.join('\n'),ranked,counts,suggestions);$('ocr-review').scrollIntoView({behavior:'smooth',block:'nearest'})}
 }catch(e){if(epoch===ocrEpoch)$('scan-status').textContent='Не удалось завершить OCR. Проверьте интернет и повторите. '+(e.message||'').slice(0,100)}
 finally{await release();if(epoch===ocrEpoch)setBusy(false)}
}
$('run-ocr').onclick=runOCR;
$('photo-button').onclick=()=>$('photo').click();$('take-photo').onclick=()=>$('camera-photo').click();
for(const id of ['photo','camera-photo'])$(id).onchange=async()=>{try{await openPhoto($(id).files[0])}finally{$(id).value=''}};
$('capture-vin').onclick=()=>{
 const video=$('video');if(!video.videoWidth||ocrBusy)return;const c=document.createElement('canvas');c.width=video.videoWidth;c.height=video.videoHeight;c.getContext('2d').drawImage(video,0,0);c.toBlob(blob=>{if(blob&&$('scan-dialog').open)openPhoto(blob)},'image/jpeg',.98);
};
$('use-ocr-text').onclick=()=>{const candidates=VinParser.extract($('ocr-text').value);if(candidates.length===1)acceptVin(candidates[0]);else showCandidates($('ocr-text').value)};
$('use-manual-vin').onclick=()=>{const vin=normalize($('ocr-vin-edit').value);if(!acceptVin(vin))$('scan-status').textContent=vinError(vin)};
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()}});
updateCounts();

$('copy-vin').onclick=async()=>{const vin=$('catalog-vin').textContent;if(vinError(vin))return;try{await navigator.clipboard.writeText(vin);$('copy-status').textContent='VIN скопирован. Откройте каталог и вставьте его в поиск.';toast('VIN скопирован')}catch{$('catalog-vin').focus();const selection=window.getSelection();const range=document.createRange();range.selectNodeContents($('catalog-vin'));selection.removeAllRanges();selection.addRange(range);$('copy-status').textContent='VIN выделен. Нажмите «Копировать» или Ctrl+C, затем откройте каталог.'}};
