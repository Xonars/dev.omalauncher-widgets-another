"""Russian site adapters informed by Creckeryop/NOBORU-parsers; current HTML/API.
No downloaded Lua or JavaScript is executed.
"""
import re, json, hashlib, urllib.parse, urllib.request, ast, time, io
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
SITES={'mangachan':('MangaChan','https://im.manga-chan.me'), 'readmanga':('ReadManga','https://readmanga.me'), 'mangahub':('MangaHub RU','https://mangahub.ru'), 'shonen':('Dreamy Manga','https://www.shonen.mobile/ru'), 'mangovaya':('Манговая','https://mangovaya.ru')}

def configure(root,request,save,load):
    global ROOT,fetch,write,read
    ROOT,fetch,write,read=root,request,save,load

def uid(source,url): return source+'-'+hashlib.sha256(url.encode()).hexdigest()[:32]
def absolute(base,url): return urllib.parse.urljoin(base,url)
def soup(url):
    try: text=fetch(url,text=True)
    except Exception:
        # Retry a stale intermediary response with a fresh ordinary GET.
        text=fetch(url+('&' if '?' in url else '?')+'owl=1',text=True)
    return BeautifulSoup(text,'html.parser')
def clean(node): return node.get_text(' ',strip=True) if node else ''
def remember(source,url,name,cover=''):
    b={'id':uid(source,url),'source':source,'url':url,'name':name,'cover':cover,'description':'','status':'ongoing'}
    write(ROOT/'books'/f'{b["id"]}.json',b);return b

def local_cover(book):
    url=book.get('cover') or ''
    if not url: return book
    path=ROOT/'covers'/(book['id']+'.image')
    failure=ROOT/'covers'/(book['id']+'.failed.json')
    if not path.exists() and time.time()-read(failure,{}).get('time',0)>600:
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':SITES[book['source']][1]+'/'})
            with urllib.request.urlopen(req,timeout=4) as r: data=r.read(4*1024*1024)
            from PIL import Image
            Image.open(io.BytesIO(data)).verify()
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix('.part');temp.write_bytes(data);temp.replace(path)
        except Exception:write(failure,{'time':time.time()})
    book=dict(book,cover=str(path) if path.exists() else '')
    write(ROOT/'books'/f'{book["id"]}.json',book)
    return book

