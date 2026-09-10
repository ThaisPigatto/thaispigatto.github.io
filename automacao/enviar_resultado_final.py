#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia por e-mail, todo dia útil às 17:30, o RESULTADO FINAL do dia:
quanto foi vendido hoje (isolado, não o acumulado do mês) + o acumulado do
mês até agora. Complementa o e-mail da manhã (enviar_metas_diarias.py, 07:50),
que mostra a meta do dia ANTES de vender; este mostra o resultado DEPOIS.

Lê o mesmo index.html publicado, sem recalcular nada da meta/faturado do mês
(usa os campos que o atualizar_painel.py já grava). A ÚNICA coisa que este
script calcula por conta própria é "quanto foi vendido HOJE" — porque esse
número não existe pronto no DATA (que só guarda o acumulado do mês) — feito
filtrando raw_real (a lista nota a nota, com data de emissão) pela data de
hoje. Validado em 10/09/2026 batendo exatamente com o faturado_total oficial
de uma família (Plásticos de Engenharia): a mesma regra de excluir vendas do
Mercado Livre/HUB (linhas com vendedor == "Jéssica") que o painel já usa pra
não contar aquilo duas vezes na família do produto.

% mostrado = % da META DO MÊS já faturada até agora (mesmo número do e-mail
da manhã) — confirmado por Thais em 10/09/2026, não é o % da meta do dia.

Aprovado por Thais em 10/09/2026 para envio real direto (sem fase de teste).
"""
import json
import os
import re
import smtplib
import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
INDEX_HTML_PATH = os.path.join(REPO_DIR, "index.html")

TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
AGORA = datetime.datetime.now(TZ_SP)
HOJE = AGORA.strftime("%d/%m/%Y")  # mesmo formato usado em raw_real[]["data_fatura"]

# ----------------------------------------------------------------------------
# CONFIG (mesma de enviar_metas_diarias.py — se mudar lá, replicar aqui também)
# ----------------------------------------------------------------------------
MODO_TESTE = False
EMAIL_TESTE = "thais.furlanbrito@gmail.com"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "thais.brito@pigattodistribuidora.com.br"
SMTP_PASSWORD = os.environ["SMTP_APP_PASSWORD"]

COR_META = "#6B1E28"
COR_GERAL = "#122038"
COR_FATURADO = "#1E7A4C"
COR_PREVISTO = "#B4650A"
COR_FALTA = "#B3261E"
COR_MUTED = "#5B6675"
COR_TEXTO = "#1B222C"
COR_LINHA = "#E1E6EB"

VENDOR_FAMILIAS_RESP = {
    "Wellington Azevedo": ["Adesivos Estruturais", "Aplicadores e Acessórios", "Linha TT"],
    "Tiago Fruet":         ["Adesivos Estruturais", "Aplicadores e Acessórios", "Linha TT"],
    "Marcelo Ribeiro":     ["Chemlok", "Bio-Chem", "Marbocote"],
    "Rhamayana":           ["Papel térmico", "Etiquetas"],
    "Maria Cristina":      ["Plásticos de Engenharia"],
}
VENDOR_CANAL_ML = {"Jéssica": 100000}

VENDOR_EMAILS = {
    "Maria Cristina":      ["maria.cristina@pigattodistribuidora.com.br"],
    "Jéssica":             ["vendas1@pigattodistribuidora.com.br", "jessica@pigattodistribuidora.com.br"],
    "Rhamayana":           ["vendas3@pigattodistribuidora.com.br", "rhamayana@pigattodistribuidora.com.br"],
    "Marcelo Ribeiro":     ["marcelo@pigattodistribuidora.com.br"],
    "Wellington Azevedo":  ["azevedo@pigattodistribuidora.com.br"],
    "Tiago Fruet":         ["tiago.fruet@pigattodistribuidora.com.br"],
}

GESTORES_EMAILS = [
    "gabriel@pigattodistribuidora.com.br",
    "gabriel.saenz@grupopigatto.com.br",
]


def carregar_data():
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    if not m:
        raise RuntimeError("Não encontrei o bloco 'const DATA = {...};' no index.html")
    return json.loads(m.group(1))


def fmt_brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v*100:.1f}%".replace(".", ",")


def grupos_por_meta(data):
    mapa = {}
    for g in data["grupos_familia"]:
        if g.get("is_spacer") or g.get("is_total") or g["id"] == "pigatto_hub":
            continue
        mapa[g["meta"]] = g
    return mapa


def vendido_hoje_familias(data, familias):
    """Soma do que foi faturado HOJE (isolado) nessas famílias, excluindo
    vendas do Mercado Livre/HUB (vendedor == 'Jéssica'), mesma regra usada
    pelo painel para não contar em duplicidade."""
    total = 0.0
    for r in data.get("raw_real", []):
        if r["familia"] not in familias:
            continue
        if r["vendedor"] == "Jéssica":
            continue
        if r["data_fatura"] != HOJE:
            continue
        total += r["total"]
    return round(total, 2)


def vendido_hoje_hub(data):
    """Soma do canal Pigatto HUB (Mercado Livre + Licitação) vendido hoje."""
    total = 0.0
    for r in data.get("raw_real", []):
        if r["data_fatura"] != HOJE:
            continue
        if r["operacao"] != "Orçamento":
            continue
        if r["vendedor"] == "Jéssica" or str(r["familia"] or "").upper().startswith("LICITA"):
            total += r["total"]
    return round(total, 2)


# ----------------------------------------------------------------------------
# HTML helpers (mesma paleta do painel)
# ----------------------------------------------------------------------------
def html_caixa(titulo, valor, cor_fundo):
    return f"""
    <div style="background:{cor_fundo};color:#FFFFFF;padding:14px 18px;border-radius:8px;
                font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:700;margin-bottom:16px;">
      ✅ {titulo}: {valor}
    </div>"""


def envolver_html(titulo, conteudo_html):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F5F6;">
  <div style="max-width:560px;margin:0 auto;padding:24px 18px;font-family:Arial,Helvetica,sans-serif;">
    <h2 style="color:{COR_GERAL};font-size:18px;margin:0 0 18px;">{titulo}</h2>
    {conteudo_html}
    <div style="color:{COR_MUTED};font-size:11px;margin-top:22px;">
      Painel Comercial Pigatto — envio automático diário.
    </div>
  </div>
</body></html>"""


