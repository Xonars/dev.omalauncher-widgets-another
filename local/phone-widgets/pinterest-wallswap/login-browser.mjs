#!/usr/bin/env node
// Full Chromium sign-in. DevTools uses private inherited pipes, never a TCP port.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn, execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const exec = promisify(execFile);
const root = path.join(os.homedir(), '.local/state/pinterest-wallswap');
const backend = path.join(os.homedir(), '.config/omalauncher/widgets/pinterest-wallswap/account.py');
const statusFile = path.join(root, 'browser-login.json');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export function netscape(cookies) {
  return '# Netscape HTTP Cookie File\n' + cookies.filter(c => c.domain.replace(/^\./, '') === 'pinterest.com' || c.domain.endsWith('.pinterest.com')).map(c => {
    const domain = (c.httpOnly ? '#HttpOnly_' : '') + c.domain;
    const expires = c.session || c.expires <= 0 ? '' : String(Math.floor(c.expires));
    return [domain, c.domain.startsWith('.') ? 'TRUE' : 'FALSE', c.path || '/', c.secure ? 'TRUE' : 'FALSE', expires, c.name, c.value].join('\t');
  }).join('\n') + '\n';
}

async function atomic(file, text) {
  const tmp = file + '.' + process.pid + '.tmp';
  await fs.writeFile(tmp, text, {mode: 0o600, flag: 'wx'});
  await fs.rename(tmp, file);
}
async function status(phase, message) {
  await atomic(statusFile, JSON.stringify({phase, message, updated: Date.now() / 1000}));
}

export class DevTools {
  constructor(child) {
    this.child = child;
    this.counter = 0;
    this.pending = new Map();
    this.listeners = [];
    this.buffer = '';
    child.stdio[4].setEncoding('utf8');
    child.stdio[4].on('data', text => {
      this.buffer += text;
      let end;
      while ((end = this.buffer.indexOf('\0')) !== -1) {
        const text = this.buffer.slice(0, end);
        this.buffer = this.buffer.slice(end + 1);
        let message;
        try { message = JSON.parse(text); } catch { continue; }
        if (message.id && this.pending.has(message.id)) {
          const pending = this.pending.get(message.id);
          this.pending.delete(message.id); clearTimeout(pending.timer);
          if (message.error) pending.reject(new Error('Ошибка связи с окном входа'));
          else pending.resolve(message.result || {});
        } else {
          for (const listener of this.listeners) listener(message);
        }
      }
    });
    child.once('exit', () => {
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer); pending.reject(new Error('Окно входа закрыто'));
      }
      this.pending.clear();
    });
    child.stdio[3].on('error', () => {});
  }
  call(method, params = {}, sessionId = undefined) {
    return new Promise((resolve, reject) => {
      const id = ++this.counter;
      const timer = setTimeout(() => {this.pending.delete(id); reject(new Error('Окно входа не отвечает'));}, 15000);
      this.pending.set(id, {resolve, reject, timer});
      this.child.stdio[3].write(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
    });
  }
}

async function acquireLock() {
  const lockFile = path.join(root, 'browser-login.lock');
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const handle = await fs.open(lockFile, 'wx', 0o600);
      await handle.writeFile(String(process.pid)); await handle.close();
      return async () => { await fs.unlink(lockFile).catch(() => {}); };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const pid = Number(await fs.readFile(lockFile, 'utf8').catch(() => '0'));
      let alive = false;
      if (pid > 0) {try {process.kill(pid, 0); alive = true;} catch {}}
      if (alive) {
        await status('waiting','Окно входа уже открыто. Закройте его и нажмите нужную кнопку снова.');
        return null;
      }
      await fs.unlink(lockFile).catch(() => {});
    }
  }
  return null;
}

export function loginUrl(args) {
  return args.includes('--reset-password') || args.includes('--self-test-reset')
    ? 'https://www.pinterest.com/password/reset/' : 'https://www.pinterest.com/login/';
}

async function testPinterestForm(cdp, reset) {
  for (let i=0;i<60;i++) {
    const {targetInfos}=await cdp.call('Target.getTargets');
    const target=targetInfos.find(t=>t.type==='page' && t.url.startsWith(loginUrl(reset ? ['--reset-password'] : []).replace(/\/$/,'')));
    if (target) {
      const {sessionId}=await cdp.call('Target.attachToTarget',{targetId:target.targetId,flatten:true});
      const result=await cdp.call('Runtime.evaluate',{expression:"[...document.querySelectorAll('input[type=email], input[name=id], input[name=email], input[id=email], input[type=text], input[type=search]')].some(i=>i.getBoundingClientRect().height>0 && getComputedStyle(i).visibility!=='hidden')",returnByValue:true},sessionId);
      if (result.result?.value) {
        await delay(2000);
        const screenshot=await cdp.call('Page.captureScreenshot',{format:'png'},sessionId);
        await fs.writeFile(reset ? '/tmp/pinterest-password-reset-form.png' : '/tmp/pinterest-email-login-form.png',Buffer.from(screenshot.data,'base64'));
        process.stdout.write(reset ? 'pinterest-reset-form-ready\n' : 'pinterest-login-form-ready\n');
        return;
      }
      await cdp.call('Target.detachFromTarget',{sessionId});
    }
    await delay(500);
  }
  throw new Error('Не открылась форма Pinterest');
}

