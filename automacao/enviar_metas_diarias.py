#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia por e-mail, todo dia útil às 08:00, a meta diária de cada vendedor
(por família de produto) e um resumo geral para os gestores.

Lê o index.html publicado (mesmo arquivo que atualizar_painel.py mantém
atualizado) e reaproveita o bloco `const DATA = {...};` — não recalcula
nada por conta própria, só formata o que já está lá.

E-mail em HTML com cores (mesma paleta do painel), com fallback em texto
simples pra clientes de e-mail que não renderizam HTML.

MODO_TESTE = False -> envio real para vendedores e gestores (aprovado por
Thais em 09/09/2026, após teste aprovado enviando só para ela).
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
HOJE = datetime.datetime.now(TZ_SP).strftime("%d/%m/%Y")

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
MODO_TESTE = False  # aprovado por Thais em 09/09/2026 — envio real ativado
EMAIL_TESTE = "thais.furlanbrito@gmail.com"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "thais.brito@pigattodistribuidora.com.br"
SMTP_PASSWORD = os.environ["SMTP_APP_PASSWORD"]  # GitHub Secret

# Mesma paleta de cores do painel (template_painel.html), pra ficar consistente
COR_META = "#6B1E28"      # vermelho escuro usado no cabeçalho das tabelas do painel
COR_GERAL = "#122038"     # navy usado no header do painel
COR_FATURADO = "#1E7A4C"  # verde (--dark-green / --green)
COR_PREVISTO = "#B4650A"  # amber (--amber)
COR_FALTA = "#B3261E"     # vermelho (--red)
COR_MUTED = "#5B6675"
COR_TEXTO = "#1B222C"
COR_LINHA = "#E1E6EB"

# Mesma lista de responsabilidade usada no template_painel.html (VENDOR_FAMILIAS_RESP).
# Se essa lista mudar lá (nova contratação, remanejo de família), replicar aqui também.
VENDOR_FAMILIAS_RESP = {
    "Wellington Azevedo": ["Adesivos Estruturais", "Aplicadores e Acessórios", "Linha TT", "Chemlok", "Bio-Chem", "Marbocote"],
    "Tiago Fruet":         ["Adesivos Estruturais", "Aplicadores e Acessórios", "Linha TT", "Chemlok", "Bio-Chem", "Marbocote"],
    "Marcelo Ribeiro":     ["Chemlok", "Bio-Chem", "Marbocote"],
    "Rhamayana":           ["Papel térmico", "Etiquetas"],
    "Maria Cristina":      ["Plásticos de Engenharia"],
}
# Jéssica não tem família própria — meta é só o canal Pigatto HUB (ver template)
VENDOR_CANAL_ML = {"Jéssica": 100000}

# E-mail(s) de cada vendedor (pode ter mais de um, separados por vírgula)
VENDOR_EMAILS = {
    "Maria Cristina":      ["maria.cristina@pigattodistribuidora.com.br"],
    "Jéssica":             ["vendas1@pigattodistribuidora.com.br", "jessica@pigattodistribuidora.com.br"],
    "Rhamayana":           ["vendas3@pigattodistribuidora.com.br", "rhamayana@pigattodistribuidora.com.br"],
    "Marcelo Ribeiro":     ["marcelo@pigattodistribuidora.com.br"],
    "Wellington Azevedo":  ["azevedo@pigattodistribuidora.com.br"],
    "Tiago Fruet":         ["tiago.fruet@pigattodistribuidora.com.br"],
}

