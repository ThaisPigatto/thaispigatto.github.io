#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualização automática do Painel Comercial Pigatto.
Roda dentro do GitHub Actions (robô), sem depender de nenhuma sessão do Claude
nem do computador de ninguém ligado. Busca dados frescos na API da OMIE
(Matriz e Papéis), recalcula os totais seguindo as regras de negócio validadas
(RESUMO_PROJETO_painel_pigatto.md, Seção 2-A) e regrava o index.html do site.

CONFIG que precisa de ajuste manual (1x por mês, no início do mês):
  META_GERAL, DIAS_UTEIS_TOTAL (calculado automaticamente) e as metas por
  grupo de família logo abaixo, se a diretoria mudar a meta do mês.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import datetime
import calendar
import zoneinfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
INDEX_HTML_PATH = os.path.join(REPO_DIR, "index.html")

CACHE_FAM_NOME = os.path.join(BASE_DIR, "fam_nome_cache.json")
CACHE_VEND_NOME = os.path.join(BASE_DIR, "vend_nome_cache.json")
CACHE_PRODUTO_FAMILIA = os.path.join(BASE_DIR, "produto_familia_cache.json")

# ----------------------------------------------------------------------------
# CONFIG — ajustar manualmente quando a meta do mês mudar (normalmente só
# no começo de cada mês). O resto (dias úteis, datas) é calculado sozinho.
# ----------------------------------------------------------------------------
META_GERAL = 1575000  # a partir de set/2026 já inclui a meta da HUB (100.000) — pedido Thais 01/09/2026
GRUPOS = [
    {"id": "adesivos", "cor": "#C0392B", "meta": 870000,
     "familias": ["Adesivos Estruturais", "Aplicadores e Acessórios", "Linha TT"],
     "cor_tint": "#f6e5e3", "cor_texto": "#FFFFFF", "row_bg": "#D7E7C6"},
    {"id": "quimicos", "cor": "#1B6B3D", "meta": 105000,
     "familias": ["Chemlok", "Bio-Chem", "Marbocote"],
     "cor_tint": "#e1ebe5", "cor_texto": "#FFFFFF", "row_bg": "#FFFFFF"},
    {"id": "papeis", "cor": "#8E3A9E", "meta": 200000,
     "familias": ["Papel térmico", "Etiquetas"],
     "cor_tint": "#f0e5f2", "cor_texto": "#FFFFFF", "row_bg": "#D7E7C6"},
    {"id": "plasticos", "cor": "#2E6F9E", "meta": 300000,
     "familias": ["Plásticos de Engenharia"],
     "cor_tint": "#e3ecf2", "cor_texto": "#FFFFFF", "row_bg": "#FFFFFF"},
]
HUB_META = 100000

# Credenciais da OMIE (vêm dos Secrets do GitHub — nunca ficam no código)
EMPRESAS = {
    "matriz": (os.environ["OMIE_MATRIZ_APP_KEY"], os.environ["OMIE_MATRIZ_APP_SECRET"]),
    "papeis": (os.environ["OMIE_PAPEIS_APP_KEY"], os.environ["OMIE_PAPEIS_APP_SECRET"]),
}

PREVISAO_ETAPAS = {"matriz": {"20", "80", "50"}, "papeis": {"20", "50"}}
REALIZADO_ETAPAS = {"matriz": {"60", "70"}, "papeis": {"60", "80"}}
CFOP_PREVISAO = {"5.102", "6.102", "5.112"}
CFOP_REALIZADO = {"5.102", "6.102", "5.112", "2.202", "5.202"}

TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
AGORA = datetime.datetime.now(TZ_SP)
HOJE = AGORA.date()
MES, ANO = HOJE.month, HOJE.year
ULTIMO_DIA_MES = calendar.monthrange(ANO, MES)[1]
LIMITE_PREVISAO = datetime.datetime(ANO, MES, ULTIMO_DIA_MES)


# Feriados nacionais/confirmados que NÃO contam como dia útil (nem para o total de
# dias úteis do mês, nem para "dias decorridos"/ESPERADO, nem para "dias restantes").
# Adicionar aqui manualmente conforme confirmado — nunca supor feriado sem confirmação.
FERIADOS = {
    datetime.date(2026, 9, 7),  # Independência do Brasil — confirmado por Thais (01/09/2026)
}