def cor_pct(pct):
    if pct is None:
        return COR_MUTED
    if pct >= 1.0:
        return COR_FATURADO
    if pct >= 0.7:
        return COR_PREVISTO
    return COR_FALTA


# ----------------------------------------------------------------------------
# E-mail dos vendedores
# ----------------------------------------------------------------------------
def coletar_itens_vendedor(vendedor, data):
    gfp = grupos_por_meta(data)
    grupo_map = data["grupo_map"]
    familias_resp = set(VENDOR_FAMILIAS_RESP.get(vendedor, []))
    itens = []

    for grupo in grupo_map:
        if not grupo.get("meta"):
            continue
        if not any(f in familias_resp for f in grupo["familias"]):
            continue
        g = gfp.get(grupo["meta"])
        if not g:
            continue
        itens.append({
            "nome": " + ".join(grupo["familias"]),
            "meta_dia": g["meta_diaria_necessaria"],
            "vendido_hoje": vendido_hoje_familias(data, set(grupo["familias"])),
            "faturado_mes": g["faturado_total"],
            "pct": g["realizado_pct"],
        })

    if vendedor in VENDOR_CANAL_ML:
        hub = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
        if hub:
            itens.append({
                "nome": "Pigatto HUB - Marketplace/Licitação",
                "meta_dia": hub["meta_diaria_necessaria"],
                "vendido_hoje": vendido_hoje_hub(data),
                "faturado_mes": hub["faturado_total"],
                "pct": hub["realizado_pct"],
            })
    return itens