GESTORES_EMAILS = [
    "gabriel@pigattodistribuidora.com.br",       # Gabriel Pigatto
    "gabriel.saenz@grupopigatto.com.br",         # Gabriel Saenz
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
    """Mapa meta -> objeto do grupo em grupos_familia (exclui total_geral/spacer/hub)."""
    mapa = {}
    for g in data["grupos_familia"]:
        if g.get("is_spacer") or g.get("is_total") or g["id"] == "pigatto_hub":
            continue
        mapa[g["meta"]] = g
    return mapa


# ----------------------------------------------------------------------------
# Helpers de HTML (mesma paleta de cores do painel)
# ----------------------------------------------------------------------------
def html_caixa_meta(titulo, valor, cor_fundo):
    return f"""
    <div style="background:{cor_fundo};color:#FFFFFF;padding:14px 18px;border-radius:8px;
                font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:700;margin-bottom:16px;">
      🎯 {titulo}: {valor}
    </div>"""


def html_bloco_familia(nome_familia, meta_dia, faturado, previsto, falta_mes):
    caixa = html_caixa_meta(f"META DE HOJE — {nome_familia}", fmt_brl(meta_dia), COR_META)
    return f"""
    <div style="border:1px solid {COR_LINHA};border-radius:8px;padding:16px 18px;margin-bottom:18px;">
      {caixa}
      <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;">
        <tr><td style="padding:5px 0;color:{COR_MUTED};">Faturado</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{COR_FATURADO};">{fmt_brl(faturado)}</td></tr>
        <tr><td style="padding:5px 0;color:{COR_MUTED};">Previsto</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{COR_PREVISTO};">{fmt_brl(previsto)}</td></tr>
        <tr><td style="padding:5px 0;color:{COR_MUTED};">Falta para bater a meta do mês</td>
            <td style="padding:5px 0;text-align:right;font-weight:700;color:{COR_FALTA};">{fmt_brl(falta_mes)}</td></tr>
      </table>
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
        itens.append((
            " + ".join(grupo["familias"]),
            g["meta_diaria_necessaria"],
            g["faturado_total"],
            g["previsto_total"],
            max(g["meta"] - g["prev_fat_total"], 0),
        ))

    if vendedor in VENDOR_CANAL_ML:
        hub = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
        if hub:
            itens.append((
                "Pigatto HUB - Marketplace/Licitação",
                hub["meta_diaria_necessaria"],
                hub["faturado_total"],
                hub["previsto_total"],
                max(hub["meta"] - hub["prev_fat_total"], 0),
            ))
    return itens


def montar_email_vendedor_html(vendedor, data):
    itens = coletar_itens_vendedor(vendedor, data)
    if not itens:
        return None

    partes = []
    if len(itens) > 1:
        total_meta_dia = sum(i[1] for i in itens)
        partes.append(html_caixa_meta(f"META DE HOJE ({HOJE}) — TOTAL DE TODAS AS FAMÍLIAS",
                                       fmt_brl(total_meta_dia), COR_GERAL))
    for nome_familia, meta_dia, faturado, previsto, falta_mes in itens:
        partes.append(html_bloco_familia(nome_familia, meta_dia, faturado, previsto, falta_mes))

    return envolver_html(f"Meta de vendas do dia — {HOJE}", "".join(partes))


def montar_email_vendedor_texto(vendedor, data):
    """Fallback em texto simples (mesmos números, sem formatação/cor)."""
    itens = coletar_itens_vendedor(vendedor, data)
    if not itens:
        return None
    linhas = []
    if len(itens) > 1:
        total_meta_dia = sum(i[1] for i in itens)
        linhas.append(f"META DE HOJE ({HOJE}) - TOTAL DE TODAS AS FAMÍLIAS: {fmt_brl(total_meta_dia)}\n")
    for nome_familia, meta_dia, faturado, previsto, falta_mes in itens:
        linhas.append(
            f"Família: {nome_familia}\n"
            f"Meta de hoje: {fmt_brl(meta_dia)}\n"
            f"Faturado: {fmt_brl(faturado)}\n"
            f"Previsto: {fmt_brl(previsto)}\n"
            f"Falta para bater a meta do mês: {fmt_brl(falta_mes)}\n"
        )
    return "\n".join(linhas)


# ----------------------------------------------------------------------------
# E-mail dos gestores
# ----------------------------------------------------------------------------
def ranking_vendedores(data):
    """Mesma lógica do ranking do painel: ordena do maior para o menor % de
    atingimento (Prev+Fat / meta da família), incluindo HUB."""
    gfp = grupos_por_meta(data)
    linhas = []
    for grupo in data["grupo_map"]:
        if not grupo.get("meta"):
            continue
        g = gfp.get(grupo["meta"])
        if not g:
            continue
        responsaveis = [v for v, fams in VENDOR_FAMILIAS_RESP.items()
                         if any(f in fams for f in grupo["familias"])]
        pct = g["prevfat_pct"]
        linhas.append((responsaveis, pct))

    hub = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
    if hub and hub.get("meta"):
        linhas.append((list(VENDOR_CANAL_ML.keys()), hub["prevfat_pct"]))

    por_vendedor = {}
    for responsaveis, pct in linhas:
        for v in responsaveis:
            if v not in por_vendedor or (pct is not None and (por_vendedor[v] is None or pct > por_vendedor[v])):
                por_vendedor[v] = pct

    return sorted(por_vendedor.items(), key=lambda kv: (kv[1] if kv[1] is not None else -1), reverse=True)


def cor_pct(pct):
    """Mesmos limiares do painel (pct_pill ok/warn/bad): >=100% verde, >=70% âmbar, resto vermelho."""
    if pct is None:
        return COR_MUTED
    if pct >= 1.0:
        return COR_FATURADO
    if pct >= 0.7:
        return COR_PREVISTO
    return COR_FALTA


def montar_email_gestores_html(data):
    t = data["totais"]
    linhas = ranking_vendedores(data)
    falta = max(t["meta"] - (t["faturado"] + t["devolucoes"]), 0)
    falta_pct = (1 - t["realizado_pct"]) if t.get("realizado_pct") is not None else None

    caixa = html_caixa_meta(f"META GERAL DE HOJE ({HOJE})", fmt_brl(t["meta_diaria_necessaria"]), COR_GERAL)

    resumo = f"""
    <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;margin-bottom:20px;">
      <tr><td style="padding:6px 0;color:{COR_MUTED};">Faturado até o momento</td>
          <td style="padding:6px 0;text-align:right;font-weight:700;color:{COR_FATURADO};">{fmt_brl(t['faturado'])} ({fmt_pct(t['realizado_pct'])})</td></tr>
      <tr><td style="padding:6px 0;color:{COR_MUTED};">Previsto até o momento</td>
          <td style="padding:6px 0;text-align:right;font-weight:700;color:{COR_PREVISTO};">{fmt_brl(t['previsto'])} ({fmt_pct(t['previsto_pct'])})</td></tr>
      <tr><td style="padding:6px 0;color:{COR_MUTED};">Falta para a meta (considerando o faturado)</td>
          <td style="padding:6px 0;text-align:right;font-weight:700;color:{COR_FALTA};">{fmt_brl(falta)} ({fmt_pct(falta_pct)})</td></tr>
    </table>"""

    linhas_ranking = ""
    for i, (v, pct) in enumerate(linhas):
        cor = cor_pct(pct)
        linhas_ranking += f"""
        <tr>
          <td style="padding:6px 4px;border-bottom:1px solid {COR_LINHA};color:{COR_TEXTO};">{i+1}º</td>
          <td style="padding:6px 4px;border-bottom:1px solid {COR_LINHA};color:{COR_TEXTO};">{v}</td>
          <td style="padding:6px 4px;border-bottom:1px solid {COR_LINHA};text-align:right;">
            <span style="background:{cor};color:#FFFFFF;padding:2px 10px;border-radius:12px;font-weight:700;font-size:12.5px;">{fmt_pct(pct)}</span>
          </td>
        </tr>"""

    ranking_html = f"""
    <div style="font-weight:700;color:{COR_GERAL};margin-bottom:8px;font-family:Arial,Helvetica,sans-serif;font-size:14px;">
      Desempenho por vendedor (do melhor para o pior % da meta da família)
    </div>
    <table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:13.5px;">
      {linhas_ranking}
    </table>"""

    return envolver_html(f"Resultado geral de faturamento — {HOJE}", caixa + resumo + ranking_html)


def montar_email_gestores_texto(data):
    """Fallback em texto simples."""
    t = data["totais"]
    linhas = ranking_vendedores(data)
    ranking_txt = "\n".join(
        f"{i+1}. {v}: {fmt_pct(pct)} da meta da família" for i, (v, pct) in enumerate(linhas)
    )
    falta = max(t["meta"] - (t["faturado"] + t["devolucoes"]), 0)
    falta_pct = (1 - t["realizado_pct"]) if t.get("realizado_pct") is not None else None
    return (
        f"Meta geral do dia ({HOJE}): {fmt_brl(t['meta_diaria_necessaria'])}\n\n"
        f"Faturado até o momento: {fmt_brl(t['faturado'])} ({fmt_pct(t['realizado_pct'])})\n"
        f"Previsto até o momento: {fmt_brl(t['previsto'])} ({fmt_pct(t['previsto_pct'])})\n"
        f"Falta para a meta (considerando o faturado): {fmt_brl(falta)} ({fmt_pct(falta_pct)})\n\n"
        f"Desempenho por vendedor (do melhor para o pior % da meta da família):\n"
        f"{ranking_txt}\n"
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

    for vendedor, emails in VENDOR_EMAILS.items():
        corpo_html = montar_email_vendedor_html(vendedor, data)
        if corpo_html is None:
            print(f"{vendedor}: nenhuma família/meta encontrada, e-mail não enviado.")
            continue
        corpo_texto = montar_email_vendedor_texto(vendedor, data)
        assunto = f"META DE VENDAS DO DIA - {HOJE}"
        enviar_email(emails, assunto, corpo_texto, corpo_html)

    corpo_html_gestores = montar_email_gestores_html(data)
    corpo_texto_gestores = montar_email_gestores_texto(data)
    assunto_gestores = f"RESULTADO GERAL DE FATURAMENTO ATÉ HOJE - {HOJE}"
    enviar_email(GESTORES_EMAILS, assunto_gestores, corpo_texto_gestores, corpo_html_gestores)


if __name__ == "__main__":
    main()
