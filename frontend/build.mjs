import {build} from 'esbuild';
import {copyFile, mkdir,readFile,writeFile,readdir} from 'node:fs/promises';
await mkdir('ui', {recursive:true});
await build({entryPoints:['frontend/main.js'],bundle:true,outfile:'ui/app.js',format:'iife',target:['chrome100'],minify:true,legalComments:'linked'});
await writeFile('ui/app.js',(await readFile('ui/app.js','utf8')).replace(/[\t ]+$/gm,''));
await copyFile('frontend/index.html','ui/index.html');
await copyFile('frontend/styles.css','ui/style.css');
let notices='Bundled frontend third-party notices\n\n';
const lock=JSON.parse(await readFile('package-lock.json','utf8'));
for(const path of Object.keys(lock.packages||{}).filter(p=>p.startsWith('node_modules/'))){
  const names=await readdir(path).catch(()=>[]);
  for(const name of names.filter(n=>/^licen[cs]e(?:\.|$)/i.test(n))){
    const text=await readFile(path+'/'+name,'utf8').catch(()=>null);
    if(text)notices+='--- '+path.replace('node_modules/','')+' ---\n'+text+'\n\n';
  }
}
await writeFile('ui/THIRD_PARTY_NOTICES.txt',notices);
console.log('Offline desktop UI built.');
