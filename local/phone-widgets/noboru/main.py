#!/usr/bin/env python3
"""Noboru-inspired OWL reader. Original implementation, MangaDex API backend."""
import re, html
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys, os, json, time, uuid, urllib.request, urllib.parse, pathlib, subprocess, fcntl, zipfile
ROOT = pathlib.Path.home()/'.local/share/noboru-owl'
ROOT.mkdir(parents=True, exist_ok=True)
API = 'https://api.mangadex.org'

def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False)); tmp.replace(p)

def load(p, default=None):
    try: return json.loads(p.read_text())
    except (OSError, ValueError): return default

def ident(s):
    if re.fullmatch(r"(?:readmanga|mangachan|mangahub|shonen|mangovaya)-[0-9a-f]{32}",s): return s
    if re.fullmatch(r"remanga-[1-9][0-9]*",s): return s
    return str(uuid.UUID(s))

def request(url, binary=False, text=False, referer=None):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':referer or ('https://remanga.org/' if 'reimg' in urllib.parse.urlparse(url).hostname or 'remanga.org' in urllib.parse.urlparse(url).hostname else urllib.parse.urlparse(url).scheme+'://'+urllib.parse.urlparse(url).netloc+'/')}), timeout=22) as r:
                if binary:
                    if not r.headers.get('Content-Type','').startswith('image/'): raise ValueError('Сервер вернул не изображение')
                    return r.read()
                if text: return r.read().decode("utf-8",errors="replace")
                return json.load(r)
        except Exception:
            if attempt==2: raise
            time.sleep(attempt+1)

import sources
sources.configure(ROOT,request,save,load)

def api(path, params=None):
    data=request(API+path+('?' + urllib.parse.urlencode(params, doseq=True) if params else ''))
    if data.get('result')!='ok': raise ValueError('Ошибка MangaDex')
    return data

def book(x):
    a=x['attributes']; titles=a['title']
    title=titles.get('ru') or titles.get('en') or next(iter(titles.values()), 'Без названия')
    cover=next((r['attributes']['fileName'] for r in x.get('relationships',[]) if r['type']=='cover_art' and 'attributes' in r), '')
    desc=a.get('description',{}); mid=ident(x['id'])
    b={'id':mid,'name':title,'description':(desc.get('ru') or desc.get('en') or '')[:2000], 'cover':f'https://uploads.mangadex.org/covers/{mid}/{cover}.256.jpg' if cover else '', 'status':a.get('status','')}
    save(ROOT/'books'/f'{mid}.json',b)
    return b

def search(q, lang, offset):
    p={'limit':20,'offset':min(int(offset),9980),'includes[]':['cover_art'],'contentRating[]':['safe','suggestive'], 'availableTranslatedLanguage[]':[lang], 'order[followedCount]':'desc','hasAvailableChapters':'true'}
    if q.strip(): p['title']=q.strip()
    d=api('/manga',p)
    return {'items':[book(x) for x in d['data']], 'total':min(d['total'],10000),'offset':int(offset),'query':q,'lang':lang}

def remapi(path, params=None):
    d=request('https://api.remanga.org/api/'+path+('?' + urllib.parse.urlencode(params) if params else ''))
    if 'content' not in d: raise ValueError(d.get('msg') or 'Ошибка ReManga')
    return d

def rembook(x):
    mid='remanga-'+str(int(x['id']))
    cover=(x.get('cover') or {}).get('mid','')
    if cover and not cover.startswith('https://'):
        cover='https://remanga.org'+(cover if cover.startswith('/media/') else '/media/'+cover.lstrip('/'))
    b={'id':mid,'source':'remanga','dir':x['dir'],'name':x.get('main_name') or x.get('rus_name') or x.get('secondary_name'), 'description':html.unescape(re.sub('<[^>]+>','',x.get('description','')))[:2000], 'cover':cover,'chapterCount':x.get('count_chapters'), 'status':{1:'completed',2:'ongoing',3:'hiatus'}.get((x.get('status') or {}).get('id'),'ongoing')}
    save(ROOT/'books'/f'{mid}.json',b); return b

