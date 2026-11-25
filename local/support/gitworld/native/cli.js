import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {World} from '../world.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const world=new World(process.env.WORLD_DIR||path.join(root,'worlds/native-island'));
let result;
try {
 const input=JSON.parse(process.argv[2]||'{"type":"status"}');
 if(input.type==='status'){
  let exists=true;try{await fs.access(path.join(world.root,'.git'));}catch{exists=false;}
  result={ok:true,state:exists?await world.state():null};
 }else if(input.type==='start'){await world.init();result={ok:true,state:await world.state()};}
 else if(input.type==='delete-info'){result={ok:true,state:await world.state(),deletion:await world.deleteInfo(input.name)};}
 else if(input.type==='diff'){result={ok:true,state:await world.state(),diff:await world.diff(input.name)};}
 else result={ok:true,state:await world.action(input.type,input)};
}catch(e){result={ok:false,error:e.message};}
process.stdout.write(JSON.stringify(result)+'\n');
