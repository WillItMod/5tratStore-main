"""Fixed recovery program sent over verified SSH. Host dependency: Umbrel's yq.

Only recipe metadata is writable here. Application lifecycle, including its
normal data migrations, remains Umbrel's responsibility. No uninstall/purge.
"""
import base64
import copy
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

SELF = 'willitmod-dev-fumbrel'
MAX_FILE = 2 * 1024 * 1024
POWPOW_SEEDS = ('data/postgres-init/2-schema.sql', 'data/postgres-init/3-multi-pool-partition.sql')
POWPOW = 'willitmod-dev-powpow'
POWPOW_STOP_GRACE = 930
# Immutable public node configurations from the observed historical indexes.
# Unknown images/policies need manual review, never an inferred safe stop.
POWPOW_NODES = {
    'litecoin': {
        'image': 'ghcr.io/willitmod/powpow-litecoin:0.2.32-dev',
        'index': 'sha256:dc271eec167e4c33fdefea6524cf40d16d52ec56b94f6dfb0f052d21ea81b6ba',
        'configs': {
            'amd64': 'sha256:da6a1cc5b59c0d3190a7d9d7a0b75109fef77758c56008ab13e0d864ac30b414',
            'arm64': 'sha256:da413e9f30ed8df5361f6e11a6b126b042b23088385ab1f0030e2b6adf726bde'},
    },
    'dogecoin': {
        'image': 'ghcr.io/willitmod/powpow-dogecoin:0.2.26-dev',
        'index': 'sha256:db33f11172b7cdbccc5cee80ca85d3b298039b54e43ed5e115cc4fd20b9a3077',
        'configs': {
            'amd64': 'sha256:304e5c54737066903bce7072c554f56fd7c9216a1a2f1652cd71ab40bdb7a0fb',
            'arm64': 'sha256:4b8f5b1b7cfcdc74fcaf63b9e6ca3f6849eb7c514f51a5698d410c71065a4e4e'},
    },
}
# Docker 29 may report an immutable index as image Id. Its selected platform
# must also match these exact rootfs diff IDs from the known config digests.
POWPOW_INDEX_ROOTFS = {'litecoin': {'amd64': ['sha256:1d69a5fd31932841d7825ef4780c06f008eea65aaa9f3110fe09d5832ed5c7d8',
                        'sha256:f952f3d014b93124e2ad48201fe2492e6d7b180b25843e6dc75e326d523c9d2a',
                        'sha256:4b1b0aa4b1cc3d7b7d499d358427c373df09bf5afb64c74c70ccc9ff35e36dcc',
                        'sha256:9283019c4e313e0b1775ae004f8356f1da85d68dc54e6d611a0e69094066c139',
                        'sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef'],
              'arm64': ['sha256:13a56b6535801be2adde694dabaf1c2df1d862a390661907dac821c42cd565cc',
                        'sha256:b9ce2cc5123feb58604bdb104c8ba7c4d976c412f52f9673abb8bae6e61a4e2a',
                        'sha256:36d67ecaacf02e3f546d10ecd6f3179db0d18b695557de63a46ec3f87bd7f6f4',
                        'sha256:0354a6cce242c583e502742982977f151d0f3e230d98930b1e8dc752310d28da',
                        'sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef']},
 'dogecoin': {'amd64': ['sha256:b2008ac19409fa6fee4b52596271400498aebd0be04dffac5351bd1dcf230f2a',
                        'sha256:a39f594bb2cb8ef59c6487de11f0550781a282069614b8bbc11c46857208af82',
                        'sha256:32bcf2631de2777f060c517c97a0bd26c04ebcd207866f659b3fe3d015f26841',
                        'sha256:6c23a77af1918ea3af0667d992b9fea821d7da448e6d53bfa07e4a7d765a2034',
                        'sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef'],
              'arm64': ['sha256:3bfd0b5a99a1f25a488230217defd5c2781ad861f692f5df22d9734bbddfc53d',
                        'sha256:afbf40ace108a8c74bfce7abde7f30dac764eb6ba0b7f30af97772a193682cfd',
                        'sha256:9ef15c60165e50196cbdf1affe05aeafcb4c0fa08fadd015f49b8ab831a0e6c9',
                        'sha256:32f1f2463f9af02846a1a294aa4abcf6a284b9499adab2a6c92151ae450809b7',
                        'sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef']}}


class RecoveryError(Exception):
    pass


def digest(body):
    return hashlib.sha256(body).hexdigest()


def allowed(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts and str(p) == name
            and (name in ('docker-compose.yml', 'umbrel-app.yml', 'exports.sh', 'torrc')
                 or (len(p.parts) == 1 and name.endswith('.template'))
                 or (len(p.parts) > 1 and p.parts[0] == 'hooks')))


def safe_path(root, name):
    if not allowed(name):
        raise RecoveryError('Unapproved recipe path. No changes made to that file.')
    p = root / name
    for component in [root, *p.relative_to(root).parents, p]:
        q = component if component.is_absolute() else root / component
        if q.is_symlink():
            raise RecoveryError('Recipe contains a symlink; manual review is required.')
    if p.exists():
        info = p.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
            raise RecoveryError('Recipe is not a regular bounded file; manual review is required.')
    return p


