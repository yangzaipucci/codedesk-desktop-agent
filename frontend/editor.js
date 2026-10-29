import {basicSetup} from 'codemirror';
import {EditorState, Compartment} from '@codemirror/state';
import {EditorView, keymap} from '@codemirror/view';
import {indentWithTab} from '@codemirror/commands';
import {HighlightStyle, syntaxHighlighting, StreamLanguage} from '@codemirror/language';
import {tags} from '@lezer/highlight';
import {python} from '@codemirror/lang-python';
import {javascript} from '@codemirror/lang-javascript';
import {json} from '@codemirror/lang-json';
import {html} from '@codemirror/lang-html';
import {css} from '@codemirror/lang-css';
import {markdown} from '@codemirror/lang-markdown';
import {powerShell} from '@codemirror/legacy-modes/mode/powershell';
import {yaml} from '@codemirror/legacy-modes/mode/yaml';
import {shell} from '@codemirror/legacy-modes/mode/shell';

const themeSlot=new Compartment();
function language(path){
  const ext=path.split('.').pop().toLowerCase();
  if(ext==='py')return python();
  if(['js','mjs','jsx','ts','tsx'].includes(ext))return javascript({typescript:['ts','tsx'].includes(ext),jsx:['jsx','tsx'].includes(ext)});
  if(ext==='json')return json();if(ext==='html')return html();if(ext==='css')return css();if(ext==='md')return markdown();
  if(ext==='ps1')return StreamLanguage.define(powerShell);if(['yaml','yml'].includes(ext))return StreamLanguage.define(yaml);if(ext==='sh')return StreamLanguage.define(shell);
  return [];
}
function appearance(dark){
  const style=HighlightStyle.define([
    {tag:[tags.keyword,tags.modifier],color:dark?'#c4a3ff':'#7951c2'},
    {tag:[tags.string,tags.regexp],color:dark?'#8bd7ad':'#177b5a'},
    {tag:[tags.number,tags.bool,tags.null],color:dark?'#ffbd83':'#bf6a2d'},
    {tag:tags.comment,color:dark?'#8290a8':'#8a94a5',fontStyle:'italic'},
    {tag:[tags.function(tags.variableName),tags.definition(tags.variableName)],color:dark?'#8fc9ff':'#306eb5'},
    {tag:[tags.typeName,tags.className],color:dark?'#8ce0dc':'#148582'},
    {tag:tags.propertyName,color:dark?'#e4bf94':'#a45f2e'},
  ]);
  return [syntaxHighlighting(style),EditorView.theme({
    '&':{height:'100%',backgroundColor:'var(--editor)',color:'var(--text)',fontSize:'13px'},
    '.cm-scroller':{fontFamily:'Consolas, "Cascadia Code", monospace',lineHeight:'1.8',overflow:'auto'},
    '.cm-content':{padding:'20px 0',caretColor:'var(--accent)'},
    '.cm-gutters':{backgroundColor:'var(--editor)',border:'none',color:'var(--muted)',paddingRight:'12px'},
    '.cm-activeLineGutter,.cm-activeLine':{backgroundColor:'var(--line-highlight)'},
    '&.cm-focused .cm-selectionBackground,.cm-selectionBackground, ::selection':{backgroundColor:dark?'#3a466b':'#dce4ff'},
    '.cm-cursor':{borderLeftColor:'var(--accent)'},
    '.cm-panels':{backgroundColor:'var(--surface)',color:'var(--text)',borderColor:'var(--border)'},
    '.cm-tooltip':{backgroundColor:'var(--surface)',color:'var(--text)',borderColor:'var(--border)'},
    '.cm-foldPlaceholder':{backgroundColor:'var(--soft)',border:'none',color:'var(--accent)'},
  },{dark})];
}
export function createCodeEditor(host,{theme,nonce,onChange,onSelection,onSave,onAsk}){
  const states=new Map();let active=null;
  const view=new EditorView({parent:host,state:EditorState.create({extensions:[basicSetup,EditorView.cspNonce.of(nonce)]})});
  function state(text,path,readOnly=false){return EditorState.create({doc:text,extensions:[basicSetup,language(path),EditorState.readOnly.of(readOnly),EditorView.editable.of(!readOnly),themeSlot.of(appearance(theme==='dark')),EditorView.cspNonce.of(nonce),keymap.of([indentWithTab,{key:'Mod-s',run:()=>{onSave();return true;}},{key:'Mod-l',run:()=>{onAsk();return true;}}]),EditorView.updateListener.of(update=>{if(!active)return;states.set(active,view.state);if(update.docChanged)onChange(active,view.state.doc.toString());if(update.selectionSet||update.docChanged)onSelection();})]});}
  return {
    open(path,text,readOnly=false){if(active)states.set(active,view.state);if(!states.has(path))states.set(path,state(text,path,readOnly));active=path;view.setState(states.get(path));view.focus();onSelection();},
    replace(path,text,readOnly=false){states.set(path,state(text,path,readOnly));if(active===path){view.setState(states.get(path));onSelection();}},
    close(path){states.delete(path);if(active===path)active=null;},
    theme(value){theme=value;for(const[path,s]of states)states.set(path,s.update({effects:themeSlot.reconfigure(appearance(value==='dark'))}).state);if(active)view.setState(states.get(active));},
    selection(){if(!active)return null;const s=view.state.selection.main;return {path:active,text:view.state.sliceDoc(s.from,s.to),start_line:view.state.doc.lineAt(s.from).number,end_line:view.state.doc.lineAt(s.to).number};},
    cursor(){const s=view.state.selection.main;const line=view.state.doc.lineAt(s.head);return {line:line.number,column:s.head-line.from+1};},
    jump(line,column=1){const target=view.state.doc.line(Math.max(1,Math.min(line,view.state.doc.lines)));const offset=Math.min(target.to,target.from+Math.max(0,column-1));view.dispatch({selection:{anchor:offset},effects:EditorView.scrollIntoView(offset,{y:'center'})});view.focus();},
    focus(){view.focus();},view,
  };
}