async function main() {
  process.umask(0o077);
  const selfTest = process.argv.includes('--self-test-login') || process.argv.includes('--self-test-reset');
  const reset = process.argv.includes('--reset-password') || process.argv.includes('--self-test-reset');
  await fs.mkdir(root, {recursive: true, mode: 0o700}); await fs.chmod(root, 0o700);
  const unlock = selfTest ? async () => {} : await acquireLock();
  if (!unlock) return;
  let child, cdp, profile;
  let connected = false, stopped = false;
  const stop = () => {stopped = true; child?.kill('SIGTERM');};
  process.once('SIGTERM',stop);process.once('SIGINT',stop);
  try {
    await fs.access('/usr/bin/chromium');
    profile = await fs.mkdtemp(path.join(root, 'login-profile-'));
    await fs.mkdir(path.join(profile, 'Default'), {mode: 0o700});
    await fs.writeFile(path.join(profile, 'Default', 'Preferences'), JSON.stringify({credentials_enable_service:false,profile:{password_manager_enabled:false},autofill:{profile_enabled:false,credit_card_enabled:false}}), {mode:0o600});
    const flags = ['--no-first-run','--no-default-browser-check','--password-store=basic','--disable-dev-shm-usage','--disable-gpu','--disable-gpu-compositing',
      '--remote-debugging-pipe','--user-data-dir='+profile,'--window-size=520,850',
      loginUrl(process.argv)];
    if (process.getuid?.() === 0) flags.push('--no-sandbox');
    if (selfTest) flags.push('--headless=new');
    else if (process.env.WAYLAND_DISPLAY) flags.push('--ozone-platform=wayland');
    if (!selfTest) await status('opening', reset ? 'Открываю восстановление пароля Pinterest…' : 'Открываю вход в Pinterest…');
    child = spawn('/usr/bin/chromium', flags, {stdio:['ignore','ignore','ignore','pipe','pipe']});
    const exited = new Promise(resolve => {child.once('exit',resolve);child.once('error',resolve);});
    cdp = new DevTools(child);
    const version = await cdp.call('Browser.getVersion');
    if (selfTest) { await testPinterestForm(cdp,reset); return; }
    await status('waiting', reset ? 'Восстановите пароль Pinterest через свою почту. Затем войдите в Pinterest с новым паролем.' : 'Введите email и пароль Pinterest. Вход через Google в этом окне недоступен.');
    let fingerprint = '', retryAt = 0;
    while (!stopped && child.exitCode === null && child.signalCode === null) {
      const {cookies} = await cdp.call('Storage.getCookies');
      const ours = cookies.filter(c=>c.domain.replace(/^\./,'')==='pinterest.com'||c.domain.endsWith('.pinterest.com'));
      const ready = ours.some(c=>c.name==='_auth'&&c.value==='1') && ours.some(c=>c.name==='_pinterest_sess'&&c.value);
      if (ready) {
        const text = netscape(ours);
        const hash = createHash('sha256').update(text).digest('hex');
        if (hash !== fingerprint || Date.now() > retryAt) {
          fingerprint = hash; retryAt = Date.now() + 15000;
          await atomic(path.join(root,'pinterest-cookies.txt'),text);
          await atomic(path.join(root,'user-agent.txt'),version.userAgent);
          await status('checking','Проверяю подключение Pinterest…');
          const result = await exec('python',[backend,'connect'],{timeout:50000, maxBuffer:64000});
          const account = JSON.parse(result.stdout);
          if (account.connected === true) {
            connected = true;
            await status('connected','Pinterest подключён');
            break;
          }
          await status('waiting',account.error || 'Завершите вход на странице Pinterest.');
        }
      }
      await Promise.race([delay(1500),exited]);
    }
    if (!connected) await status('closed','Окно входа закрыто. При необходимости откройте его снова.');
  } catch (error) {
    if (selfTest) {process.stderr.write(error.message+'\n'); process.exitCode=1;}
    else await status('error',child?.exitCode !== null && child?.exitCode !== undefined ? 'Окно входа закрыто. Нажмите «Войти в Pinterest» ещё раз.' : 'Не удалось открыть вход. Нажмите «Войти в Pinterest» ещё раз.');
  } finally {
    if (child && child.exitCode === null && child.signalCode === null) {
      try {await cdp.call('Browser.close');} catch {}
      await Promise.race([new Promise(resolve=>child.once('exit',resolve)),delay(3000)]);
      if (child.exitCode===null&&child.signalCode===null) child.kill('SIGTERM');
    }
    if (profile) await fs.rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
    await unlock();
    process.removeListener('SIGTERM',stop);process.removeListener('SIGINT',stop);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