def bloco_familia_html(item):
    caixa = html_caixa(f"VENDIDO HOJE — {item['nome']}", fmt_brl(item["vendido_hoje"]), COR_FATURADO)
    return f"""
    <div style="border:1px solid {COR_LINHA};border-radius:8px;padding:16px 18px;margin-bottom:18px;">
      {caixa}
      <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;">
        <tr><td style="padding:5px 0;color:{COR_MUTED};">Meta que era pra bater hoje</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{COR_META};">{fmt_brl(item['meta_dia'])}</td></tr>
        <tr><td style="padding:5px 0;color:{COR_MUTED};">Faturado até hoje (mês)</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{COR_TEXTO};">{fmt_brl(item['faturado_mes'])}</td></tr>
        <tr><td style="padding:5px 0;color:{COR_MUTED};">% da meta do mês já faturada</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{cor_pct(item['pct'])};">{fmt_pct(item['pct'])}</td></tr>
      </table>
    </div>"""


def montar_email_vendedor_html(vendedor, data):
    itens = coletar_itens_vendedor(vendedor, data)
    if not itens:
        return None
    partes = [bloco_familia_html(i) for i in itens]
    return envolver_html(f"Resultado final do faturamento de hoje — {HOJE}", "".join(partes))


def montar_email_vendedor_texto(vendedor, data):
    itens = coletar_itens_vendedor(vendedor, data)
    if not itens:
        return None
    linhas = []
    for i in itens:
        linhas.append(
            f"Família: {i['nome']}\n"
            f"Meta que era pra bater hoje: {fmt_brl(i['meta_dia'])}\n"
            f"Vendido hoje: {fmt_brl(i['vendido_hoje'])}\n"
            f"Faturado até hoje (mês): {fmt_brl(i['faturado_mes'])}\n"
            f"% da meta do mês já faturada: {fmt_pct(i['pct'])}\n"
        )
    return "\n".join(linhas)


# ----------------------------------------------------------------------------
# E-mail dos gestores
# ----------------------------------------------------------------------------
def resultado_time_comercial(data):
    """Uma linha por vendedor: família, meta do dia, vendido hoje, faturado do
    mês e % da meta do mês — ordenado do maior para o menor %."""
    linhas = []
    for vendedor, familias in VENDOR_FAMILIAS_RESP.items():
        itens = coletar_itens_vendedor(vendedor, data)
        for i in itens:
            linhas.append((vendedor, i))
    hub = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
    if hub:
        for vendedor in VENDOR_CANAL_ML:
            linhas.append((vendedor, {
                "nome": "Pigatto HUB - Marketplace/Licitação",
                "meta_dia": hub["meta_diaria_necessaria"],
                "vendido_hoje": vendido_hoje_hub(data),
                "faturado_mes": hub["faturado_total"],
                "pct": hub["realizado_pct"],
            }))
    linhas.sort(key=lambda vi: (vi[1]["pct"] if vi[1]["pct"] is not None else -1), reverse=True)
    return linhas