def dias_uteis_no_intervalo(d1, d2):
    """Conta dias úteis (seg-sex) entre d1 e d2, inclusive, descontando os dias em FERIADOS."""
    n = 0
    d = d1
    while d <= d2:
        if d.weekday() < 5 and d not in FERIADOS:
            n += 1
        d += datetime.timedelta(days=1)
    return n


DIAS_UTEIS_TOTAL = dias_uteis_no_intervalo(
    datetime.date(ANO, MES, 1), datetime.date(ANO, MES, ULTIMO_DIA_MES)
)
DIAS_UTEIS_DECORRIDOS = dias_uteis_no_intervalo(datetime.date(ANO, MES, 1), HOJE)
DIAS_UTEIS_RESTANTES = max(
    dias_uteis_no_intervalo(HOJE + datetime.timedelta(days=1), datetime.date(ANO, MES, ULTIMO_DIA_MES)),
    1,  # nunca divide por zero, mesmo no último dia útil do mês
)
ESPERADO_PCT = DIAS_UTEIS_DECORRIDOS / DIAS_UTEIS_TOTAL


def call(url_path, call_name, param, app_key, app_secret, retries=8):
    url = f"https://app.omie.com.br/api/v1/{url_path}/"
    payload = {"call": call_name, "app_key": app_key, "app_secret": app_secret, "param": [param]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if "Client-5113" in body:
                return {"pedido_venda_produto": [], "total_de_paginas": 0}
            if attempt < retries - 1:
                time.sleep(4)
                continue
            raise


# ----------------------------------------------------------------------------
# 1) NF-e emitidas no mês corrente (Realizado)
# ----------------------------------------------------------------------------
def buscar_nf():
    dados = {}
    d_ini = f"01/{MES:02d}/{ANO}"
    d_fim = HOJE.strftime("%d/%m/%Y")
    for empresa, (app_key, app_secret) in EMPRESAS.items():
        todas = []
        pagina = 1
        while True:
            r = call("produtos/nfconsultar", "ListarNF", {
                "pagina": pagina, "registros_por_pagina": 50,
                "dEmiInicial": d_ini, "dEmiFinal": d_fim,
                "tpNF": "1", "tpAmb": "1",
            }, app_key, app_secret)
            todas.extend(r.get("nfCadastro", []))
            if pagina >= r.get("total_de_paginas", 1):
                break
            pagina += 1
            time.sleep(1.0)
        dados[empresa] = todas
        print(f"{empresa} NFs: {len(todas)}")
        time.sleep(1.0)
    return dados


# ----------------------------------------------------------------------------
# 2) Etapas dos pedidos (histórico de status) — pagina de trás pra frente até
#    não achar mais nenhuma data do mês corrente em 5 páginas seguidas.
# ----------------------------------------------------------------------------
def buscar_etapas(empresa):
    app_key, app_secret = EMPRESAS[empresa]
    r = call("produtos/pedidoetapas", "ListarEtapasPedido", {"nPagina": 1, "nRegPorPagina": 100}, app_key, app_secret)
    total_paginas = r["nTotPaginas"]
    todos = []
    pagina = total_paginas
    sem_mes_seguidas = 0
    mes_str = f"{MES:02d}"
    ano_str = str(ANO)
    while sem_mes_seguidas < 5:
        rr = call("produtos/pedidoetapas", "ListarEtapasPedido",
                  {"nPagina": pagina, "nRegPorPagina": 100}, app_key, app_secret)
        todos.extend(rr["etapasPedido"])
        dts = [e["dDtEtapa"] for e in rr["etapasPedido"] if e["dDtEtapa"]]
        tem_mes = any(d[3:5] == mes_str and d[6:] == ano_str for d in dts)
        sem_mes_seguidas = 0 if tem_mes else sem_mes_seguidas + 1
        pagina -= 1
        time.sleep(0.8)
        if pagina < 1:
            break
    print(f"{empresa} etapas: {len(todos)}")
    return todos


# ----------------------------------------------------------------------------
# 3) Pedidos em Previsão (etapas ainda não faturadas)
# ----------------------------------------------------------------------------
def buscar_previsao():
    resultado = {}
    for empresa, etapas in PREVISAO_ETAPAS.items():
        app_key, app_secret = EMPRESAS[empresa]
        todos = []
        for etapa in etapas:
            pagina = 1
            while True:
                r = call("produtos/pedido", "ListarPedidos", {
                    "pagina": pagina, "registros_por_pagina": 100, "etapa": etapa,
                }, app_key, app_secret)
                todos.extend(r["pedido_venda_produto"])
                if pagina >= r.get("total_de_paginas", 1):
                    break
                pagina += 1
                time.sleep(1.0)
            time.sleep(1.0)
        resultado[empresa] = todos
        print(f"{empresa} pedidos previsao: {len(todos)}")
    return resultado


def montar_linhas_previsao(pedidos_por_empresa):
    linhas = []
    for empresa, pedidos in pedidos_por_empresa.items():
        for p in pedidos:
            cab = p["cabecalho"]
            info = p.get("infoCadastro", {})
            if cab["etapa"] not in PREVISAO_ETAPAS[empresa]:
                continue
            if info.get("cancelado") == "S" or info.get("autorizado") == "S":
                continue
            dp = None
            try:
                dp = datetime.datetime.strptime(cab.get("data_previsao", ""), "%d/%m/%Y")
            except Exception:
                pass
            if dp is None or dp > LIMITE_PREVISAO:
                continue
            cod_vend = p.get("informacoes_adicionais", {}).get("codVend")
            for item in p.get("det", []):
                cfop = item["produto"]["cfop"]
                if cfop not in CFOP_PREVISAO:
                    continue
                linhas.append({
                    "empresa": empresa, "pedido": cab["numero_pedido"], "cfop": cfop,
                    "valor": item["produto"]["valor_mercadoria"],
                    "cod_produto": item["produto"]["codigo_produto"], "cod_vend": cod_vend,
                })
    total = sum(l["valor"] for l in linhas)
    print(f"Previsao — Linhas: {len(linhas)} Total: {round(total, 2)}")
    return linhas


# ----------------------------------------------------------------------------
# 4) Realizado (faturado) — cruza NF com a última etapa conhecida do pedido
# ----------------------------------------------------------------------------
_ETAPA_VIVA_CACHE = {}


def confirmar_etapa_ao_vivo(empresa, nIdPedido):
    """Confirma a etapa ATUAL do pedido via ConsultarPedido (dado ao vivo), em vez de
    confiar cegamente no histórico paginado de pedidoetapas.

    Motivo (achado em 01/09/2026, cruzando o fechamento de agosto com o relatório oficial
    da OMIE a pedido da Thais): o pedido papeis/5110935412 (NF 00020009, R$120,24) tinha,
    no histórico de pedidoetapas, um registro desatualizado mostrando etapa de Faturado —
    mas o estado ao vivo do pedido já tinha avançado pra etapa 70, que pela regra
    documentada (Seção 2-A: "nunca usar etapa 70 da Papéis sem validar de novo") NÃO conta
    como Realizado. O histórico ficou "para trás" e o pedido foi contado errado.
    Essa função faz uma segunda checagem, ao vivo, pra pegar exatamente esse tipo de caso.
    Cacheada por pedido pra não repetir a mesma chamada em NFs com múltiplos itens.
    """
    key = (empresa, nIdPedido)
    if key in _ETAPA_VIVA_CACHE:
        return _ETAPA_VIVA_CACHE[key]
    app_key, app_secret = EMPRESAS[empresa]
    etapa_viva = None
    try:
        r = call("produtos/pedido", "ConsultarPedido", {"codigo_pedido": nIdPedido}, app_key, app_secret)
        etapa_viva = r.get("pedido_venda_produto", {}).get("cabecalho", {}).get("etapa")
    except Exception:
        etapa_viva = None  # falha na checagem ao vivo: não bloqueia, cai no valor do histórico
    _ETAPA_VIVA_CACHE[key] = etapa_viva
    time.sleep(0.4)
    return etapa_viva


def montar_linhas_realizado(nf_dados, etapas_matriz, etapas_papeis):
    def parse_dt(d, h):
        try:
            return datetime.datetime.strptime(f"{d} {h}", "%d/%m/%Y %H:%M:%S")
        except Exception:
            return datetime.datetime.min

    etapa_atual = {}
    for empresa, registros in [("papeis", etapas_papeis), ("matriz", etapas_matriz)]:
        for e in registros:
            pid = e["nCodPed"]
            dt = parse_dt(e["dDtEtapa"], e["cHrEtapa"])
            key = (empresa, pid)
            if key not in etapa_atual or dt > etapa_atual[key]["dt"]:
                etapa_atual[key] = {"etapa": e["cEtapa"], "cancelado": e["cancelamento"]["cCancelado"], "dt": dt}
    print("Total pedidos com etapa conhecida:", len(etapa_atual))

    linhas = []
    sem_etapa = []
    corrigidos_pelo_vivo = 0
    resgatados_pelo_vivo = 0
    for empresa in nf_dados:
        for nf in nf_dados[empresa]:
            if nf["ide"].get("cDeneg") != "N" or nf["ide"].get("dCan"):
                continue
            nIdPedido = nf["compl"].get("nIdPedido")
            key = (empresa, nIdPedido)
            est = etapa_atual.get(key)
            cod_vend = None
            if nf.get("titulos"):
                cod_vend = nf["titulos"][0].get("nCodVendedor")
            for item in nf["det"]:
                cfop = item["prod"]["CFOP"]
                if cfop not in CFOP_REALIZADO:
                    continue
                if est is None:
                    # Histórico não tem esse pedido: antes de descartar, confirma ao vivo
                    # (pode ser um pedido cujo histórico não foi capturado na paginação).
                    etapa_viva = confirmar_etapa_ao_vivo(empresa, nIdPedido)
                    if etapa_viva is None or etapa_viva not in REALIZADO_ETAPAS[empresa]:
                        sem_etapa.append((empresa, nIdPedido, nf["ide"]["nNF"], item["prod"]["vProd"]))
                        continue
                    resgatados_pelo_vivo += 1
                else:
                    if est["cancelado"] == "S":
                        continue
                    if est["etapa"] not in REALIZADO_ETAPAS[empresa]:
                        continue
                    # Histórico diz que conta: confirma ao vivo antes de aceitar, pra pegar
                    # casos como o do pedido papeis/5110935412 (histórico desatualizado).
                    etapa_viva = confirmar_etapa_ao_vivo(empresa, nIdPedido)
                    if etapa_viva is not None and etapa_viva not in REALIZADO_ETAPAS[empresa]:
                        corrigidos_pelo_vivo += 1
                        continue
                linhas.append({
                    "empresa": empresa, "nota": nf["ide"]["nNF"], "cfop": cfop,
                    "valor": item["prod"]["vProd"],
                    "cod_produto": item["nfProdInt"]["nCodProd"], "cod_vend": cod_vend,
                })
    total = sum(l["valor"] for l in linhas)
    print(f"Realizado — Linhas incluidas: {len(linhas)}  Total: {round(total, 2)}")
    print(f"Itens SEM info de etapa: {len(sem_etapa)}")
    if corrigidos_pelo_vivo or resgatados_pelo_vivo:
        print(f"Confirmação ao vivo: {corrigidos_pelo_vivo} excluído(s) por etapa desatualizada, "
              f"{resgatados_pelo_vivo} resgatado(s) que o histórico tinha perdido")
    return linhas


# ----------------------------------------------------------------------------
# 5) Família do produto — resolve códigos novos via API e guarda em cache
# ----------------------------------------------------------------------------
def atualizar_cache_familias(linhas_real, linhas_prev, produto_familia):
    distintos = set((l["empresa"], l["cod_produto"]) for l in linhas_real + linhas_prev)
    faltando = [(e, c) for (e, c) in distintos if f"{e}|{c}" not in produto_familia]
    print(f"Produtos novos a resolver: {len(faltando)}")
    for empresa, cod_produto in faltando:
        app_key, app_secret = EMPRESAS[empresa]
        try:
            r = call("geral/produtos", "ConsultarProduto", {"codigo_produto": cod_produto}, app_key, app_secret)
            fam = r.get("codigo_familia") if r else None
        except Exception:
            fam = None
        produto_familia[f"{empresa}|{cod_produto}"] = fam
        time.sleep(0.35)
    return produto_familia


# ----------------------------------------------------------------------------
# 6) Monta linhas finais com nomes de família/vendedor
# ----------------------------------------------------------------------------
def montar_parsed_rows(linhas_real, linhas_prev, fam_nome_cache, vend_nome_cache, produto_familia):
    def nome_familia(empresa, cod_produto):
        codfam = produto_familia.get(f"{empresa}|{cod_produto}")
        if codfam is None:
            return None
        return fam_nome_cache.get(f"{empresa}|{codfam}")

    def nome_vendedor(empresa, cod_vend):
        if cod_vend is None:
            return None
        return vend_nome_cache.get(f"{empresa}|{cod_vend}")

    def montar_real(l):
        vend = nome_vendedor(l["empresa"], l["cod_vend"])
        is_ml = (vend == "Mercado Livre")
        return {
            "familia": nome_familia(l["empresa"], l["cod_produto"]),
            "vendedor": "Jéssica" if is_ml else vend, "is_ml": is_ml,
            "nota_fiscal": l["nota"], "pedido": None, "situacao": "Autorizado",
            "empresa": l["empresa"], "operacao": "Orçamento", "cfop": l["cfop"], "total": l["valor"],
        }

    def montar_prev(l):
        vend = nome_vendedor(l["empresa"], l["cod_vend"])
        is_ml = (vend == "Mercado Livre")
        return {
            "familia": nome_familia(l["empresa"], l["cod_produto"]),
            "vendedor": "Jéssica" if is_ml else vend, "is_ml": is_ml,
            "nota_fiscal": "N/D", "pedido": l["pedido"], "situacao": "Aguardando faturamento",
            "empresa": l["empresa"], "operacao": "Orçamento", "cfop": l["cfop"], "total": l["valor"],
        }

    real_rows = [montar_real(l) for l in linhas_real]
    prev_rows = [montar_prev(l) for l in linhas_prev]
    print(f"Real: {len(real_rows)} linhas | sem familia: {sum(1 for r in real_rows if r['familia'] is None)} "
          f"| sem vendedor: {sum(1 for r in real_rows if r['vendedor'] is None)}")
    print(f"Prev: {len(prev_rows)} linhas | sem familia: {sum(1 for r in prev_rows if r['familia'] is None)} "
          f"| sem vendedor: {sum(1 for r in prev_rows if r['vendedor'] is None)}")
    return real_rows, prev_rows


# ----------------------------------------------------------------------------
# 7) Monta o DATA final (mesma lógica de build_data5.py)
# ----------------------------------------------------------------------------
def montar_data(real_rows, prev_rows):
    def agg_by_familia(rows, is_prev):
        fam = {}
        for r in rows:
            f = r["familia"]
            if f is None:
                continue
            # Vendas do Mercado Livre (is_ml) já contam inteiras para a HUB/Jéssica (hub_fat/hub_prev
            # mais abaixo, calculado direto de real_rows/prev_rows) — não podem também entrar aqui,
            # senão duplicam dentro da família/grupo de produto (ex: Papel térmico) e inflam a meta de
            # quem não vendeu aquilo (ex: Rhamayana). Regra confirmada por Thais em 01/09/2026: só o que
            # foi vendido direto pelo sistema da Papéis (fora do Mercado Livre/licitação) conta pra
            # família/vendedor responsável.
            if r.get("is_ml"):
                continue
            e = fam.setdefault(f, {"faturado": 0.0, "previsto": 0.0, "devolucoes": 0.0, "aguardando": 0.0, "hoje": 0.0})
            val = r["total"]
            situ = r.get("situacao", "")
            if r["operacao"] == "Orçamento":
                if is_prev:
                    e["previsto"] += val
                    if situ == "Aguardando faturamento":
                        e["aguardando"] += val
                    elif situ == "Previsto para hoje":
                        e["hoje"] += val
                else:
                    e["faturado"] += val
            else:
                if is_prev:
                    e["previsto"] += val
                else:
                    e["devolucoes"] += val
        return fam

    fam_real = agg_by_familia(real_rows, False)
    fam_prev = agg_by_familia(prev_rows, True)

    all_familias = set(fam_real.keys()) | set(fam_prev.keys())
    for g in GRUPOS:
        for f in g["familias"]:
            all_familias.add(f)
    all_familias.add("LICITAÇÕES")

    def fam_entry(fname, meta=None):
        r = fam_real.get(fname, {"faturado": 0.0, "previsto": 0.0, "devolucoes": 0.0, "aguardando": 0.0, "hoje": 0.0})
        p = fam_prev.get(fname, {"previsto": 0.0, "aguardando": 0.0, "hoje": 0.0})
        faturado = round(r["faturado"], 2)
        devolucoes = round(r["devolucoes"], 2)
        previsto = round(p["previsto"], 2)
        prev_fat = round(previsto + faturado + devolucoes, 2)
        entry = {
            "familia": fname, "faturado": faturado, "devolucoes": devolucoes,
            "previsto": previsto, "prev_fat": prev_fat,
            "previsto_aguardando": round(p["aguardando"], 2), "previsto_hoje": round(p["hoje"], 2),
        }
        if meta is not None:
            prevfat_pct = prev_fat / meta if meta else None
            entry.update({
                "meta": meta,
                "dif_meta_real": round(meta - (faturado + devolucoes), 2) if meta else None,
                "realizado_pct": (faturado + devolucoes) / meta if meta else None,
                "dif_meta_prev": round(meta - prev_fat, 2) if meta else None,
                "previsto_pct": previsto / meta if meta else None,
                "prevfat_pct": prevfat_pct,
                "faltante_pct": 1 - prevfat_pct if prevfat_pct is not None else None,
                "esperado_pct": ESPERADO_PCT,
                "esperado_valor": meta * ESPERADO_PCT if meta else None,
                "meta_diaria_necessaria": (meta - prev_fat) / DIAS_UTEIS_RESTANTES if meta else None,
            })
        else:
            entry["meta"] = None
        return entry

    grupos_familia_out = []
    for g in GRUPOS:
        linhas = []
        fat_t = prev_t = dev_t = 0.0
        for f in g["familias"]:
            r = fam_real.get(f, {"faturado": 0.0, "devolucoes": 0.0})
            p = fam_prev.get(f, {"previsto": 0.0})
            linhas.append({"familia": f, "faturado": round(r["faturado"], 2),
                            "previsto": round(p["previsto"], 2), "devolucoes": round(r["devolucoes"], 2)})
            fat_t += r["faturado"]; prev_t += p["previsto"]; dev_t += r["devolucoes"]
        prev_fat_t = fat_t + prev_t + dev_t
        meta = g["meta"]
        grupos_familia_out.append({
            "id": g["id"], "cor": g["cor"], "meta": meta, "linhas": linhas,
            "faturado_total": round(fat_t, 2), "previsto_total": round(prev_t, 2),
            "devolucoes_total": round(dev_t, 2), "prev_fat_total": round(prev_fat_t, 2),
            "realizado_pct": (fat_t + dev_t) / meta, "prevfat_pct": prev_fat_t / meta,
            "meta_diaria_necessaria": (meta - prev_fat_t) / DIAS_UTEIS_RESTANTES,
            "faturamento_atrasado": 0.0,
            "cor_tint": g["cor_tint"], "cor_texto": g["cor_texto"], "row_bg": g["row_bg"],
        })

    # HUB (Marketplace/Licitação) — calculado ANTES do "TOTAL GERAL" porque, a partir de
    # setembro/2026, a meta da HUB passou a contar dentro da Meta Geral (a pedido da Thais,
    # 01/09/2026). Antes disso a HUB era só uma linha separada, fora do total.
    ml_real = [r for r in real_rows if r["is_ml"]]
    ml_prev = [r for r in prev_rows if r["is_ml"]]
    lic_real = [r for r in real_rows if (r["familia"] or "").upper().startswith("LICITA")]
    lic_prev = [r for r in prev_rows if (r["familia"] or "").upper().startswith("LICITA")]
    hub_fat = sum(r["total"] for r in ml_real + lic_real if r["operacao"] == "Orçamento")
    hub_dev = sum(r["total"] for r in ml_real + lic_real if r["operacao"] != "Orçamento")
    hub_prev_v = sum(r["total"] for r in ml_prev + lic_prev)
    hub_prevfat = hub_fat + hub_dev + hub_prev_v

    tot_fat = sum(g["faturado_total"] for g in grupos_familia_out) + hub_fat
    tot_prev = sum(g["previsto_total"] for g in grupos_familia_out) + hub_prev_v
    tot_dev = sum(g["devolucoes_total"] for g in grupos_familia_out) + hub_dev
    tot_prevfat = tot_fat + tot_prev + tot_dev
    grupos_familia_out.append({
        "id": "total_geral", "cor": "#122038", "meta": META_GERAL,
        "linhas": [{"familia": "TOTAL GERAL", "faturado": round(tot_fat, 2),
                    "previsto": round(tot_prev, 2), "devolucoes": round(tot_dev, 2)}],
        "faturado_total": round(tot_fat, 2), "previsto_total": round(tot_prev, 2),
        "devolucoes_total": round(tot_dev, 2), "prev_fat_total": round(tot_prevfat, 2),
        "realizado_pct": (tot_fat + tot_dev) / META_GERAL, "prevfat_pct": tot_prevfat / META_GERAL,
        "is_total": True,
        "meta_diaria_necessaria": (META_GERAL - tot_prevfat) / DIAS_UTEIS_RESTANTES,
        "faturamento_atrasado": 0.0,
        "cor_tint": "#e0e2e5", "cor_texto": "#FFFFFF", "row_bg": "#A6C97E",
    })
    grupos_familia_out.append({"id": "spacer", "is_spacer": True})

    grupos_familia_out.append({
        "id": "pigatto_hub", "cor": "#C9A227", "meta": HUB_META,
        "linhas": [{"familia": "Pigatto HUB - Marketplace/Licitação", "faturado": round(hub_fat, 2),
                    "previsto": round(hub_prev_v, 2), "devolucoes": round(hub_dev, 2)}],
        "faturado_total": round(hub_fat, 2), "previsto_total": round(hub_prev_v, 2),
        "devolucoes_total": round(hub_dev, 2), "prev_fat_total": round(hub_prevfat, 2),
        "realizado_pct": (hub_fat + hub_dev) / HUB_META, "prevfat_pct": hub_prevfat / HUB_META,
        "meta_diaria_necessaria": (HUB_META - hub_prevfat) / DIAS_UTEIS_RESTANTES,
        "faturamento_atrasado": 0.0,
        "cor_tint": "#f7f2e2", "cor_texto": "#111111", "row_bg": "#F3EE9E",
    })

    familias_flat = []
    for g in GRUPOS:
        head = g["familias"][0]
        for f in g["familias"]:
            familias_flat.append(fam_entry(f, meta=g["meta"] if f == head else None))
    covered = set()
    for g in GRUPOS:
        covered |= set(g["familias"])
    leftover = all_familias - covered - {"LICITAÇÕES"}
    for f in sorted(leftover):
        familias_flat.append(fam_entry(f))
    familias_flat.append({
        "familia": "LICITAÇÃO", "faturado": 0.0, "devolucoes": 0.0, "previsto": 0.0, "prev_fat": 0.0,
        "previsto_aguardando": 0.0, "previsto_hoje": 0.0, "meta": 0,
        "dif_meta_real": 0.0, "realizado_pct": None, "dif_meta_prev": 0.0,
        "previsto_pct": None, "prevfat_pct": None, "faltante_pct": None,
        "esperado_pct": ESPERADO_PCT, "esperado_valor": 0.0, "meta_diaria_necessaria": 0.0,
    })

    totais = {
        "meta": META_GERAL, "previsto": round(tot_prev, 2), "faturado": round(tot_fat, 2),
        "devolucoes": round(tot_dev, 2), "prev_fat": round(tot_prevfat, 2),
        "dif_meta_real": round(META_GERAL - (tot_fat + tot_dev), 2),
        "realizado_pct": (tot_fat + tot_dev) / META_GERAL,
        "dif_meta_prev": round(META_GERAL - tot_prevfat, 2),
        "previsto_pct": tot_prev / META_GERAL, "prevfat_pct": tot_prevfat / META_GERAL,
        "faltante_pct": 1 - (tot_prevfat / META_GERAL),
        "esperado_pct": ESPERADO_PCT, "esperado_valor": META_GERAL * ESPERADO_PCT,
        "meta_diaria_necessaria": (META_GERAL - tot_prevfat) / DIAS_UTEIS_RESTANTES,
        "dias_uteis_total": DIAS_UTEIS_TOTAL, "dias_uteis_decorridos": DIAS_UTEIS_DECORRIDOS,
        "dias_uteis_restantes": DIAS_UTEIS_RESTANTES,
        "notas_real": len(real_rows), "pedidos_prev": len(prev_rows),
        "ticket_medio_real": round(tot_fat / len(real_rows), 2) if real_rows else 0,
    }

    meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
                "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    meta_info = {
        "inicio_mes": f"01/{MES:02d}/{ANO}",
        "fim_mes": f"{ULTIMO_DIA_MES:02d}/{MES:02d}/{ANO}",
        "dia_atual": HOJE.strftime("%d/%m/%Y"),
        "fonte_meta": "Base do relatório de referência enviado (RELATÓRIO_COMERCIAL_DIÁRIO.xlsx)",
        "atualizado_em": AGORA.strftime("%d/%m/%Y · %H:%M:%S"),
    }

    grupo_map = [{"meta": g["meta"], "familias": g["familias"]} for g in GRUPOS]
    grupo_map.append({"meta": 0, "familias": ["LICITAÇÃO"]})

    def vend_agg(rows):
        v = {}
        for r in rows:
            name = r["vendedor"] or "N/D"
            e = v.setdefault(name, {"total": 0.0, "linhas": 0})
            e["total"] += r["total"]; e["linhas"] += 1
        out = [{"Vendedor": k, "total": round(v[k]["total"], 2), "linhas": v[k]["linhas"]} for k in v]
        out.sort(key=lambda x: -x["total"])
        return out

    def vend_fam_agg(rows):
        vf = {}
        for r in rows:
            f = r["familia"]
            if f is None:
                continue
            key = (r["vendedor"] or "N/D", f)
            vf[key] = vf.get(key, 0.0) + r["total"]
        return [{"Vendedor": k[0], "Família de Produto": k[1], "Total de Mercadoria": round(v, 2)} for k, v in vf.items()]

    raw_cols = ["familia", "vendedor", "nota_fiscal", "pedido", "situacao", "empresa", "operacao", "cfop", "total"]

    return {
        "totais": totais,
        "familias": familias_flat,
        "vend_real": vend_agg(real_rows),
        "vend_prev": vend_agg(prev_rows),
        "vend_fam_real": vend_fam_agg(real_rows),
        "vend_fam_prev": vend_fam_agg(prev_rows),
        "meta_info": meta_info,
        "grupos_familia": grupos_familia_out,
        "grupo_map": grupo_map,
        "raw_real": [{c: r[c] for c in raw_cols} for r in real_rows],
        "raw_prev": [{c: r[c] for c in raw_cols} for r in prev_rows],
    }


