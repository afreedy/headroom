#!/usr/bin/env python3
"""Local-only Codex usage bridge. No OAuth credentials leave the Mac."""
import argparse, hashlib, json, os, secrets, shutil, subprocess, threading, time, webbrowser, sys
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

DATA = Path(os.environ.get('HEADROOM_DATA', str(Path.home() / 'Library/Application Support/Headroom')))
BINARY = os.environ.get('CODEX_BIN') or ('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex' if Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex').exists() else shutil.which('codex'))
LOCK = threading.Lock()
LOGIN = {}
WAKE = threading.Event()
# One module instance shares the refresh lock with the warmup worker.
if __name__ == "__main__": sys.modules["server"] = sys.modules[__name__]

class Rpc:
    def __init__(self, home=None):
        env = os.environ.copy()
        if home: env['CODEX_HOME'] = str(home)
        self.proc = subprocess.Popen([BINARY, 'app-server', '--listen', 'stdio://'], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.pending = {}; self.seq = 0; self.turn_done = threading.Event()
        threading.Thread(target=self.read, daemon=True).start()
        self.call('initialize', {'clientInfo': {'name': 'headroom', 'version': '1.0.0'}, 'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized'})
    def read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
                if msg.get('id') in self.pending:
                    waiter, box = self.pending[msg['id']]; box.append(msg); waiter.set()
                if msg.get('method') == 'account/login/completed': self.login_result = msg.get('params', {})
                if msg.get('method') == 'turn/completed':
                    self.turn_result = msg.get('params', {}).get('turn', {}); self.turn_done.set()
            except (ValueError, KeyError): pass
    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + '\n'); self.proc.stdin.flush()
    def call(self, method, params=None):
        self.seq += 1; ident = self.seq; ev = threading.Event(); box = []
        self.pending[ident] = (ev, box)
        self.send({'id': ident, 'method': method, **({'params': params} if params is not None else {})})
        if not ev.wait(30):
            self.pending.pop(ident, None); raise RuntimeError('Codex did not respond within 30 seconds.')
        self.pending.pop(ident, None); msg = box[0]
        if 'error' in msg: raise RuntimeError(msg['error'].get('message', 'Codex request failed.'))
        return msg.get('result', {})
    def close(self):
        self.proc.terminate()
        try: self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired: self.proc.kill()

def load():
    path = DATA / 'snapshots.json'
    return json.loads(path.read_text()) if path.exists() else []

def save(rows):
    temp = DATA / 'snapshots.tmp'
    temp.write_text(json.dumps(rows)); temp.chmod(0o600); temp.replace(DATA / 'snapshots.json')

def normalize(account, result, home):
    if not account or account.get('type') != 'chatgpt': raise RuntimeError('Sign into a ChatGPT account in Codex first.')
    key = result.get('accountId') or account.get('email')
    if not key: raise RuntimeError('Codex did not return an account identity.')
    buckets = result.get('rateLimitsByLimitId') or {'codex': result.get('rateLimits')}
    return {'id': hashlib.sha256(key.encode()).hexdigest()[:20], 'email': account.get('email'), 'plan': account.get('planType'), 'home': str(home) if home else None, 'updatedAt': time.time(), 'buckets': buckets, 'resetCredits': (result.get('rateLimitResetCredits') or {}).get('availableCount'), 'resetCreditDetails': [{k: c.get(k) for k in ('title', 'grantedAt', 'expiresAt')} for c in result['rateLimitResetCredits']['credits']] if (result.get('rateLimitResetCredits') or {}).get('credits') is not None else None, 'error': None}

def refresh(warm=False):
    from warmup import process_account
    with LOCK:
        rows = load(); errors = []; state_path = DATA/'warmup-state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        for index, old in enumerate(rows):
            rpc = None
            try:
                home = old.get('home')
                if not home or not Path(home).is_relative_to(DATA/'accounts') or not (Path(home)/'auth.json').exists():
                    old['needsLogin'] = True
                    raise RuntimeError('Reconnect this account once for independent refresh and warmup.')
                rpc = Rpc(home)
                account = rpc.call('account/read', {'refreshToken': False}).get('account')
                limits = rpc.call('account/rateLimits/read')
                row = normalize(account, limits, home)
                if row['id'] != old['id']:
                    old['needsLogin'] = True
                    raise RuntimeError('Saved login belongs to a different account. Reconnect this account.')
                row['needsLogin'] = False
                rows[index] = row
                if warm:
                    process_account(rpc, row, state, state_path)
                row['warmup'] = state.get(row['id'], {})
            except Exception as e:
                current = rows[index]
                current['error'] = str(e); current['lastAttemptAt'] = time.time()
                current['warmup'] = state.get(current['id'], {})
                errors.append(str(e))
            finally:
                if rpc: rpc.close()
        save(rows)
        return {'accounts': [{k:v for k,v in row.items() if k != 'home'} for row in rows], 'activeId': None, 'errors': errors, 'checkedAt': time.time(), 'scheduler': True}

def scheduler_delay(rows, now):
    deadlines = [(r.get('warmup') or {}).get('nextCheckAt') for r in rows if not r.get('error')]
    return max(1, min([60] + [t-now for t in deadlines if isinstance(t, (int,float))]))

def scheduler():
    while True:
        try:
            refresh(warm=True)
            delay = scheduler_delay(load(), time.time())
        except Exception:
            delay = 60
        WAKE.wait(delay); WAKE.clear()

def start_login(expected=None):
    if expected and expected not in {r["id"] for r in load()}: raise RuntimeError("Unknown account.")
    if LOGIN.get('running'): raise RuntimeError('A sign-in is already open. Finish it in your browser first.')
    home = DATA / 'accounts' / secrets.token_hex(8); home.mkdir(parents=True, mode=0o700)
    rpc = Rpc(home)
    try: response = rpc.call('account/login/start', {'type': 'chatgpt'})
    except Exception:
        rpc.close(); raise
    url = response.get('authUrl')
    if not url: rpc.close(); raise RuntimeError('Codex did not return a sign-in URL.')
    LOGIN.update(running=True, error=None)
    def wait():
        try:
            for _ in range(600):
                result = getattr(rpc, 'login_result', None)
                if result is not None:
                    if not result.get('success'): raise RuntimeError(result.get('error') or 'Sign-in failed.')
                    account = rpc.call('account/read', {'refreshToken': False}).get('account')
                    row = normalize(account, rpc.call('account/rateLimits/read'), home)
                    if expected and row['id'] != expected:
                        raise RuntimeError('You signed into a different account. Reconnect the intended account.')
                    with LOCK:
                        rows = load(); previous = next((r for r in rows if r['id'] == row['id']), None)
                        row['warmup'] = (previous or {}).get('warmup', {})
                        save([r for r in rows if r['id'] != row['id']] + [row])
                    WAKE.set()
                    return
                time.sleep(1)
            raise RuntimeError('Sign-in timed out. Try connecting the account again.')
        except Exception as e:
            LOGIN['error'] = str(e)
            # Only a newly created, unsuccessful login directory is removed.
            rpc.close(); shutil.rmtree(home)
        finally: rpc.close(); LOGIN['running'] = False
    threading.Thread(target=wait, daemon=True).start()
    return {'url': url}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, code, value):
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
        if self.headers.get('Origin') in self.server.origins: self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin'))
        self.send_header('Vary', 'Origin'); self.end_headers(); self.wfile.write(json.dumps(value).encode())
    def do_OPTIONS(self):
        if self.headers.get('Origin') not in self.server.origins: return self.reply(403, {'error':'Origin denied'})
        self.send_response(204); self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin'))
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network','true'); self.end_headers()
    def route(self):
        if self.headers.get('Host') != '127.0.0.1:4318': return self.reply(403, {'error':'Host denied'})
        if self.headers.get('Origin') not in self.server.origins: return self.reply(403, {'error':'Origin denied'})
        if not secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+self.server.token): return self.reply(401, {'error':'Pair the dashboard with your local connector.'})
        try:
            if self.command == 'GET' and self.path == '/usage':
                result = refresh(); WAKE.set()
                return self.reply(200, {**result, 'login': LOGIN})
            if self.command == 'POST' and self.path.startswith('/login'):
                from urllib.parse import urlparse, parse_qs
                u = urlparse(self.path)
                if u.path == '/login': return self.reply(200, start_login(parse_qs(u.query).get('account', [None])[0]))
            return self.reply(404, {'error':'Not found'})
        except Exception as e: self.reply(500, {'error':str(e)})
    do_GET = route
    do_POST = route

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--origin', required=True); parser.add_argument('--allow-origin', action='append', default=[]); parser.add_argument('--open', action='store_true'); args = parser.parse_args()
    from urllib.parse import urlparse
    u=urlparse(args.origin)
    if u.scheme not in ('http','https') or not u.netloc or u.path not in ('','/'): parser.error('Use an origin such as https://example.vercel.app')
    if not BINARY: parser.error('Codex binary not found. Set CODEX_BIN.')
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700); (DATA/'accounts').mkdir(exist_ok=True,mode=0o700)
    path=DATA/'pairing-key'; token=path.read_text().strip() if path.exists() else secrets.token_urlsafe(32)
    if not path.exists(): path.write_text(token); path.chmod(0o600)
    server=ThreadingHTTPServer(('127.0.0.1',4318),Handler); server.origin=args.origin.rstrip('/'); server.origins={server.origin, *args.allow_origin}; server.token=token
    if args.open: webbrowser.open(server.origin+'/#pair='+token)
    print('Headroom connector listening on 127.0.0.1:4318. Credentials stay local.',flush=True)
    threading.Thread(target=scheduler, daemon=True).start()
    server.serve_forever()
if __name__ == '__main__': main()
