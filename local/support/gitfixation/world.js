// GitWorld's real Git engine is retained behind the narrative controller.
import {World as LegacyWorld} from './legacy-world.js';
import scene from './data/scene.json' with {type:'json'};
import story from './data/story.json' with {type:'json'};
import episode from './data/episode.json' with {type:'json'};
import {initial} from './gitworld-core.js';
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

const controls = {
 report:['dismiss','Найти журнал'], insight:['checkpoint','Зафиксировать расхождение'],
 fixed:['dismiss','Пойти в архив'],notebook:['protect','Сохранить личную версию'],
 forked:['official','Посмотреть официальную версию'],officialShift:['dismiss','Проверить страницу'],
 erased:['memory','Вернуться к личной версии'],memoryShift:['dismiss','Открыть блокнот'],
 confirmed:['dismiss','Найти пульт согласования'],comparison:['merge','Попробовать совместить'],
 verdict:['dismiss','Вернуться в отдел']
};
const action=(type,label,extra={})=>({type:'story-'+type,label,...extra});
const pointKey=(x,y)=>`${x},${y}`;
export function navigation(target){
 const tiles=new Map();
 for(const r of [...scene.rooms,...scene.links])for(let y=r.y;y<r.y+r.h;y++)for(let x=r.x;x<r.x+r.w;x++)tiles.set(pointKey(x,y),{x,y});
 for(const o of scene.objects)tiles.delete(pointKey(o.x,o.y));
 for(const f of scene.furniture)for(let y=f.y;y<f.y+f.h;y++)for(let x=f.x;x<f.x+f.w;x++)tiles.delete(pointKey(x,y));
 const queue=[];const dist=new Map();
 for(const [dx,dy] of [[0,1],[0,-1],[1,0],[-1,0]]){const k=pointKey(target.x+dx,target.y+dy);if(tiles.has(k)){const p=tiles.get(k);const n={...p,d:0,nx:p.x,ny:p.y};queue.push(n);dist.set(k,n);}}
 for(let i=0;i<queue.length;i++){const p=queue[i];for(const [dx,dy] of [[0,1],[0,-1],[1,0],[-1,0]]){const k=pointKey(p.x+dx,p.y+dy);if(tiles.has(k)&&!dist.has(k)){const n={...tiles.get(k),d:p.d+1,nx:p.x,ny:p.y};queue.push(n);dist.set(k,n);}}}
 return {tiles:[...tiles.values()],route:[...dist.values()]};
}
export class World extends LegacyWorld {
 async archives(){
  const dir=path.join(this.root,'.git','fixation-sessions');try{const names=(await fs.readdir(dir)).filter(n=>n.endsWith('.json')).sort();return await Promise.all(names.map(async name=>JSON.parse(await fs.readFile(path.join(dir,name),'utf8'))));}catch(e){if(e.code==='ENOENT')return [];throw e;}
 }
 async begin(){
  await this.clean();const s=await this.session();const roots=(await this.git('rev-list','--max-parents=0','HEAD')).split('\n');
  const branches=(await this.git('branch','--format=%(refname:short)')).split('\n');let n=s.round||1;while(branches.includes('shift-'+n)||branches.includes('memory-'+n))n++;
  if(s.seen?.length||s.journal?.length){const dir=path.join(this.root,'.git','fixation-sessions');await fs.mkdir(dir,{recursive:true});await fs.writeFile(path.join(dir,Date.now()+'-'+randomUUID()+'.json'),JSON.stringify({...s,archivedAt:new Date().toISOString()}));}
  await this.git('switch','-c','shift-'+n,roots[0]);
  // Existing snapshots are untouched; current layout is supplied by scene.json.
  await this.saveSession({edition:2,round:n,seen:[],journal:[],phase:'intro',intro:0,screen:'intro',official:'shift-'+n,memory:'memory-'+n,position:scene.spawn});
  return this.state();
 }
 async card(s,base){
  if(!s.screen)return null;
  if(s.screen==='intro')return {...story.intro[s.intro||0],kind:'intro',actions:[action('next',story.intro[s.intro||0].button)]};
  if(s.screen==='quiz')return {kind:'quiz',eyebrow:'СВЕРКА ДВУХ ДОКУМЕНТОВ',title:'Сколько исправлений не подтверждено?',text:'В отчёте заявлено 24 исправления. В журнале вы нашли 17. Сколько записей не хватает?',feedback:s.feedback||'',actions:[7,17,24].map(number=>action('answer',String(number),{number})),aside:'Ошибиться можно. Документы никуда не исчезнут.'};
  if(s.screen==='epilogue'){const end=story.epilogues[s.choice]||story.epilogues.both;return {...end,kind:'ending',eyebrow:'ЭПИЗОД I / СЕМЬ ИСПРАВЛЕНИЙ',aside:end.last,actions:[action('dismiss','Остаться в отделе')]};}
  if(s.screen==='optional')return {kind:'document',...s.optional,actions:[action('dismiss','Вернуться к проверке')]};
  const c=story.cards[s.screen];if(!c)return null;
  let extra={};
  if(s.screen==='verdict'){extra.text=story.resolutions.find(r=>r.id===s.choice).consequence+'\n\n'+story.epilogues[s.choice].text;}
  if(s.screen==='comparison'){
   const rows=[];
   for(const id of ['event','notebook']){const left=JSON.parse(await this.git('show',`${s.official}:objects/${id}.json`));const right=JSON.parse(await this.git('show',`${s.memory}:objects/${id}.json`));rows.push({name:initial[id].name,official:left.states[left.state],memory:right.states[right.state]});}
   extra.rows=rows;
  }
  const [type,label]=controls[s.screen];return {...c,...extra,kind:s.screen==='comparison'?'comparison':'document',actions:[action(type,label)]};
 }
 async state(){
  const base=await super.state();const s=await this.session();const phase=story.phases[s.phase]||story.phases.intro;
  const target=scene.objects.find(o=>o.id===phase.target);const nav=navigation(target);
  const objects=scene.objects.map(o=>({...base.objects.find(b=>b.id===o.id),...o}));
  const eventState=objects.find(o=>o.id==='event').state;
  let version=eventState===1?'Официальная 5.3':eventState===2?'Личная версия':eventState===3?'Две версии рядом':'До корректировки';if(base.branch.startsWith('result-'))version='Ваше решение';
  return {...base,config:{...base.config,...scene},objects,scene,tiles:nav.tiles,route:nav.route,edition:s.edition||1,phase:s.phase||'intro',objective:phase,target,card:await this.card(s,base),introIndex:s.intro||0,version,choice:s.choice||'',savedPosition:s.position||scene.spawn,resolutions:story.resolutions,official:s.official,memory:s.memory,title:story.title,archivedSessions:await this.archives(),hasCampaign:s.edition===2};
 }
 async storyAction(type,data){
  const s=await this.session();
  if(type==='begin')return this.begin();
  if(s.edition!==2)throw Error('Начните новую смену на титульном экране. Прежнее прохождение сохранено.');
  const expect=(...phases)=>{if(!phases.includes(s.phase))throw Error('Сейчас другая задача. Откройте подсказку рядом с целью.');};
  const save=async()=>{await this.saveSession(s);return this.state();};
  if(type==='position'){
   const {tiles}=navigation(scene.objects[0]);if(!tiles.some(p=>p.x===data.px&&p.y===data.py))throw Error('Недоступная точка');s.position={x:data.px,y:data.py};return save();
  }
  if(Number.isInteger(data.px)&&Number.isInteger(data.py)){const nav=navigation(scene.objects[0]);if(nav.tiles.some(p=>p.x===data.px&&p.y===data.py))s.position={x:data.px,y:data.py};}
  if(type==='dismiss'){s.screen=null;return save();}
  if(type==='next'){expect('intro');if(s.intro<2)s.intro++;else{s.phase='report';s.screen=null;}return save();}
  if(type==='answer'){
   expect('compare');if(data.number!==7){s.feedback='Это число уже есть в документах. Нужна разница: 24 − 17. Попробуйте ещё раз.';return save();}
   s.feedback='';s.phase='fix';s.screen='insight';return save();
  }
  if(type==='checkpoint'){
   expect('fix');await this.clean();await this.set('log',1);await this.commit('Сверка: семь исправлений не подтверждены');
   s.phase='archive';s.screen='fixed';s.journal.push({title:'Семь исправлений',text:'В отчёте 24, в журнале 17. Снимок документов сохранён. Это моя первая фиксация.',branch:s.official});return save();
  }
  if(type==='protect'){
   expect('protect');await this.clean();
   await this.git('switch','-c',s.memory);await this.set('event',2);await this.set('notebook',1);await this.commit('Личная версия: я помню 12 число');
   await this.git('switch',s.official);await this.set('event',1);await this.commit('5.3: официальная корректировка завершена');await this.git('switch',s.memory);
   s.phase='official';s.screen='forked';s.journal.push({title:'Отдельное продолжение',text:'Я сохранил запись в личной версии. Официальный отчёт продолжает существовать отдельно.',branch:s.memory});return save();
  }
  if(type==='official'){expect('official');await this.clean();await this.git('switch',s.official);s.phase='observeOfficial';s.screen='officialShift';return save();}
  if(type==='memory'){expect('restore');await this.clean();await this.git('switch',s.memory);s.phase='verifyMemory';s.screen='memoryShift';return save();}
  if(type==='merge'){
   expect('compareVersions');await this.clean();const branches=(await this.state()).branches;let name='result-'+s.round;let i=2;while(branches.includes(name))name='result-'+s.round+'-'+i++;
   // Both source branch tips stay intact; the decision has its own branch.
   await this.git('switch','-c',name,s.memory);s.result=name;s.phase='reconcile';s.screen=null;await this.saveSession(s);
   await super.action('merge',{name:s.official});return this.state();
  }
  if(type==='resolve'){
   expect('reconcile');if(!story.resolutions.some(r=>r.id===data.choice))throw Error('Выберите одно из трёх решений.');
   const file='objects/event.json';if(!(await this.conflicts()).includes(file))throw Error('Конфликт уже разрешён.');
   const o=JSON.parse(await this.git('show',`:2:${file}`));o.state={official:1,memory:2,both:3}[data.choice];await this.write(file,o);await this.git('add','--',file);await this.git('commit','--no-edit');
   s.choice=data.choice;s.phase='exit';s.screen='verdict';s.finished=true;s.journal.push({title:'Решение',text:story.resolutions.find(r=>r.id===data.choice).consequence,branch:s.result});return save();
  }
  if(type==='abort'){
   expect('reconcile');await this.git('merge','--abort');await this.git('switch',s.memory);s.phase='compareVersions';s.screen='comparison';return save();
  }
  throw Error('Неизвестное действие.');
 }
 async interact(data){
  const s=await this.session();if(s.edition!==2)return super.action('interact',data);
  if((await this.conflicts()).length)throw Error('Сначала выберите, как разрешить противоречие.');
  const o=scene.objects.find(o=>o.id===data.id);if(!o)throw Error('Предмет не найден.');
  if(Number.isInteger(data.px)&&Number.isInteger(data.py)){
   if(Math.abs(data.px-o.x)+Math.abs(data.py-o.y)>1)throw Error('Подойдите ближе к предмету.');
   s.position={x:data.px,y:data.py};
  }
  if(!s.seen.includes(o.id))s.seen.push(o.id);
  if(o.id==='event'&&s.phase==='report'){s.phase='ledger';s.screen='report';s.journal.push({title:'Отчёт 5.3',text:'В отчёте 24 исправления. Событие от 12 числа исключено из версии.',branch:s.official});}
  else if(o.id==='log'&&['ledger','compare','fix'].includes(s.phase)){s.screen=s.phase==='fix'?'insight':'quiz';if(s.phase!=='fix')s.phase='compare';}
  else if(o.id==='notebook'&&['archive','protect'].includes(s.phase)){s.phase='protect';s.screen='notebook';}
  else if(o.id==='notebook'&&s.phase==='observeOfficial'){s.phase='restore';s.screen='erased';s.journal.push({title:'Пустая страница',text:'В официальной версии записи нет. Комната та же. Я помню прочитанное.',branch:s.official});}
  else if(o.id==='notebook'&&s.phase==='verifyMemory'){s.phase='terminal';s.screen='confirmed';s.journal.push({title:'Запись вернулась',text:'После переключения вернулась сама запись в блокноте. Теперь две версии можно сравнить.',branch:s.memory});}
  else if(o.id==='terminal'&&['terminal','compareVersions'].includes(s.phase)){s.phase='compareVersions';s.screen='comparison';}
  else if(o.id==='exit'&&['exit','done'].includes(s.phase)){s.phase='done';s.screen='epilogue';}
  else {
   let text='';let title=o.name;
   if(o.id==='card'){text='Арен. Министерство информационной синхронизации.\n\nЗадание на смену: сверка служебного отчёта версии 5.3. На обороте — пустое поле «Особые отметки».';}
   else if(o.id==='colleague'){text=s.phase==='report'?'«Ваш отчёт наверху, в отделе сверки. Сначала прочтите его. Если числа не совпадут — не торопитесь подписывать».':s.phase==='exit'||s.phase==='done'?'«Смена закрыта. Можете идти».\n\nКоллега не спрашивает, что именно вы оставили в отчёте.':'«Сверьте документы. То, что вы помните, — отдельный вопрос».\n\nКоллега возвращается к работе.';}
   else if(o.id==='terminal'){text='На экране: «Нет двух версий для согласования».\n\nСначала закончите сверку и сохраните личную запись. Текущая цель указана над сценой.';}
   else if(o.id==='exit'){text='Смена ещё не закрыта.\n\nВыход останется здесь. Сначала завершите задачу, указанную над сценой.';}
   else{const obj=await this.object(o.id);text=episode.documents[o.id][obj.state];if(o.id==='notebook'&&['intro','report','ledger','compare','fix'].includes(s.phase))text='Личный блокнот. Страница кажется пустой.\n\nСначала стоит закончить обычную сверку отчёта. К собственным записям вы ещё вернётесь.';}
   s.optional={eyebrow:o.id==='colleague'?'РАЗГОВОР':'ОСМОТР',title,text};s.screen='optional';
  }
  await this.saveSession(s);return this.state();
 }
 async action(type,data={}){
  if(type.startsWith('story-'))return this.storyAction(type.slice(6),data);
  if(type==='interact')return this.interact(data);
  const s=await this.session();
  if(s.edition===2&&!['checkout','diff'].includes(type)&&!['done','exit'].includes(s.phase))throw Error('Это действие пока не требуется. Следуйте текущей цели; все инструменты появятся в нужный момент.');
  return super.action(type,data);
 }
}
