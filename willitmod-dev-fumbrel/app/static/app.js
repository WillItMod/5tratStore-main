'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('fumbrel-session') || '';
let scan = null, job = null, busy = false;
const selected = new Set();
function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notice(message) { $('notice').textContent = message; $('notice').classList.toggle('hidden', !message); }
async function api(path, data) {
  const headers = {'X-Fumbrel-Client': '1'};
  if (token) headers['X-Fumbrel-Session'] = token;
  const options = {headers, cache: 'no-store'};
  if (data !== undefined) { headers['Content-Type'] = 'application/json'; options.method = 'POST'; options.body = JSON.stringify(data); }
  const response = await fetch('/api/' + path, options);
  let value;
  try { value = await response.json(); } catch { throw new Error('Fumbrel could not read the response. Check that the app is still running.'); }
  if (response.status === 401) disconnect();
  if (!response.ok) throw new Error(value.error || 'Request failed.');
  return value;
}
function disconnect() {
  token = ''; sessionStorage.removeItem('fumbrel-session'); sessionStorage.removeItem('fumbrel-job');
  $('workspace').classList.add('hidden'); $('logout').classList.add('hidden'); $('login-panel').classList.remove('hidden');
  selected.clear();
}
function actions() {
  $('selected-count').textContent = `${selected.size} selected`;
  const rows = (scan?.apps || []).filter(row => selected.has(row.id));
  $('repair').disabled = busy || !rows.length || rows.some(row => !row.can_repair);
  $('update').disabled = busy || !rows.length || rows.some(row => !row.can_update);
  $('rescan').disabled = busy;
  $('start-after').disabled = busy;
  $('select-all').disabled = busy;
  document.querySelectorAll('.app-select, .restore').forEach(el => { el.disabled = busy || el.dataset.unavailable === 'true'; });
  $('logout').disabled = busy;
}
function renderScan(value) {
  scan = value;
  $('login-panel').classList.add('hidden'); $('workspace').classList.remove('hidden'); $('logout').classList.remove('hidden');
  $('app-count').textContent = scan.apps.length;
  $('issue-count').textContent = scan.apps.filter(row => row.issues.length).length;
  $('backup-count').textContent = scan.backups.length;
  $('app-list').replaceChildren();
  for (const row of scan.apps) {
    const entry = element('div', undefined, 'app-row');
    const input = document.createElement('input'); input.type = 'checkbox'; input.className = 'app-select'; input.setAttribute('aria-label', 'Select ' + row.name);
    input.dataset.unavailable = String(!row.can_repair && !row.can_update); input.checked = selected.has(row.id);
    input.addEventListener('change', () => { input.checked ? selected.add(row.id) : selected.delete(row.id); actions(); });
    const body = element('div'); const name = element('div', row.name, 'app-name');
    name.append(element('span', row.running ? 'RUNNING' : 'STOPPED', 'flag'));
    body.append(name, element('div', row.id, 'app-id'));
    body.append(element('div', row.issues.length ? row.issues.join(' · ') : 'No known recipe fixes needed. Package can still be reapplied.', 'app-issues'));
    const versions = element('div', undefined, 'versions'); versions.append(element('span', row.installed), element('span', '↓ bundled ' + row.channel, 'arrow'), element('span', row.target, 'target'));
    entry.append(input, body, versions); $('app-list').append(entry);
  }
  if (!scan.apps.length) $('app-list').append(element('div', 'No supported WillItMod apps are installed on this Umbrel.', 'empty'));
  $('backups-list').replaceChildren();
  for (const backup of scan.backups) {
    const row = element('div', undefined, 'backup-row'); const info = element('div');
    info.append(element('strong', backup.app), element('div', new Date(backup.created * 1000).toLocaleString() + ' · ' + backup.phase, 'backup-meta'));
    const button = element('button', 'Restore recipe', 'secondary restore'); button.addEventListener('click', () => reviewRestore(backup));
    row.append(info, button); $('backups-list').append(row);
  }
  if (!scan.backups.length) $('backups-list').append(element('p', 'Backups appear here after your first recovery.', 'muted'));
  actions();
}
async function refresh() {
  try { notice(''); $('rescan').disabled = true; renderScan(await api('scan')); }
  catch (error) { notice(error.message); }
  finally { actions(); }
}
function confirmation(title, text, lines, label) {
  $('review-title').textContent = title; $('review-text').textContent = text; $('review-apps').replaceChildren(...lines.map(line => element('li', line))); $('confirm').textContent = label;
  const dialog = $('review'); dialog.returnValue = ''; dialog.showModal();
  return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once: true}));
}
async function recover(mode) {
  const rows = scan.apps.filter(row => selected.has(row.id));
  const start = $('start-after').checked;
  const confirmed = await confirmation(mode === 'update' ? 'Repair & update these apps?' : 'Repair these apps?',
    `${rows.length} app(s) will be stopped and ${mode === 'update' ? 'receive the bundled packages' : 'have recognized recipe problems repaired'}. ${start ? 'Apps will then start; normal app data migrations may run.' : 'Apps will remain stopped until you start them in Umbrel.'}`,
    rows.map(row => row.name + ' · ' + row.installed + (mode === 'update' ? ' → ' + row.target + ' (' + row.channel + ')' : ' · keep this version')), 'Begin recovery');
  if (confirmed) await launch({action: 'recover', apps: rows.map(row => row.id), mode, start});
}
async function reviewRestore(backup) {
  if (await confirmation('Restore this recipe?', 'The app must be stopped. This cannot undo changes an updated app made to its data. A backup of the current recipe will also be saved.', [backup.app, new Date(backup.created * 1000).toLocaleString()], 'Restore & leave stopped')) {
    await launch({action: 'restore', backup: backup.id});
  }
}
async function launch(payload) {
  busy = true; actions(); notice('');
  try { const result = await api('jobs', payload); sessionStorage.setItem('fumbrel-job', result.id); await poll(result.id); }
  catch (error) { notice(error.message); busy = false; actions(); }
}
async function poll(id) {
  busy = true; actions(); $('job-panel').classList.remove('hidden');
  try {
    job = await api('jobs/' + id);
    $('job-title').textContent = job.status === 'running' ? 'Working on it…' : job.status === 'complete' ? 'Recovery complete.' : 'Paused for a closer look.';
    $('events').replaceChildren(...job.events.map(event => {
      const li = element('li'); li.append(element('time', new Date(event.time * 1000).toLocaleTimeString()), element('span', (event.app || '') + ' · ' + (event.message || 'Recipe backup saved'))); return li;
    }));
    $('results').replaceChildren(...job.results.map(result => element('div', (result.app || 'Restore') + ' · ' + (result.ok ? (result.message || `Recipe applied. App ${result.state}.`) : result.error), 'result' + (result.ok ? '' : ' error'))));
    if (job.status === 'running') { setTimeout(() => poll(id), 1800); return; }
    busy = false; sessionStorage.removeItem('fumbrel-job'); await refresh();
  } catch (error) { busy = false; notice(error.message + ' An interrupted browser connection does not cancel a host operation. Scan before retrying.'); actions(); }
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); notice(''); $('connect').disabled = true; $('connect').textContent = 'Connecting & scanning…';
  const credentials = {username: $('username').value, password: $('password').value, sudo_password: $('sudo-password').value};
  $('password').value = ''; $('sudo-password').value = '';
  try { const result = await api('login', credentials); token = result.token; sessionStorage.setItem('fumbrel-session', token); renderScan(result.scan); }
  catch (error) { notice(error.message); }
  finally { credentials.password = ''; credentials.sudo_password = ''; $('connect').disabled = false; $('connect').textContent = 'Connect & scan ↗'; }
});
$('logout').addEventListener('click', async () => { try { await api('logout', {}); } finally { disconnect(); } });
$('rescan').addEventListener('click', refresh);
$('select-all').addEventListener('change', () => { selected.clear(); if ($('select-all').checked) scan.apps.filter(row => row.can_repair || row.can_update).forEach(row => selected.add(row.id)); renderScan(scan); });
$('repair').addEventListener('click', () => recover('repair'));
$('update').addEventListener('click', () => recover('update'));
$('report').addEventListener('click', () => {
  const report = {fumbrel: scan?.release, generated: new Date().toISOString(), scan, job};
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const link = element('a'); link.href = url; link.download = 'fumbrel-recovery-report.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try { const info = await api('info'); $('version').textContent = info.version; $('fingerprint').textContent = info.fingerprint; }
  catch (error) { notice(error.message); }
  if (token) {
    const activeJob = sessionStorage.getItem('fumbrel-job');
    if (activeJob) { $('login-panel').classList.add('hidden'); $('workspace').classList.remove('hidden'); $('logout').classList.remove('hidden'); await poll(activeJob); }
    else await refresh();
  }
})();