def read_file(root, name):
    path = safe_path(root, name)
    return path.read_bytes() if path.exists() else None


def atom_write(path, body, mode=0o644, uid=0, gid=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.fumbrel-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode & 0o777)
            if os.geteuid() == 0:
                os.fchown(stream.fileno(), uid, gid)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def command(argv, timeout=30, input_text=None):
    try:
        result = subprocess.run(argv, input=input_text, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RecoveryError('A host command timed out or is unavailable. Inspect Umbrel before retrying.') from None
    if result.returncode:
        # Never return subprocess output: Compose and Umbrel can include secrets.
        raise RecoveryError('Umbrel could not complete this step. The recipe backup is available; inspect Umbrel troubleshooting.')
    return result.stdout


def yaml_load(body):
    return json.loads(command(['yq', '-o=json', '.', '-'], input_text=body.decode('utf-8-sig')))


def yaml_dump(value):
    # JSON is YAML 1.2, including multiline strings and literal ${variables}.
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def version_tuple(value):
    # Keep Umbrel's historical four-part numeric versions, but compare the
    # prerelease identifiers using SemVer precedence. Build metadata has no
    # precedence. In particular, dev.1 must never be replaced by older dev.
    match = re.fullmatch(
        r'v?([0-9]+(?:\.[0-9]+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
        r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', str(value))
    if not match:
        raise RecoveryError('Unrecognized version; automatic replacement is disabled.')
    prerelease = match.group(2)
    if prerelease and any(part.isdigit() and len(part) > 1 and part.startswith('0')
                          for part in prerelease.split('.')):
        raise RecoveryError('Unrecognized version; automatic replacement is disabled.')
    return (tuple(int(part) for part in match.group(1).split('.')),
            None if prerelease is None else tuple(
                (0, int(part)) if part.isdigit() else (1, part)
                for part in prerelease.split('.')))


def is_newer(installed, target):
    (a, a_pre), (b, b_pre) = version_tuple(installed), version_tuple(target)
    count = max(len(a), len(b))
    a, b = a + (0,) * (count - len(a)), b + (0,) * (count - len(b))
    if a != b:
        return a > b
    if a_pre is None or b_pre is None:
        return a_pre is None and b_pre is not None
    return a_pre > b_pre


def fix_compose(value, app_id):
    value = copy.deepcopy(value)
    issues = []
    services = value.get('services', {})
    proxy = services.get('app_proxy', {})
    env = proxy.get('environment', {})
    if isinstance(env, list):
        env = dict(item.split('=', 1) for item in env if '=' in item)
    host = env.get('APP_HOST')
    if host:
        candidates = []
        for name, service in services.items():
            if name == 'app_proxy':
                continue
            networks = service.get('networks', {})
            aliases = [alias for network in (networks.values() if isinstance(networks, dict) else [])
                       for alias in (network or {}).get('aliases', [])]
            if host in [name, service.get('hostname'), service.get('container_name'),
                        f'{app_id}_{name}_1', f'{app_id}-{name}-1', *aliases]:
                candidates.append(name)
        if len(candidates) != 1:
            raise RecoveryError('Cannot identify a unique dashboard service. Manual recipe review is required.')
        service = services[candidates[0]]
        if service.get('hostname') != host:
            service['hostname'] = host
            issues.append('Declare dashboard hostname for the Umbrel 2 gateway')
    if app_id == 'willitmod-dev-fracattack':
        service = services.get('app', {})
        old_ports = service.get('ports', [])
        ports = []
        for port in old_ports:
            duplicate = (isinstance(port, str) and re.fullmatch(r'(?:0\.0\.0\.0:)?21225:3000(?:/tcp)?', port))
            duplicate = duplicate or (isinstance(port, dict) and str(port.get('published')) == '21225' and str(port.get('target')) == '3000' and port.get('protocol', 'tcp') == 'tcp')
            if not duplicate:
                ports.append(port)
        if ports != old_ports:
            if ports:
                service['ports'] = ports
            else:
                service.pop('ports', None)
            issues.append('Remove the duplicate dashboard port binding')
    if app_id == 'willitmod-dev-powpow':
        for name in ('litecoin', 'dogecoin'):
            if name in services and services[name].get('user') != '1000:1000':
                if services[name].get('user') not in (None, 'root', '0', '0:0'):
                    raise RecoveryError('Custom PowPow node ownership requires manual review.')
                services[name]['user'] = '1000:1000'
                issues.append(f'Run {name} as the existing data owner')
    return value, issues


class Engine:
    def __init__(self, app_path, catalog, emit=lambda event: None):
        self.home = Path(app_path)
        if not self.home.is_absolute() or self.home.name != SELF or self.home.parent.name != 'app-data':
            raise RecoveryError('The installed Fumbrel path is invalid.')
        if self.home.resolve() != self.home or not self.home.is_dir():
            raise RecoveryError('Fumbrel must use its regular Umbrel app-data directory.')
        self.root = self.home.parent.parent
        if not (self.root / 'umbrel.yaml').is_file():
            raise RecoveryError('Umbrel configuration was not found at the expected location.')
        self.catalog = catalog
        self.emit = emit
        self.backups = self.home / 'data' / 'backups'
        self.cli = shutil.which('umbreld') or '/usr/local/bin/umbreld'

    def installed(self):
        config = yaml_load((self.root / 'umbrel.yaml').read_bytes())
        apps = config.get('apps', [])
        if not isinstance(apps, list) or not all(isinstance(x, str) for x in apps):
            raise RecoveryError('Umbrel installed-app registry is not recognized.')
        return apps

    def appdir(self, app_id):
        if app_id not in self.catalog['apps'] or app_id == SELF or app_id not in self.installed():
            raise RecoveryError('Only installed, supported WillItMod apps can be recovered.')
        folder = self.root / 'app-data' / app_id
        if folder.resolve() != folder or not folder.is_dir():
            raise RecoveryError('App definition path is not a regular directory.')
        return folder

    def target(self, app_id):
        entry = self.catalog['apps'][app_id]
        files = {}
        for name, record in entry['files'].items():
            if not allowed(name):
                raise RecoveryError('Bundled package includes an unapproved file.')
            body = base64.b64decode(record['body'], validate=True)
            if digest(body) != record['sha256'] or len(body) > MAX_FILE:
                raise RecoveryError('Bundled package failed its integrity check.')
            # Preserve MAIN identity where the DEV package uses a different ID.
            if app_id != entry['source_id']:
                body = body.replace(entry['source_id'].encode(), app_id.encode())
            files[name] = body
        manifest = yaml_load(files['umbrel-app.yml'])
        manifest['id'] = app_id
        files['umbrel-app.yml'] = yaml_dump(manifest)
        for name in ('docker-compose.yml', 'docker-compose.yml.template'):
            if name in files:
                fixed, _ = fix_compose(yaml_load(files[name]), app_id)
                files[name] = yaml_dump(fixed)
        # Umbrel templates render at start. Its pre-start patch must also see
        # the Umbrel definition (AxeBC2's base Compose targets another platform).
        if 'docker-compose.yml.template' in files:
            files['docker-compose.yml'] = files['docker-compose.yml.template']
        return files

    def repair_plan(self, app_id):
        folder = self.appdir(app_id)
        changes, issues = {}, []
        entry = self.catalog['apps'][app_id]
        exports = read_file(folder, 'exports.sh')
        target_exports = entry['files'].get('exports.sh')
        if exports is not None:
            known_good = target_exports and digest(exports) == target_exports['sha256']
            if digest(exports) in self.catalog['legacy_exports'] and target_exports:
                changes['exports.sh'] = base64.b64decode(target_exports['body'])
                issues.append('Repair legacy auth lookup that blocks start, stop and update')
            elif not known_good:
                raise RecoveryError('Unrecognized exports.sh. Repair & update can replace it with the bundled package.')
        for name in ('docker-compose.yml', 'docker-compose.yml.template'):
            body = read_file(folder, name)
            if body:
                fixed, found = fix_compose(yaml_load(body), app_id)
                if found:
                    changes[name] = yaml_dump(fixed)
                    issues.extend(found)
        return changes, list(dict.fromkeys(issues))

    def require_existing_seeds(self, folder, entry):
        requirements = entry.get('required_existing_files', {})
        if entry['source_id'] != 'willitmod-dev-powpow' and not requirements:
            return
        if (entry['source_id'] != 'willitmod-dev-powpow' or not isinstance(requirements, dict)
                or set(requirements) != set(POWPOW_SEEDS)):
            raise RecoveryError('Bundled SQL prerequisite metadata is invalid. No changes were made.')
        for name in POWPOW_SEEDS:
            record = requirements[name]
            if (not isinstance(record, dict) or set(record) != {'sha256'}
                    or not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256'])):
                raise RecoveryError('Bundled SQL prerequisite metadata is invalid. No changes were made.')
            descriptor = None
            try:
                path = folder / name
                if path.resolve(strict=True) != path:
                    raise ValueError()
                # Open only these two fixed SQL names, using directory handles
                # and O_NOFOLLOW so ancestor changes cannot redirect the read.
                descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                parts = name.split('/')
                for part in parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = child
                child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
                    raise ValueError()
                hasher, total = hashlib.sha256(), 0
                while block := os.read(descriptor, 64 * 1024):
                    total += len(block)
                    if total > MAX_FILE:
                        raise ValueError()
                    hasher.update(block)
                if hasher.hexdigest() != record['sha256']:
                    raise ValueError()
            except (OSError, ValueError):
                raise RecoveryError('PowPow SQL seed files are missing, changed or unsafe. Use the normal Umbrel store update before Fumbrel package recovery. Changed or redirected seeds require manual review.') from None
            finally:
                if descriptor is not None:
                    os.close(descriptor)

    def scan(self):
        rows = []
        for app_id in sorted(set(self.installed()) & self.catalog['apps'].keys()):
            entry = self.catalog['apps'][app_id]
            row = {'id': app_id, 'name': entry['name'], 'target': entry['version'], 'channel': entry['channel'],
                   'source_commit': entry['source_commit'], 'installed': 'unknown', 'issues': [], 'can_update': False}
            try:
                folder = self.appdir(app_id)
                manifest = yaml_load(read_file(folder, 'umbrel-app.yml'))
                row['installed'] = str(manifest['version'])
                downgrade = is_newer(row['installed'], entry['version'])
                row['can_update'] = not downgrade
                row['main_identity'] = app_id != entry['source_id']
                try:
                    _, row['issues'] = self.repair_plan(app_id)
                    row['can_repair'] = True
                except RecoveryError as error:
                    row['issues'] = [str(error)]
                    row['can_repair'] = False
                if downgrade:
                    row['issues'].append('Installed version is newer than this recovery package; downgrade blocked')
                else:
                    try:
                        self.require_existing_seeds(folder, entry)
                    except RecoveryError as error:
                        row['can_update'] = False
                        row['issues'].append(str(error))
                row['running'] = bool(self.running(app_id))
            except (RecoveryError, KeyError, TypeError, ValueError):
                row.update(can_repair=False, can_update=False, issues=['Installed metadata needs manual review'])
            rows.append(row)
        return {'apps': rows, 'release': self.catalog['release'], 'backups': self.list_backups(),
                'scope': 'Installed WillItMod apps only. Unrecognized failures and CPU instruction crashes require separate diagnosis.'}

    def metadata_names(self, folder):
        names = set()
        for p in folder.iterdir():
            if p.name == 'hooks':
                if p.is_symlink():
                    raise RecoveryError('Hooks directory is a symlink; manual review is required.')
                if p.exists():
                    for child in p.rglob('*'):
                        if child.is_symlink():
                            raise RecoveryError('Hooks contain a symlink; manual review is required.')
                        if child.is_file():
                            names.add(child.relative_to(folder).as_posix())
            elif allowed(p.name):
                names.add(p.name)
        for name in names:
            safe_path(folder, name)
        return names

    def backup(self, app_id, names):
        folder = self.appdir(app_id)
        # Backups live below Fumbrel only, not below the app being repaired.
        for p in (self.home / 'data', self.backups):
            if p.is_symlink():
                raise RecoveryError('Backup directory cannot be a symlink.')
            p.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.backups, 0o700)
        backup_id = uuid.uuid4().hex
        destination = self.backups / backup_id
        destination.mkdir(mode=0o700)
        records = {}
        for name in sorted(names):
            path = safe_path(folder, name)
            if path.exists():
                body, info = path.read_bytes(), path.stat()
                records[name] = {'body': base64.b64encode(body).decode(), 'sha256': digest(body),
                                 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
            else:
                records[name] = None
        record = {'id': backup_id, 'app': app_id, 'created': int(time.time()), 'phase': 'backup-complete', 'files': records}
        self.save_backup(record)
        return record

    def save_backup(self, record):
        atom_write(self.backups / record['id'] / 'index.json', yaml_dump(record), 0o600)

    def list_backups(self):
        if self.backups.is_symlink():
            raise RecoveryError('Backup directory cannot be a symlink.')
        rows = []
        if self.backups.exists():
            for p in self.backups.iterdir():
                if p.is_symlink() or not re.fullmatch(r'[a-f0-9]{32}', p.name):
                    continue
                index = p / 'index.json'
                if index.is_symlink() or not index.is_file() or index.stat().st_size > 16 * MAX_FILE:
                    continue
                record = json.loads(index.read_text())
                rows.append({k: record[k] for k in ('id', 'app', 'created', 'phase')})
        return sorted(rows, key=lambda row: row['created'], reverse=True)

    def step(self, app_id, message):
        self.emit({'type': 'step', 'app': app_id, 'message': message})

    def running(self, app_id):
        ids = command(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + app_id]).split()
        if not ids:
            return []
        details = json.loads(command(['docker', 'inspect', *ids]))
        return [{'id': d['Id'], 'service': d['Config']['Labels'].get('com.docker.compose.service')}
                for d in details if d['State']['Running'] or d['State'].get('Paused')]

    def lifecycle(self, app_id, action):
        if action not in ('start', 'stop'):
            raise RecoveryError('Unsupported lifecycle action.')
        command([self.cli, 'client', 'apps.' + action + '.mutate', '--appId', app_id], timeout=1800)

    def stop_legacy_peercoin(self, app_id):
        """Protect the selected PPC node from its installed short stop grace.

        This changes no container/recipe setting. Docker's negative timeout
        sends the existing TERM signal and never escalates to SIGKILL, even
        after our bounded CLI observer has timed out.
        """
        if app_id != 'willitmod-dev-ppc':
            return
        folder = self.appdir(app_id)
        entry = self.catalog['apps'][app_id]
        if entry.get('source_id') != app_id:
            raise RecoveryError('Peercoin package identity needs manual review before stopping.')
        ids = command(['docker', 'ps', '-q', '--no-trunc', '--filter',
                       'label=com.docker.compose.project=' + app_id, '--filter',
                       'label=com.docker.compose.service=ppcd']).split()
        if not ids:
            return
        if len(ids) != 1 or not re.fullmatch('[0-9a-f]{64}', ids[0]):
            raise RecoveryError('Peercoin node identity is ambiguous. Inspect Umbrel before retrying.')
        cid = ids[0]
        try:
            record = entry['files']['docker-compose.yml']
            body = base64.b64decode(record['body'], validate=True)
            if len(body) > MAX_FILE or digest(body) != record['sha256']:
                raise ValueError()
            target = yaml_load(body)['services']['ppcd']
            # The reviewed bundle promises two minutes. A future policy needs
            # another explicit review instead of silently expanding this guard.
            if (target.get('stop_grace_period') not in ('2m', '120s', 120)
                    or target.get('stop_signal') != 'SIGTERM'):
                raise ValueError()
            installed = yaml_load(read_file(folder, 'docker-compose.yml'))['services']['ppcd']
            image = installed.get('image')
            if image is None:
                # The observed pre-immutable recipe built this exact context;
                # Compose named its local image willitmod-dev-ppc-ppcd.
                if installed.get('build') != {'context': '${APP_DATA_DIR}/data/peercoind'}:
                    raise ValueError()
                image = app_id + '-ppcd'
            elif (not isinstance(image, str) or 'build' in installed
                  or not image.startswith(('ghcr.io/willitmod/axeppc-peercoind:',
                                            'ghcr.io/willitmod/axeppc-peercoind@sha256:'))):
                raise ValueError()
            details = json.loads(command(['docker', 'inspect', cid]))
            if len(details) != 1:
                raise ValueError()
            before = details[0]
            config, state = before['Config'], before['State']
            labels = config['Labels']
            if (before['Id'] != cid or config['Image'] != image
                    or labels.get('com.docker.compose.project') != app_id
                    or labels.get('com.docker.compose.service') != 'ppcd'
                    or not state['Running'] or state.get('Paused') or state.get('Restarting')
                    or config.get('StopSignal') not in (None, '', 'TERM', 'SIGTERM', '15')):
                raise ValueError()
            images = json.loads(command(['docker', 'image', 'inspect', image]))
            if len(images) != 1 or images[0]['Id'] != before['Image']:
                raise ValueError()
            grace = config.get('StopTimeout')
            if grace is None:
                grace = 10  # Docker's Linux default, not an override.
            if isinstance(grace, bool) or not isinstance(grace, int):
                raise ValueError()
            started_at = datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00'))
        except (KeyError, TypeError, ValueError):
            raise RecoveryError('Peercoin stop policy or container identity needs manual review.') from None
        if grace < 0 or grace >= 120:
            return
        self.step(app_id, 'Waiting for Peercoin to shut down safely')
        started = time.monotonic()
        try:
            result = subprocess.run(['docker', 'stop', '--time', '-1', cid],
                                    text=True, capture_output=True, timeout=150)
        except subprocess.TimeoutExpired:
            raise RecoveryError('Peercoin shutdown is still pending. Fumbrel stopped here; inspect Umbrel and wait for a clean shutdown before retrying.') from None
        except OSError:
            raise RecoveryError('Docker is unavailable. Peercoin shutdown cannot be verified; inspect Umbrel before retrying.') from None
        if result.returncode:
            raise RecoveryError('Peercoin graceful shutdown could not be verified. Inspect Umbrel before retrying.')
        try:
            details = json.loads(command(['docker', 'inspect', cid]))
            if len(details) != 1:
                raise ValueError()
            after = details[0]
            state = after['State']
            if (after['Id'] != cid or after['Image'] != before['Image']
                    or after['Config']['Image'] != image
                    or after['Config']['Labels'] != before['Config']['Labels']
                    or state['StartedAt'] != before['State']['StartedAt']
                    or state['Running'] or state.get('Paused') or state.get('Restarting')
                    or state['ExitCode'] != 0 or state.get('OOMKilled')
                    or datetime.fromisoformat(state['FinishedAt'].replace('Z', '+00:00')) <= started_at):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RecoveryError('Peercoin did not have a verified clean shutdown. Fumbrel stopped here for review.') from None
        self.step(app_id, 'Peercoin stopped cleanly')
        return {'container': cid, 'exit': 0, 'seconds': round(time.monotonic() - started, 3)}

    def stop(self, app_id):
        self.stop_legacy_peercoin(app_id)
        self.stop_legacy_powpow(app_id)
        self.step(app_id, 'Stopping through Umbrel')
        # A failed normal stop is not permission to replace a live node recipe.
        self.lifecycle(app_id, 'stop')
        remaining = self.running(app_id)
        for container in remaining:
            if container['service'] == 'app_proxy':
                self.step(app_id, 'Removing the obsolete legacy dashboard proxy')
                command(['docker', 'stop', '--time', '20', container['id']], timeout=40)
                command(['docker', 'rm', container['id']])
        if self.running(app_id):
            raise RecoveryError('App containers are still running. No package replacement was performed.')

    def powpow_node_models(self, model):
        if not isinstance(model, dict) or not isinstance(model.get('services'), dict):
            raise ValueError()
        nodes = {}
        for service, known in POWPOW_NODES.items():
            node = model['services'][service]
            if (not isinstance(node, dict)
                    or node.get('image') not in (known['image'], known['image'] + '@' + known['index'])
                    or 'build' in node or node.get('command') is not None
                    or node.get('entrypoint') is not None or node.get('user') != '1000:1000'
                    or node.get('volumes') != ['${APP_DATA_DIR}/data:/data']
                    or node.get('stop_signal') not in (None, 'SIGTERM')
                    or node.get('stop_grace_period') not in (None, '10s', 10, '15m30s', '930s', 930)):
                raise ValueError()
            nodes[service] = node
        return nodes

    def require_powpow_target_policy(self, app_id):
        if app_id != POWPOW:
            return
        try:
            entry = self.catalog['apps'][app_id]
            if entry['source_id'] != POWPOW:
                raise ValueError()
            record = entry['files']['docker-compose.yml']
            body = base64.b64decode(record['body'], validate=True)
            if len(body) > MAX_FILE or digest(body) != record['sha256']:
                raise ValueError()
            nodes = self.powpow_node_models(yaml_load(body))
            if any(node.get('stop_signal') != 'SIGTERM'
                   or node.get('stop_grace_period') not in ('15m30s', '930s', 930)
                   for node in nodes.values()):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RecoveryError('The bundled PowPow shutdown policy is outdated or unknown. Install a newer Fumbrel release before updating PowPow.') from None

    def stop_legacy_powpow(self, app_id):
        """Stop only the two admitted old Core nodes without Docker escalation."""
        if app_id != POWPOW:
            return
        folder = self.appdir(app_id)
        try:
            if self.catalog['apps'][app_id]['source_id'] != POWPOW:
                raise ValueError()
            ids = command(['docker', 'ps', '-aq', '--no-trunc', '--filter',
                           'label=com.docker.compose.project=' + app_id]).split()
            if len(set(ids)) != len(ids) or any(not re.fullmatch('[0-9a-f]{64}', cid) for cid in ids):
                raise ValueError()
            details = json.loads(command(['docker', 'inspect', *ids])) if ids else []
            if len(details) != len(ids) or {row['Id'] for row in details} != set(ids):
                raise ValueError()
            if not any(row['State']['Running'] or row['State'].get('Paused')
                       or row['State'].get('Restarting') for row in details):
                return {'stopped': [], 'no_running_project': True}
            body = read_file(folder, 'docker-compose.yml')
            if body is None:
                raise ValueError()
            installed = self.powpow_node_models(yaml_load(body))
            data = folder / 'data'
            if data.is_symlink() or data.resolve() != data or not data.is_dir():
                raise ValueError()
            nodes = {}
            for row in details:
                labels = row['Config']['Labels']
                if labels.get('com.docker.compose.project') != app_id:
                    raise ValueError()
                service = labels.get('com.docker.compose.service')
                if service not in POWPOW_NODES:
                    continue
                if service in nodes:
                    raise ValueError()
                nodes[service] = row
            if set(nodes) != set(POWPOW_NODES):
                raise ValueError()
            short, never_started = [], []
            lifecycle_fields = ('Status', 'Running', 'Paused', 'Restarting', 'OOMKilled',
                                'Dead', 'Pid', 'ExitCode', 'Error', 'StartedAt', 'FinishedAt')
            for service, before in nodes.items():
                config, state, known = before['Config'], before['State'], POWPOW_NODES[service]
                images = json.loads(command(['docker', 'image', 'inspect', installed[service]['image']]))
                if len(images) != 1:
                    raise ValueError()
                image = images[0]
                arch = image.get('Architecture')
                index_identity = (before['Image'] == known['index']
                                  and arch in known['configs']
                                  and image.get('RootFS', {}).get('Type') == 'layers'
                                  and image['RootFS'].get('Layers') == POWPOW_INDEX_ROOTFS[service][arch])
                if (image['Id'] != before['Image']
                        or not (known['configs'].get(arch) == before['Image'] or index_identity)
                        or config['Image'] != installed[service]['image']
                        or config.get('User') != '1000:1000'
                        or config.get('Entrypoint') != ['/usr/local/bin/start-' + service]
                        or config.get('Cmd') not in (None, [])
                        or config.get('StopSignal') not in (None, '', 'TERM', 'SIGTERM', '15')
                        or state.get('Paused') or state.get('Restarting') or state.get('OOMKilled')):
                    raise ValueError()
                mounts = before['Mounts']
                if (len(mounts) != 1 or mounts[0].get('Type') != 'bind'
                        or mounts[0].get('Destination') != '/data' or mounts[0].get('Source') != str(data)
                        or mounts[0].get('RW') is not True):
                    raise ValueError()
                grace = config.get('StopTimeout')
                grace = 10 if grace is None else grace
                if isinstance(grace, bool) or not isinstance(grace, int) or grace not in (10, POWPOW_STOP_GRACE, -1):
                    raise ValueError()
                zero_time = lambda value: isinstance(value, str) and re.fullmatch(r'0001-01-01T00:00:00(?:\.0+)?Z', value)
                created = (state.get('Status') == 'created'
                           and all(state.get(key) is False for key in ('Running', 'Paused', 'Restarting', 'OOMKilled', 'Dead'))
                           and type(state.get('Pid')) is int and state['Pid'] == 0
                           and type(state.get('ExitCode')) is int and state['ExitCode'] == 0
                           and state.get('Error') == ''
                           and zero_time(state.get('StartedAt')) and zero_time(state.get('FinishedAt')))
                node_data = data / service
                if (node_data.is_symlink() or node_data.resolve() != node_data
                        or (not node_data.is_dir() and not (created and not node_data.exists()))):
                    raise ValueError()
                started = datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00'))
                if created:
                    never_started.append(before['Id'])
                elif not state['Running']:
                    if (state['ExitCode'] != 0
                            or zero_time(state['StartedAt'])
                            or datetime.fromisoformat(state['FinishedAt'].replace('Z', '+00:00')) <= started):
                        raise ValueError()
                elif grace == 10:
                    short.append(before['Id'])
            latest = json.loads(command(['docker', 'inspect', *[row['Id'] for row in nodes.values()]]))
            if len(latest) != 2 or {row['Id'] for row in latest} != {row['Id'] for row in nodes.values()}:
                raise ValueError()
            for row in latest:
                before = nodes[row['Config']['Labels']['com.docker.compose.service']]
                if (any(row[key] != before[key] for key in ('Id', 'Image', 'Config', 'Mounts'))
                        or any(row['State'].get(key) != before['State'].get(key)
                               for key in lifecycle_fields)):
                    raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RecoveryError('PowPow node identity, data mount or stop policy needs manual review before stopping.') from None
        if not short:
            if never_started:
                return {'stopped': [], 'no_preparatory_stop_required': True, 'never_started': never_started}
            return {'stopped': [], 'adequate_or_cleanly_stopped': True}
        self.step(app_id, 'Waiting for Litecoin and Dogecoin to shut down safely')
        # Admit both nodes before sending either signal. One bounded client
        # request sends TERM only; an observer timeout never kills either node.
        try:
            result = subprocess.run(['docker', 'stop', '--time', '-1', *short],
                                    text=True, capture_output=True, timeout=960)
        except subprocess.TimeoutExpired:
            raise RecoveryError('PowPow node shutdown is still pending. Fumbrel stopped here; inspect Umbrel and wait for clean shutdown before retrying.') from None
        except OSError:
            raise RecoveryError('Docker is unavailable. PowPow shutdown cannot be verified; inspect Umbrel before retrying.') from None
        if result.returncode:
            raise RecoveryError('PowPow graceful shutdown could not be verified. Inspect Umbrel before retrying.')
        try:
            after = json.loads(command(['docker', 'inspect', *[row['Id'] for row in nodes.values()]]))
            if len(after) != 2 or {row['Id'] for row in after} != {row['Id'] for row in nodes.values()}:
                raise ValueError()
            for row in after:
                service = row['Config']['Labels']['com.docker.compose.service']
                before = nodes[service]
                if any(row[key] != before[key] for key in ('Id', 'Image', 'Config', 'Mounts')):
                    raise ValueError()
                state = row['State']
                if state['StartedAt'] != before['State']['StartedAt'] or state.get('OOMKilled'):
                    raise ValueError()
                if row['Id'] in short:
                    if (state['Running'] or state.get('Paused') or state.get('Restarting') or state['ExitCode'] != 0
                            or datetime.fromisoformat(state['FinishedAt'].replace('Z', '+00:00')) <= datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00'))):
                        raise ValueError()
                elif any(state.get(key) != before['State'].get(key) for key in lifecycle_fields):
                    raise ValueError()
            current = command(['docker', 'ps', '-aq', '--no-trunc', '--filter',
                               'label=com.docker.compose.project=' + app_id]).split()
            if set(current) != set(ids) or len(current) != len(ids):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RecoveryError('PowPow did not have verified clean same-generation shutdown. Fumbrel stopped here for review.') from None
        self.step(app_id, 'Legacy PowPow nodes stopped cleanly')
        result = {'stopped': short, 'exit': 0}
        if never_started:
            result['never_started'] = never_started
        return result

    def write_changes(self, folder, changes, entry=None):
        for name, body in changes.items():
            path = safe_path(folder, name)
            previous = path.stat() if path.exists() else None
            # A full package update must retain the executable bits from Git,
            # including when replacing an existing hook with a broken mode.
            # Metadata-only repairs preserve the installed file's mode.
            bundled_mode = (entry or {}).get('files', {}).get(name, {}).get('mode')
            mode = bundled_mode if bundled_mode is not None else (previous.st_mode & 0o777 if previous else 0o644)
            if body is None:
                if path.exists():
                    path.unlink()
            else:
                atom_write(path, body, mode, previous.st_uid if previous else 0, previous.st_gid if previous else 0)

    def recover(self, app_id, mode, start):
        if mode not in ('repair', 'update') or not isinstance(start, bool):
            raise RecoveryError('Invalid recovery options.')
        folder = self.appdir(app_id)
        entry = self.catalog['apps'][app_id]
        installed = str(yaml_load(read_file(folder, 'umbrel-app.yml'))['version'])
        if mode == 'update' and is_newer(installed, entry['version']):
            raise RecoveryError('Downgrades are blocked. Install a newer Fumbrel release first.')
        if mode == 'update':
            self.require_powpow_target_policy(app_id)
            self.require_existing_seeds(folder, entry)
            target = self.target(app_id)
            # Only exports is replaced before stop; all other metadata waits
            # until normal Umbrel stop has completed and no nodes are running.
            bootstrap = {}
            if 'exports.sh' in target and read_file(folder, 'exports.sh') != target['exports.sh']:
                bootstrap['exports.sh'] = target['exports.sh']
            names = self.metadata_names(folder) | set(target)
            changes = {name: target.get(name) for name in names}
        else:
            changes, _ = self.repair_plan(app_id)
            bootstrap = {name: body for name, body in changes.items() if name == 'exports.sh'}
            names = self.metadata_names(folder) | set(changes)
        record = self.backup(app_id, names)
        self.emit({'type': 'backup', 'app': app_id, 'backup': record['id']})
        try:
            record['phase'] = 'bootstrapping-stop'
            self.save_backup(record)
            self.write_changes(folder, bootstrap)
            self.stop(app_id)
            record['phase'] = 'applying-recipe'
            self.save_backup(record)
            self.step(app_id, 'Applying verified package' if mode == 'update' else 'Applying compatibility repairs')
            self.write_changes(folder, changes, entry if mode == 'update' else None)
            record['phase'] = 'recipe-applied'
            self.save_backup(record)
            if start:
                record['phase'] = 'starting'
                self.save_backup(record)
                self.step(app_id, 'Starting through Umbrel; normal app migrations may run')
                self.lifecycle(app_id, 'start')
                if not self.running(app_id):
                    raise RecoveryError('Umbrel returned from start but no app containers are running.')
            record['phase'] = 'complete-started' if start else 'complete-stopped'
            self.save_backup(record)
            return {'app': app_id, 'ok': True, 'backup': record['id'], 'state': 'started' if start else 'stopped',
                    'version': entry['version'] if mode == 'update' else installed}
        except Exception:
            # Deliberately retain the checkpoint. Never auto-restore an old
            # binary after a new binary could have migrated persistent data.
            record['phase'] = 'needs-review-' + record['phase']
            self.save_backup(record)
            raise

    def restore(self, backup_id):
        if not re.fullmatch(r'[a-f0-9]{32}', backup_id):
            raise RecoveryError('Invalid backup identifier.')
        candidates = {row['id']: row for row in self.list_backups()}
        if backup_id not in candidates:
            raise RecoveryError('Backup not found.')
        record = json.loads((self.backups / backup_id / 'index.json').read_text())
        app_id = record['app']
        folder = self.appdir(app_id)
        if self.running(app_id):
            raise RecoveryError('Stop the app in Umbrel before restoring a recipe backup.')
        files = record['files']
        for name, item in files.items():
            safe_path(folder, name)
            if item:
                body = base64.b64decode(item['body'], validate=True)
                if digest(body) != item['sha256'] or len(body) > MAX_FILE:
                    raise RecoveryError('Backup integrity check failed.')
        current = self.backup(app_id, set(files) | self.metadata_names(folder))
        for name, item in files.items():
            path = safe_path(folder, name)
            if item:
                atom_write(path, base64.b64decode(item['body']), item['mode'], item['uid'], item['gid'])
            elif path.exists():
                path.unlink()
        record['phase'] = 'restored-stopped'
        self.save_backup(record)
        return {'app': app_id, 'ok': True, 'state': 'stopped', 'backup': current['id'],
                'message': 'Recipe restored. App data was not rolled back. Review compatibility before starting.'}


def main():
    def emit(event):
        print(json.dumps(event), flush=True)
    try:
        # With passwordless sudo, the password line remains unread on stdin.
        prefix = 'FUMBREL_REQUEST_V1:'
        line = sys.stdin.readline()
        if not line.startswith(prefix):
            line = sys.stdin.readline()
        if not line.startswith(prefix):
            raise RecoveryError('Invalid recovery request framing.')
        request = json.loads(line[len(prefix):])
        if os.geteuid() != 0:
            raise RecoveryError('Administrator access through sudo is required.')
        engine = Engine(request['app_path'], request['catalog'], emit)
        lock_path = engine.home / '.fumbrel-recovery.lock'
        if lock_path.is_symlink():
            raise RecoveryError('Recovery lock cannot be a symlink.')
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RecoveryError('Another Fumbrel recovery is running. Wait for it to finish.') from None
            action = request['action']
            if action == 'scan':
                result = engine.scan()
            elif action == 'recover':
                result = engine.recover(request['app'], request['mode'], request['start'])
            elif action == 'restore':
                result = engine.restore(request['backup'])
            else:
                raise RecoveryError('Unsupported recovery action.')
            emit({'type': 'result', 'result': result})
    except RecoveryError as error:
        emit({'type': 'error', 'message': str(error)})
        return 1
    except Exception:
        emit({'type': 'error', 'message': 'Recovery stopped on an unexpected host condition. Existing recipe backups are retained.'})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
