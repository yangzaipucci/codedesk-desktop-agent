const names={skills:'技能目录与按需加载',custom:'全局与项目 AGENTS.md',hooks:'危险操作拦截',autotest:'修改后自动运行相关测试',reviewer:'独立只读 reviewer',daemon:'常驻任务',scheduler:'按 routines.yaml 定时运行技能',resume:'中断后按检查点继续',notifications:'Windows 系统完成通知'};
export function installPatchSettings(api,toast){
  const details=document.createElement('details');details.className='advanced';
  const summary=document.createElement('summary');summary.textContent='技能、定制与常驻任务';details.append(summary);
  const help=document.createElement('p');help.className='help';help.textContent='可单独关闭新增能力；环境变量开关优先。常驻计划与验收命令见 README。';details.append(help);
  for(const[name,label]of Object.entries(names)){const row=document.createElement('label');row.className='checkbox patch-option';const input=document.createElement('input');input.type='checkbox';input.id='patch-'+name;row.append(input,document.createTextNode(label));details.append(row);}
  const info=document.createElement('p');info.className='help';info.textContent='MCP HTTP 默认 127.0.0.1:8001/mcp，需另行启动服务并配置本机连接令牌。stdio 不使用 TCP 端口。';details.append(info);
  const routineHelp=document.createElement('p');routineHelp.className='help';routineHelp.textContent='定时任务读取当前项目的 routines.yaml。先保存开关与模型设置，再启动。关闭窗口会停止本窗口的定时器；独立常驻方式见 README。';details.append(routineHelp);
  for(const[action,label]of [['start','启动定时技能'],['stop','停止定时技能']]){const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent=label;button.onclick=async()=>{button.disabled=true;try{const data=await api('daemon/scheduler/'+action,{});toast(data.status==='stopped'?'定时技能已停止':'已读取 routines.yaml，定时技能已启动');}catch(error){toast(error.message,true);}finally{button.disabled=false;}};details.append(button);}
  document.querySelector('.settings-scroll').append(details);
}
export function fillPatchSettings(config){for(const name of Object.keys(names)){const input=document.getElementById('patch-'+name);input.checked=config['enable_'+name]!==false;input.title=config.active_features?.[name]===false?'当前被配置或环境变量关闭':'已启用';}}
export function patchSettings(){return Object.fromEntries(Object.keys(names).map(name=>['enable_'+name,document.getElementById('patch-'+name).checked]));}
export function watchCompletions(api,toast){
  let saved=[];try{saved=JSON.parse(localStorage.getItem('codedesk-daemon-notices')||'[]');if(!Array.isArray(saved))saved=[];}catch{}
  const seen=new Set(saved);
  async function poll(){try{const data=await api('daemon');for(const notice of data.notifications||[]){if(!seen.has(notice.id))toast('后台任务已完成：'+notice.name);seen.add(notice.id);}try{localStorage.setItem('codedesk-daemon-notices',JSON.stringify([...seen].slice(-100)));}catch{}}catch{} }
  poll();setInterval(poll,5000);
}
export function renderAutotest(card,report){if(!report)return;const badge=document.createElement('p');badge.className='autotest-state '+report.status;badge.textContent='自动测试：'+({passed:'通过',failed:'未通过',skipped:'跳过'})[report.status];card.append(badge);if(report.summary){const summary=document.createElement('pre');summary.className='autotest-summary';summary.textContent=report.summary;card.append(summary);}}
