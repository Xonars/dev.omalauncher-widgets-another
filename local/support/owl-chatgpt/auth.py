"""Direct OpenAI OAuth for this local application. No Codex dependency."""
import os, json, time, uuid, secrets, hashlib, base64, pathlib, urllib.request, urllib.parse, urllib.error, fcntl, hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
ROOT = pathlib.Path(__file__).parent
STORE = ROOT / 'accounts.json'
ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'

def load():
    try: return json.loads(STORE.read_text())
    except FileNotFoundError: return {'host': 'urn:uuid:' + str(uuid.uuid4()), 'active': '', 'profiles': []}

def save(d):
    p = ROOT / ('credentials-' + uuid.uuid4().hex)
    with open(p, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as f: json.dump(d, f)
    p.replace(STORE)

class Lock:
    def __enter__(self):
        self.f = (ROOT / 'auth.lock').open('a'); fcntl.flock(self.f, fcntl.LOCK_EX)
        self.d = load(); return self.d
    def __exit__(self, typ, val, tb):
        if typ is None: save(self.d)
        self.f.close()

def request(url, data=None, token=None, form=False):
    headers = {'Accept': 'application/json', 'User-Agent': 'OwlChatGPT/2.0'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=45) as r:
            raw = r.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e); error = body.get('error', {})
            msg = error.get('message', error.get('code', '')) if isinstance(error, dict) else str(error)
        except Exception: msg = ''
        raise RuntimeError(f'OpenAI HTTP {e.code}: {msg or e.reason}') from None

def decode(s): return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
def b64(b): return base64.urlsafe_b64encode(b).decode().rstrip('=')

