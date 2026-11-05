#!/usr/bin/env python3
"""Receive terminal key sequences; no global keyboard capture or key-up claims."""
import os, sys, termios, tty, select, time, json, re
from pathlib import Path
TARGET = Path(__file__).with_name('events.json')

def decode(raw):
    mods = []
    keys = {b'\x1b[A':'UP', b'\x1b[B':'DOWN', b'\x1b[C':'RIGHT', b'\x1b[D':'LEFT', b'\x1b[H':'HOME', b'\x1b[F':'END', b'\x1b[Z':'TAB', b'\x1bOP':'F1', b'\x1bOQ':'F2', b'\x1bOR':'F3', b'\x1bOS':'F4'}
    special = {2:'INS',3:'DEL',5:'PGUP',6:'PGDN',15:'F5',17:'F6',18:'F7',19:'F8',20:'F9',21:'F10',23:'F11',24:'F12'}
    if raw in keys:
        return (['SHIFT'] if raw == b'\x1b[Z' else []) + [keys[raw]]
    m = re.fullmatch(rb'\x1b\[(\d+)(?:;(\d+))?([~A-DFHPQRS])', raw)
    if m:
        n, mod, final = int(m[1]), int(m[2] or 1)-1, m[3]
        mods = [name for bit,name in [(1,'SHIFT'),(2,'ALT'),(4,'CTRL'),(8,'SUPER')] if mod & bit]
        key = special.get(n, '?') if final == b'~' else {b'A':'UP',b'B':'DOWN',b'C':'RIGHT',b'D':'LEFT',b'H':'HOME',b'F':'END',b'P':'F1',b'Q':'F2',b'R':'F3',b'S':'F4'}.get(final,'?')
        return mods + [key]
    if raw.startswith(b'\x1b') and len(raw)>1:
        mods=['ALT']; raw=raw[1:]
    if len(raw)==1:
        n=raw[0]
        if n in (10,13): key='ENTER'
        elif n==9: key='TAB'
        elif n in (8,127): key='BKSP'
        elif n==27: key='ESC'
        elif n==0: mods+=['CTRL']; key='SPACE'
        elif n<27: mods+=['CTRL']; key=chr(n+64)
        elif n==32: key='SPACE'
        else:
            key=chr(n).upper()
            if 65<=n<=90: mods+=['SHIFT']
        return mods+[key]
    return mods+[raw.decode('utf-8','replace')]

def publish(data):
    temp=TARGET.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False)); os.replace(temp,TARGET)

def main():
    fd=sys.stdin.fileno(); old=termios.tcgetattr(fd); count=0; history=[]
    try:
        tty.setraw(fd)
        sys.stdout.write('\x1b[2J\x1b[H\x1b[?25lГотово · нажимайте клавиши\r\nНазад — выйти из захвата'); sys.stdout.flush()
        publish({'keys':[], 'count':0,'combo':'Ожидание клавиши','raw':'','history':[]})
        clear_at=0
        while True:
            if select.select([fd],[],[],0.06)[0]:
                raw=os.read(fd,1)
                if not raw: break
                if raw==b'\x1b':
                    while select.select([fd],[],[],0.025)[0]: raw+=os.read(fd,1)
                elif raw[0]>=128:
                    while select.select([fd],[],[],0.005)[0]: raw+=os.read(fd,1)
                keys=decode(raw); count+=1; combo=' + '.join(keys)
                history=([combo]+history)[:5]
                data={'keys':keys,'count':count,'combo':combo,'raw':raw.hex(' '),'history':history}
                publish(data); clear_at=time.monotonic()+0.45
                sys.stdout.write('\x1b[H\x1b[2KПолучено: '+combo+'\r\n\x1b[2KНазад — выйти из захвата'); sys.stdout.flush()
            elif clear_at and time.monotonic()>clear_at:
                data['keys']=[]; publish(data); clear_at=0
    finally:
        termios.tcsetattr(fd,termios.TCSADRAIN,old)
        sys.stdout.write('\x1b[?25h'); sys.stdout.flush()
if __name__=='__main__': main()
