#!/usr/bin/env python3
"""Build reviewed local collection entries without changing installed phone files."""
from pathlib import Path
import hashlib, io, json, re, shutil, zipfile, subprocess
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
}
SLUGS={'70-apk-share.owl':'apk-share','76-oma-update-app.owl':'oma-update','81-developer-guide.owl':'developer-guide','82-key-bindings.owl':'key-bindings','83-themes.owl':'themes','55-system-panel.owl':'system-panel','65-cava-terminal.owl':'cava-terminal','noboru.owl':'noboru','quiet-reader.owl':'quiet-reader','pinterest-wallswap.owl':'pinterest-wallswap','cassette.owl':'cassette','chess-app.owl':'chess-app','apk-maker-app.owl':'apk-maker-app'}
def bumped_version(value):
 parts=[int(x) for x in re.match(r'[0-9.]+',value)[0].strip('.').split('.')][:3]
 parts += [0]*(3-len(parts))
 parts[-1]+=1
 return '.'.join(map(str,parts))
def main():
 manifest=[]
 for item in json.loads((LOCAL/'ATTRIBUTION.json').read_text()):
  if item['kind'] not in ('widget','app'): continue
  filename=item['file']; source=LOCAL/filename; kind=item['kind']; group=kind+'s'
  if filename.startswith('market-'):
   author=item['original_author']; slug=filename.removeprefix('market-').removeprefix('app-').removesuffix('.owl')[len(author)+1:]
  else: author='xonars'; slug=SLUGS[filename]
  entry=author+'-'+slug; folder=ROOT/group/author/slug; folder.mkdir(parents=True,exist_ok=True)
  text=source.read_text()
  if filename=='market-app-shafiqimtiaz-omagit.owl':
   text=re.sub(r'\$\{len\((repo|hsel)\)\}',r'${int(len(\1))}',text).replace('${climit}','${int(climit)}')
   clone=re.search(r'^  let cloneCmd = (.+)$',text,re.M)[1]
   text=text.replace('terminal(cloneCmd,', 'terminal('+clone+',')
   helper=(ROOT/'tools/store-omagit-counts.py').read_text()
   text=text.replace('  source workNums = ', '  let storeWorkCounts = """\n'+helper+'"""\n  source workNums = ',1)
   text=re.sub(r'^  source workNums = .*$', lambda m:'  source workNums = cmd("python -c ${sh(storeWorkCounts)} ${sh(repo)}") every 10s timeout 20s',text,flags=re.M)

  if filename=='cassette.owl': text=text.replace("'cassette.owl'", "'market-app-xonars-xonars-cassette.owl'")
  paths=DEPENDENCIES.get(filename,[]); replacements={}
  if paths:
   replacements={'~/.config/omalauncher/widgets':f'~/.local/share/omalauncher-store/{entry}/widgets','/root/.config/omalauncher/widgets':f'/root/.local/share/omalauncher-store/{entry}/widgets','$HOME/.config/omalauncher/widgets':f'$HOME/.local/share/omalauncher-store/{entry}/widgets',"'.config/omalauncher/widgets'":f"'.local/share/omalauncher-store/{entry}/widgets'"}
   if filename=='76-oma-update-app.owl':
    replacements.update({'/root/.local/share/oma-updater':f'/root/.local/share/omalauncher-store/{entry}/support/oma-updater',"'.local/share/oma-updater'":f"'.local/share/omalauncher-store/{entry}/support/oma-updater'"})
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
      files['widgets/'+str(f.relative_to(LOCAL))]=data
   if filename=='76-oma-update-app.owl':
    for f in sorted((ROOT/'local/support/oma-updater').glob('*')):
     if f.is_file(): files['support/oma-updater/'+f.name]=transform(f.read_text()).encode()
   archive=io.BytesIO()
   with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,data in sorted(files.items()):
     info=zipfile.ZipInfo(name,(2026,11,6,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; z.writestr(info,data)
   payload=archive.getvalue(); digest=hashlib.sha256(payload).hexdigest(); resources=ROOT/'resources'; resources.mkdir(exist_ok=True)
   (resources/(digest+'.zip')).write_bytes(payload)
   bootstrap=(ROOT/'tools/store-bootstrap.py').read_text()+f'\ninstall({BASE+"resources/"+digest+".zip"!r}, {digest!r}, {entry!r})\n'
   # Prefix each actual shell invocation; fixed source, no command uses unverified resources.
   text=transform(text)
   text=re.sub(r'(owl:\s*)([0-9]+)',lambda m:m[1]+str(max(6,int(m[2]))),text,count=1)
   text=re.sub(r'(description:\s*")([^"]+)(")',lambda m:m[1]+m[2][:155]+' · ресурсы при первом запуске'+m[3],text,count=1)
   # File-backed indexes must wait for initial package installation as well.
   if filename=='market-app-simonschubert-linux-commands.owl':
    text=re.sub(r'file\("([^"\n]*linux-commands-data[^"\n]*)"\)',r'cmd("cat \1") timeout 120s',text)
   if filename=='market-app-simonschubert-linux-commands.owl':
    text=text.replace('every 24h json', 'every 24h json timeout 120s')
   # Keep conditional/null sources intact: prefix literal helper commands only.
   if filename=='noboru.owl':
    text=re.sub(r'(: )null(\) json)',r'\1""\2',text)
    text=text.replace('${helper}', 'python ~/.local/share/omalauncher-store/'+entry+'/widgets/noboru/main.py')
   if filename=='quiet-reader.owl':
    text=text.replace('${script}', '~/.local/share/omalauncher-store/'+entry+'/widgets/quiet-reader/main.py')
   pattern=r"([\"'])(?P<start>(?:python3?|cat|exec bash) (?:~|/root)/\.local/share/omalauncher-store/)"
   text=re.sub(pattern, lambda m:m[1]+"python -c ${sh(storeBootstrap)} && "+m['start'], text)
   insertion='\n  // Fixed SHA-256 resource package; installed only inside this entry\'s private directory.\n  let storeBootstrap = """\n'+bootstrap+'"""\n  let storeInstall = "python -c ${sh(storeBootstrap)}"\n'
   opening=re.search(r'^(?:app|widget)\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:opening]+insertion+text[opening:]
   # Bootstrap uses only Python standard library.
   match=re.search(r'pacman:\s*\[',text)
   if match: text=text[:match.end()]+'"python", '+text[match.end():]
   else: text=text[:opening]+'\n  requires { pacman: ["python"] }\n'+text[opening:]
  meta=re.search(r'\bmeta\s*\{([^}]+)\}',text,re.S); body=meta[1] if meta else ''
  additions=[]
  for key,value in [('description',item['name']+' — локальная версия из коллекции Xonars'),('version','1.0'),('license','MIT'),('category','system')]:
   if not re.search(r'\b'+key+r'\s*:',body): additions.append(key+': '+json.dumps(value,ensure_ascii=False))
  if meta: text=text[:meta.end()-1]+'; '+'; '.join(additions)+' '+text[meta.end()-1:] if additions else text
  else:
   pos=re.search(r'^(?:app|widget)\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:pos]+'\n  meta { '+'; '.join(additions)+' }\n'+text[pos:]
  text=text.replace('category: "reading"', 'category: "productivity"')
  # A version change causes existing store installs to receive the packaged helpers.
  text=re.sub(r'(\bversion:\s*")([^"]+)(")',lambda m:m[1]+bumped_version(m[2])+m[3],text,count=1)
  if filename=='cassette.owl': text=text.replace('version: "1.11.1"', 'version: "1.11.2"')
  if kind=='app' and not re.search(r'^\s*icon:',text,re.M):
   pos=re.search(r'^app\s+"[^"]+"\s*\{',text,re.M).end(); text=text[:pos]+'\n  icon: "<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 48 48\'><rect x=\'8\' y=\'8\' width=\'32\' height=\'32\' rx=\'6\' fill=\'currentColor\'/></svg>"\n'+text[pos:]
  owl=folder/(kind+'.owl'); owl.write_text(text.rstrip()+'\n')
  original=ROOT/'docs/store-original-readmes'/(slug+'.md') if author=='xonars' else ROOT/'docs/store-original-readmes'/'.absent'
  (folder/'README.md').write_text(f"# {item['name']}\n\nАвтор оригинала: [{item['original_author']}]({item['source']}).\n\n{item['note']}\n\nЛокальная упаковка и сопровождение: Xonars. Исходная лицензия: {item['license']}. Уведомления о лицензиях в исходниках и ресурсах сохранены.\n\n"+('При первом запуске скачивается пакет ресурсов с этого магазина, проверяется SHA-256 и устанавливается в собственный каталог `~/.local/share/omalauncher-store/'+entry+'/`. Требуется сеть; установленные ресурсы доступны офлайн. Личные файлы и исходные помощники телефона не перезаписываются.\n' if paths else 'Дополнительный пакет ресурсов не требуется.\n')+('\nОбновлятор предназначен для конфигурации OMA Another с репозиторием `~/dev.omalauncher-another`; ключ подписи и SDK не входят в магазин.\n' if filename=='76-oma-update-app.owl' else '')+('\n---\n\n'+original.read_text() if original.exists() else ''))
  preview=Path('/root/.config/omalauncher/widgets/.preview')/(filename+'.png')
  if preview.exists():
   image=Image.open(preview).convert('RGB'); image.thumbnail((900,1400)); image.save(folder/'preview.png',optimize=True)
   if (folder/'preview.png').stat().st_size>300*1024: image.thumbnail((500,800)); image.save(folder/'preview.png',optimize=True)
  elif not (folder/'preview.png').exists():
   image=Image.new('RGB',(720,360),'#191b24'); d=ImageDraw.Draw(image); font=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',28); d.text((28,60),item['name'],font=font,fill='#c0caf5'); d.text((28,145),author,font=font,fill='#7aa2f7'); d.text((28,240),'OWL · '+kind,font=font,fill='#a9b1d6'); image.save(folder/'preview.png')
  manifest.append({'source':filename,'path':str(owl.relative_to(ROOT)),'author':author,'resources': ('resources/'+digest+'.zip') if paths else None})
 (ROOT/'store-collection.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print('Store entries:',len(manifest))
if __name__=='__main__': main()