def montar_email_gestores_html(data):
    t = data["totais"]
    vendido_hoje_geral = sum(
        vendido_hoje_familias(data, set(grupo["familias"]))
        for grupo in data["grupo_map"] if grupo.get("meta")
    )
    caixa_meta = html_caixa(f"META GERAL DE HOJE ({HOJE})", fmt_brl(t["meta_diaria_necessaria"]), COR_GERAL)
    caixa_realizado = html_caixa(f"REALIZADO HOJE ({HOJE})", fmt_brl(vendido_hoje_geral), COR_FATURADO)

    resumo = f"""
    <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;margin-bottom:20px;">
      <tr><td style="padding:6px 0;color:{COR_MUTED};">Faturado até hoje (mês)</td>
          <td style="padding:6px 0;text-align:right;font-weight:700;color:{COR_TEXTO};">{fmt_brl(t['faturado'])} ({fmt_pct(t['realizado_pct'])})</td></tr>
    </table>"""

    linhas_time = resultado_time_comercial(data)
    linhas_html = ""
    for vendedor, i in linhas_time:
        cor = cor_pct(i["pct"])
        linhas_html += f"""
        <tr>
          <td style="padding:8px 4px;border-bottom:1px solid {COR_LINHA};color:{COR_TEXTO};vertical-align:top;">
            <div style="font-weight:700;">{vendedor}</div>
            <div style="font-size:11.5px;color:{COR_MUTED};margin-top:2px;">{i['nome']}</div>
            <div style="font-size:11.5px;color:{COR_MUTED};margin-top:2px;">
              Meta do dia: {fmt_brl(i['meta_dia'])} &nbsp;•&nbsp;
              Vendido hoje: <span style="color:{COR_FATURADO};font-weight:700;">{fmt_brl(i['vendido_hoje'])}</span>
              &nbsp;•&nbsp; Faturado no mês: {fmt_brl(i['faturado_mes'])}
            </div>
          </td>
          <td style="padding:8px 4px;border-bottom:1px solid {COR_LINHA};text-align:right;vertical-align:top;">
            <span style="background:{cor};color:#FFFFFF;padding:2px 10px;border-radius:12px;font-weight:700;font-size:12.5px;">{fmt_pct(i['pct'])}</span>
          </td>
        </tr>"""

    time_html = f"""
    <div style="font-weight:700;color:{COR_GERAL};margin-bottom:8px;font-family:Arial,Helvetica,sans-serif;font-size:14px;">
      Resultado do time comercial
    </div>
    <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:13.5px;">
      {linhas_html}
    </table>"""

    return envolver_html(f"Resultado final do faturamento de hoje — {HOJE}",
                          caixa_meta + caixa_realizado + resumo + time_html)


def montar_email_gestores_texto(data):
    t = data["totais"]
    vendido_hoje_geral = sum(
        vendido_hoje_familias(data, set(grupo["familias"]))
        for grupo in data["grupo_map"] if grupo.get("meta")
    )
    linhas_time = resultado_time_comercial(data)
    time_txt = "\n".join(
        f"{vendedor} — {i['nome']}\n"
        f"  Meta do dia: {fmt_brl(i['meta_dia'])} | Vendido hoje: {fmt_brl(i['vendido_hoje'])} | "
        f"Faturado no mês: {fmt_brl(i['faturado_mes'])} | {fmt_pct(i['pct'])}"
        for vendedor, i in linhas_time
    )
    return (
        f"Meta geral de hoje ({HOJE}): {fmt_brl(t['meta_diaria_necessaria'])}\n"
        f"Realizado hoje: {fmt_brl(vendido_hoje_geral)}\n"
        f"Faturado até hoje (mês): {fmt_brl(t['faturado'])} ({fmt_pct(t['realizado_pct'])})\n\n"
        f"Resultado do time comercial:\n{time_txt}\n"
    )


def enviar_email(destinatarios, assunto, corpo_texto, corpo_html):
    if MODO_TESTE:
        destinatarios_reais = destinatarios
        destinatarios = [EMAIL_TESTE]
        aviso = f"[TESTE - destinatário real seria: {', '.join(destinatarios_reais)}]\n\n"
        corpo_texto = aviso + corpo_texto
        corpo_html = f"<p style='color:#B3261E;font-family:Arial;'>{aviso}</p>" + corpo_html

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())
    print(f"E-mail enviado: {assunto} -> {destinatarios}")


def main():
    data = carregar_data()
    assunto = f"RESULTADO FINAL DO FATURAMENTO DE HOJE - {HOJE}"

    for vendedor, emails in VENDOR_EMAILS.items():
        corpo_html = montar_email_vendedor_html(vendedor, data)
        if corpo_html is None:
            print(f"{vendedor}: nenhuma família/meta encontrada, e-mail não enviado.")
            continue
        corpo_texto = montar_email_vendedor_texto(vendedor, data)
        enviar_email(emails, assunto, corpo_texto, corpo_html)

    corpo_html_gestores = montar_email_gestores_html(data)
    corpo_texto_gestores = montar_email_gestores_texto(data)
    enviar_email(GESTORES_EMAILS, assunto, corpo_texto_gestores, corpo_html_gestores)


if __name__ == "__main__":
    main()
