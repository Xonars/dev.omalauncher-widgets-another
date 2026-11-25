import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';
const exec = promisify(execFile);
export const initial = {bridge:{id:'bridge',name:'Мост',x:12,y:7,state:0,states:['Разрушен','Восстановлен','Укреплён']},garden:{id:'garden',name:'Сад',x:5,y:5,state:0,states:['Спит','Цветёт','Одичал']},beacon:{id:'beacon',name:'Маяк',x:16,y:4,state:0,states:['Погашен','Зажжён','Синий огонь']}};
export class World {
 constructor(root){this.root=root;this.tail=Promise.resolve();}
 run(fn){const job=this.tail.then(fn);this.tail=job.catch(()=>{});return job;}
 async git(...args){return (await exec('git',args,{cwd:this.root})).stdout.trim();}
 async write(file,data){await fs.writeFile(path.join(this.root,file),JSON.stringify(data,null,2)+'\n');}
 async init(){await fs.mkdir(this.root,{recursive:true});try{await fs.access(path.join(this.root,'.git'));return;}catch{} await this.git('init','-b','main');await this.git('config','user.name','Первый автор');await this.git('config','user.email','author@gitworld.local');await this.git('config','commit.gpgsign','false');await fs.mkdir(path.join(this.root,'objects'));await this.write('world.json',{name:'Остров начала',width:22,height:14,author:'Первый автор',spawn:[4,9],trees:[[3,4],[3,5],[7,3],[8,4],[7,10],[8,11],[17,9],[18,10],[18,3],[4,10]].map(([x,y],id)=>({id,x,y})),river:{x:12,crossingY:7},bounds:{minX:2,maxX:19,minY:2,maxY:11}});for(const [id,obj] of Object.entries(initial))await this.write(`objects/${id}.json`,obj);await this.commit('Первый свет: рождение мира');}
 async conflicts(){return (await this.git('diff','--name-only','--diff-filter=U')).split('\n').filter(Boolean);}
 async state(){const conflicts=await this.conflicts();const objects=[];for(const id of Object.keys(initial)){const file=`objects/${id}.json`; if(conflicts.includes(file)){objects.push(JSON.parse(await this.git('show',`:2:${file}`)));}else objects.push(JSON.parse(await fs.readFile(path.join(this.root,file),'utf8')));}const raw=await this.git('log','-15','--format=%h|%s|%ar');return {config:JSON.parse(await fs.readFile(path.join(this.root,'world.json'),'utf8')),objects,branch:await this.git('branch','--show-current'),branches:(await this.git('branch','--format=%(refname:short)')).split('\n'),dirty:!!(await this.git('status','--porcelain')),conflicts:conflicts.map(f=>({file:f,name:initial[path.basename(f,'.json')]?.name||f})),history:raw.split('\n').map(l=>{const [hash,message,time]=l.split('|');return {hash,message,time};})};}
 async clean(){if((await this.conflicts()).length)throw Error('Сначала разрешите конфликт миров.');if(await this.git('status','--porcelain'))throw Error('Сначала создайте коммит: в мире есть несохранённые изменения.');}
 async commit(message){if(!message?.trim())throw Error('Назовите этот момент.');if((await this.conflicts()).length)throw Error('Сначала разрешите конфликт.');await this.git('add','.');if(!(await this.git('status','--porcelain')))throw Error('Мир ещё не изменился.');await this.git('commit','-m',message.trim());}
 async action(type,data={}){if(type==='interact'){if((await this.conflicts()).length)throw Error('Сначала разрешите конфликт.');if(!Object.hasOwn(initial,data.id))throw Error('Объект не найден');const file=`objects/${data.id}.json`;const obj=JSON.parse(await fs.readFile(path.join(this.root,file),'utf8'));obj.state=(obj.state+1)%obj.states.length;await this.write(file,obj);}
 else if(type==='commit')await this.commit(data.message);
 else if(type==='branch'){await this.clean();if(!/^[a-zA-Z][a-zA-Z0-9_-]{0,39}$/.test(data.name))throw Error('Имя ветки: латинские буквы, цифры, дефис; начало — буква.');await this.git('switch','-c',data.name);}
 else if(type==='switch'){await this.clean();await this.ensureBranch(data.name);await this.git('switch',data.name);}
 else if(type==='merge'){await this.clean();await this.ensureBranch(data.name);try{await this.git('merge','--no-ff','-m',`Слияние мира ${data.name}`,data.name);}catch(e){if(!(await this.conflicts()).length)throw e;}}
 else if(type==='delete'){await this.clean();const info=await this.deleteInfo(data.name);if(info.unmerged && data.force!==true)throw Error(`В ветке ${data.name} есть ${info.commits} коммит(ов), отсутствующих в текущем мире. Подтвердите удаление вместе с ними.`);await this.git('branch',info.unmerged?'-D':'-d','--',data.name);}
 else if(type==='resolve'){const files=await this.conflicts();if(!files.includes(data.file)||!['ours','theirs'].includes(data.choice))throw Error('Некорректное разрешение конфликта');await this.git('checkout',`--${data.choice}`,'--',data.file);await this.git('add','--',data.file);if(!(await this.conflicts()).length)await this.git('commit','--no-edit');}
 else if(type==='abort')await this.git('merge','--abort');
 else throw Error('Неизвестное действие');return this.state();}
 async ensureBranch(name){const branches=(await this.git('branch','--format=%(refname:short)')).split('\n');if(!branches.includes(name))throw Error('Мир не найден');}
 async deleteInfo(name){await this.ensureBranch(name);if(name==='main')throw Error('Основной мир main нельзя удалить.');if(name===await this.git('branch','--show-current'))throw Error('Текущую ветку нельзя удалить. Сначала перейдите в другой мир.');const commits=Number(await this.git('rev-list','--count',`HEAD..${name}`));return {name,commits,unmerged:commits>0};}
 async diff(name){await this.ensureBranch(name);return this.git('diff',name,'--','objects');}
}
