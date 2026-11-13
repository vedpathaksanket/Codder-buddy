'use strict';
let token = '', selected = null, timer = null, revision = 0, fileRevision = 0, providerReady = false, importBrief = '';
const $ = id => document.getElementById(id);
const tell = message => { $('notice').textContent = message; };
async function api(path, options = {}) {
  const res = await fetch(path, {...options, headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...options.headers}});
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try { const data = await res.json(); message = typeof data.detail === 'string' ? data.detail : 'Please check the project description.'; } catch (_) { /* retain status */ }
    throw new Error(message);
  }
  return res;
}
function disconnect() {
  token = ''; selected = null; revision++; clearTimeout(timer);
  $('studio').hidden = true; $('login').hidden = false; $('project').hidden = true;
  $('source').textContent = ''; $('history').replaceChildren();
  $('bundle').value = ''; $('chatgpt-prompt').value = ''; $('bundle-file').value = '';
  $('chatgpt-bridge').hidden = true; importBrief = ''; tell('Disconnected.');
}
$('logout').onclick = disconnect;
$('login-form').onsubmit = async event => {
  event.preventDefault(); token = $('token').value.trim();
  try {
    const config = await (await api('/api/config')).json();
    $('token').value = ''; $('login').hidden = true; $('studio').hidden = false;
    providerReady = config.provider_configured;
    $('mode').value = providerReady ? 'groq' : 'chatgpt'; setMode();
    tell(providerReady ? 'Connected. Ready to build.' : 'Connected. Use ChatGPT import without an API key, or configure Groq for automatic generation.');
    await history();
  } catch (e) { token = ''; tell(e.message); }
};
const examples = {
  todo: 'Build a responsive task manager with HTML, CSS and JavaScript. Include add/edit/delete, priorities, status filters and local storage. Provide setup and manual test instructions.',
  api: 'Build a small FastAPI notes API with SQLite, validated request models, CRUD endpoints, pytest tests and a README with setup and run instructions.'
};
document.querySelectorAll('[data-example]').forEach(button => { button.onclick = () => { $('prompt').value = examples[button.dataset.example]; }; });
$('generate-form').onsubmit = async event => {
  event.preventDefault(); $('generate').disabled = true; tell('Preparing project…');
  try {
    if ($('mode').value === 'chatgpt') {
      const brief = $('prompt').value;
      const response = await (await api('/api/chatgpt-prompt', {method:'POST', body:JSON.stringify({prompt:brief})})).json();
      importBrief = brief; $('chatgpt-prompt').value = response.prompt; $('chatgpt-bridge').hidden = false;
      tell('Copy the prepared prompt into ChatGPT, then paste its JSON response below.');
      $('chatgpt-bridge').scrollIntoView({behavior:'smooth'}); return;
    }
    const job = await (await api('/api/projects', {method:'POST', body:JSON.stringify({prompt:$('prompt').value})})).json();
    tell('Project queued. You can revisit it from Your projects.'); await history(); await openProject(job.id);
  } catch (e) { tell(e.message); } finally { setMode(); }
};
async function history() {
  const jobs = await (await api('/api/projects')).json();
  $('history').replaceChildren();
  if (!jobs.length) { $('history').textContent = 'Your first project starts with a brief.'; return; }
  for (const job of jobs) {
    const button = document.createElement('button'); button.className = 'project-item';
    button.append(document.createTextNode(job.prompt.slice(0, 100)));
    const status = document.createElement('small'); status.textContent = job.status.toUpperCase(); button.append(status);
    button.onclick = () => openProject(job.id); $('history').append(button);
  }
}
async function openProject(id) {
  selected = id; const version = ++revision; clearTimeout(timer);
  $('project').hidden = false; $('files-layout').hidden = true; $('download').hidden = true;
  $('delete').hidden = true; $('validation').hidden = true; $('source').textContent = '';
  $('project-name').textContent = 'Project progress'; $('progress').textContent = 'Loading…';
  async function refresh() {
    try {
      const job = await (await api(`/api/projects/${id}`)).json();
      if (version !== revision) return;
      $('stage').textContent = job.stage.toUpperCase(); $('progress').textContent = job.message;
      if (['queued','running'].includes(job.status)) { timer = setTimeout(refresh, 2000); return; }
      $('delete').hidden = false; await history();
      if (version !== revision || job.status !== 'completed') return;
      $('project-name').textContent = job.result.plan.name;
      $('validation').hidden = false;
      $('validation').textContent = 'File checks passed. Python and JSON syntax checked where applicable. Runtime tests have NOT been run. Review the README, inspect the code and test it in isolation.';
      $('download').hidden = false; $('files-layout').hidden = false; $('files').replaceChildren();
      for (const path of job.result.files) {
        const button = document.createElement('button'); button.textContent = path;
        button.onclick = async () => {
          try {
            const requestVersion = ++fileRevision;
            const file = await (await api(`/api/projects/${id}/file?path=${encodeURIComponent(path)}`)).json();
            if (version !== revision || requestVersion !== fileRevision) return;
            $('filename').textContent = file.path; $('source').textContent = file.content;
            document.querySelectorAll('#files button').forEach(b => b.classList.toggle('active', b === button));
          } catch (e) { tell(e.message); }
        };
        $('files').append(button);
      }
      const readme = [...$('files').children].find(b => b.textContent === 'README.md');
      (readme || $('files').firstChild)?.click();
    } catch (e) { if (version === revision) tell(`${e.message} Select the project again to reconnect.`); }
  }
  await refresh();
}
$('download').onclick = async () => {
  const id = selected;
  try {
    const blob = await (await api(`/api/projects/${id}/download`)).blob();
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `coder-buddy-${id.slice(0,8)}.zip`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { tell(e.message); }
};
$('delete').onclick = async () => {
  if (!confirm('Permanently delete this generated project and its files?')) return;
  try {
    await api(`/api/projects/${selected}`, {method:'DELETE'}); revision++; clearTimeout(timer); selected = null;
    $('project').hidden = true; await history(); tell('Project deleted.');
  } catch (e) { tell(e.message); }
};

function setMode() {
  const manual = $('mode').value === 'chatgpt';
  $('generate').textContent = manual ? 'Prepare ChatGPT prompt →' : 'Generate project →';
  $('generate').disabled = !manual && !providerReady;
  if (!manual && !providerReady) tell('Configure GROQ_API_KEY on the server, or select ChatGPT import.');
}
$('mode').onchange = setMode;
$('copy-prompt').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('chatgpt-prompt').value);
    tell('Prompt copied. Paste it into ChatGPT.');
  } catch (_) {
    $('chatgpt-prompt').focus(); $('chatgpt-prompt').select();
    tell('Prompt selected. Press Ctrl+C (or Command+C) to copy.');
  }
};
$('bundle-file').onchange = async () => {
  const file = $('bundle-file').files[0];
  if (!file) return;
  if (file.size > 2000000) { tell('Choose a JSON file smaller than 2 MB.'); return; }
  try { $('bundle').value = await file.text(); } catch (_) { tell('Could not read the file. Paste the JSON instead.'); }
};
$('import-form').onsubmit = async event => {
  event.preventDefault(); $('import-project').disabled = true;
  try {
    let raw = $('bundle').value.trim();
    const fenced = raw.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
    if (fenced) raw = fenced[1];
    let project;
    try { project = JSON.parse(raw); } catch (_) { throw new Error('Invalid JSON. Ask ChatGPT to return the complete JSON object with escaped quotes and newlines.'); }
    const job = await (await api('/api/import', {method:'POST', body:JSON.stringify({prompt:importBrief, project})})).json();
    tell('Project imported. File checks passed; runtime tests have not been run.');
    $('bundle').value = ''; $('bundle-file').value = '';
    await history(); await openProject(job.id); $('project').scrollIntoView({behavior:'smooth'});
  } catch (e) { tell(e.message); } finally { $('import-project').disabled = false; }
};
