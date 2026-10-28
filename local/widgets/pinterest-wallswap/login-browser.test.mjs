import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {netscape, DevTools, loginUrl} from './login-browser.mjs';

test('only Pinterest session cookies are exported; Google stays in the temporary browser',()=>{
  const text=netscape([
    {domain:'.pinterest.com',name:'_pinterest_sess',value:'test-session',path:'/',secure:true,httpOnly:true,session:true,expires:-1},
    {domain:'.google.com',name:'SID',value:'test-google-session',path:'/',secure:true,expires:2000000000},
    {domain:'notpinterest.com',name:'wrong',value:'ignored',path:'/',expires:2000000000}
  ]);
  assert.match(text,/#HttpOnly_\.pinterest\.com\tTRUE\t\/\tTRUE\t\t_pinterest_sess\ttest-session/);
  assert.ok(!text.includes('test-google-session'));
  assert.ok(!text.includes('notpinterest.com'));
});

test('persistent cookie expiry uses Netscape seconds',()=>{
  const text=netscape([{domain:'www.pinterest.com',name:'csrftoken',value:'test-csrf',path:'/',secure:true,expires:2000000000.9}]);
  assert.match(text,/www.pinterest.com\tFALSE\t\/\tTRUE\t2000000000\tcsrftoken/);
});

function fakeBrowser(){
  const browser=new EventEmitter();browser.stdio=[null,null,null,new PassThrough(),new PassThrough()];
  return browser;
}

test('private-pipe transport handles split messages and events',async()=>{
  const child=fakeBrowser();const cdp=new DevTools(child);let event;
  cdp.listeners.push(e=>{event=e.method;});
  const pending=cdp.call('Browser.getVersion');
  child.stdio[4].write('{"id":1,"res');
  child.stdio[4].write('ult":{"userAgent":"test-browser"}}\0{"method":"Target.targetCreated"}\0');
  assert.equal((await pending).userAgent,'test-browser');
  assert.equal(event,'Target.targetCreated');
});

test('closing browser rejects pending work instead of leaving sign-in running',async()=>{
  const child=fakeBrowser();const cdp=new DevTools(child);
  const pending=cdp.call('Storage.getCookies');child.emit('exit',0);
  await assert.rejects(pending,/Окно входа закрыто/);
  assert.equal(cdp.pending.size,0);
});

test('login and reset use Pinterest; the old Google shortcut never retries blocked Google sign-in',()=>{
  assert.equal(loginUrl([]),'https://www.pinterest.com/login/');
  assert.equal(loginUrl(['--reset-password']),'https://www.pinterest.com/password/reset/');
  assert.equal(loginUrl(['--google']),'https://www.pinterest.com/login/');
});
