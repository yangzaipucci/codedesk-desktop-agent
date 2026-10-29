'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="session-token"]').content;
let config=null, running=false, socket=null, currentFile='', assistant=null;
const toolNodes=new Map(), providerDrafts=new Map();
async function api(path,body,method) {
  const response=await fetch('/api/'+path,{method:method||(body===undefined?'GET':'POST'),headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  let data; try{data=await response.json();}catch{throw new Error('本地服务返回了无法读取的数据。');}
  if(!response.ok)throw new Error(data.error||data.detail||'请求失败。'); return data;
}
function element(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
let toastTimer;
function toast(text,error=false){$('toast').textContent=text;$('toast').className=error?'error':'';$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6000);}
function handleError(error){toast(error.message||String(error),true);}
async function busy(id,action){$(id).disabled=true;try{return await action();}catch(error){handleError(error);}finally{$(id).disabled=false;}}
function syncConfig(value){
  config=value;$('workspacePath').textContent=config.workspace||'请选择工作目录';$('workspacePath').title=config.workspace;
  $('folderLabel').textContent=(config.workspace.split(/[\\/]/).pop()||'WORKSPACE').toUpperCase();
  $('modelButton').textContent=config.presets[config.provider]?.label||config.provider;
  $('footerModel').textContent=(config.model||'未选择模型')+' · '+(config.has_key?'已配置 Key':'请接入 API Key');
  $('keyState').textContent=config.has_key?'已配置 · 留空保留':'尚未配置';
  const servers=Object.entries(config.mcp_servers).filter(([,v])=>v.enabled!==false);
  $('mcpSummary').textContent=servers.length?servers.map(([name])=>'◇ '+name).join('\n'):'尚未连接 MCP 服务';
}
function fillSettings(){
  $('provider').replaceChildren();for(const[key,value]of Object.entries(config.presets)){const option=element('option','',value.label);option.value=key;$('provider').append(option);}
  $('provider').value=config.provider;$('provider').dataset.previous=config.provider;$('baseUrl').value=config.base_url;$('model').value=config.model;
  $('apiKey').value='';$('apiKey').type='password';$('toggleKey').textContent='显示';$('rememberKey').checked=false;
  $('mcpConfig').value=JSON.stringify(config.mcp_servers,null,2);$('maxSteps').value=config.max_steps;$('budgetTokens').value=config.budget_tokens;$('runTimeout').value=config.run_timeout;
  $('connectionResult').textContent='测试连接会产生少量 API 用量。';$('mcpResult').textContent='演示服务无需 API Key。';providerDrafts.clear();
}
function showSettings(){if(running)return toast('请先中断当前任务。');fillSettings();$('settingsDialog').showModal();}
async function saveForm(){
  let mcp;try{mcp=JSON.parse($('mcpConfig').value||'{}');}catch{throw new Error('MCP 配置不是合法 JSON。');}
  const value=await api('settings',{provider:$('provider').value,base_url:$('baseUrl').value,model:$('model').value,api_key:$('apiKey').value,remember_key:$('rememberKey').checked,mcp_servers:mcp,max_steps:Number($('maxSteps').value),budget_tokens:Number($('budgetTokens').value),run_timeout:Number($('runTimeout').value)});
  $('apiKey').value='';syncConfig(value);return value;
}
$('settingsButton').onclick=showSettings;$('modelButton').onclick=showSettings;$('mcpButton').onclick=showSettings;
$('closeSettings').onclick=()=>$('settingsDialog').close();
$('settingsForm').onsubmit=e=>{e.preventDefault();busy('saveSettings',async()=>{await saveForm();$('settingsDialog').close();toast('设置已保存。');});};
$('provider').onchange=()=>{
  const previous=$('provider').dataset.previous||config.provider;providerDrafts.set(previous,{base_url:$('baseUrl').value,model:$('model').value});
  const selected=$('provider').value,preset=providerDrafts.get(selected)||config.presets[selected];
  $('baseUrl').value=preset.base_url;$('model').value=preset.model;$('apiKey').value='';$('rememberKey').checked=false;
  $('keyState').textContent='此服务商的 Key 单独配置';$('provider').dataset.previous=selected;$('modelOptions').replaceChildren();$('connectionResult').textContent='填写此服务商的 Key，再测试连接。';
};
$('toggleKey').onclick=()=>{const hidden=$('apiKey').type==='password';$('apiKey').type=hidden?'text':'password';$('toggleKey').textContent=hidden?'隐藏':'显示';};
$('testConnection').onclick=()=>busy('testConnection',async()=>{
  $('connectionResult').textContent='连接中…';try{await saveForm();const value=await api('test',{});$('connectionResult').textContent='✓ '+value.message+' · '+value.reply;}catch(error){$('connectionResult').textContent=error.message;throw error;}
});
$('fetchModels').onclick=()=>busy('fetchModels',async()=>{await saveForm();const value=await api('models');$('modelOptions').replaceChildren(...value.models.map(name=>{const option=element('option');option.value=name;return option;}));toast('已读取 '+value.models.length+' 个模型，请在模型框选择或输入。');$('model').focus();});
$('forgetKey').onclick=()=>busy('forgetKey',async()=>{const value=await api('settings',{base_url:$('baseUrl').value,forget_key:true});$('apiKey').value='';syncConfig(value);toast('已删除此接口的 Key。');});
$('enableDemo').onclick=()=>busy('enableDemo',async()=>{await saveForm();const value=await api('mcp/demo',{});syncConfig(value);$('mcpConfig').value=JSON.stringify(value.mcp_servers,null,2);$('mcpResult').textContent='演示服务已添加，点击检查即可真实调用。';});
$('testMcp').onclick=()=>busy('testMcp',async()=>{
  $('mcpResult').textContent='正在连接外部服务…';await saveForm();const value=await api('mcp/test',{});const okay=value.statuses.filter(s=>s.ok).length;
  $('mcpResult').textContent=`${okay}/${value.statuses.length} 个服务连接成功，发现 ${value.tools.length} 个工具。`+(value.demo_call?.ok?' 演示工具调用成功。':'');
  if(value.demo_call){status('MCP · workspace-demo / workspace_info');$('messages').append(element('pre','message-body',JSON.stringify(value.demo_call,null,2)));$('chatWelcome').hidden=true;scrollChat();}
});
async function loadFiles(container=$('fileTree'),path='.',depth=0){
  const value=await api('files?path='+encodeURIComponent(path));container.replaceChildren();
  for(const file of value.files){
    const row=element('button','file-row'+(file.directory?' directory':''));row.title=file.path;row.style.paddingLeft=(14+depth*13)+'px';
    row.append(element('span','',file.directory?'▸':file.name.endsWith('.py')?'py':file.name.endsWith('.md')?'M':'⌘'),element('span','',file.name));
    const group=element('div');container.append(row,group);
    if(file.directory)row.onclick=async()=>{try{if(group.childNodes.length){group.replaceChildren();row.firstChild.textContent='▸';}else{await loadFiles(group,file.path,depth+1);row.firstChild.textContent='▾';}}catch(error){handleError(error);}};
    else{row.dataset.path=file.path;row.onclick=()=>openFile(file.path).catch(handleError);}
  }
}
async function openFile(path){
  const value=await api('file?path='+encodeURIComponent(path));if(!value.ok)throw new Error(value.error);
  currentFile=path;$('editorWelcome').hidden=true;$('editorTitle').textContent=path.split('/').pop();
  if(value.content?.[0]?.type==='image'){const image=value.content[0];$('codeView').hidden=true;$('imageView').src=`data:${image.mimeType};base64,${image.data}`;$('imageView').hidden=false;$('editorMeta').textContent=image.mimeType;}
  else{$('imageView').hidden=true;$('imageView').removeAttribute('src');$('codeView').hidden=false;$('codeView').className='';$('codeView').textContent=value.text+(value.remaining_lines?'\n\n…还有 '+value.remaining_lines+' 行，预览显示前 500 行。':'');$('editorMeta').textContent=value.total_lines+' 行 · UTF-8';}
  for(const row of document.querySelectorAll('.file-row'))row.classList.toggle('selected',row.dataset.path===path);
}
$('refreshFiles').onclick=()=>loadFiles().catch(handleError);
$('chooseFolder').onclick=async()=>{
  if(running)return toast('请先中断当前任务。');
  try{
    const bridge=window.pywebview?.api;if(!bridge)return toast('请在 CodeDesk 桌面窗口中选择目录。',true);
    const path=await bridge.choose_folder();if(!path)return;
    syncConfig(await api('settings',{workspace:path}));await api('new',{});clearChat();await loadFiles();
    $('editorWelcome').hidden=false;$('codeView').hidden=true;$('imageView').hidden=true;$('editorTitle').textContent='欢迎使用';currentFile='';
  }catch(error){handleError(error);}
};
function scrollChat(){$('messages').scrollTop=$('messages').scrollHeight;}
function addMessage(role,text=''){
  $('chatWelcome').hidden=true;const node=element('article','message '+role);node.append(element('div','message-label',role==='user'?'你':'CODEDESK'));
  const body=element('div','message-body',text);node.append(body);$('messages').append(node);scrollChat();return body;
}
function status(text,error=false){$('messages').append(element('div','inline-status'+(error?' error':''),text));scrollChat();}
function updateRunning(value){running=value;$('sendButton').hidden=value;$('stopButton').hidden=!value;$('prompt').disabled=value;$('runState').className=value?'running':'';$('stateText').textContent=value?'● 正在处理':'● 准备就绪';$('settingsButton').disabled=value;$('modelButton').disabled=value;}
function receive(event){
  switch(event.type){
    case 'user':assistant=null;addMessage('user',event.text);break;
    case 'assistant_delta':if(!assistant)assistant=addMessage('assistant');assistant.textContent+=event.text;scrollChat();break;
    case 'assistant_end':assistant=null;break;
    case 'step':$('stepText').textContent=event.step+' / '+event.max_steps+' 步';break;
    case 'status':status(event.text);break;
    case 'error':status(event.text,true);break;
    case 'mcp_status':status('MCP · '+event.server+' · '+(event.ok?'已连接，'+event.tools.length+' 个工具':event.error),!event.ok);break;
    case 'tool_start':{
      assistant=null;const node=element('details','tool');node.open=true;const summary=element('summary'),indicator=element('span','tool-state','执行中');
      summary.append(element('span','tool-name',event.name),element('span','tool-source',event.source),indicator);node.append(summary,element('pre','',JSON.stringify(event.arguments,null,2)));$('messages').append(node);toolNodes.set(event.id,{node,indicator});scrollChat();
      if(event.name==='bash')$('terminal').textContent='$ '+event.arguments.command+'\n\n';break;
    }
    case 'command_output':$('terminal').textContent+=event.text;$('terminal').scrollTop=$('terminal').scrollHeight;break;
    case 'tool_result':{
      const record=toolNodes.get(event.id);if(!record)break;const result=event.result;
      record.node.classList.toggle('failed',!result.ok);record.indicator.textContent=result.ok?'完成':'失败';record.node.append(element('pre','',JSON.stringify(result,null,2)));record.node.open=!result.ok;
      if(result.diff!==undefined){const button=element('button','text-button','查看修改差异 ↗');button.onclick=()=>{$('editorWelcome').hidden=true;$('imageView').hidden=true;$('codeView').hidden=false;$('codeView').className='diff';$('codeView').textContent=result.diff||'文件内容没有变化。';$('editorTitle').textContent=result.path+' · 差异';$('editorMeta').textContent=result.old_lines+' → '+result.new_lines+' 行';};record.node.append(button);}
      if(result.change_id){const undo=element('button','text-button','撤销这次修改');undo.onclick=async()=>{if(running)return toast('请先等待任务完成或中断。');undo.disabled=true;try{const restored=await api('undo',{change_id:result.change_id});await loadFiles();if(currentFile===restored.path)await openFile(restored.path);undo.textContent='已撤销';status('已撤销：'+restored.path);toast('修改已撤销。');}catch(error){undo.disabled=false;handleError(error);}};record.node.append(undo);}
      if(['write','edit'].includes(event.name)&&result.ok){loadFiles().catch(handleError);if(currentFile===result.path)openFile(currentFile).catch(handleError);}
      if(event.name==='bash')$('terminal').textContent+='\n[exit '+result.exit_code+(result.timed_out?' · 超时':'')+(result.truncated?' · 输出已截断':'')+']\n';scrollChat();break;
    }
    case 'done':assistant=null;updateRunning(false);$('stateText').textContent=({completed:'● 已完成',cancelled:'● 已中断',timeout:'● 已超时',error:'● 需要处理'})[event.status]||'已停止';if(event.tokens)$('stepText').textContent+=' · ≈'+event.tokens+' tokens';break;
  }
}
async function sendPrompt(text){
  if(running||!text.trim())return;if(!config.has_key){showSettings();toast('先在桌面设置中接入 API Key。');return;}
  if(!config.workspace)return toast('请先打开工作目录。',true);
  updateRunning(true);$('prompt').value='';assistant=null;socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
  socket.onopen=()=>{socket.send(JSON.stringify({token}));socket.send(JSON.stringify({prompt:text}));};
  socket.onmessage=event=>{try{receive(JSON.parse(event.data));}catch(error){handleError(error);}};
  socket.onerror=()=>{status('本地连接失败，请重新打开应用。',true);updateRunning(false);};
  socket.onclose=()=>{if(running){updateRunning(false);status('连接已关闭，当前任务已停止。',true);}};
}
$('chatForm').onsubmit=event=>{event.preventDefault();sendPrompt($('prompt').value).catch(handleError);};
$('prompt').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chatForm').requestSubmit();}};
for(const button of document.querySelectorAll('.suggestion'))button.onclick=()=>{$('prompt').value=button.dataset.prompt;$('prompt').focus();};
$('stopButton').onclick=()=>busy('stopButton',async()=>{$('stateText').textContent='正在中断…';await api('stop',{});updateRunning(false);});
function clearChat(){for(const node of [...$('messages').children])if(node.id!=='chatWelcome')node.remove();$('chatWelcome').hidden=false;assistant=null;toolNodes.clear();$('stepText').textContent='';$('stateText').textContent='● 准备就绪';}
$('newSession').onclick=async()=>{try{await api('new',{});clearChat();toast('已新建会话。');}catch(error){handleError(error);}};
$('clearTerminal').onclick=()=>$('terminal').textContent='';
$('exportTrace').onclick=async()=>{try{const response=await fetch('/api/trace',{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw new Error('导出失败。');const blob=await response.blob(),url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download='trace.md';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('运行记录已导出。');}catch(error){handleError(error);}};
(async()=>{try{syncConfig(await api('settings'));await loadFiles();const history=await api('history');for(const event of history.events)receive(event);}catch(error){handleError(error);}})();
