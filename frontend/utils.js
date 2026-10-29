export function filterPaths(paths, query, limit=60) {
  const needle=query.trim().toLowerCase();
  return paths.filter(path=>path.toLowerCase().includes(needle)).sort((a,b)=>{
    const ab=a.split('/').pop().toLowerCase().startsWith(needle), bb=b.split('/').pop().toLowerCase().startsWith(needle);
    return Number(bb)-Number(ab)||a.length-b.length;
  }).slice(0,limit);
}
export function expandCommand(prompt) {
  const commands={explain:'请解释所关联文件或选中代码的逻辑、关键步骤及注意点。',fix:'请检查并修复所关联文件或选中代码中的问题；先读取，再做最小修改并验证。',test:'请为所关联代码运行相关测试，必要时补充有价值的测试，并说明结果。',review:'请审查所关联代码，优先报告实际问题、影响及具体位置。'};
  const match=prompt.match(/^\/(explain|fix|test|review)(?:\s|$)/);
  return match?commands[match[1]]+'\n'+prompt.slice(match[0].length).trim():prompt;
}
export function cleanTheme(theme){return theme==='dark'?'dark':'light';}
export function compactEvents(events){
  const result=[];
  for(const event of events){
    const previous=result.at(-1);
    if(previous&&['assistant_delta','command_output'].includes(event.type)&&previous.type===event.type&&previous.id===event.id)previous.text+=event.text;
    else result.push({...event});
  }
  return result;
}
export function isImage(path){return /\.(png|jpe?g|gif|webp|bmp|ico)$/i.test(path);}
export function languageLabel(path){return ({py:'Python',js:'JavaScript',mjs:'JavaScript',ts:'TypeScript',tsx:'TypeScript',json:'JSON',html:'HTML',css:'CSS',md:'Markdown',ps1:'PowerShell',yml:'YAML',yaml:'YAML',sh:'Shell'})[path.split('.').pop()]||'纯文本';}
export function fileGlyph(path){return ({py:'PY',js:'JS',mjs:'JS',ts:'TS',tsx:'TS',json:'{}',html:'<>',css:'#',md:'M',ps1:'PS'})[path.split('.').pop()]||'·';}
