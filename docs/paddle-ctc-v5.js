(function(root){
'use strict';
function decode(data,dims,dictionary){
 const classes=dims[dims.length-1],steps=dims[dims.length-2];
 if(classes!==dictionary.length+2)throw Error('Словарь OCR не соответствует модели.');
 let previous=-1,text='',sum=0;const symbols=[];
 for(let t=0;t<steps;t++){let best=0,prob=-Infinity;for(let c=0;c<classes;c++){const value=data[t*classes+c];if(value>prob){prob=value;best=c}}if(best!==0&&best!==previous){const char=best===classes-1?' ':dictionary[best-1];text+=char;sum+=prob;symbols.push({char,score:prob})}previous=best}
 return {text,confidence:symbols.length?sum/symbols.length:0,symbols};
}
root.PaddleCTC={decode};
})(typeof self==='undefined'?globalThis:self);
