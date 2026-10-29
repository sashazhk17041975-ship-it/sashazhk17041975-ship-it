'use strict';
importScripts('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/ort.min.js','paddle-ctc-v5.js');
ort.env.wasm.wasmPaths='https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/';
ort.env.wasm.numThreads=1;ort.env.wasm.proxy=false;
let session,dictionary;
self.onmessage=async event=>{const {id,type,data,width}=event.data;try{
 if(type==='init'){
  self.postMessage({type:'progress',message:'Загрузка PaddleOCR. Первый запуск потребует загрузки модели…'});
  const base='https://cdn.jsdelivr.net/npm/@gutenye/ocr-models@1.4.2/assets/';
  const [modelResponse,dictResponse]=await Promise.all([fetch(base+'ch_PP-OCRv4_rec_infer.onnx'),fetch(base+'ppocr_keys_v1.txt')]);
  if(!modelResponse.ok||!dictResponse.ok)throw Error('Не удалось загрузить модель или словарь. Проверьте интернет.');
  const [buffer,text]=await Promise.all([modelResponse.arrayBuffer(),dictResponse.text()]);dictionary=text.replace(/\r/g,'').replace(/\n$/,'').split('\n');
  self.postMessage({type:'progress',message:'Подготовка модели PaddleOCR…'});
  session=await ort.InferenceSession.create(buffer,{executionProviders:['wasm'],graphOptimizationLevel:'all'});self.postMessage({id,result:true});
 }else if(type==='recognize'){
  if(!session)throw Error('Модель OCR ещё не готова.');
  const tensor=new ort.Tensor('float32',data,[1,3,48,width]);const outputs=await session.run({[session.inputNames[0]]:tensor});const output=outputs[session.outputNames[0]];
  self.postMessage({id,result:PaddleCTC.decode(output.data,output.dims,dictionary)});
 }
 }catch(error){self.postMessage({id,error:error.message||String(error)})}};
