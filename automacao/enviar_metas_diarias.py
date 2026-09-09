#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia por e-mail, todo dia útil às 08:00, a meta diária de cada vendedor
(por família de produto) e um resumo geral para os gestores.

Lê o index.html publicado (mesmo arquivo que atualizar_painel.py mantém
atualizado) e reaproveita o bloco `const DATA = {...};` — não recalcula
nada por conta própria, só formata o que já está lá.

FASE DE TESTE (ver seção CONFIG): todos os e-mails saem só para
thais.furlanbrito@gmail.com, independente do destinatário real.
Quando aprovado, trocar MODO_TESTE para False.
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
MODO_TESTE = True  # enquanto True, TODO mundo recebe cópia só em EMAIL_TESTE
EMAIL_TESTE = "thais.furlanbrito@gmail.com"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "thais.brito@pigattodistribuidora.com.br"
SMTP_PASSWORD = os.environ["SMTP_APP_PASSWORD"]  # GitHub Secret

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


def montar_email_vendedor(vendedor, data):
    """Monta o corpo em texto simples do e-mail de um vendedor: um bloco por família."""
    gfp = grupos_por_meta(data)
    grupo_map = data["grupo_map"]  # [{"meta":..., "familias":[...]}, ...]
    familias_resp = set(VENDOR_FAMILIAS_RESP.get(vendedor, []))

    blocos = []

    # Famílias/grupos de meta compartilhada pelos quais o vendedor é responsável
    for grupo in grupo_map:
        if not grupo.get("meta"):
            continue
        if not any(f in familias_resp for f in grupo["familias"]):
            continue
        g = gfp.get(grupo["meta"])
        if not g:
            continue
        nome_familia = " + ".join(grupo["familias"])
        blocos.append(
            f"Família: {nome_familia}\n"
            f"Meta do dia ({HOJE}): {fmt_brl(g['meta_diaria_necessaria'])}\n"
            f"Faturado: {fmt_brl(g['faturado_total'])}\n"
            f"Previsto: {fmt_brl(g['previsto_total'])}\n"
            f"Falta para bater a meta do mês: {fmt_brl(max(g['meta'] - g['prev_fat_total'], 0))}\n"
        )

    # Canal Pigatto HUB (só Jéssica, hoje)
    if vendedor in VENDOR_CANAL_ML:
        hub = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
        if hub:
            blocos.append(
                f"Família: Pigatto HUB - Marketplace/Licitação\n"
                f"Meta do dia ({HOJE}): {fmt_brl(hub['meta_diaria_necessaria'])}\n"
                f"Faturado: {fmt_brl(hub['faturado_total'])}\n"
                f"Previsto: {fmt_brl(hub['previsto_total'])}\n"
                f"Falta para bater a meta do mês: {fmt_brl(max(hub['meta'] - hub['prev_fat_total'], 0))}\n"
            )

    if not blocos:
        return None
    return "\n\n".join(blocos)


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

    # Achata por vendedor (guarda o maior % entre os grupos que ele participa)
    por_vendedor = {}
    for responsaveis, pct in linhas:
        for v in responsaveis:
            if v not in por_vendedor or (pct is not None and (por_vendedor[v] is None or pct > por_vendedor[v])):
                por_vendedor[v] = pct

    ranking = sorted(por_vendedor.items(), key=lambda kv: (kv[1] if kv[1] is not None else -1), reverse=True)
    return ranking


def montar_email_gestores(data):
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


def enviar_email(destinatarios, assunto, corpo):
    if MODO_TESTE:
        destinatarios_reais = destinatarios
        destinatarios = [EMAIL_TESTE]
        corpo = f"[TESTE - destinatário real seria: {', '.join(destinatarios_reais)}]\n\n" + corpo

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())
    print(f"E-mail enviado: {assunto} -> {destinatarios}")


def main():
    data = carregar_data()

    for vendedor, emails in VENDOR_EMAILS.items():
        corpo = montar_email_vendedor(vendedor, data)
        if corpo is None:
            print(f"{vendedor}: nenhuma família/meta encontrada, e-mail não enviado.")
            continue
        assunto = f"META DE VENDAS DO DIA - {HOJE}"
        enviar_email(emails, assunto, corpo)

    corpo_gestores = montar_email_gestores(data)
    assunto_gestores = f"RESULTADO GERAL DE FATURAMENTO ATÉ HOJE - {HOJE}"
    enviar_email(GESTORES_EMAILS, assunto_gestores, corpo_gestores)


if __name__ == "__main__":
    main()
