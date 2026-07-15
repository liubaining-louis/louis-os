from __future__ import annotations

DASHBOARD_HTML = r'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0b1020">
  <title>Louis OS</title>
  <style>
    :root{--bg:#080b14;--panel:#111728;--panel2:#171f34;--line:#27314c;--text:#eef2ff;--muted:#94a3c7;--accent:#7c9cff;--green:#34d399;--red:#fb7185;--amber:#fbbf24;--shadow:0 18px 55px rgba(0,0,0,.32)}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#17203c 0,transparent 35%),var(--bg);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;min-height:100vh}
    button,input,textarea,select{font:inherit}.app{display:grid;grid-template-columns:250px 1fr;min-height:100vh}.sidebar{padding:24px 18px;border-right:1px solid var(--line);background:rgba(8,11,20,.78);backdrop-filter:blur(18px);position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:12px;margin:4px 8px 28px}.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(145deg,#8aa5ff,#5c73e8);display:grid;place-items:center;font-weight:900;box-shadow:0 10px 30px rgba(92,115,232,.35)}.brand h1{font-size:18px;margin:0}.brand small{color:var(--muted)}
    nav{display:grid;gap:7px}.nav{border:0;background:transparent;color:var(--muted);text-align:left;padding:11px 12px;border-radius:10px;cursor:pointer}.nav:hover,.nav.active{background:var(--panel2);color:white}.sidebar-foot{position:absolute;bottom:22px;left:18px;right:18px}.status-pill{display:flex;align-items:center;gap:9px;padding:11px 12px;border:1px solid var(--line);border-radius:12px;color:var(--muted);background:var(--panel)}.dot{width:8px;height:8px;border-radius:50%;background:var(--amber)}.dot.ok{background:var(--green);box-shadow:0 0 14px rgba(52,211,153,.7)}
    main{padding:30px;max-width:1500px;width:100%}.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:25px}.topbar h2{font-size:28px;margin:0 0 4px}.muted{color:var(--muted)}.actions{display:flex;gap:10px}.btn{border:1px solid var(--line);border-radius:10px;padding:10px 14px;background:var(--panel);color:var(--text);cursor:pointer}.btn:hover{border-color:#536486}.btn.primary{background:linear-gradient(135deg,#6d88f7,#5268d5);border:0}.grid{display:grid;gap:18px}.stats{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px}.card{background:linear-gradient(180deg,rgba(23,31,52,.93),rgba(17,23,40,.93));border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}.stat-label{color:var(--muted);font-size:13px}.stat-value{font-size:27px;font-weight:800;margin-top:8px}.two{grid-template-columns:minmax(0,1.3fr) minmax(320px,.7fr)}.card h3{margin:0 0 16px;font-size:17px}.mission-list{display:grid;gap:10px}.mission{display:grid;grid-template-columns:1fr auto;gap:14px;padding:14px;border:1px solid var(--line);border-radius:12px;background:rgba(8,11,20,.35);cursor:pointer}.mission:hover{border-color:#516184}.mission-title{font-weight:700}.mission-meta{font-size:12px;color:var(--muted);margin-top:4px}.badge{padding:4px 8px;border-radius:99px;font-size:11px;font-weight:700;background:rgba(52,211,153,.12);color:var(--green);height:max-content}.badge.failed{background:rgba(251,113,133,.13);color:var(--red)}
    label{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}.field{margin-bottom:13px}input,textarea,select{width:100%;border:1px solid var(--line);background:#0b1020;color:var(--text);border-radius:10px;padding:11px 12px;outline:none}textarea{min-height:110px;resize:vertical}input:focus,textarea:focus,select:focus{border-color:var(--accent)}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.output{white-space:pre-wrap;background:#090d18;border:1px solid var(--line);border-radius:12px;padding:14px;max-height:460px;overflow:auto;color:#dbe4ff}.hidden{display:none!important}.empty{padding:28px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:12px}.keybox{display:flex;gap:8px}.keybox input{flex:1}.toast{position:fixed;right:22px;bottom:22px;background:#182138;border:1px solid var(--line);padding:13px 16px;border-radius:12px;box-shadow:var(--shadow);opacity:0;transform:translateY(12px);pointer-events:none;transition:.2s}.toast.show{opacity:1;transform:none}.section{display:none}.section.active{display:block}
    @media(max-width:980px){.app{grid-template-columns:1fr}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}nav{grid-template-columns:repeat(4,1fr)}.sidebar-foot{display:none}.stats{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}
    @media(max-width:620px){main{padding:18px}.topbar{display:block}.actions{margin-top:12px}.stats{grid-template-columns:1fr 1fr}.form-row{grid-template-columns:1fr}nav{grid-template-columns:1fr 1fr}.sidebar{padding:15px}.brand{margin-bottom:15px}}
  </style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><div class="logo">L</div><div><h1>Louis OS</h1><small>Industrial Intelligence</small></div></div>
    <nav>
      <button class="nav active" data-page="overview">Vue d'ensemble</button>
      <button class="nav" data-page="missions">Missions</button>
      <button class="nav" data-page="memory">Mémoire</button>
      <button class="nav" data-page="system">Système</button>
    </nav>
    <div class="sidebar-foot"><div class="status-pill"><span id="statusDot" class="dot"></span><span id="statusText">Connexion...</span></div></div>
  </aside>
  <main>
    <section id="overview" class="section active">
      <div class="topbar"><div><h2>Centre de contrôle</h2><div class="muted">Pilotage des missions, de la mémoire et du moteur ATLAS.</div></div><div class="actions"><button class="btn" onclick="refreshAll()">Actualiser</button><button class="btn primary" onclick="showPage('missions')">Nouvelle mission</button></div></div>
      <div class="grid stats">
        <div class="card"><div class="stat-label">État du système</div><div id="systemState" class="stat-value">—</div></div>
        <div class="card"><div class="stat-label">Missions récentes</div><div id="missionCount" class="stat-value">—</div></div>
        <div class="card"><div class="stat-label">Taux de succès</div><div id="successRate" class="stat-value">—</div></div>
        <div class="card"><div class="stat-label">Stockage</div><div id="storeType" class="stat-value">—</div></div>
      </div>
      <div class="grid two">
        <div class="card"><h3>Dernières missions</h3><div id="recentMissions" class="mission-list"><div class="empty">Aucune mission chargée</div></div></div>
        <div class="card"><h3>Accès sécurisé</h3><div class="field"><label>Clé Louis OS</label><div class="keybox"><input id="apiKey" type="password" placeholder="X-Louis-Key"><button class="btn" onclick="saveKey()">Enregistrer</button></div></div><div class="muted">La clé reste uniquement dans le stockage local de ce navigateur.</div><hr style="border:0;border-top:1px solid var(--line);margin:20px 0"><h3>Capacités actives</h3><div id="capabilities" class="muted">Chargement...</div></div>
      </div>
    </section>

    <section id="missions" class="section">
      <div class="topbar"><div><h2>Missions</h2><div class="muted">Créer une mission structurée et consulter son exécution.</div></div><button class="btn" onclick="loadMissions()">Actualiser</button></div>
      <div class="grid two">
        <div class="card"><h3>Nouvelle mission</h3>
          <form id="missionForm">
            <div class="form-row"><div class="field"><label>Type</label><select id="missionType"><option value="research">Recherche</option><option value="supplier_qualification">Qualification fournisseur</option><option value="import_cost_analysis">Analyse coût import</option><option value="industrial_analysis">Analyse industrielle</option></select></div><div class="field"><label>Domaine</label><input id="missionDomain" value="industrial"></div></div>
            <div class="field"><label>Objectif</label><textarea id="missionObjective" required placeholder="Décris précisément le résultat attendu..."></textarea></div>
            <div class="field"><label>Contexte JSON</label><textarea id="missionContext" placeholder='{"product":"...","country":"..."}'>{}</textarea></div>
            <button class="btn primary" type="submit">Lancer la mission</button>
          </form>
        </div>
        <div class="card"><h3>Résultat</h3><div id="missionOutput" class="output">Aucune mission exécutée.</div></div>
      </div>
      <div class="card" style="margin-top:18px"><h3>Historique</h3><div id="missionHistory" class="mission-list"><div class="empty">Chargement...</div></div></div>
    </section>

    <section id="memory" class="section">
      <div class="topbar"><div><h2>Mémoire</h2><div class="muted">Connaissances persistantes et réutilisables par Louis OS.</div></div><button class="btn" onclick="loadMemories()">Actualiser</button></div>
      <div class="grid two"><div class="card"><h3>Rechercher</h3><div class="keybox"><input id="memoryQuery" placeholder="Rechercher dans la mémoire..."><button class="btn primary" onclick="loadMemories()">Chercher</button></div><div id="memoryList" class="mission-list" style="margin-top:16px"><div class="empty">Aucune mémoire chargée</div></div></div><div class="card"><h3>Ajouter une mémoire</h3><div class="field"><label>Domaine</label><input id="memoryDomain" value="industrial"></div><div class="field"><label>Type</label><input id="memoryType" value="knowledge"></div><div class="field"><label>Contenu</label><textarea id="memoryContent"></textarea></div><button class="btn primary" onclick="createMemory()">Mémoriser</button></div></div>
    </section>

    <section id="system" class="section">
      <div class="topbar"><div><h2>Système</h2><div class="muted">État de l’API, du modèle et des composants persistants.</div></div><button class="btn" onclick="loadHealth()">Tester</button></div>
      <div class="card"><h3>Diagnostic</h3><div id="healthOutput" class="output">Chargement...</div></div>
    </section>
  </main>
</div>
<div id="toast" class="toast"></div>
<script>
const $=id=>document.getElementById(id); const base='';
function key(){return localStorage.getItem('louisKey')||''} function headers(json=true){const h={'X-Louis-Key':key()};if(json)h['Content-Type']='application/json';return h}
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400)}
function saveKey(){localStorage.setItem('louisKey',$('apiKey').value.trim());toast('Clé enregistrée');refreshAll()}
function showPage(id){document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===id));$(id).classList.add('active');if(id==='missions')loadMissions();if(id==='memory')loadMemories();if(id==='system')loadHealth()}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>showPage(b.dataset.page));
async function api(path,opt={}){const r=await fetch(base+path,opt);const text=await r.text();let data;try{data=JSON.parse(text)}catch{data={error:text}}if(!r.ok)throw new Error(data.error||('HTTP '+r.status));return data}
async function loadHealth(){try{const h=await api('/health',{headers:{}});$('statusDot').classList.add('ok');$('statusText').textContent='En ligne · v'+h.version;$('systemState').textContent='En ligne';$('storeType').textContent=h.mission_store||'local';$('capabilities').innerHTML=['LLM : '+(h.llm_configured?'actif':'inactif'),'Core : '+(h.core||'standard'),'Mémoire : '+(h.memory_store||'local')].join('<br>');$('healthOutput').textContent=JSON.stringify(h,null,2)}catch(e){$('statusText').textContent='Hors ligne';$('systemState').textContent='Erreur';$('healthOutput').textContent=e.message}}
function missionItem(m){const status=m.status||'unknown';const title=m.objective||m.mission_type||m.type||'Mission';const id=m.mission_id||'';return `<div class="mission" onclick="viewMission('${id}')"><div><div class="mission-title">${escapeHtml(title)}</div><div class="mission-meta">${escapeHtml(m.mission_type||m.type||'')} · ${escapeHtml(id.slice(0,12))}</div></div><span class="badge ${status==='failed'?'failed':''}">${escapeHtml(status)}</span></div>`}
async function loadMissions(){if(!key()){return}try{const d=await api('/missions?limit=30',{headers:headers(false)});const arr=d.missions||[];$('missionCount').textContent=arr.length;const ok=arr.filter(x=>x.status==='completed').length;$('successRate').textContent=arr.length?Math.round(ok/arr.length*100)+'%':'—';const html=arr.length?arr.map(missionItem).join(''):'<div class="empty">Aucune mission</div>';$('recentMissions').innerHTML=arr.slice(0,6).map(missionItem).join('')||'<div class="empty">Aucune mission</div>';$('missionHistory').innerHTML=html}catch(e){$('missionHistory').innerHTML='<div class="empty">'+escapeHtml(e.message)+'</div>'}}
async function viewMission(id){if(!id)return;showPage('missions');try{const d=await api('/missions/'+id,{headers:headers(false)});$('missionOutput').textContent=JSON.stringify(d,null,2)}catch(e){toast(e.message)}}
$('missionForm').onsubmit=async e=>{e.preventDefault();let context;try{context=JSON.parse($('missionContext').value||'{}')}catch{return toast('Contexte JSON invalide')}const payload={type:$('missionType').value,objective:$('missionObjective').value.trim(),context:{...context,domain:$('missionDomain').value.trim()}};$('missionOutput').textContent='Mission en cours...';try{const d=await api('/missions',{method:'POST',headers:headers(),body:JSON.stringify(payload)});$('missionOutput').textContent=JSON.stringify(d,null,2);toast('Mission terminée');loadMissions()}catch(e){$('missionOutput').textContent=e.message}}
async function loadMemories(){if(!key())return;const q=encodeURIComponent($('memoryQuery').value||'');try{const d=await api('/memories?limit=30&query='+q,{headers:headers(false)});const arr=d.memories||[];$('memoryList').innerHTML=arr.length?arr.map(m=>`<div class="mission"><div><div class="mission-title">${escapeHtml(m.content||'')}</div><div class="mission-meta">${escapeHtml(m.domain||'')} · ${escapeHtml(m.memory_type||m.type||'')}</div></div><span class="badge">${Math.round((m.confidence||0)*100)}%</span></div>`).join(''):'<div class="empty">Aucun résultat</div>'}catch(e){$('memoryList').innerHTML='<div class="empty">'+escapeHtml(e.message)+'</div>'}}
async function createMemory(){const payload={type:$('memoryType').value,domain:$('memoryDomain').value,content:$('memoryContent').value,confidence:.85,tags:[],source:'dashboard'};try{await api('/memories',{method:'POST',headers:headers(),body:JSON.stringify(payload)});$('memoryContent').value='';toast('Mémoire enregistrée');loadMemories()}catch(e){toast(e.message)}}
function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
async function refreshAll(){await loadHealth();await loadMissions()}
$('apiKey').value=key();refreshAll();
</script>
</body></html>'''