def main():
    fam_nome_cache = json.load(open(CACHE_FAM_NOME, encoding="utf-8"))
    vend_nome_cache = json.load(open(CACHE_VEND_NOME, encoding="utf-8"))
    produto_familia = json.load(open(CACHE_PRODUTO_FAMILIA, encoding="utf-8"))

    nf_dados = buscar_nf()
    etapas_matriz = buscar_etapas("matriz")
    etapas_papeis = buscar_etapas("papeis")
    pedidos_previsao = buscar_previsao()

    linhas_prev = montar_linhas_previsao(pedidos_previsao)
    linhas_real = montar_linhas_realizado(nf_dados, etapas_matriz, etapas_papeis)

    produto_familia = atualizar_cache_familias(linhas_real, linhas_prev, produto_familia)
    json.dump(produto_familia, open(CACHE_PRODUTO_FAMILIA, "w", encoding="utf-8"), ensure_ascii=False)

    real_rows, prev_rows = montar_parsed_rows(linhas_real, linhas_prev, fam_nome_cache, vend_nome_cache, produto_familia)

    data = montar_data(real_rows, prev_rows)

    soma_vend = round(sum(v["total"] for v in data["vend_real"]), 2)
    soma_fat_dev = round(data["totais"]["faturado"] + data["totais"]["devolucoes"], 2)
    print(f"Total geral faturado: {data['totais']['faturado']} | previsto: {data['totais']['previsto']}")
    print(f"Soma vend_real: {soma_vend} vs faturado+dev: {soma_fat_dev}")

    if abs(soma_vend - soma_fat_dev) > 0.5:
        print("!! VALIDAÇÃO FALHOU: soma por vendedor não bate com o total geral. Abortando sem publicar.")
        sys.exit(1)

    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    new_data_json = json.dumps(data, ensure_ascii=False)
    new_html, n = re.subn(r"const DATA = \{.*?\};\n", "const DATA = " + new_data_json + ";\n",
                           html, count=1, flags=re.S)
    if n != 1:
        print("!! Não encontrei o bloco 'const DATA = {...};' no index.html. Abortando sem publicar.")
        sys.exit(1)

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print("index.html atualizado com sucesso.")


if __name__ == "__main__":
    main()