def search(source,q,lang,offset):
    label,base=SITES[source];offset=max(0,int(offset));items=[];total=None
    if source=='readmanga' and q:
        d=fetch(base+'/api/catalog/search?'+urllib.parse.urlencode({'q':q,'offset':offset,'sortType':'rate'}))
        for x in d.get('list',[])[:20]:
            url=absolute(base,x.get('url') or x.get('link') or '/'+x['elementId']['linkName'])
            cover=x.get('picUrl') or x.get('image') or x.get('cover') or ''
            if isinstance(cover,dict):cover=cover.get('original') or cover.get('preview') or ''
            items.append(remember(source,url,x.get('russian') or x.get('name') or x.get('title'),absolute(base,cover)))
        total=d.get('total',len(items))
    else:
        if source=='mangachan':
            params={'do':'search','subaction':'search','search_start':1,'full_search':0,'result_from':offset+1,'result_num':20,'story':q,'need_sort_date':'false'}
            url=base+'/?'+urllib.parse.urlencode({'do':'search','subaction':'search','story':q} if offset==0 else params) if q else base+'/mostfavorites?offset='+str(offset)
        elif source=='mangahub':
            url=base+('/search/title?'+urllib.parse.urlencode({'query':q,'page':offset//20+1}) if q else '/explore?page='+str(offset//48+1))
        elif source=='shonen':
            url=base+('/?'+urllib.parse.urlencode({'s':q}) if q else '/')
        elif source=='mangovaya':
            url=base+('/search?'+urllib.parse.urlencode({'q':q}) if q else '/catalog')
        else:url=base+'/list?sortType=rate&offset='+str(offset)
        doc=soup(url)
        if source=='mangachan':
            for row in doc.select('.content_row'):
                a=row.select_one('a.title_link, .manga_row1 h2 a[href]');im=row.select_one('.manga_images img')
                if a:items.append(remember(source,absolute(base,a['href']),clean(a),absolute(base,im.get('src','')) if im else ''))
        elif source=='mangahub':
            for row in doc.select('.item-grid'):
                a=row.select_one('a.fw-medium');im=row.select_one('img')
                if a:items.append(remember(source,absolute(base,a['href']),clean(a),absolute(base,im.get('src','')) if im else ''))
        elif source=='shonen':
            for row in doc.select('.series-card'):
                a=row.select_one('a.series-card-link'); title=row.select_one('.series-card-title')
                style=(row.select_one('.series-card-thumb') or {}).get('style','')
                cover=(re.search(r"url\(['\"]?([^'\")]+)",style) or [None,''])[1]
                if a and title:items.append(remember(source,absolute(base,a['href']),clean(title),absolute(base,cover)))
        elif source=='mangovaya':
            for row in doc.select('.manga-card[data-slug]'):
                title=row.select_one('.manga-title'); im=row.select_one('img')
                if title:
                    url=base+'/manga/'+row['data-slug']
                    items.append(remember(source,url,clean(title),absolute(base,im.get('src','')) if im else ''))
        else:
            for a in doc.select('a.non-hover'):
                im=a.select_one('img')
                if im:items.append(remember(source,absolute(base,a['href']),im.get('title') or im.get('alt') or clean(a),absolute(base,im.get('data-original') or im.get('src',''))))
        if not items and not q:raise ValueError(label+': каталог не распознан; сайт мог изменить разметку')
        # HTML sites expose a next-page link, not a reliable grand total.
        nextpage=doc.select_one('a[rel="next"],.pagination .next a,a.next')
        if source=='readmanga': nextpage=len(items)>=20
        if source=='mangahub': nextpage=len(items)>=20
        if source=='mangachan':nextpage=len(items)>=20
        if source in ('shonen','mangovaya'):nextpage=False
        total=offset+len(items)+(1 if nextpage else 0)
    if q and source=='mangachan': items.sort(key=lambda b: (q.casefold() not in b['name'].casefold(),len(b['name'])))
    with ThreadPoolExecutor(max_workers=8) as executor: items=list(executor.map(local_cover,items))
    return {'items':items,'total':total,'offset':offset,'query':q,'lang':lang,'source':source,'totalApprox':source!='readmanga' or not q,'pageSize':48 if source=='mangahub' and not q else 70 if source=='readmanga' and not q else 20}

def chapter_index(mid):
    b=read(ROOT/'books'/f'{mid}.json');source=b['source'];label,base=SITES[source]
    url=b['url']+('/chapters' if source=='mangahub' else '')
    doc=soup(url);items=[];seen=set()
    if source=='shonen':
        holder=doc.select_one('.chapters-list[data-category]')
        if not holder:raise ValueError(label+': список глав не распознан')
        category=holder['data-category']
        nonce_match=re.search(r'"nonce"\s*:\s*"([^"]+)"',str(doc));nonce=nonce_match.group(1) if nonce_match else ''
        current=doc;page_number=1
        while True:
            for a in current.select('a.chapter-link'):
                href=absolute(base,a['href']).split('?')[0].rstrip('/');name=clean(a.select_one('.chapter-title') or a)
                if href in seen or not name:continue
                seen.add(href);cid=uid(source,href)
                c={'id':cid,'source':source,'url':href,'name':name,'group':label+' · RU','pages':None,'manga':mid}
                write(ROOT/'chapters'/cid/'info.json',c);items.append(c)
            button=current.select_one('#load-more-series') if page_number==1 else None
            if page_number==1 and not button:break
            page_number+=1
            body=urllib.parse.urlencode({'action':'mangaverse_load_more','nonce':nonce,'page':page_number,'type':'series','category_id':category,'order':'desc','lang':'ru'}).encode()
            req=urllib.request.Request('https://www.shonen.mobile/wp-admin/admin-ajax.php',data=body,headers={'User-Agent':'Mozilla/5.0','Referer':url})
            with urllib.request.urlopen(req,timeout=22) as response: payload=json.load(response)
            if not payload.get('success'):break
            current=BeautifulSoup(payload.get('data',{}).get('html',''),'html.parser')
            if not payload.get('data',{}).get('has_more'):
                # Consume this final page, then stop on the next iteration.
                for a in current.select('a.chapter-link'):
                    href=absolute(base,a['href']).split('?')[0].rstrip('/');name=clean(a.select_one('.chapter-title') or a)
                    if href in seen or not name:continue
                    seen.add(href);cid=uid(source,href)
                    c={'id':cid,'source':source,'url':href,'name':name,'group':label+' · RU','pages':None,'manga':mid}
                    write(ROOT/'chapters'/cid/'info.json',c);items.append(c)
                break
        items.reverse()
        if not items:raise ValueError(label+': главы не найдены')
        return items
    selector={'mangachan':'.manga2 a[href*="/online/"]','readmanga':'td a[href*="/vol"]','mangahub':'a[href*="/read/"]','shonen':'a.chapter-link','mangovaya':'a.chapter-item[href*="/read/"]'}[source]
    for a in doc.select(selector):
        href=absolute(base,a['href']).split('?')[0].rstrip('/')
        name=clean(a)
        if href in seen or not name or name=='Начать читать':continue
        seen.add(href);cid=uid(source,href)
        c={'id':cid,'source':source,'url':href,'name':name,'group':label+' · RU','pages':None,'manga':mid}
        if source=='mangovaya':c['external']=href
        write(ROOT/'chapters'/cid/'info.json',c);items.append(c)
    items.reverse()
    # Do not silently accept the first HTML page of a chapter list.
    nextpage=doc.select_one('a[rel="next"]')
    while nextpage:
        target=absolute(url,nextpage['href'])
        if target in seen:break
        seen.add(target);doc=soup(target)
        for a in doc.select(selector):
            href=absolute(base,a['href']).split('?')[0].rstrip('/');name=clean(a)
            if href in seen or not name:continue
            seen.add(href);cid=uid(source,href)
            c={'id':cid,'source':source,'url':href,'name':name,'group':label+' · RU','pages':None,'manga':mid}
            if source=='mangovaya':c['external']=href
            write(ROOT/'chapters'/cid/'info.json',c);items.append(c)
        nextpage=doc.select_one('a[rel="next"]')
    if not items:
        text=clean(doc)
        if re.search(r'Главы\s*0|Глав нет|нет глав',text,re.I):return []
        raise ValueError(label+': главы не найдены — возможны ограничение доступа или изменение разметки')
    return items

def pages(cid):
    c=read(ROOT/'chapters'/cid/'info.json');source=c['source'];label,base=SITES[source]
    text=fetch(c['url']+('?mtr=1&_owl='+str(int(time.time())) if source=='readmanga' else ''),text=True);urls=[]
    if source=='mangachan':
        match=re.search(r'"fullimg"\s*:\s*(\[.*?\])',text,re.S)
        if match:urls=json.loads(re.sub(r',\s*\]',']',match[1]))
    elif source=='readmanga':
        match=re.search(r'rm_h\.(?:readerInit|init)\([^\[]*(\[\[.*?\]\])',text,re.S)
        if match:
            # Literal arrays only. Never eval site JavaScript.
            rows=ast.literal_eval(match[1])
            urls=[r[0]+r[2] for r in rows]
    elif source=='shonen':
        doc=BeautifulSoup(text,'html.parser')
        urls=[im.get('data-src') or im.get('src') for im in doc.select('.entry-content figure img')]
    elif source=='mangovaya':
        raise ValueError('Манговая: чтение доступно на сайте')
    else:
        # The reader stores page objects as HTML-escaped JSON in a component attribute.
        import html
        decoded=html.unescape(text).replace('\\/','/')
        urls=re.findall(r'"src"\s*:\s*"(https?://[^"<>]+)"',decoded)
        if not urls:
            doc=BeautifulSoup(text,'html.parser')
            urls=[im.get('data-src') or im.get('src') for im in doc.select('reader-scan img,.reader img,.page-image img,img.page-image')]
    urls=list(dict.fromkeys(absolute(base,u) for u in urls if u))
    if not urls:raise ValueError(label+': нет доступных изображений этой главы')
    result={'id':cid,'urls':urls,'referer':c['url']}
    write(ROOT/'chapters'/cid/'pages.json',result);return result
