const $=id=>document.getElementById(id);
const token=document.querySelector('meta[name=session-token]').content;
let state,selected=null,lastDetail='',toastTimer;
const labels={queued:'排队中',running:'执行中',completed:'已完成',awaiting_approval:'等待批准',paused:'已暂停',pausing:'等待暂停',cancelled:'已取消',error:'执行失败',timeout:'已超时',interrupted:'已中断'};
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5000);}
async function api(path,body){const r=await fetch(path,{headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},method:body===undefined?'GET':'POST',...(body===undefined?{}:{body:JSON.stringify(body)})});const value=await r.json();if(!r.ok)throw Error(value.error||value.detail||'请求失败');return value;}
function guard(fn){return async e=>{e?.preventDefault();try{await fn(e);}catch(error){toast(error.message);}};}
function bubble(text,who='assistant'){const div=document.createElement('div');div.className='bubble '+who;div.textContent=text;$('conversation').append(div);$('conversation').scrollTop=$('conversation').scrollHeight;}
async function send(text){bubble(text,'user');const r=await api('/api/remote/message',{user:$('user').value.trim(),message_id:crypto.randomUUID(),text});bubble(r.reply);if(r.job_id)selected=r.job_id;await refresh();return r;}
function showTab(name){for(const b of document.querySelectorAll('nav button'))b.classList.toggle('active',b.dataset.tab===name);for(const name2 of ['tasks','projects','connect'])$(name2+'Tab').hidden=name2!==name;}
for(const b of document.querySelectorAll('nav button'))b.addEventListener('click',()=>showTab(b.dataset.tab));
$('refresh').onclick=guard(()=>refresh());
$('messageForm').onsubmit=guard(async()=>{const text=$('message').value.trim();if(!text)return;await send(text);$('message').value='';});
$('help').onclick=guard(()=>send('帮助'));
$('user').onchange=guard(()=>refresh());
$('projectSelect').onchange=guard(async()=>{try{await send('切换 '+$('projectSelect').value);}finally{await refresh();}});
$('usersForm').onsubmit=guard(async()=>{await api('/api/remote/config',{users:$('allowedUsers').value.split(/[,，\n]/).map(x=>x.trim()).filter(Boolean)});toast('身份已保存');await refresh();});
$('accepting').onchange=guard(async()=>{await api('/api/remote/config',{accepting:$('accepting').checked});await refresh();});
$('projectForm').onsubmit=guard(async()=>{await api('/api/remote/project',{name:$('projectName').value.trim(),path:$('projectPath').value.trim(),mode:$('projectMode').value,rules:$('projectRules').value});toast('项目已保存');await refresh();});
$('connectForm').onsubmit=guard(async()=>{const secret=$('botSecret').value;$('botSecret').value='';await api('/api/remote/connect',{bot_id:$('botId').value.trim(),secret});toast('正在连接，请查看真实连接状态');await refresh();});
$('disconnect').onclick=guard(async()=>{await api('/api/remote/disconnect',{});await refresh();});
$('attachment').onchange=guard(async()=>{const file=$('attachment').files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('单个附件最多 8 MiB');const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});await api('/api/remote/attachment',{user:$('user').value.trim(),name:file.name,data});bubble('已暂存附件：'+file.name+'。继续发送要求或输入“开始”。');$('attachment').value='';});
async function action(name,text=''){const r=await api('/api/remote/action',{id:selected,action:name,text});toast(r.reply);lastDetail='';await refresh();}
async function download(index){const r=await fetch('/api/remote/artifact?id='+encodeURIComponent(selected)+'&index='+index,{headers:{Authorization:'Bearer '+token}});if(!r.ok){const v=await r.json();throw Error(v.error||'下载失败');}const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=state.jobs.find(j=>j.id===selected).artifacts[index].name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
function renderDetail(job){const signature=JSON.stringify(job);if(signature===lastDetail)return;lastDetail=signature;$('selectedId').textContent=job.id;
const terminal=['completed','cancelled','error','timeout','interrupted'].includes(job.status);
let actions='';if(job.status==='awaiting_approval')actions+='<button data-action="approve" class="primary">批准执行此任务</button>';if(['running','queued'].includes(job.status))actions+='<button data-action="pause">在下一轮暂停</button>';if(['paused','pausing'].includes(job.status))actions+='<button data-action="resume">继续执行</button>';if(!terminal)actions+='<button data-action="cancel">取消任务</button>';
$('detailBody').className='';$('detailBody').innerHTML='<div class="detail-meta">'+escape(job.project)+' · '+escape(job.channel==='local'?'本地联调':'企业微信')+' · '+escape(job.user)+' · <span class="badge '+job.status+'">'+escape(labels[job.status]||job.status)+'</span><br>'+escape(job.workspace)+'</div><pre>'+escape(job.prompt)+'</pre><div class="detail-actions">'+actions+'</div>'+(!terminal?'<form id="appendForm"><div class="row"><input id="appendText" placeholder="补充要求（修改模式需重新批准；运行中先取消）"><button>追加</button></div></form>':'')+
'<p class="muted">'+(job.updates.length?'追加记录：'+job.updates.map(u=>escape(u.text)+'（'+(u.applied?'已注入执行':'待执行边界处理')+'）').join('；'):'执行模式：'+(job.mode==='ask'?'只读问答':'允许修改和命令执行'))+'</p>'+
(job.result?'<pre>'+escape(job.result)+'</pre>':'')+(job.error?'<p class="error-text">'+escape(job.error)+'</p>':'')+job.artifacts.map((a,i)=>'<button class="artifact" data-download="'+i+'">↓ '+escape(a.name)+' · '+a.size+' B</button>').join('');
for(const b of $('detailBody').querySelectorAll('[data-action]'))b.onclick=guard(()=>action(b.dataset.action));for(const b of $('detailBody').querySelectorAll('[data-download]'))b.onclick=guard(()=>download(Number(b.dataset.download)));if($('appendForm'))$('appendForm').onsubmit=guard(()=>action('append',$('appendText').value));}
async function refresh(){const user=$('user').value.trim();state=await api('/api/remote?user='+encodeURIComponent(user));$('queuedCount').textContent=state.jobs.filter(j=>['queued','awaiting_approval'].includes(j.status)).length;$('runningCount').textContent=state.jobs.filter(j=>['running','pausing','paused'].includes(j.status)).length;$('completedCount').textContent=state.jobs.filter(j=>j.status==='completed').length;$('projectCount').textContent=state.projects.length;
$('connectionText').textContent=({disconnected:'未连接企业微信',connecting:'正在连接',connected:'企业微信已连接',reconnecting:'断线重连中',error:'连接失败'})[state.connection]||state.connection;$('connectionDot').classList.toggle('online',state.connection==='connected');$('connectionError').textContent=state.error;$('accepting').checked=state.config.accepting;
if(document.activeElement!==$('allowedUsers'))$('allowedUsers').value=state.config.users.join(', ');if(document.activeElement!==$('botId'))$('botId').value=state.config.bot_id||'';
const options=state.projects.map(p=>'<option value="'+escape(p.name)+'">'+escape(p.name)+'</option>').join('');if($('projectSelect').dataset.options!==options){const old=$('projectSelect').value;$('projectSelect').innerHTML=options||'<option value="">请先登记项目</option>';$('projectSelect').dataset.options=options;if(state.projects.some(p=>p.name===old))$('projectSelect').value=old;}if(state.current_project)$('projectSelect').value=state.current_project;
$('projectList').innerHTML=state.projects.map(p=>'<div class="project-item"><b>'+escape(p.name)+'</b><p>'+escape(p.path)+'</p><small>'+(p.mode==='ask'?'只读问答':'修改与命令 · 需批准')+'</small><p>'+escape(p.rules||'未设置额外规则')+'</p><button data-edit="'+escape(p.name)+'">编辑</button></div>').join('')||'<div class="empty">尚未登记项目</div>';for(const b of $('projectList').querySelectorAll('[data-edit]'))b.onclick=()=>{const p=state.projects.find(p=>p.name===b.dataset.edit);$('projectName').value=p.name;$('projectPath').value=p.path;$('projectMode').value=p.mode;$('projectRules').value=p.rules;};
$('jobList').innerHTML=state.jobs.map(j=>'<button class="job '+(j.id===selected?'selected':'')+'" data-id="'+j.id+'"><div class="job-top"><span>'+escape(j.project)+' · '+(j.channel==='local'?'本地联调':'企业微信')+'</span><span class="badge '+j.status+'">'+escape(labels[j.status]||j.status)+'</span></div><p>'+escape(j.prompt)+'</p><small>'+j.id+' · '+new Date(j.created_at).toLocaleString()+'</small></button>').join('')||'<div class="empty">还没有任务<br><small>从左侧发送一个需求开始</small></div>';for(const b of $('jobList').querySelectorAll('[data-id]'))b.onclick=guard(async()=>{selected=b.dataset.id;lastDetail='';await refresh();});
const job=state.jobs.find(j=>j.id===selected);if(job)renderDetail(job);
$('deliveries').innerHTML=state.outbox.slice().reverse().slice(0,10).map(m=>'<div class="delivery-item"><span>'+m.job_id+' · '+escape(({local:'已生成本地结果（未发送企微）',sent:'企微已确认接收',pending:'等待发送',sending:'发送中',failed:'发送失败',uncertain:'回执不确定',blocked:'身份已解绑，停止交付'})[m.status]||m.status)+(m.error?' · '+escape(m.error):'')+'</span>'+(['failed','uncertain'].includes(m.status)?'<button data-retry="'+m.id+'">核对后重发消息</button>':'')+'</div>').join('')||'暂无交付记录';for(const b of $('deliveries').querySelectorAll('[data-retry]'))b.onclick=guard(async()=>{await api('/api/remote/retry-delivery',{id:b.dataset.retry});await refresh();});
$('demoBanner').hidden=!state.demonstration;
}
guard(refresh)();setInterval(()=>{if(!document.hidden)refresh().catch(e=>{$('connectionText').textContent='本机服务不可达';});},1500);

if (window.parent !== window) {
  for (const link of document.querySelectorAll('a[href="/"]')) {
    link.addEventListener('click', event => {
      event.preventDefault();
      window.parent.postMessage('codedesk:close-remote', location.origin);
    });
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !event.isComposing) {
      event.preventDefault();
      window.parent.postMessage('codedesk:close-remote', location.origin);
    }
  });
}