def validate(token, client, nonce=None, subject=None):
    try:
        a,b,c = token.split('.')
        header, claims = json.loads(decode(a)), json.loads(decode(b))
        keys = request(ISSUER + '/.well-known/jwks.json')['keys']
        k = next(k for k in keys if k['kid'] == header.get('kid'))
        if header.get('alg') == 'RS256' and k['kty'] == 'RSA':
            key = rsa.RSAPublicNumbers(int.from_bytes(decode(k['e']), 'big'), int.from_bytes(decode(k['n']), 'big')).public_key()
            key.verify(decode(c), (a+'.'+b).encode(), padding.PKCS1v15(), hashes.SHA256())
        elif header.get('alg') == 'ES256' and k['kty'] == 'EC' and k.get('crv') == 'P-256':
            key = ec.EllipticCurvePublicNumbers(int.from_bytes(decode(k['x']), 'big'), int.from_bytes(decode(k['y']), 'big'), ec.SECP256R1()).public_key()
            sig = decode(c)
            if len(sig) != 64: raise ValueError('signature')
            key.verify(encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')), (a+'.'+b).encode(), ec.ECDSA(hashes.SHA256()))
        else: raise ValueError('algorithm')
        aud = claims.get('aud', [])
        if isinstance(aud, str): aud = [aud]
        if claims.get('iss') != ISSUER or client not in aud or claims.get('exp', 0) <= time.time(): raise ValueError('claims')
        if len(aud) > 1 and claims.get('azp') != client: raise ValueError('azp')
        if nonce is not None and claims.get('nonce') != nonce: raise ValueError('nonce')
        if not claims.get('sub') or (subject is not None and claims['sub'] != subject): raise ValueError('subject')
        return claims
    except Exception:
        raise RuntimeError('Не удалось проверить подлинность входа OpenAI. Повторите вход.') from None

def public():
    with Lock() as d:
        p = next((p for p in d['profiles'] if p['id'] == d['active']), {})
        return {'logged_in': bool(p.get('access_token')), 'sharing': 'chatgpt.tokens.use.direct' in p.get('scopes', []), 'account': p.get('email', ''), 'active_profile': d['active'], 'profiles': [{'id': x['id'], 'email': x.get('email', 'Аккаунт'), 'connected': bool(x.get('access_token'))} for x in d['profiles']]}

def merge_tokens(p, t):
    if not t.get('access_token'): raise RuntimeError('OpenAI не вернул токен доступа.')
    if t.get('token_type', 'Bearer').lower() != 'bearer': raise RuntimeError('Неподдерживаемый тип токена.')
    p.update(access_token=t['access_token'], expires_at=time.time()+int(t.get('expires_in', 3600)))
    for k in ('refresh_token', 'id_token'):
        if t.get(k): p[k] = t[k]
    if 'scope' in t: p['scopes'] = t['scope'].split()

def access():
    with Lock() as d:
        p = next((p for p in d['profiles'] if p['id'] == d['active']), {})
        if not p.get('access_token'): raise RuntimeError('Войдите в ChatGPT в настройках приложения.')
        if p.get('expires_at', 0) < time.time()+90:
            if not p.get('refresh_token'): raise RuntimeError('Сессия истекла. Войдите снова.')
            t = request(ISSUER+'/api/accounts/oauth/token', {'grant_type':'refresh_token', 'client_id':p['client_id'], 'refresh_token':p['refresh_token'], 'resource':RESOURCE}, form=True)
            if t.get('id_token'): validate(t['id_token'], p['client_id'], subject=p['subject'])
            merge_tokens(p, t)
        if 'chatgpt.tokens.use.direct' not in p.get('scopes', []): raise RuntimeError('В настройках войдите снова и разрешите использование плана ChatGPT.')
        return p['access_token']

def sign_in(update, profile=''):
    result = {}
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with Lock() as d:
        host = d['host']
        old = next((dict(p) for p in d['profiles'] if p['id'] == profile), {})
    client = old.get('client_id', 'dynamic_agent_client')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = {k:v[0] for k,v in urllib.parse.parse_qs(u.query).items()}
            if u.path != '/auth/callback' or not hmac.compare_digest(q.get('state',''), state):
                self.send_error(400, 'Invalid callback'); return
            result.update(q)
            body = '<!doctype html><meta charset="utf-8"><title>ChatGPT · Owl</title><p>Вернитесь в приложение ChatGPT · Owl для завершения входа.</p>'.encode()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = 1
        redirect = f'http://127.0.0.1:{server.server_port}/auth/callback'
        params = {'client_id':client,'ext_agent_host_id':host,'response_type':'code','redirect_uri':redirect,'scope':SCOPES,'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':b64(hashlib.sha256(verifier.encode()).digest())}
        if client == 'dynamic_agent_client': params['agent_name_hint'] = 'ChatGPT · Owl'
        elif old.get('email'): params['login_hint'] = old['email']
        update({'waiting':True,'url':ISSUER+'/api/accounts/authorize?'+urllib.parse.urlencode(params),'message':'Откройте ссылку, войдите в ChatGPT и разрешите доступ приложению.'})
        end = time.monotonic()+600
        while not result and time.monotonic() < end: server.handle_request()
    if not result: raise RuntimeError('Время ожидания входа истекло. Попробуйте снова.')
    if result.get('error'): raise RuntimeError('Вход не завершён: '+result['error'])
    issued = result.get('client_id', client)
    if issued == 'dynamic_agent_client' or not issued or (client != 'dynamic_agent_client' and issued != client): raise RuntimeError('OpenAI не подтвердил регистрацию приложения.')
    # Retain registration even if the code exchange fails, to avoid duplicate clients.
    pid = old.get('id', uuid.uuid4().hex)
    with Lock() as d:
        p = next((p for p in d['profiles'] if p['id'] == pid), None)
        if p is None: p={'id':pid,'client_id':issued}; d['profiles'].append(p)
    t = request(ISSUER+'/api/accounts/oauth/token', {'grant_type':'authorization_code','client_id':issued,'code':result.get('code',''),'code_verifier':verifier,'redirect_uri':redirect,'resource':RESOURCE}, form=True)
    claims = validate(t.get('id_token',''), issued, nonce, old.get('subject'))
    with Lock() as d:
        p = next(p for p in d['profiles'] if p['id'] == pid)
        p.update(subject=claims['sub'], email=claims.get('email','Аккаунт'), issuer=ISSUER)
        merge_tokens(p, t)
        d['active'] = pid
    update({'waiting':False, 'message':'Вход выполнен' if 'chatgpt.tokens.use.direct' in t.get('scope','').split() else 'Вы вошли. Для чата нужно разрешить использование плана ChatGPT.'})

def select(profile):
    with Lock() as d:
        if any(p['id'] == profile for p in d['profiles']): d['active'] = profile

def sign_out():
    error = ''
    with Lock() as d:
        p = next((p for p in d['profiles'] if p['id'] == d['active']), {})
        if p.get('refresh_token'):
            try:
                config = request(ISSUER+'/.well-known/openid-configuration')
                endpoint = config['revocation_endpoint']
                if not endpoint.startswith(ISSUER+'/'): raise RuntimeError('Invalid revocation endpoint')
                request(endpoint, {'token':p['refresh_token'],'token_type_hint':'refresh_token','client_id':p['client_id']}, form=True)
            except Exception: error = 'Вы вышли на этом устройстве. Отзыв удалённой сессии не подтверждён; отключить приложение можно в настройках ChatGPT.'
        for k in ('access_token','refresh_token','id_token','expires_at','scopes'): p.pop(k, None)
    return error or 'Вы вышли из аккаунта.'
