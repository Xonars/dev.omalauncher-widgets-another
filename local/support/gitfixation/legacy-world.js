// Adapted from /root/GitWorld/world.js: retain its filesystem/Git engine.
import {World as GitWorld, initial} from './gitworld-core.js';
import episode from './data/episode.json' with {type:'json'};
import fs from 'node:fs/promises';
import path from 'node:path';
export class World extends GitWorld {
 async session(){try{return JSON.parse(await fs.readFile(path.join(this.root,'session.json'),'utf8'));}catch{return {seen:[],journal:[],round:1};}}
 async saveSession(s){const file=path.join(this.root,'session.json');await fs.writeFile(file+'.tmp',JSON.stringify(s));await fs.rename(file+'.tmp',file);}
 async init(){await super.init();await fs.writeFile(path.join(this.root,'.git','info','exclude'),'session.json\nsession.json.tmp\n');await this.saveSession(await this.session());}
 async object(id){if(!Object.hasOwn(initial,id))throw Error('Предмет не найден');return JSON.parse(await fs.readFile(path.join(this.root,'objects',id+'.json'),'utf8'));}
 async set(id,state){const o=await this.object(id);o.state=state;await this.write('objects/'+id+'.json',o);}
 async state(){const s=await super.state();const session=await this.session();const e=s.objects.find(o=>o.id==='event');const raw=await this.git('log','--all','--topo-order','--format=%h|%p|%s');return {...s,seen:session.seen,journal:session.journal,round:session.round,document:session.document||null,ending:session.finished?episode.endings[e.state]||'Проверка продолжается.':'',graph:raw.split('\n').map(l=>{const [hash,parents,message]=l.split('|');return {hash,parents,message};}),task:session.finished?'Проверка завершена. Исследуйте сохранённые версии.':!session.seen.includes('event')?'Осмотрите отчёт 5.3 в Министерстве.':!session.seen.includes('log')?'Сверьте журнал исправлений с отчётом.':!s.branches.includes('memory-'+session.round)?'Зафиксируйте расхождение и сохраните альтернативу.':'Прочтите блокнот в архиве, затем объедините версии.'};}
 async diff(name){await this.ensureBranch(name);const lines=[];for(const id of Object.keys(initial)){const before=JSON.parse(await this.git('show',`${name}:objects/${id}.json`));const after=(await super.state()).objects.find(o=>o.id===id);if(before.state!==after.state)lines.push(`${before.name}\n− ${name}: ${before.states[before.state]}\n+ текущая: ${after.states[after.state]}`);}return lines.join('\n\n');}
 async action(type,data={}){
  const session=await this.session();
  if(type==='interact'){
   if((await this.conflicts()).length)throw Error('Сначала завершите согласование.');
   const o=await this.object(data.id);if(!session.seen.includes(o.id))session.seen.push(o.id);
   session.document={id:o.id,title:o.name,text:episode.documents[o.id][o.state],source:o.id==='event'||o.id==='notebook'?'Опорные посты: 2–3. Игровая адаптация.':'Игровой объект по спецификации.'};
   session.journal.push({title:o.name,text:session.document.text,branch:await this.git('branch','--show-current')});
   await this.saveSession(session);return this.state();
  }
  if(type==='checkpoint'){
   if(!session.seen.includes('event')||!session.seen.includes('log'))throw Error('Сначала прочтите отчёт и журнал.');
   await this.clean();await this.set('log',1);await this.commit('Сверка: 17 исправлений вместо 24');return this.state();
  }
  if(type==='alternative'){
   await this.clean();if((await this.object('log')).state!==1)throw Error('Сначала зафиксируйте расхождение.');
   const branch='memory-'+session.round;
   if((await this.git('branch','--format=%(refname:short)')).split('\n').includes(branch))throw Error('Альтернатива уже существует. Откройте «Версии».');
   const official=await this.git('branch','--show-current');
   await super.action('branch',{name:branch});await this.set('event',2);await this.set('notebook',1);await this.commit('Память: сохранить свидетельство о 12 числе');
   await super.action('switch',{name:official});await this.set('event',1);await this.commit('5.3: официальная корректировка');
   await super.action('switch',{name:branch});session.journal.push({title:'Два продолжения',text:'В альтернативе появилась запись. Переключение версии меняет листы на столе и страницу блокнота.',branch});await this.saveSession(session);return this.state();
  }
  if(type==='resolve'){
   const files=await this.conflicts();if(!files.includes(data.file)||!['official','memory','both'].includes(data.choice))throw Error('Некорректное разрешение.');
   if(data.file!=='objects/event.json')throw Error('Неизвестный сценарный конфликт');
   const o=structuredClone(initial.event);o.state={official:1,memory:2,both:3}[data.choice];await this.write(data.file,o);await this.git('add','--',data.file);if(!(await this.conflicts()).length)await this.git('commit','--no-edit');
   session.finished=true;session.journal.push({title:'Остаток',text:episode.endings[o.state],branch:await this.git('branch','--show-current')});await this.saveSession(session);return this.state();
  }
  if(type==='checkout'){
   await this.clean();const hashes=(await this.state()).graph.map(n=>n.hash);if(!hashes.includes(data.hash))throw Error('Неизвестная фиксация');
   const branches=(await this.state()).branches;let n=1;while(branches.includes('view-'+n))n++;
   await this.git('switch','-c','view-'+n,data.hash);return this.state();
  }
  if(type==='revert'){
   await this.clean();const allowed=(await this.git('log','--format=%h')).split('\n');if(!allowed.includes(data.hash))throw Error('Неизвестная фиксация');
   const parents=(await this.git('rev-list','--parents','-n','1',data.hash)).split(' ');if(parents.length!==2)throw Error('Для отмены выберите обычную фиксацию, не слияние и не корень.');
   try{await this.git('revert','--no-edit',data.hash);}catch{await this.git('revert','--abort');throw Error('Отмена пересекается с поздними изменениями. Мир восстановлен; выберите другую фиксацию.');}return this.state();
  }
  if(type==='restart'){
   if(data.confirm!==true)throw Error('Подтвердите новое прохождение.');await this.clean();const root=(await this.git('rev-list','--max-parents=0','HEAD')).split('\n')[0];let n=session.round+1;const branches=(await this.state()).branches;while(branches.includes('review-'+n))n++;await this.git('switch','-c','review-'+n,root);await this.saveSession({seen:[],journal:[],round:n,finished:false});return this.state();
  }
  if(!['branch','switch','merge','commit','abort'].includes(type))throw Error('Неизвестное действие');
  return super.action(type,data);
 }
}
