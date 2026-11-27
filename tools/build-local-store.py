#!/usr/bin/env python3
"""Build reviewed local collection entries without changing installed phone files."""
from pathlib import Path
import hashlib, io, json, re, sys, zipfile
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'local/phone-widgets'
BASE='https://xonars.github.io/dev.omalauncher-widgets-another/'
DEPENDENCIES={
 '70-apk-share.owl':['apk-share'], '76-oma-update-app.owl':['oma-update','apk-share'],
 '82-key-bindings.owl':['key-bindings'], '83-themes.owl':['theme-catalog'],
 '65-cava-terminal.owl':['terminal-support','cava'],
 'market-justqrius-matrix-terminal.owl':['terminal-support','matrix-terminal'],
 'noboru.owl':['noboru'], 'quiet-reader.owl':['quiet-reader'],
 'pinterest-wallswap.owl':['pinterest-wallswap'],
 'market-app-simonschubert-linux-commands.owl':['linux-commands','linux-commands-data'],
 '84-oma-another-features-app.owl':['oma-another-features'],
 '85-oma-another-features.owl':['oma-another-features'],
 'browser.owl':['browser'], 'ghost-letters.owl':['ghost-letters'],
 'lofi-radio.owl':['lofi-radio'], 'lofi-radio-widget.owl':['lofi-radio'],
}
SLUGS={'70-apk-share.owl':'apk-share','76-oma-update-app.owl':'oma-update','81-developer-guide.owl':'developer-guide','82-key-bindings.owl':'key-bindings','83-themes.owl':'themes','55-system-panel.owl':'system-panel','65-cava-terminal.owl':'cava-terminal','noboru.owl':'noboru','quiet-reader.owl':'quiet-reader','pinterest-wallswap.owl':'pinterest-wallswap','cassette.owl':'cassette','chess-app.owl':'chess-app','apk-maker-app.owl':'apk-maker-app'}
SLUGS.update({'84-oma-another-features-app.owl':'oma-another-features','85-oma-another-features.owl':'oma-another-features-widget','lofi-radio-widget.owl':'lofi-radio-widget','market-jonasallencodes-digital-clock-copy-fb01f1c2-da15-466e-91fa-598dfb50097f.owl':'digital-clock-wide'})
SUPPORT = {
 '76-oma-update-app.owl': ('oma-updater', '/root/.local/share/oma-updater'),
 'chatgpt.owl': ('owl-chatgpt', '/root/.local/bin/owl-chatgpt'),
 'fixation.owl': ('gitfixation', '/root/GitFixation'),
 'gitworld.owl': ('gitworld', '/root/GitWorld'),
 'owl-studio-v01.owl': ('owl-studio', '~/.local/share/owl-studio'),
 'telegram.owl': ('telegram-owl', '/root/.local/share/telegram-owl'),
}
EXTRA_PACKAGES = {
 'chatgpt.owl': ['python-cryptography', 'nodejs'],
 'telegram.owl': ['python-pip', 'python-qrcode'],
 'owl-studio-v01.owl': ['jdk21-openjdk'],
}
MARKET_LINKS = {
 '85-oma-another-features.owl': ('84-oma-another-features-app.owl', 'oma-another-features'),
 'lofi-radio-widget.owl': ('lofi-radio.owl', 'lofi-radio'),
}
# Store editions previously published with their own patch versions.
VERSION_FLOORS = {'market-app-perminder-klair-solitaire.owl': '1.2.2',
 'market-app-placq-reader.owl': '2.1.2',
 'market-app-placq-send-files.owl': '1.3.3',
 'market-rcrohmana-breakout.owl': '3.3.3',
 'market-app-shafiqimtiaz-omagit.owl': '1.0.2',
 'market-app-simonschubert-bastion.owl': '1.1.2',
 'market-app-simonschubert-checkmate.owl': '1.1.2',
 'market-app-simonschubert-linux-commands.owl': '1.6.2',
 'market-app-simonschubert-notes.owl': '1.0.2',
 'market-app-simonschubert-power-atlas.owl': '1.1.2',
 'market-app-vanyapoker-corsair.owl': '1.7.2',
 'apk-maker-app.owl': '3.0.2',
 'chess-app.owl': '1.7.2',
 '81-developer-guide.owl': '1.0.2',
 '82-key-bindings.owl': '1.1.2',
 'noboru.owl': '2.1.2',
 '76-oma-update-app.owl': '1.0.2',
 'market-app-xonars-owl-guide.owl': '1.5.2',
 'quiet-reader.owl': '1.3.3',
 'market-justqrius-matrix-terminal.owl': '1.2.2',
 '65-cava-terminal.owl': '1.2.2',
 '83-themes.owl': '1.0.3'}