def remsearch(q,lang,offset):
    offset=max(0,int(offset)); params={'count':20,'page':offset//20+1}
    if q.strip(): params['query']=q.strip()
    d=remapi('search/' if q.strip() else 'titles/',params)
    return {'items':[rembook(x) for x in d['content']], 'total':int(d.get('props',{}).get('total_items',offset+len(d['content']))), 'offset':offset,'query':q,'lang':lang,'source':'remanga'}

def russian_search(q, lang, offset):
    """Search Russian providers independently; one failed site cannot erase results."""
    offset=max(0,int(offset)); items=[]; errors=[]; more=False
    providers=['remanga','shonen','mangovaya','mangahub','mangachan','mangadex']
    def fetch_provider(source):
        if source=='remanga': return remsearch(q,'ru',offset)
        if source=='mangadex': return dict(search(q,'ru',offset),source=source)
        return sources.search(source,q,'ru',offset)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(fetch_provider,source):source for source in providers}
        for future in as_completed(pending):
            source=pending[future]
            try:
                result=future.result()
                for b in result['items']:
                    if b.get('chapterCount')==0: continue
                    b.setdefault('source',source);items.append(b)
                more=more or offset+len(result['items'])<result['total']
            except Exception as e: errors.append(source+': '+str(e)[:100])
    items.sort(key=lambda b:(providers.index(b['source']),b['name'].casefold()))
    return {'items':items,'total':offset+len(items)+(1 if more else 0),'offset':offset,
            'query':q,'lang':'ru','source':'all','pageSize':20,'hasNext':more,
            'totalApprox':True,'warnings':errors,
            'error':'Источники недоступны. Скачанные главы доступны во вкладке «Офлайн».' if not items and len(errors)==len(providers) else None}


def natural(value):
    return tuple((0,float(x)) if re.fullmatch(r'\d+(?:\.\d+)?',x) else (1,x.casefold()) for x in re.split(r'(\d+(?:\.\d+)?)',str(value)))

def all_chapters(mid,lang):
    if mid.split('-')[0] in sources.SITES: return sources.chapter_index(mid),1
    if mid.startswith('remanga-'):
        b=load(ROOT/'books'/f'{mid}.json')
        if not b: raise ValueError('Откройте мангу из каталога ReManga')
        d=remapi('titles/'+urllib.parse.quote(b['dir'],safe='')+'/')['content']
        branches=d.get('branches') or [];items=[];seen=set()
        for branch in branches:
            page_number=1
            label=', '.join(p.get('name','') for p in branch.get('publishers',[])) or 'Ветка '+str(branch['id'])
            while True:
                result=remapi('titles/chapters/',{'branch_id':branch['id'],'count':80,'page':page_number,'ordering':'index'})['content']
                fresh=0
                for x in result:
                    cid='remanga-'+str(int(x['id']))
                    if cid in seen:continue
                    seen.add(cid);fresh+=1
                    c={'id':cid,'source':'remanga','number':str(x.get('chapter') or ''),'volume':str(x.get('tome') or '0'), 'name':'Том '+str(x.get('tome') or '0')+' · Глава '+str(x.get('chapter') or '—')+(' · '+x['name'] if x.get('name') else ''), 'group':('Платная · ' if x.get('is_paid') else '')+label,'pages':None,'manga':mid}
                    if x.get('is_paid') and not x.get('is_bought'): c['external']='https://remanga.org/manga/'+b['dir']
                    save(ROOT/'chapters'/cid/'info.json',c);items.append(c)
                if not result:break
                if not fresh:raise ValueError('ReManga повторяет страницу списка — обновите позже')
                page_number+=1
        items.sort(key=lambda x:(natural(x['number']),natural(x['volume']),x['group']))
        return items,len(branches)
    items=[];offset=0
    while True:
        d=api(f'/manga/{mid}/feed',{'limit':500,'offset':offset,'translatedLanguage[]':[lang],'order[volume]':'asc','order[chapter]':'asc','includes[]':['scanlation_group'],'includeExternalUrl':1})
        for x in d['data']:
            a=x['attributes'];group=next((r.get('attributes',{}).get('name','') for r in x['relationships'] if r['type']=='scanlation_group'),'')
            c={'id':x['id'],'name':'Том '+str(a.get('volume') or '0')+' · Глава '+str(a.get('chapter') or '—')+(' · '+a['title'] if a.get('title') else ''),'group':group,'pages':a.get('pages',0),'manga':mid,'external':a.get('externalUrl')}
            save(ROOT/'chapters'/x['id']/'info.json',c);items.append(c)
        offset+=len(d['data'])
        if offset>=d['total']:break
        if not d['data']:raise ValueError('MangaDex вернул неполный список глав')
        if offset>=10000:raise ValueError('MangaDex ограничивает список 10 000 записями для одного языка')
    return items,0

