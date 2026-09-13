"""Relay Communications -- live dashboard server.

Run:
    python3 -m relay_comms dashboard [--port 9876]
    python3 -m relay_comms.dashboard

Opens at http://localhost:9876
Embeddable at http://localhost:9876/?embed=true
API at http://localhost:9876/api/messages
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from relay_comms.config import MESSAGE_LOG, RELAY_LOG

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RELAY COMMS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#080808;--bg-card:#0d0d0d;--bg-hover:#141414;
  --border:#1c1c1c;--text:#b0b0b0;--text-dim:#505050;--text-bright:#e0e0e0;
  --accent:#00ccff;
  --r-operator:#00ccff;--r-builder:#00ff88;--r-librarian:#ffaa00;
  --r-sentinel:#ff4466;--r-designer:#cc66ff;--r-unknown:#808080;
  --p-info-bg:transparent;--p-alert-bg:rgba(255,170,0,0.06);--p-urgent-bg:rgba(255,34,34,0.08);
  --p-info:#44cc44;--p-alert:#ffaa00;--p-urgent:#ff4444;
}
body{
  background:var(--bg);color:var(--text);
  font-family:'JetBrains Mono','Fira Code','Cascadia Code','SF Mono',Consolas,monospace;
  font-size:13px;line-height:1.5;height:100vh;overflow:hidden;display:flex;flex-direction:column;
}
.header{
  display:flex;align-items:center;justify-content:space-between;
  padding:8px 16px;border-bottom:1px solid var(--border);background:var(--bg-card);
  flex-shrink:0;
}
.header h1{font-size:14px;font-weight:600;color:var(--accent);letter-spacing:2px}
.status{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-dim)}
.status-dot{
  width:8px;height:8px;border-radius:50%;background:#44cc44;
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.filters{
  display:flex;gap:4px;padding:6px 16px;border-bottom:1px solid var(--border);
  background:var(--bg-card);flex-wrap:wrap;flex-shrink:0;align-items:center;
}
.filter-label{color:var(--text-dim);padding:2px 4px;font-size:11px}
.filter-sep{width:12px}
.filter-btn{
  padding:2px 10px;border:1px solid var(--border);border-radius:3px;
  background:transparent;color:var(--text-dim);font-family:inherit;
  font-size:11px;cursor:pointer;transition:all .15s;
}
.filter-btn:hover{border-color:var(--text-dim);color:var(--text)}
.filter-btn.active{border-color:var(--accent);color:var(--accent);background:rgba(0,204,255,.08)}
.feed{flex:1;overflow-y:auto;padding:8px 16px}
.msg{
  padding:6px 10px;margin-bottom:2px;border-left:3px solid transparent;
  border-radius:2px;transition:background .15s;
}
.msg:hover{background:var(--bg-hover)}
.msg.pri-info{border-left-color:var(--p-info);background:var(--p-info-bg)}
.msg.pri-alert{border-left-color:var(--p-alert);background:var(--p-alert-bg)}
.msg.pri-urgent{border-left-color:var(--p-urgent);background:var(--p-urgent-bg)}
.msg-hdr{display:flex;align-items:center;gap:8px;font-size:11px}
.msg-time{color:var(--text-dim);min-width:65px}
.msg-route{font-weight:600}
.msg-pri{font-size:10px;padding:0 4px;border-radius:2px;text-transform:uppercase;letter-spacing:1px}
.msg-pri.info{color:var(--p-info)} .msg-pri.alert{color:var(--p-alert)} .msg-pri.urgent{color:var(--p-urgent);font-weight:700}
.msg-body{color:var(--text-bright);margin-top:2px;white-space:pre-wrap;word-break:break-word}
.msg-att{color:var(--text-dim);font-size:11px;margin-top:2px}
.footer{
  display:flex;justify-content:space-between;padding:4px 16px;
  border-top:1px solid var(--border);background:var(--bg-card);
  font-size:11px;color:var(--text-dim);flex-shrink:0;
}
.role-operator{color:var(--r-operator)} .role-builder{color:var(--r-builder)}
.role-librarian{color:var(--r-librarian)} .role-sentinel{color:var(--r-sentinel)}
.role-designer{color:var(--r-designer)} .role-unknown{color:var(--r-unknown)}
.embed .header,.embed .filters,.embed .footer{display:none}
.embed .feed{height:100vh}
.empty{color:var(--text-dim);text-align:center;padding:40px;font-size:12px}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--text-dim)}
</style>
</head>
<body>
<div class="header">
  <h1>RELAY COMMS</h1>
  <div class="status"><div class="status-dot" id="dot"></div><span id="status-text">CONNECTING</span></div>
</div>
<div class="filters">
  <span class="filter-label">ROLE:</span>
  <button class="filter-btn active" data-f="role" data-v="all">ALL</button>
  <button class="filter-btn" data-f="role" data-v="operator">OPERATOR</button>
  <button class="filter-btn" data-f="role" data-v="builder">BUILDER</button>
  <button class="filter-btn" data-f="role" data-v="librarian">LIBRARIAN</button>
  <button class="filter-btn" data-f="role" data-v="sentinel">SENTINEL</button>
  <button class="filter-btn" data-f="role" data-v="designer">DESIGNER</button>
  <div class="filter-sep"></div>
  <span class="filter-label">PRIORITY:</span>
  <button class="filter-btn active" data-f="pri" data-v="all">ALL</button>
  <button class="filter-btn" data-f="pri" data-v="info">INFO</button>
  <button class="filter-btn" data-f="pri" data-v="alert">ALERT</button>
  <button class="filter-btn" data-f="pri" data-v="urgent">URGENT</button>
</div>
<div class="feed" id="feed"><div class="empty">waiting for messages...</div></div>
<div class="footer">
  <span id="msg-count">messages: 0</span>
  <span id="last-update">--</span>
</div>
<script>
const feed=document.getElementById('feed'),
      countEl=document.getElementById('msg-count'),
      updateEl=document.getElementById('last-update'),
      statusEl=document.getElementById('status-text'),
      dotEl=document.getElementById('dot');

let msgs=[],roleF='all',priF='all',autoScroll=true,knownCount=0;

const RC={operator:'role-operator',builder:'role-builder',librarian:'role-librarian',
          sentinel:'role-sentinel',designer:'role-designer'};

document.querySelectorAll('.filter-btn').forEach(b=>{
  b.addEventListener('click',()=>{
    const f=b.dataset.f,v=b.dataset.v;
    document.querySelectorAll(`.filter-btn[data-f="${f}"]`).forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    if(f==='role')roleF=v; else priF=v;
    render();
  });
});

feed.addEventListener('scroll',()=>{
  autoScroll=feed.scrollHeight-feed.scrollTop-feed.clientHeight<50;
});

function esc(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML}

function render(){
  const fl=msgs.filter(m=>{
    if(roleF!=='all'&&m.source!==roleF&&m.target!==roleF)return false;
    if(priF!=='all'&&m.priority!==priF)return false;
    return true;
  });
  if(!fl.length){feed.innerHTML='<div class="empty">no messages match filters</div>';countEl.textContent='messages: 0 / '+msgs.length;return}
  feed.innerHTML=fl.map(m=>{
    const t=m.timestamp.substring(11,19),
          sc=RC[m.source]||'role-unknown',tc=RC[m.target]||'role-unknown';
    let h='<div class="msg pri-'+m.priority+'">';
    h+='<div class="msg-hdr">';
    h+='<span class="msg-time">'+t+'</span>';
    h+='<span class="msg-route"><span class="'+sc+'">'+m.source.toUpperCase()+'</span>';
    h+=' <span style="color:var(--text-dim)">&rarr;</span> ';
    h+='<span class="'+tc+'">'+m.target.toUpperCase()+'</span></span>';
    h+='<span class="msg-pri '+m.priority+'">'+m.priority+'</span>';
    h+='</div>';
    h+='<div class="msg-body">'+esc(m.body)+'</div>';
    if(m.attachment)h+='<div class="msg-att">att: '+esc(m.attachment)+'</div>';
    h+='</div>';
    return h;
  }).join('');
  countEl.textContent='messages: '+fl.length+' / '+msgs.length;
  if(autoScroll)feed.scrollTop=feed.scrollHeight;
}

async function poll(){
  try{
    const r=await fetch('/api/messages?limit=2000');
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(d.length!==knownCount){msgs=d;knownCount=d.length;render()}
    updateEl.textContent=new Date().toLocaleTimeString();
    statusEl.textContent='LIVE';dotEl.style.background='#44cc44';
  }catch(e){
    statusEl.textContent='OFFLINE';dotEl.style.background='#ff4444';
    updateEl.textContent='error: '+e.message;
  }
}
poll();setInterval(poll,1000);

// embed mode
if(location.search.includes('embed'))document.body.classList.add('embed');
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/messages':
            self._serve_messages(parsed)
        elif parsed.path == '/api/log':
            self._serve_log()
        else:
            self._serve_dashboard()

    def _serve_dashboard(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML.encode())

    def _serve_messages(self, parsed):
        params = parse_qs(parsed.query)
        limit = int(params.get('limit', [500])[0])

        messages = []
        if MESSAGE_LOG.exists():
            with open(MESSAGE_LOG, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        messages = messages[-limit:]

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(messages).encode())

    def _serve_log(self):
        text = ''
        if RELAY_LOG.exists():
            text = RELAY_LOG.read_text()

        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(text.encode())

    def log_message(self, format, *args):
        pass  # suppress access logs


def main(port=9876):
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"relay dashboard:  http://localhost:{port}")
    print(f"embeddable:       http://localhost:{port}/?embed=true")
    print(f"api:              http://localhost:{port}/api/messages")
    print(f"ctrl+c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ndashboard stopped.")
        server.server_close()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9876
    main(port=port)