def bumped_version(value):
 parts=[int(x) for x in re.match(r'[0-9.]+',value)[0].strip('.').split('.')][:3]
 parts += [0]*(3-len(parts))
 parts[-1]+=1
 return '.'.join(map(str,parts))
def main():
 selected=set(sys.argv[1:])
 previous={row['source']:row for row in json.loads((ROOT/'store-collection.json').read_text())}
 manifest=[]
 for item in json.loads((LOCAL/'ATTRIBUTION.json').read_text()):
  if item['kind'] not in ('widget','app'): continue
  filename=item['file']; source=LOCAL/filename; kind=item['kind']; group=kind+'s'
  # Fetch is maintained by the upstream OWL store; keep the historical source only.
  if filename == 'market-simonschubert-fetch.owl': continue
  if selected and filename not in selected and filename in previous:
   manifest.append(previous[filename])
   continue
  if filename.startswith('market-'):
   author=item['original_author']; slug=filename.removeprefix('market-').removeprefix('app-').removesuffix('.owl')[len(author)+1:]
  else: author='xonars'; slug=source.stem
  slug=SLUGS.get(filename,slug)
  entry=author+'-'+slug; folder=ROOT/group/author/slug; folder.mkdir(parents=True,exist_ok=True)
  text=source.read_text()
  if filename in MARKET_LINKS:
   original_app, market_app=MARKET_LINKS[filename]
   text=text.replace('o:'+original_app, 'o:market-app-xonars-xonars-'+market_app+'.owl')
  if filename=='market-simonschubert-today.owl':
   text=text.replace('${at}','${int(at)}')
  if filename=='market-app-shafiqimtiaz-omagit.owl':
   text=re.sub(r'\$\{len\((repo|hsel)\)\}',r'${int(len(\1))}',text).replace('${climit}','${int(climit)}')
   clone=re.search(r'^  let cloneCmd = (.+)$',text,re.M)[1]
   text=text.replace('terminal(cloneCmd,', 'terminal('+clone+',')
   helper=(ROOT/'tools/store-omagit-counts.py').read_text()
   text=text.replace('  source workNums = ', '  let storeWorkCounts = """\n'+helper+'"""\n  source workNums = ',1)
   text=re.sub(r'^  source workNums = .*$', lambda m:'  source workNums = cmd("python -c ${sh(storeWorkCounts)} ${sh(repo)}") every 10s timeout 20s',text,flags=re.M)

  if filename=='cassette.owl': text=text.replace("'cassette.owl'", "'market-app-xonars-xonars-cassette.owl'")
  paths=DEPENDENCIES.get(filename,[]); support=SUPPORT.get(filename); replacements={}
  if paths or support:
   replacements={'~/.config/omalauncher/widgets':f'~/.local/share/omalauncher-store/{entry}/widgets','/root/.config/omalauncher/widgets':f'/root/.local/share/omalauncher-store/{entry}/widgets','$HOME/.config/omalauncher/widgets':f'$HOME/.local/share/omalauncher-store/{entry}/widgets',"'.config/omalauncher/widgets'":f"'.local/share/omalauncher-store/{entry}/widgets'"}
   if filename=='76-oma-update-app.owl':
    replacements.update({'/root/.local/share/oma-updater':f'/root/.local/share/omalauncher-store/{entry}/support/oma-updater',"'.local/share/oma-updater'":f"'.local/share/omalauncher-store/{entry}/support/oma-updater'"})
   elif support:
    name, location=support
    target=f'~/.local/share/omalauncher-store/{entry}/support/{name}'
    if location.startswith('/root/') and name!='owl-chatgpt':
     target=target.replace('~','/root',1)
    if name=='telegram-owl':
     replacements[location+'/venv/bin/python '+location+'/client.py']=location+'/venv/bin/python '+target+'/client.py'
    else:
     replacements[location]=f'python {target}/chat.py' if name=='owl-chatgpt' else target
   def transform(s):
    for a,b in replacements.items(): s=s.replace(a,b)
    return s
   files={}
   for directory in paths:
    for f in sorted((LOCAL/directory).rglob('*')):
     if f.is_file() and not any(p.startswith('.') or p=='__pycache__' for p in f.relative_to(LOCAL).parts) and f.name!='events.json':
      data=f.read_bytes()
      try: data=transform(data.decode()).encode()
      except UnicodeDecodeError: pass
      if filename=='lofi-radio.owl' and f.name=='player.py':
       data=data.replace(b'ASSETS / track["path"]',b'offline_track(track)')
       data=data.replace(b'def offline_playlist', b'''def offline_track(track):
    bundled = ASSETS / track["path"]
    original = Path.home() / ".config/omalauncher/widgets/lofi-radio" / track["path"]
    return bundled if bundled.is_file() else original


def offline_playlist''')
      files['widgets/'+str(f.relative_to(LOCAL))]=data
   if support:
    name, _ = support
    directory=ROOT/'local/support'/name
    for f in sorted(directory.rglob('*')):
     if f.is_file() and all(not p.startswith('.') and p!='__pycache__' for p in f.relative_to(directory).parts):
      data=f.read_bytes()
      if name=='oma-updater':
       data=transform(data.decode()).encode()
      if name=='owl-chatgpt' and f.name=='auth.py':
       data=data.replace(b'ROOT = pathlib.Path(__file__).parent', b"ROOT = pathlib.Path.home() / '.local/share/owl-chatgpt'\nROOT.mkdir(mode=0o700, parents=True, exist_ok=True)")
      files[f'support/{name}/{f.relative_to(directory)}']=data
    if name=='owl-studio':
     files[f'support/{name}/owl.jar']=(ROOT/'tools/owl.jar').read_bytes()
   archive=io.BytesIO()
   with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,data in sorted(files.items()):
     info=zipfile.ZipInfo(name,(2026,11,6,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; z.writestr(info,data)
   payload=archive.getvalue(); digest=hashlib.sha256(payload).hexdigest(); resources=ROOT/'resources'; resources.mkdir(exist_ok=True)
   (resources/(digest+'.zip')).write_bytes(payload)
   bootstrap=(ROOT/'tools/store-bootstrap.py').read_text()+f'\ninstall({BASE+"resources/"+digest+".zip"!r}, {digest!r}, {entry!r})\n'
   # Prefix each actual shell invocation; fixed source, no command uses unverified resources.
   text=transform(text)
   if filename in {'lofi-radio.owl','lofi-radio-widget.owl'}:
    packaged=f'~/.local/share/omalauncher-store/{entry}/widgets/lofi-radio/'
    for reference in ('${sceneKey}', '${choice.asset}'):
     text=text.replace(packaged+reference,'~/.config/omalauncher/widgets/lofi-radio/'+reference)
   text=re.sub(r'(owl:\s*)([0-9]+)',lambda m:m[1]+str(max(6,int(m[2]))),text,count=1)
   text=re.sub(r'(description:\s*")([^"]+)(")',lambda m:m[1]+m[2][:155]+' · ресурсы при первом запуске'+m[3],text,count=1)
   # File-backed indexes must wait for initial package installation as well.
   if filename=='market-app-simonschubert-linux-commands.owl':
    text=re.sub(r'file\("([^"\n]*linux-commands-data[^"\n]*)"\)',r'cmd("cat \1") timeout 120s',text)
   if filename=='market-app-simonschubert-linux-commands.owl':
    text=text.replace('every 24h json', 'every 24h json timeout 120s')
   text=re.sub(r'file\("([^"\n]*omalauncher-store/[^"\n]+)"\)',r'cmd("cat \1") timeout 60s',text)
   # Keep conditional/null sources intact: prefix literal helper commands only.
   if filename=='noboru.owl':
    text=re.sub(r'(: )null(\) json)',r'\1""\2',text)
    text=text.replace('${helper}', 'python ~/.local/share/omalauncher-store/'+entry+'/widgets/noboru/main.py')
   if filename=='quiet-reader.owl':
    text=re.sub(r'^  let script = [^\n]*\n','',text,flags=re.M)
    text=text.replace('${script}', '~/.local/share/omalauncher-store/'+entry+'/widgets/quiet-reader/main.py')
   if filename=='pinterest-wallswap.owl':
    text=text.replace('${galleryPage}', '${int(galleryPage)}')
   if filename=='owl-studio-v01.owl':
    text=re.sub(r'cmd\(checkProject == "" \? null : "([^\n]+)"\)', lambda m: 'cmd("if [ -n ${sh(checkProject)} ]; then python -c ${sh(storeBootstrap)} && '+m[1]+'; fi")', text)
   # Prefix command arguments only. Image and other data paths use the installed files directly.
   pattern=r"""(\b(?:cmd|run|terminal)\(\s*["'])(?=(?:python3? |cat |exec bash |flock -w 15 )?(?:~|/root)/\.local/share/omalauncher-store/)"""
   if filename=='telegram.owl':
    pattern=r'(\b(?:cmd|run|terminal)\(\s*")(?=/root/\.local/share/telegram-owl/venv/bin/python )'
   if filename in {'noboru.owl','quiet-reader.owl','pinterest-wallswap.owl'}:
    pattern=r"""(["'])(?=(?:python3? |cat |exec bash )?(?:~|/root)/\.local/share/omalauncher-store/)"""
   text=re.sub(pattern, lambda m:m[1]+"python -c ${sh(storeBootstrap)} && ", text)
   insertion='\n  // Fixed SHA-256 resource package; installed only inside this entry\'s private directory.\n  let storeBootstrap = """\n'+bootstrap+'"""\n  let storeInstall = "python -c ${sh(storeBootstrap)}"\n'
   opening=re.search(r'^(?:app|widget)\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:opening]+insertion+text[opening:]
   # Bootstrap uses only Python standard library.
   match=re.search(r'pacman:\s*\[',text)
   packages=['python']+EXTRA_PACKAGES.get(filename,[])
   if match:
    end=text.index(']',match.end())
    existing=text[match.end():end]
    new=[pkg for pkg in packages if json.dumps(pkg) not in existing]
    if new: text=text[:match.end()]+', '.join(map(json.dumps,new))+(', ' if existing.strip() else '')+text[match.end():]
   else: text=text[:opening]+'\n  requires { pacman: '+json.dumps(packages)+' }\n'+text[opening:]
  meta=re.search(r'\bmeta\s*\{([^}]+)\}',text,re.S); body=meta[1] if meta else ''
  additions=[]
  for key,value in [('description',item['name']+' — локальная версия из коллекции Xonars'),('version','1.0'),('license','MIT'),('category','system')]:
   if not re.search(r'\b'+key+r'\s*:',body): additions.append(key+': '+json.dumps(value,ensure_ascii=False))
  if meta: text=text[:meta.end()-1]+'; '+'; '.join(additions)+' '+text[meta.end()-1:] if additions else text
  else:
   pos=re.search(r'^(?:app|widget)\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:pos]+'\n  meta { '+'; '.join(additions)+' }\n'+text[pos:]
  text=re.sub(r'(category:\s*)"(?:reading|education|tools)"',r'\1"productivity"',text)
  # A version change causes existing store installs to receive the packaged helpers.
  version_floor=VERSION_FLOORS.get(filename,'0.0.0')
  text=re.sub(r'(\bversion:\s*")([^"]+)(")',lambda m:m[1]+max(bumped_version(m[2]),version_floor,key=lambda v:tuple(map(int,v.split('.'))))+m[3],text,count=1)
  if filename=='cassette.owl': text=text.replace('version: "1.11.1"', 'version: "1.11.2"')
  if kind=='app' and not re.search(r'^\s*icon:',text,re.M):
   pos=re.search(r'^app\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:pos]+'\n  icon: "<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 48 48\'><rect x=\'8\' y=\'8\' width=\'32\' height=\'32\' rx=\'6\' fill=\'currentColor\'/></svg>"\n'+text[pos:]
  owl=folder/(kind+'.owl'); owl.write_text(text.rstrip()+'\n')
  original=ROOT/'docs/store-original-readmes'/(slug+'.md') if author=='xonars' else ROOT/'docs/store-original-readmes'/'.absent'
  (folder/'README.md').write_text(f"# {item['name']}\n\nАвтор оригинала: [{item['original_author']}]({item['source']}).\n\n{item['note']}\n\nЛокальная упаковка и сопровождение: Xonars. Исходная лицензия: {item['license']}. Уведомления о лицензиях в исходниках и ресурсах сохранены.\n\n"+('При первом запуске скачивается пакет ресурсов с этого магазина, проверяется SHA-256 и устанавливается в собственный каталог `~/.local/share/omalauncher-store/'+entry+'/`. Требуется сеть; установленные ресурсы доступны офлайн. Личные файлы и исходные помощники телефона не перезаписываются.\n' if paths or support else 'Дополнительный пакет ресурсов не требуется.\n')+('\nОбновлятор предназначен для конфигурации OMA Another с репозиторием `~/dev.omalauncher-another`; ключ подписи и SDK не входят в магазин.\n' if filename=='76-oma-update-app.owl' else '')+('\n---\n\n'+original.read_text() if original.exists() else ''))
  if not (folder/'preview.png').exists():
   image=Image.new('RGB',(720,360),'#191b24'); d=ImageDraw.Draw(image); font=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',28); d.text((28,60),item['name'],font=font,fill='#c0caf5'); d.text((28,145),author,font=font,fill='#7aa2f7'); d.text((28,240),'OWL · '+kind,font=font,fill='#a9b1d6'); image.save(folder/'preview.png')
  manifest.append({'source':filename,'path':str(owl.relative_to(ROOT)),'author':author,'resources': ('resources/'+digest+'.zip') if paths or support else None})
 (ROOT/'store-collection.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print('Store entries:',len(manifest))
if __name__=='__main__': main()
