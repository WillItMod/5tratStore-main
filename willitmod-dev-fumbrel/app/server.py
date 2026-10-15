"""Fumbrel web UI. SSH credentials and browser sessions are memory-only."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory
import paramiko

BASE = Path(__file__).resolve().parent
CATALOG = json.loads((BASE / 'catalog.json').read_text())
ENGINE = (BASE / 'engine.py').read_text()
SSH_HOST = 'host.docker.internal'
KEY_FILE = Path('/host/ssh_host_ed25519_key.pub')
APP_PATH = os.environ.get('FUMBREL_APP_PATH', '')
SESSION_TTL = 30 * 60
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
sessions = {}
jobs = {}
guard = threading.Lock()
job_lock = threading.Lock()
failed_logins = []


def expire_sessions():
    now = time.monotonic()
    with guard:
        for expired in [key for key, value in sessions.items() if now - value['last'] > SESSION_TTL]:
            sessions.pop(expired)['credentials'].clear()


def reap_sessions():
    while True:
        time.sleep(30)
        expire_sessions()


threading.Thread(target=reap_sessions, daemon=True).start()


class AccessError(Exception):
    pass


def host_key():
    try:
        kind, encoded, *_ = KEY_FILE.read_text().strip().split()
        if kind != 'ssh-ed25519':
            raise ValueError()
        return paramiko.Ed25519Key(data=base64.b64decode(encoded, validate=True))
    except Exception:
        raise AccessError('The host SSH public key is unavailable. Check that SSH is enabled on Umbrel, then restart Fumbrel.') from None


def fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def remote(credentials, action, event=lambda item: None, **kwargs):
    key = host_key()
    client = paramiko.SSHClient()
    client.get_host_keys().add(SSH_HOST, key.get_name(), key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(SSH_HOST, port=22, username=credentials['username'], password=credentials['password'],
                       look_for_keys=False, allow_agent=False, timeout=12, auth_timeout=15, banner_timeout=15)
        transport = client.get_transport()
        transport.set_keepalive(20)
        stdin, stdout, stderr = client.exec_command('sudo -k -S -p \'\' python3 -c ' + shlex.quote(ENGINE), timeout=3700)
        payload = {'action': action, 'app_path': APP_PATH, 'catalog': CATALOG, **kwargs}
        stdin.write(credentials['sudo_password'] + '\n')
        stdin.write('FUMBREL_REQUEST_V1:' + json.dumps(payload) + '\n')
        stdin.flush()
        stdin.channel.shutdown_write()
        result, error = None, None
        for line in stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('type') == 'result':
                result = message['result']
            elif message.get('type') == 'error':
                error = message['message']
            else:
                event(message)
        status = stdout.channel.recv_exit_status()
        if error:
            raise AccessError(error)
        if status or result is None:
            raise AccessError('Administrator access failed or the SSH session ended. Check the sudo password and scan again before retrying.')
        return result
    except paramiko.BadHostKeyException:
        raise AccessError('SSH host key mismatch. No credentials were sent to the unexpected host.') from None
    except paramiko.AuthenticationException:
        raise AccessError('SSH login was rejected. Check your Umbrel SSH username and password.') from None
    except AccessError:
        raise
    except Exception:
        raise AccessError('Cannot reach this Umbrel over SSH. Check SSH availability and scan again before retrying.') from None
    finally:
        client.close()


def authenticated():
    token = request.headers.get('X-Fumbrel-Session', '')
    now = time.monotonic()
    expire_sessions()
    with guard:
        session = sessions.get(token)
        if session:
            session['last'] = now
            return token, session
    raise AccessError('Your recovery session has ended. Sign in again.')


@app.before_request
def protect():
    if request.path.startswith('/api/'):
        if request.headers.get('X-Fumbrel-Client') != '1':
            return jsonify(error='This request must come from Fumbrel.'), 403
        origin = request.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.netloc != request.host:
                return jsonify(error='Cross-origin requests are blocked.'), 403
        if request.method == 'POST' and not request.is_json:
            return jsonify(error='JSON request required.'), 415
        if request.path not in ('/api/info', '/api/login'):
            try:
                authenticated()
            except AccessError as error:
                return jsonify(error=str(error)), 401


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.errorhandler(AccessError)
def access_error(error):
    return jsonify(error=str(error)), 400


@app.get('/')
def index():
    return send_from_directory(BASE / 'static', 'index.html')


@app.get('/health')
def health():
    return jsonify(ok=True)


@app.get('/api/info')
def info():
    return jsonify(version=CATALOG['release'], fingerprint=fingerprint(host_key()), packages=14)


@app.post('/api/login')
def login():
    data = request.get_json()
    if not isinstance(data, dict) or set(data) - {'username', 'password', 'sudo_password'}:
        raise AccessError('Invalid login request.')
    username, password = data.get('username', 'umbrel'), data.get('password', '')
    sudo_password = data.get('sudo_password') or password
    if not isinstance(username, str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username):
        raise AccessError('Enter a valid SSH username.')
    if any(not isinstance(secret, str) or not secret or len(secret) > 1024 or '\n' in secret or '\r' in secret
           for secret in (password, sudo_password)):
        raise AccessError('Enter a valid SSH password.')
    now = time.monotonic()
    with guard:
        failed_logins[:] = [stamp for stamp in failed_logins if now - stamp < 300]
        if len(failed_logins) >= 5:
            return jsonify(error='Too many login attempts. Wait five minutes before trying again.'), 429
        failed_logins.append(now)
    credentials = {'username': username, 'password': password, 'sudo_password': sudo_password}
    result = remote(credentials, 'scan')
    token = secrets.token_urlsafe(32)
    with guard:
        failed_logins.remove(now)
        # A bounded session table avoids retaining unlimited admin credentials.
        if len(sessions) >= 8:
            oldest = min(sessions, key=lambda key: sessions[key]['last'])
            sessions.pop(oldest)['credentials'].clear()
        sessions[token] = {'credentials': credentials, 'last': time.monotonic()}
    return jsonify(token=token, scan=result)


@app.post('/api/logout')
def logout():
    token, _ = authenticated()
    with guard:
        previous = sessions.pop(token, None)
        if previous:
            previous['credentials'].clear()
    return jsonify(ok=True)


@app.get('/api/scan')
def scan():
    _, session = authenticated()
    if job_lock.locked():
        return jsonify(error='Recovery is running. Scan again when it finishes.'), 409
    return jsonify(remote(session['credentials'], 'scan'))


def run_job(job, credentials, action, selected, mode, start, backup):
    def event(item):
        with guard:
            if len(job['events']) < 500:
                job['events'].append({**item, 'time': int(time.time())})
    try:
        for app_id in selected if action == 'recover' else [None]:
            try:
                kwargs = {'app': app_id, 'mode': mode, 'start': start} if action == 'recover' else {'backup': backup}
                result = remote(credentials, action, event, **kwargs)
            except AccessError as error:
                result = {'app': app_id, 'ok': False, 'error': str(error)}
            with guard:
                job['results'].append(result)
            if not result['ok']:
                event({'type': 'step', 'app': app_id, 'message': 'Stopped here for review. Remaining selected apps were not changed.'})
                break
    finally:
        credentials.clear()
        with guard:
            job['status'] = 'complete' if all(row['ok'] for row in job['results']) and job['results'] else 'needs-review'
        job_lock.release()


@app.post('/api/jobs')
def create_job():
    token, session = authenticated()
    data = request.get_json()
    if not isinstance(data, dict) or set(data) - {'action', 'apps', 'mode', 'start', 'backup'}:
        raise AccessError('Invalid recovery request.')
    action = data.get('action', 'recover')
    selected, mode, start, backup = data.get('apps', []), data.get('mode'), data.get('start', False), data.get('backup', '')
    if action == 'recover':
        if (not isinstance(selected, list) or not selected or len(selected) > 18
                or any(not isinstance(item, str) or item not in CATALOG['apps'] for item in selected)
                or len(set(selected)) != len(selected) or mode not in ('repair', 'update') or not isinstance(start, bool)):
            raise AccessError('Select supported apps and a recovery action.')
    elif action != 'restore' or not isinstance(backup, str) or not re.fullmatch(r'[a-f0-9]{32}', backup):
        raise AccessError('Invalid recovery action or backup.')
    if not job_lock.acquire(blocking=False):
        return jsonify(error='Another recovery is already running.'), 409
    job_id = secrets.token_hex(16)
    job = {'id': job_id, 'owner': token, 'status': 'running', 'action': action, 'mode': mode,
           'events': [], 'results': [], 'created': int(time.time())}
    with guard:
        while len(jobs) >= 30:
            jobs.pop(next(iter(jobs)))
        jobs[job_id] = job
    threading.Thread(target=run_job, args=(job, dict(session['credentials']), action, selected, mode, start, backup), daemon=True).start()
    return jsonify(id=job_id), 202


@app.get('/api/jobs/<job_id>')
def get_job(job_id):
    token, _ = authenticated()
    with guard:
        job = jobs.get(job_id)
        if not job or job['owner'] != token:
            return jsonify(error='Recovery job not found in this session.'), 404
        return jsonify({key: value for key, value in job.items() if key != 'owner'})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8099, debug=False)