def chapter_listing(mid,lang,offset,query='',revision='0'):
    mid=ident(mid);offset=max(0,int(offset));cache=ROOT/'indexes'/f'{mid}-{lang}.json'
    if lang not in ('ru','en','ja'):raise ValueError('Неподдерживаемый язык')
    data=load(cache)
    if not data or time.time()-data.get('time',0)>600 or data.get('revision')!=str(revision):
        try:
            items,branches=all_chapters(mid,lang)
        except Exception:
            if not data: raise
            data=dict(data,stale=True)
        else:
            data={'items':items,'branches':branches,'time':time.time(),'revision':str(revision)};save(cache,data)
    items=data['items'];total_all=len(items)
    if query.strip():
        q=query.strip().casefold();items=[x for x in items if q in (x['name']+' '+x['group']).casefold()]
    return {'items':items[offset:offset+80],'total':len(items),'allTotal':total_all,'branches':data['branches'],'offset':offset,'manga':mid,'lang':lang,'query':query,'revision':str(revision),'stale':data.get('stale',False)}

def next_chapter(mid, lang, cid):
    mid=ident(mid); cid=ident(cid)
    cache=ROOT/'indexes'/f'{mid}-{lang}.json'
    data=load(cache)
    if not data:
        chapter_listing(mid,lang,0)
        data=load(cache,{})
    items=data.get('items',[])
    current=next((i for i,c in enumerate(items) if c['id']==cid),None)
    if current is None: raise ValueError('Глава не найдена в списке — обновите главы манги')
    candidates=items[current+1:]
    chapter=items[current]
    if chapter.get('number'):
        candidates=[c for c in candidates if (c.get('volume'),c.get('number')) != (chapter.get('volume'),chapter['number'])]
    following=candidates[0] if candidates else None
    if following and following.get('number'):
        same_number=[c for c in candidates if (c.get('volume'),c.get('number')) == (following.get('volume'),following['number'])]
        following=next((c for c in same_number if c.get('group')==chapter.get('group')),following)
    return {'id':cid,'next':following}

def rempages(cid):
    d=remapi('titles/chapters/'+cid.split('-')[1]+'/')['content']
    if d.get('is_paid') and not d.get('is_bought'): raise ValueError('Платная глава доступна на сайте ReManga')
    urls=[]
    for group in d.get('pages') or []:
        for p in (group if isinstance(group,list) else [group]):
            link=p.get('link','')
            if link.startswith('https://'): urls.append(link)
    if not urls: raise ValueError('Нет доступных страниц этой главы')
    result={'id':cid,'urls':urls}
    save(ROOT/'chapters'/cid/'pages.json',result); return result

def pages(cid):
    cid=ident(cid); folder=ROOT/'chapters'/cid
    cached=load(folder/'pages.json')
    if cached and (folder/'complete.json').exists(): return cached
    if cid.split('-')[0] in sources.SITES: return sources.pages(cid)
    if cid.startswith('remanga-'): return rempages(cid)
    d=api('/at-home/server/'+cid)
    ch=d['chapter']; names=ch['dataSaver']
    if not names: raise ValueError('В этой главе нет страниц')
    result={'id':cid,'urls':[d['baseUrl']+'/data-saver/'+ch['hash']+'/'+n for n in names]}
    save(folder/'pages.json',result); return result

def page(cid, index):
    cid=ident(cid); index=int(index); folder=ROOT/'chapters'/cid
    ps=load(folder/'pages.json') or pages(cid)
    if index<0 or index>=len(ps['urls']): raise ValueError('Нет такой страницы')
    target=folder/f'{index+1:04d}.jpg'
    if not target.exists():
        try: data=request(ps['urls'][index],True,referer=ps.get('referer'))
        except Exception:
            ps=pages(cid); data=request(ps['urls'][index],True,referer=ps.get('referer'))
        from PIL import Image
        import io
        im=Image.open(io.BytesIO(data)); im.verify()
        tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.part'); tmp.write_bytes(data); tmp.replace(target)
    from PIL import Image
    with Image.open(target) as im: ratio=im.height/im.width
    return {'id':cid,'index':index,'path':str(target),'ratio':ratio,'count':len(ps['urls'])}

