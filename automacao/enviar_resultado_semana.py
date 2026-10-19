#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia por e-mail o link do "Resultado da Semana - CRM" (esforco.html#semana/AAAA-MM-DD).

Quem recebe:
  --destino teste   -> comercial@pigattodistribuidora.com.br  (teste; o assunto ganha o prefixo [TESTE])
  --destino gabriel -> gabriel@pigattodistribuidora.com.br    (envio real; é o padrão do agendamento de sábado)

Semana usada (segunda a sexta):
  sexta, sábado e domingo -> a semana que está terminando (ex.: sábado 10/10 -> 05/10 a 09/10)
  segunda a quinta        -> a semana anterior já fechada

Mesmo padrão dos e-mails que vocês já enviam (Gmail SMTP, senha de app no Secret SMTP_APP_PASSWORD).
Use --dry-run para ver o e-mail sem enviar.
"""
import argparse
import datetime
import os
import smtplib
import sys
import time
import zoneinfo
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
LINK_BASE = "https://thaispigatto.github.io/esforco.html"
EMAIL_GABRIEL = "gabriel@pigattodistribuidora.com.br"
EMAIL_TESTE = "comercial@pigattodistribuidora.com.br"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
SMTP_USER = "thais.brito@pigattodistribuidora.com.br"

TEXTO = "Bom dia, segue o link dos indicadores dessa semana de esforço comercial e preenchimento do CRM:"


def envio_ativo():
    """O envio automático de sábado só liga quando a Thais troca 'nao' por 'sim' neste arquivo (depois de aprovar o teste)."""
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "envio_semanal_ativo.txt")
    try:
        return open(caminho, encoding="utf-8").read().strip().lower() == "sim"
    except FileNotFoundError:
        return False


MARCADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultimo_envio_semana.txt")


def ja_enviado(seg):
    """True se o e-mail desta semana (segunda = seg) já foi enviado ao Gabriel."""
    try:
        return open(MARCADOR, encoding="utf-8").read().strip() == seg.isoformat()
    except FileNotFoundError:
        return False


def marcar_enviado(seg):
    with open(MARCADOR, "w", encoding="utf-8") as f:
        f.write(seg.isoformat() + "\n")


def enviar_com_tentativas(msg, para, senha, esperas=(15, 45, 90)):
    """O Gmail às vezes derruba a conexão vinda dos servidores do GitHub. Tenta de novo, alternando as duas portas
    do Gmail (587 com STARTTLS e 465 com SSL), com espera crescente entre as tentativas."""
    modos = [("starttls", 587), ("ssl", 465), ("starttls", 587), ("ssl", 465)]
    ultimo = None
    for i, (modo, porta) in enumerate(modos, 1):
        try:
            if modo == "ssl":
                srv = smtplib.SMTP_SSL(SMTP_HOST, porta, timeout=40)
            else:
                srv = smtplib.SMTP(SMTP_HOST, porta, timeout=40)
                srv.ehlo()
                srv.starttls()
                srv.ehlo()
            with srv:
                srv.login(SMTP_USER, senha)
                srv.sendmail(SMTP_USER, para, msg.as_string())
            print(f"Tentativa {i} ({modo}, porta {porta}): enviado.")
            return
        except (smtplib.SMTPException, OSError) as e:
            ultimo = e
            print(f"Tentativa {i} ({modo}, porta {porta}) falhou: {type(e).__name__}: {e}")
            if i < len(modos):
                time.sleep(esperas[min(i - 1, len(esperas) - 1)])
    raise ultimo


def montar_aviso_falha():
    link = os.environ.get("LINK_EXECUCAO", "(sem link)")
    msg = MIMEText("O e-mail semanal do Diagnóstico da Semana (CRM) NÃO foi enviado nesta tentativa.\n\n"
                   "Se for sábado, o sistema tenta de novo nas próximas horas.\n\nDetalhes: " + link, "plain", "utf-8")
    msg["Subject"] = str(Header("⚠️ E-mail semanal do CRM NÃO enviado (nova tentativa em breve)", "utf-8"))
    msg["From"] = SMTP_USER
    msg["To"] = SMTP_USER
    return msg


def semana_de_referencia(hoje):
    """(segunda, sexta) da semana a ser reportada."""
    seg = hoje - datetime.timedelta(days=hoje.weekday())
    if hoje.weekday() < 4:                 # segunda a quinta: semana anterior
        seg -= datetime.timedelta(days=7)
    return seg, seg + datetime.timedelta(days=4)


def montar(destino, hoje):
    seg, sex = semana_de_referencia(hoje)
    assunto = f"Diagnóstico completo da semana {seg:%d/%m} a {sex:%d/%m} - CRM"
    if destino == "teste":
        assunto = "[TESTE] " + assunto
    link = f"{LINK_BASE}#semana/{seg.isoformat()}"
    texto = f"{TEXTO}\n\n{link}\n"
    html = (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;line-height:1.5">'
            f'<p>{TEXTO}</p><p><a href="{link}">{link}</a></p></div>')
    para = [EMAIL_TESTE] if destino == "teste" else [EMAIL_GABRIEL]
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(para)
    msg["Subject"] = str(Header(assunto, "utf-8"))
    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg, para, assunto, texto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", choices=["teste", "gabriel"], default="gabriel")
    ap.add_argument("--dry-run", action="store_true", help="mostra o e-mail e não envia")
    ap.add_argument("--data", help="simula 'hoje' (AAAA-MM-DD), só para teste")
    ap.add_argument("--aviso-falha", action="store_true", help="envia só o aviso de falha para a Thais (usado pelo workflow)")
    ap.add_argument("--agendado", action="store_true", help="execução automática de sábado: só envia se automacao/envio_semanal_ativo.txt estiver com 'sim'")
    a = ap.parse_args()
    senha = os.environ.get("SMTP_APP_PASSWORD")
    if a.aviso_falha:
        if not senha:
            print("ERRO: Secret SMTP_APP_PASSWORD não encontrado.")
            sys.exit(1)
        enviar_com_tentativas(montar_aviso_falha(), [SMTP_USER], senha)
        return
    hoje = datetime.date.fromisoformat(a.data) if a.data else datetime.datetime.now(TZ_SP).date()
    seg, _ = semana_de_referencia(hoje)
    if a.agendado and not envio_ativo():
        print("Envio automático de sábado ainda DESLIGADO (automacao/envio_semanal_ativo.txt = 'nao'). Nada foi enviado.")
        return
    if a.agendado and ja_enviado(seg):
        print(f"O e-mail da semana de {seg:%d/%m} já foi enviado antes. Nada a fazer.")
        return
    msg, para, assunto, texto = montar(a.destino, hoje)
    print(f"Para: {', '.join(para)}\nAssunto: {assunto}\n---\n{texto}")
    if a.dry_run:
        print("(dry-run: nada foi enviado)")
        return
    if not senha:
        print("ERRO: Secret SMTP_APP_PASSWORD não encontrado.")
        sys.exit(1)
    enviar_com_tentativas(msg, para, senha)
    if a.destino == "gabriel":
        marcar_enviado(seg)       # evita mandar de novo se uma tentativa reserva rodar depois
    print("E-mail enviado.")


if __name__ == "__main__":
    main()
