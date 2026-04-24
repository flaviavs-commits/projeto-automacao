from datetime import date

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import settings


router = APIRouter(tags=["legal"])


def _base_layout(title: str, body_html: str) -> str:
    today = date.today().isoformat()
    app_name = settings.app_name
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} - {app_name}</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 16px;
      color: #111827;
      line-height: 1.6;
    }}
    h1, h2 {{ color: #0f172a; }}
    p, li {{ font-size: 15px; }}
    .meta {{
      color: #475569;
      font-size: 13px;
      margin-bottom: 24px;
    }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">
    Aplicativo: {app_name} | Ultima atualizacao: {today}
  </div>
  {body_html}
</body>
</html>
"""


@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy() -> HTMLResponse:
    body = """
<p>
Esta Politica de Privacidade descreve como coletamos, usamos e protegemos os dados
fornecidos durante interacoes em nossos canais digitais.
</p>

<h2>1. Dados coletados</h2>
<ul>
  <li>Identificadores de conta e contato enviados pelas plataformas integradas.</li>
  <li>Mensagens de texto e metadados tecnicos necessarios para atendimento.</li>
  <li>Dados operacionais para seguranca, auditoria e melhoria de servico.</li>
</ul>

<h2>2. Finalidade de uso</h2>
<ul>
  <li>Responder solicitacoes e prestar atendimento.</li>
  <li>Registrar historico de conversas para continuidade do suporte.</li>
  <li>Monitorar estabilidade, seguranca e qualidade do sistema.</li>
</ul>

<h2>3. Compartilhamento</h2>
<p>
Os dados podem ser processados por provedores de infraestrutura e comunicacao,
somente na medida necessaria para operacao da plataforma.
</p>

<h2>4. Retencao e seguranca</h2>
<p>
Aplicamos medidas tecnicas e organizacionais para proteger os dados. As informacoes
sao mantidas pelo periodo necessario para cumprimento das finalidades e obrigacoes legais.
</p>

<h2>5. Direitos do titular</h2>
<p>
Voce pode solicitar informacoes, correcao ou exclusao de dados, quando aplicavel por lei,
entrando em contato pelo canal oficial de atendimento.
</p>

<h2>6. Contato</h2>
<p>
Para duvidas sobre privacidade, entre em contato pelo nosso suporte oficial.
</p>
"""
    return HTMLResponse(content=_base_layout("Politica de Privacidade", body), status_code=200)


@router.get("/terms-of-service", response_class=HTMLResponse)
def terms_of_service() -> HTMLResponse:
    body = """
<p>
Estes Termos de Uso regem o acesso e utilizacao deste aplicativo e de seus canais integrados.
Ao utilizar o servico, voce concorda com as condicoes abaixo.
</p>

<h2>1. Uso permitido</h2>
<p>
O servico deve ser utilizado apenas para finalidades licitas e em conformidade com as regras
das plataformas integradas.
</p>

<h2>2. Responsabilidades</h2>
<ul>
  <li>Manter informacoes fornecidas corretas e atualizadas.</li>
  <li>Nao utilizar o servico para fraude, abuso ou spam.</li>
  <li>Respeitar direitos de terceiros e legislacao vigente.</li>
</ul>

<h2>3. Disponibilidade</h2>
<p>
Podemos atualizar, suspender ou interromper funcionalidades para manutencao, seguranca ou evolucao do servico.
</p>

<h2>4. Limitacao de responsabilidade</h2>
<p>
Dentro dos limites legais, nao nos responsabilizamos por indisponibilidades temporarias
de plataformas de terceiros ou eventos fora de controle razoavel.
</p>

<h2>5. Alteracoes dos termos</h2>
<p>
Os termos podem ser atualizados periodicamente. A versao vigente sera sempre a publicada nesta pagina.
</p>
"""
    return HTMLResponse(content=_base_layout("Termos de Uso", body), status_code=200)
