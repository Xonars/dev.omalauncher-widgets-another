#!/usr/bin/env python3
import os, sys, json, time, uuid, subprocess, pathlib, fcntl, signal, urllib.request, urllib.error, html, copy
os.umask(0o077)
ROOT = pathlib.Path('/root/.local/share/owl-chatgpt')
DATA = ROOT / 'history.json'
EXPORT_DIR = pathlib.Path('/sdcard/Documents/ChatGPT')
ROOT.mkdir(parents=True, exist_ok=True); ROOT.chmod(0o700)
import auth

def read():
    try: return json.loads(DATA.read_text())
    except FileNotFoundError: return {'chats': [], 'busy': False, 'error': '', 'auth': {}}

def atomic(path, text):
    p = path.with_name(path.name+'.'+uuid.uuid4().hex)
    p.write_text(text); p.replace(path)

def save(d): atomic(DATA, json.dumps(d, ensure_ascii=False))

class Locked:
    def __enter__(self):
        self.f = (ROOT / 'lock').open('a'); fcntl.flock(self.f, fcntl.LOCK_EX)
        self.d = read(); return self.d
    def __exit__(self, typ, val, tb):
        if typ is None: save(self.d)
        self.f.close()

def spawn(*args):
    return subprocess.Popen([sys.executable, __file__, *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def alive(pid):
    try: os.kill(int(pid), 0); return True
    except (OSError, TypeError, ValueError): return False

def update_auth(value):
    with Locked() as d: d['auth'] = value

def catalog():
    raw = auth.request(auth.RESOURCE+'/models', token=auth.access())
    if 'models' in raw:
        return [{'id':m['slug'], 'name':m.get('display_name',m['slug'])} for m in raw['models'] if m.get('visibility') == 'list']
    return [{'id':m['id'], 'name':m['id']} for m in raw.get('data', [])]

def worker(cid, job):
    try:
        d = read(); chat = next(c for c in d['chats'] if c['id'] == cid)
        model = d.get('model')
        if not model:
            models = catalog()
            if not models: raise RuntimeError('Нет доступных моделей. Проверьте разрешения аккаунта.')
            model = models[0]['id']
            with Locked() as d: d.update(model=model, models=models)
        body = {'model':model, 'input':[{'role':m['role'],'content':m['text']} for m in chat['messages']], 'store':False, 'stream':True}
        request = urllib.request.Request(auth.RESOURCE+'/responses', data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+auth.access(), 'Content-Type':'application/json','Accept':'text/event-stream','User-Agent':'OwlChatGPT/2.0'})
        answer, completed, last = '', False, 0
        deadline = time.monotonic()+300
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                for raw in response:
                    if time.monotonic() > deadline: raise RuntimeError('Время ожидания ответа истекло.')
                    if not raw.startswith(b'data:'): continue
                    payload = raw[5:].strip()
                    if payload == b'[DONE]': break
                    try: event = json.loads(payload)
                    except ValueError: continue
                    typ = event.get('type')
                    if typ == 'response.output_text.delta':
                        answer += event.get('delta','')
                        if time.monotonic()-last > 0.3:
                            with Locked() as d:
                                if d.get('job') != job: return
                                d['partial'] = answer
                            last = time.monotonic()
                    elif typ == 'response.completed': completed = True
                    elif typ in ('response.failed','response.incomplete','error'):
                        err = event.get('response', {}).get('error') or event.get('error') or {}
                        if isinstance(err, dict): err = err.get('message') or err.get('code')
                        raise RuntimeError(str(err or event.get('message') or 'Ответ не завершён.'))
        except urllib.error.HTTPError as e:
            try:
                err = json.load(e).get('error', {}); msg = err.get('message', '') if isinstance(err, dict) else str(err)
            except Exception: msg = ''
            raise RuntimeError(f'OpenAI HTTP {e.code}: {msg or e.reason}') from None
        if not completed: raise RuntimeError('Соединение прервано до завершения ответа.')
        if not answer.strip(): raise RuntimeError('OpenAI не вернул текст ответа.')
        with Locked() as d:
            if d.get('job') == job:
                c = next(c for c in d['chats'] if c['id'] == cid)
                c['messages'].append({'role':'assistant','text':answer.strip(),'time':time.time()})
                c['updated'] = time.time(); d.update(busy=False,error='',partial='')
    except Exception as e:
        with Locked() as d:
            if d.get('job') == job: d.update(busy=False,error=str(e),partial='')

def offline_records():
    folder = ROOT/'offline'; folder.mkdir(exist_ok=True)
    return [json.loads(p.read_text()) for p in folder.glob('*.json')]

def offline_save(cid):
    with Locked() as d:
        c = next((c for c in d['chats'] if c['id'] == cid), None)
        if c is None: raise RuntimeError('Сначала откройте чат.')
        if d.get('busy'): raise RuntimeError('Дождитесь завершения ответа перед сохранением.')
        c = copy.deepcopy(c); c['saved_at'] = time.time()
    folder = ROOT/'offline'; folder.mkdir(exist_ok=True)
    atomic(folder/(c['id']+'.json'),json.dumps(c,ensure_ascii=False))
    return 'Чат сохранён для чтения офлайн.'

def export(cid, offline=False):
    candidates = offline_records() if offline else read()['chats']
    c = next((c for c in candidates if c['id']==cid),None)
    if not c: raise RuntimeError('Сначала откройте чат.')
    folder = EXPORT_DIR; folder.mkdir(parents=True,exist_ok=True)
    name = 'chat-'+c['id']
    md = '# '+c['title']+'\n\n'+'\n\n'.join('## '+('Вы' if m['role']=='user' else 'ChatGPT')+'\n\n'+m['text'] for m in c['messages'])+'\n'
    content = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(c['title'])+'</title><style>body{max-width:740px;margin:40px auto;padding:0 20px;font:17px/1.6 system-ui;color:#ddd;background:#171717}article{white-space:pre-wrap;overflow-wrap:anywhere;border-bottom:1px solid #444;padding:20px 0}h1{font-size:24px}h2{font-size:13px;color:#aaa}</style><h1>'+html.escape(c['title'])+'</h1>'
    for m in c['messages']: content += '<article><h2>'+('Вы' if m['role']=='user' else 'ChatGPT')+'</h2>'+html.escape(m['text'])+'</article>'
    content += '</html>'
    atomic(folder/(name+'.md'),md); atomic(folder/(name+'.html'),content)
    return 'Сохранено в Документы → ChatGPT:\n'+name+'.html\n'+name+'.md'

def main():
    cmd = sys.argv[1] if len(sys.argv)>1 else 'snapshot'
    if cmd == 'worker': return worker(*sys.argv[2:4])
    if cmd == 'login-worker':
        try: auth.sign_in(update_auth,sys.argv[2] if len(sys.argv)>2 else '')
        except Exception as e: update_auth({'waiting':False,'message':str(e)})
        return
    if cmd == 'snapshot':
        with Locked() as d:
            if d.get('busy') and not alive(d.get('worker')): d.update(busy=False,error='Запрос прерван. Можно отправить сообщение снова.',partial='')
            if d.get('auth',{}).get('waiting') and not alive(d.get('login_pid')): d['auth']={'waiting':False,'message':'Вход прерван. Попробуйте снова.'}
        d.update(auth.public()); d['offline_chats']=offline_records()
        print(json.dumps(d,ensure_ascii=False)); return
    try:
        if cmd == 'send':
            cid,text = sys.argv[2],sys.argv[3].strip()
            if not text: return
            if not auth.public()['logged_in']: raise RuntimeError('Войдите в ChatGPT в настройках приложения.')
            with Locked() as d:
                if d.get('busy'): return
                if len(text)>20000: raise RuntimeError('Сообщение длиннее 20 000 символов.')
                c = next((c for c in d['chats'] if c['id']==cid),None)
                if c is None:
                    c={'id':uuid.uuid4().hex,'title':text[:48].replace('\n',' '),'messages':[],'updated':time.time()}; d['chats'].insert(0,c)
                if sum(len(m['text']) for m in c['messages'])+len(text)>160000: raise RuntimeError('Этот чат слишком длинный. Начните новый.')
                c['messages'].append({'role':'user','text':text,'time':time.time()}); c['updated']=time.time()
                job=uuid.uuid4().hex; d.update(current=c['id'],busy=True,error='',job=job,partial='')
                d['worker']=spawn('worker',c['id'],job).pid
        elif cmd == 'cancel':
            with Locked() as d:
                if d.get('busy') and alive(d.get('worker')): os.killpg(d['worker'],signal.SIGTERM)
                d.update(busy=False,job='',partial='',error='Ответ остановлен.')
        elif cmd == 'login':
            with Locked() as d:
                if d.get('auth',{}).get('waiting') and alive(d.get('login_pid')): return
                d['auth']={'waiting':True,'message':'Готовим вход…'}
                d['login_pid']=spawn('login-worker',sys.argv[2] if len(sys.argv)>2 else '').pid
        elif cmd == 'cancel-login':
            with Locked() as d:
                if d.get('auth',{}).get('waiting') and alive(d.get('login_pid')): os.killpg(d['login_pid'],signal.SIGTERM)
                d['auth']={'waiting':False,'message':'Вход отменён.'}
        elif cmd == 'logout':
            with Locked() as d:
                if d.get('busy') and alive(d.get('worker')): os.killpg(d['worker'],signal.SIGTERM)
                d.update(busy=False,job='',partial='')
            message=auth.sign_out(); update_auth({'waiting':False,'message':message})
            with Locked() as d: d.update(models=[],model='')
        elif cmd == 'select-account':
            auth.select(sys.argv[2])
            with Locked() as d: d.update(models=[],model='')
        elif cmd == 'check': pass
        elif cmd == 'models':
            models=catalog()
            with Locked() as d:
                d['models']=models
                if not any(m['id']==d.get('model') for m in models): d['model']=models[0]['id'] if models else ''
                d['error']=''
        elif cmd == 'model':
            with Locked() as d:
                if any(m['id']==sys.argv[2] for m in d.get('models',[])): d['model']=sys.argv[2]
        elif cmd == 'offline':
            msg=offline_save(sys.argv[2])
            with Locked() as d: d.update(notice=msg,error='')
        elif cmd == 'export':
            msg=export(sys.argv[2], len(sys.argv)>3 and sys.argv[3]=='offline')
            with Locked() as d: d.update(notice=msg,error='')
        elif cmd == 'delete-offline':
            cid=sys.argv[2]
            p=next((p for p in (ROOT/'offline').glob('*.json') if p.stem==cid),None)
            if p: p.unlink()
            with Locked() as d: d['notice']='Офлайн-копия удалена.'
        elif cmd == 'delete':
            with Locked() as d:
                if not d.get('busy'): d['chats']=[c for c in d['chats'] if c['id']!=sys.argv[2]]; d['error']=''
        elif cmd == 'init':
            with Locked() as d: d.update(auth={},logged_in=False,busy=False,error='',partial='',models=[],model='',notice='')
        else: raise ValueError('Unknown command')
    except Exception as e:
        with Locked() as d: d['error']=str(e)

if __name__=='__main__': main()
