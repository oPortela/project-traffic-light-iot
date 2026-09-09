const $ = (id) => document.getElementById(id);
const phases = {idle:'Aguardando pedestre',yellow:'Preparando a travessia',clearance:'Intervalo de segurança',crossing:'Travessia liberada',return:'Encerrando a travessia'};
const colors = {red:'Vermelho',yellow:'Amarelo',green:'Verde'};
let current = null, connected = false, hydrated = false;
async function post(url, data) {
  try {
    const response = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Confira os valores dos ajustes.');
    $('error').hidden = true;
    render(result);
    return true;
  } catch(error) { $('error').textContent=error.message; $('error').hidden=false; return false; }
}
function render(s) {
  current=s;
  $('mode').value=s.mode;
  $('mode').disabled=s.running || !connected;
  $('start').disabled=s.running || !connected;
  $('stop').disabled=!s.running || !connected;
  $('reset').disabled=!connected;
  $('presence').disabled=!s.running || s.mode!=='demo' || !connected;
  $('presence').checked=s.presence;
  $('settings-fields').disabled=s.running || !connected;
  $('run-status').textContent=s.running?'Simulação em andamento':'Simulação parada';
  $('camera-status').textContent=s.mode==='demo'?'Demonstração':s.camera_status;
  $('demo-controls').hidden=s.mode!=='demo';
  $('camera-help').hidden=s.mode!=='camera';
  const showVideo=s.mode==='camera' && s.running && s.camera_status==='ativa';
  $('video').hidden=!showVideo;
  $('placeholder').hidden=showVideo;
  if(showVideo && !$('video').getAttribute('src')) $('video').src='/video';
  if(!showVideo) $('video').removeAttribute('src');
  const present=s.running && (s.mode==='demo'?s.presence:s.ids.length>0);
  $('person').hidden=!present || s.mode!=='demo';
  $('demo-message').textContent=s.mode==='camera' ? (s.running ? 'Iniciando câmera e detecção…' : 'Selecione Iniciar para abrir a webcam') : present?'Pessoa detectada':'Aguardando presença';
  $('detection').textContent=present?'Pessoa na área de espera':'Nenhuma pessoa na área';
  for(const type of ['car','pedestrian']) {
    $(type).querySelectorAll('.light').forEach(light=>light.classList.toggle('active',light.classList.contains(s[type])));
    $(type).setAttribute('aria-label',`${type==='car'?'Veículos':'Pedestres'}: ${colors[s[type]]}`);
    $(`${type}-label`).textContent=colors[s[type]];
  }
  $('phase-title').textContent=phases[s.phase];
  $('phase-detail').textContent=!s.running?'Inicie a simulação para acompanhar a travessia.':s.phase==='idle'?`A mesma pessoa precisa permanecer por ${s.wait_target} segundos.`:s.phase==='crossing'?'Carros parados. O pedestre pode atravessar.':'Aguarde a sequência de mudança dos sinais.';
  $('waited').textContent=s.waited.toFixed(1); $('target').textContent=s.wait_target;
  $('progress').max=s.wait_target; $('progress').value=s.waited;
  $('cycles').textContent=String(s.cycles).padStart(2,'0');
  $('remaining').textContent=s.phase==='idle'?'—':`${s.remaining.toFixed(1)} s`;
  $('events').replaceChildren();
  for(const event of s.events) {const li=document.createElement('li'); li.textContent=phases[event.phase]; $('events').appendChild(li);}
  if(!s.events.length) {const li=document.createElement('li'); li.textContent='As mudanças de sinal aparecerão aqui.'; $('events').appendChild(li);}
  if(s.error) { $('error').textContent=s.error; $('error').hidden=false; }
  if(!hydrated) {
    $('wait').value=s.wait_target; $('crossing').value=s.crossing_duration;
    ['x1','y1','x2','y2'].forEach((id,i)=>$(id).value=Math.round(s.roi[i]*100));
    hydrated=true;
  }
}
function connect() {
  const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
  ws.onopen=()=>{connected=true;$('connection').textContent='● CONECTADO';};
  ws.onmessage=(event)=>render(JSON.parse(event.data));
  ws.onclose=()=>{connected=false;$('connection').textContent='○ SEM CONEXÃO';if(current)render(current);$('run-status').textContent='Conexão perdida · tentando reconectar';setTimeout(connect,1500);};
  ws.onerror=()=>ws.close();
}
for(const action of ['start','stop','reset']) $(action).onclick=()=>post('/api/control',{action,mode:$('mode').value});
$('mode').onchange=()=>post('/api/control',{action:'reset',mode:$('mode').value});
$('presence').onchange=()=>post('/api/control',{action:'presence',presence:$('presence').checked});
$('settings').onsubmit=async(event)=>{event.preventDefault(); const ok=await post('/api/config',{wait:Number($('wait').value),crossing:Number($('crossing').value),roi:['x1','y1','x2','y2'].map(id=>Number($(id).value)/100)});if(ok){$('saved').textContent='Ajustes salvos';setTimeout(()=>$('saved').textContent='',3000);}};
for(const id of ['start','stop','reset','presence','mode','settings-fields']) $(id).disabled=true;
connect();
