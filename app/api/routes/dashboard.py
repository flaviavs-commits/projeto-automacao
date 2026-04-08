from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>bot-multiredes dashboard</title>
  <style>
    :root{
      --bg:#f4f6f8;
      --card:#ffffff;
      --text:#0f172a;
      --muted:#64748b;
      --line:#e2e8f0;
      --brand:#0f766e;
      --brand-soft:#ccfbf1;
      --warn:#9a3412;
      --warn-soft:#ffedd5;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family: "Segoe UI", Tahoma, Arial, sans-serif;
      color:var(--text);
      background:
        radial-gradient(circle at 0% 0%, #ecfeff 0%, transparent 32%),
        radial-gradient(circle at 100% 100%, #fef3c7 0%, transparent 28%),
        var(--bg);
    }
    .container{
      max-width:1100px;
      margin:0 auto;
      padding:24px 16px 40px;
    }
    .header{
      display:flex;
      justify-content:space-between;
      align-items:flex-start;
      gap:16px;
      margin-bottom:20px;
    }
    .title{margin:0;font-size:28px;line-height:1.2}
    .subtitle{margin:6px 0 0;color:var(--muted)}
    .actions{display:flex;gap:8px;align-items:center}
    .badge{
      padding:6px 10px;border-radius:999px;font-size:12px;
      background:var(--brand-soft);color:var(--brand);font-weight:700;
    }
    button{
      border:none;background:var(--brand);color:#fff;
      padding:8px 12px;border-radius:10px;cursor:pointer;font-weight:600;
    }
    .grid{
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:12px;margin-bottom:16px;
    }
    .card{
      background:var(--card);
      border:1px solid var(--line);
      border-radius:14px;
      padding:14px;
      box-shadow:0 1px 2px rgba(15,23,42,.05);
    }
    .kpi-label{font-size:12px;color:var(--muted);margin-bottom:8px}
    .kpi-value{font-size:26px;font-weight:700}
    .panels{
      display:grid;
      grid-template-columns:2fr 1fr;
      gap:12px;
    }
    .panel-title{margin:0 0 10px;font-size:16px}
    .list{margin:0;padding:0;list-style:none;display:grid;gap:8px}
    .item{
      padding:10px;border:1px solid var(--line);border-radius:10px;
      display:flex;justify-content:space-between;gap:12px;background:#fff;
    }
    .muted{color:var(--muted);font-size:13px}
    .error{
      margin-top:12px;padding:10px;border-radius:10px;
      background:var(--warn-soft);color:var(--warn);display:none;
      border:1px solid #fdba74;
    }
    @media (max-width: 920px){
      .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
      .panels{grid-template-columns:1fr}
    }
  </style>
</head>
<body>
  <main class="container">
    <section class="header">
      <div>
        <h1 class="title">Dashboard Central</h1>
        <p class="subtitle">Leads, mensagens principais e sinais para marketing e remarketing.</p>
      </div>
      <div class="actions">
        <span class="badge" id="health-badge">health: ...</span>
        <button id="refresh">Atualizar</button>
      </div>
    </section>

    <section class="grid">
      <article class="card"><div class="kpi-label">Leads (contatos)</div><div class="kpi-value" id="kpi-leads">-</div></article>
      <article class="card"><div class="kpi-label">Conversas abertas</div><div class="kpi-value" id="kpi-open">-</div></article>
      <article class="card"><div class="kpi-label">Mensagens recebidas</div><div class="kpi-value" id="kpi-inbound">-</div></article>
      <article class="card"><div class="kpi-label">Posts publicados</div><div class="kpi-value" id="kpi-published">-</div></article>
    </section>

    <section class="panels">
      <article class="card">
        <h2 class="panel-title">Principais mensagens (top 10)</h2>
        <ul class="list" id="top-messages"></ul>
      </article>
      <article class="card">
        <h2 class="panel-title">Leads recentes</h2>
        <ul class="list" id="recent-leads"></ul>
        <h2 class="panel-title" style="margin-top:14px;">Posts recentes</h2>
        <ul class="list" id="recent-posts"></ul>
      </article>
    </section>
    <div class="error" id="error-box"></div>
  </main>

  <script>
    const text = (v) => (v === null || v === undefined || v === "") ? "-" : String(v);
    const byId = (id) => document.getElementById(id);

    function renderList(targetId, items, renderFn, emptyText) {
      const ul = byId(targetId);
      ul.innerHTML = "";
      if (!items || items.length === 0) {
        const li = document.createElement("li");
        li.className = "item muted";
        li.textContent = emptyText;
        ul.appendChild(li);
        return;
      }
      items.forEach((item) => ul.appendChild(renderFn(item)));
    }

    function makeItem(left, right) {
      const li = document.createElement("li");
      li.className = "item";
      const l = document.createElement("div");
      l.textContent = left;
      const r = document.createElement("div");
      r.className = "muted";
      r.textContent = right;
      li.appendChild(l);
      li.appendChild(r);
      return li;
    }

    async function loadDashboard() {
      const errorBox = byId("error-box");
      errorBox.style.display = "none";
      errorBox.textContent = "";

      try {
        const [health, contacts, conversations, messages, posts] = await Promise.all([
          fetch("/health").then((r) => r.json()),
          fetch("/contacts").then((r) => r.json()),
          fetch("/conversations").then((r) => r.json()),
          fetch("/messages").then((r) => r.json()),
          fetch("/posts").then((r) => r.json()),
        ]);

        byId("health-badge").textContent = "health: " + text(health.status);
        byId("kpi-leads").textContent = String((contacts || []).length);
        byId("kpi-open").textContent = String((conversations || []).filter((c) => c.status === "open").length);
        byId("kpi-inbound").textContent = String((messages || []).filter((m) => m.direction === "inbound").length);
        byId("kpi-published").textContent = String((posts || []).filter((p) => p.status === "published").length);

        const topMap = {};
        (messages || []).forEach((m) => {
          const body = (m.text_content || "").trim();
          if (!body) return;
          topMap[body] = (topMap[body] || 0) + 1;
        });
        const topMessages = Object.entries(topMap)
          .sort((a,b) => b[1] - a[1])
          .slice(0, 10)
          .map(([msg, count]) => ({ msg, count }));

        renderList(
          "top-messages",
          topMessages,
          (item) => makeItem(item.msg, item.count + "x"),
          "Sem mensagens textuais ainda."
        );

        renderList(
          "recent-leads",
          (contacts || []).slice(0, 6),
          (c) => makeItem(text(c.name || c.phone || c.email), text(c.created_at)),
          "Sem leads cadastrados."
        );

        renderList(
          "recent-posts",
          (posts || []).slice(0, 6),
          (p) => makeItem(text(p.title || p.caption || p.platform), text(p.status)),
          "Sem posts registrados."
        );
      } catch (err) {
        errorBox.textContent = "Erro ao carregar dados do dashboard: " + err;
        errorBox.style.display = "block";
      }
    }

    byId("refresh").addEventListener("click", loadDashboard);
    loadDashboard();
    setInterval(loadDashboard, 30000);
  </script>
</body>
</html>
"""