def webtoon(cid, start):
    """Emit cached page metadata as images arrive; OWL lazily builds visible rows."""
    cid=ident(cid); ps=load(ROOT/'chapters'/cid/'pages.json') or pages(cid)
    start=max(0,min(int(start),len(ps['urls'])-1))
    result={'id':cid,'start':start,'items':[],'total':len(ps['urls']),'done':False}
    def emit(): print(json.dumps(result,ensure_ascii=False),flush=True)
    # Publish cached pages together so opening an offline chapter has no empty frame.
    next_index=start
    while next_index < len(ps['urls']) and (ROOT/'chapters'/cid/f'{next_index+1:04d}.jpg').exists():
        result['items'].append(page(cid,next_index))
        next_index+=1
    if result['items']: emit()
    for i in range(next_index,len(ps['urls'])):
        try:
            result['items'].append(page(cid,i))
            emit()
        except Exception as e:
            result['error']='Страница '+str(i+1)+': '+str(e)[:180]
            emit(); return
    result['done']=True
    emit()

def library():
    items=[]
    for p in (ROOT/'chapters').glob('*/complete.json'):
        c=load(p.parent/'info.json',{}); b=load(ROOT/'books'/f'{c.get("manga")}.json',{})
        if c: items.append(dict(c,book=b,archive=str(p.parent/'chapter.cbz')))
    jobs=[]
    for p in (ROOT/'chapters').glob('*/job.json'):
        j=load(p,{})
        if j: jobs.append(j)
    return {'items':items,'jobs':sorted(jobs,key=lambda x:-x.get('time',0))[:12],'path':str(ROOT/'chapters'),'downloaded':[x['id'] for x in items],'covers':{p.stem:str(p) for p in (ROOT/'covers').glob('*.image')}}

def download(cid):
    cid=ident(cid); folder=ROOT/'chapters'/cid; folder.mkdir(parents=True,exist_ok=True)
    with open(folder/'download.lock','w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        info=load(folder/'info.json',{})
        def status(text,n=0,total=0): save(folder/'job.json',{'id':cid,'name':info.get('name',cid),'status':text,'done':n,'total':total,'time':time.time()})
        try:
            status('Получение страниц'); ps=pages(cid); total=len(ps['urls'])
            for i in range(total):
                status('Скачивание',i,total); page(cid,i)
            target=folder/'chapter.cbz'; tmp=folder/'chapter.cbz.part'
            with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED) as z:
                for i in range(total): z.write(folder/f'{i+1:04d}.jpg',f'{i+1:04d}.jpg')
            tmp.replace(target); save(folder/'complete.json',{'pages':total}); status('Скачано',total,total)
        except Exception as e: status('Ошибка: '+str(e)[:160])

def main():
    cmd,*args=sys.argv[1:]
    if cmd=='enqueue-book':
        mid=ident(args[0])
        subprocess.Popen([sys.executable,__file__,'download-book',mid],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return {'ok':True}
    if cmd=='download-book':
        listing=chapter_listing(args[0],'ru',0)
        index=load(ROOT/'indexes'/f'{ident(args[0])}-ru.json',{})
        for c in index.get('items',[]):
            if not c.get('external'): download(c['id'])
        return {'ok':True}
    if cmd=='search':
        source=args.pop() if len(args)==4 else 'mangadex'
        if source=='all': return russian_search(*args)
        if source in sources.SITES: return sources.search(source,*args)
        if source=='remanga': return remsearch(*args)
        return dict(search(*args),source='mangadex')
    if cmd=='chapters': return chapter_listing(*args)
    if cmd=='next-chapter': return next_chapter(*args)
    if cmd=='pages': return pages(*args)
    if cmd=='page': return page(*args)
    if cmd=='webtoon': webtoon(*args); return None
    if cmd=='library': return library()
    if cmd=='download':
        cid=ident(args[0]); folder=ROOT/'chapters'/cid; folder.mkdir(parents=True,exist_ok=True)
        subprocess.Popen([sys.executable,__file__,'worker',cid],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return {'ok':True}
    if cmd=='worker': download(*args); return {'ok':True}
    raise ValueError('Неизвестная команда')

if __name__=='__main__':
    try:
        result=main()
        if result is not None: print(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        detail=str(e)[:220]
        if isinstance(e,urllib.error.HTTPError) and e.code==300:
            detail='Источник отклонил изображение или вернул недоступную страницу. Попробуйте другой перевод или источник.'
        print(json.dumps({'error':'Не удалось загрузить: '+detail},ensure_ascii=False))
