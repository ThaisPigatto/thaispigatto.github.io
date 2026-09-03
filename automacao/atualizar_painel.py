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
import shutil
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
TEMPLATE_HTML_PATH = os.path.join(BASE_DIR, "template_painel.html")
MESES_JSON_PATH = os.path.join(REPO_DIR, "meses.json")

CACHE_FAM_NOME = os.path.join(BASE_DIR, "fam_nome_cache.json")
CACHE_VEND_NOME = os.path.join(BASE_DIR, "vend_nome_cache.json")
CACHE_PRODUTO_FAMILIA = os.path.join(BASE_DIR, "produto_familia_cache.json")

# ----------------------------------------------------------------------------
# CONFIG — ajustar manualmente quando a meta do mês mudar (normalmente só
# no começo de cada mês). O resto (dias úteis, datas) é calculado sozinho.
# ----------------------------------------------------------------------------
META_GERAL = 1475000  # só os 4 grupos (870+105+200+300) — HUB tem meta própria, separada (Thais, 02/09/2026)
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
# Etapa "70" da Papéis passou a contar como Realizado em 03/09/2026 — decisão da Thais:
# "siga o do financeiro, o dele é sempre o correto, ajuste pra ficar igual". Achado que gerou
# a mudança: NF 00019902 (R$309,12, pedido em etapa 70 na Papéis) estava Autorizada e presente
# no relatório oficial do financeiro, mas ficava de fora do painel por essa regra excluir a 70.
REALIZADO_ETAPAS = {"matriz": {"60", "70"}, "papeis": {"60", "70", "80"}}

# CFOPs de SAÍDA que são venda de verdade (nota emitida pra cliente). 5.112/5.202 foram
# retirados em 03/09/2026: são "devolução de COMPRA" (a Pigatto devolvendo mercadoria pro
# FORNECEDOR dela) — não é receita de venda nenhuma, e estava inflando o faturado (achado
# cruzando o fechamento de agosto com o relatório do financeiro, NF 00019903, R$462,56).
CFOP_PREVISAO = {"5.102", "6.102"}
CFOP_REALIZADO = {"5.102", "6.102"}

# CFOPs de ENTRADA que representam devolução de VENDA (cliente devolvendo mercadoria pra
# Pigatto) — reduz o faturado. Adicionado em 03/09/2026: o robô nunca buscava nota de
# ENTRADA nenhuma (buscar_nf só pedia tpNF=1/saída), então nenhuma devolução de cliente
# jamais tinha sido contabilizada, em nenhum mês (achado: devolução ML de R$125,21 em
# agosto, CFOP 2.202, que não aparecia em lugar nenhum do painel).
CFOP_DEVOLUCAO_VENDA = {"1.202", "2.202", "3.202"}

TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
AGORA = datetime.datetime.now(TZ_SP)
HOJE = AGORA.date()
MES, ANO = HOJE.month, HOJE.year
ULTIMO_DIA_MES = calendar.monthrange(ANO, MES)[1]
INICIO_PREVISAO = datetime.datetime(ANO, MES, 1)
LIMITE_PREVISAO = datetime.datetime(ANO, MES, ULTIMO_DIA_MES)

# ----------------------------------------------------------------------------
# Virada de mês automática (desde 02/09/2026, pedido da Thais): o robô mesmo detecta
# quando o mês mudou, congela o index.html do mês anterior num arquivo separado
# (ex: 2026-09.html) e já nasce um index.html novo para o mês corrente, atualizando o
# seletor "Agosto / Setembro / ..." em TODOS os arquivos de mês existentes. Não precisa
# mais eu (Claude) gerar isso na mão todo início de mês.
# ----------------------------------------------------------------------------
MES_ATUAL_ID = f"{ANO:04d}-{MES:02d}"
NOME_MES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def carregar_meses():
    if os.path.exists(MESES_JSON_PATH):
        with open(MESES_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_meses(meses):
    with open(MESES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(meses, f, ensure_ascii=False, indent=2)


def atualizar_seletor_mes_no_arquivo(caminho, meses):
    """Reescreve só a linha 'const MESES_DISPONIVEIS = [...]' de um arquivo de mês
    (index.html atual ou um arquivo congelado), sem tocar em mais nada — inclusive um
    arquivo já congelado pode e deve continuar recebendo essa atualização, pra sempre
    listar todos os meses (inclusive os que vierem depois dele)."""
    with open(caminho, "r", encoding="utf-8") as f:
        html = f.read()
    meses_json_str = json.dumps(meses, ensure_ascii=False)
    new_html, n = re.subn(
        r"const MESES_DISPONIVEIS = \[.*?\];\n",
        "const MESES_DISPONIVEIS = " + meses_json_str + ";\n",
        html, count=1, flags=re.S,
    )
    if n == 1 and new_html != html:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(new_html)
        return True
    return False


def gerar_index_novo_mes():
    """Cria um index.html do zero (a partir do template) pro mês corrente, quando
    o mês vira. O DATA é preenchido depois, no fluxo normal do main()."""
    with open(TEMPLATE_HTML_PATH, "r", encoding="utf-8") as f:
        tpl = f.read()
    titulo_mes = f"{NOME_MES_PT[MES]}/{ANO}"
    range_mes = f"01/{MES:02d} a {ULTIMO_DIA_MES:02d}/{MES:02d}"
    html = tpl.replace("__PIGATTO_TITULO_MES__", titulo_mes)
    html = html.replace("__PIGATTO_RANGE_MES__", range_mes)
    html = html.replace("__PIGATTO_MES_ATUAL_ID__", MES_ATUAL_ID)
    html = html.replace("const MESES_DISPONIVEIS = __PIGATTO_MESES_JSON__;\n", "const MESES_DISPONIVEIS = [];\n")
    html = html.replace("const DATA = __PIGATTO_DATA_JSON__;\n", "const DATA = {};\n")
    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def checar_virada_de_mes(fam_nome_cache, vend_nome_cache, produto_familia):
    """Se o mês corrente ainda não está registrado em meses.json, congela o index.html
    de hoje (que é do mês anterior) num arquivo separado, refaz esse mês fechado do zero
    com dados frescos da OMIE (ver refazer_fechamento_do_mes) e cria um index.html novo."""
    meses = carregar_meses()
    if not meses:
        # meses.json não existe ainda (primeira vez que essa lógica roda) — não inventa
        # nada sozinho pra trás; só continua sem mexer no index.html atual. A Thais
        # semeia o meses.json manualmente 1x com o histórico já existente.
        print("!! meses.json não encontrado — virada de mês automática desativada até ele existir.")
        return meses, produto_familia
    if any(m["id"] == MES_ATUAL_ID for m in meses):
        return meses, produto_familia  # mês corrente já está registrado, nada a fazer
    print(f">> Virada de mês detectada: {MES_ATUAL_ID} ainda não existe em meses.json.")
    anterior = meses[-1]
    if anterior["arquivo"] == "index.html" and os.path.exists(INDEX_HTML_PATH):
        novo_nome_congelado = f"{anterior['id']}.html"
        caminho_congelado = os.path.join(REPO_DIR, novo_nome_congelado)
        shutil.copyfile(INDEX_HTML_PATH, caminho_congelado)
        anterior["arquivo"] = novo_nome_congelado
        print(f"   Mês {anterior['id']} congelado em {novo_nome_congelado} (snapshot do último horário rodado).")
        try:
            produto_familia = refazer_fechamento_do_mes(
                anterior["id"], caminho_congelado, fam_nome_cache, vend_nome_cache, produto_familia)
        except Exception as e:
            print(f"!! Recomputo do fechamento de {anterior['id']} falhou ({e}) — "
                  f"mantendo o snapshot cru do último horário rodado, sem travar a virada de mês.")
    meses.append({"id": MES_ATUAL_ID, "label": f"{NOME_MES_PT[MES]} {ANO}", "arquivo": "index.html"})
    gerar_index_novo_mes()
    salvar_meses(meses)
    print(f"   index.html novo criado para {MES_ATUAL_ID}.")
    return meses, produto_familia


# Feriados nacionais/confirmados que NÃO contam como dia útil (nem para o total de
# dias úteis do mês, nem para "dias decorridos"/ESPERADO, nem para "dias restantes").
# Adicionar aqui manualmente conforme confirmado — nunca supor feriado sem confirmação.
FERIADOS = {
    datetime.date(2026, 9, 7),   # Independência do Brasil — confirmado por Thais (01/09/2026)
    datetime.date(2026, 10, 12),  # Nossa Senhora Aparecida — confirmado por Thais (03/09/2026)
    datetime.date(2026, 11, 2),   # Finados — confirmado por Thais (03/09/2026)
    datetime.date(2026, 11, 15),  # Proclamação da República — confirmado por Thais (03/09/2026)
    datetime.date(2026, 11, 20),  # Consciência Negra — confirmado por Thais (03/09/2026)
    datetime.date(2026, 12, 25),  # Natal — confirmado por Thais (03/09/2026)
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
def _listar_nf_tipo(app_key, app_secret, d_ini, d_fim, tp_nf):
    todas = []
    pagina = 1
    while True:
        r = call("produtos/nfconsultar", "ListarNF", {
            "pagina": pagina, "registros_por_pagina": 50,
            "dEmiInicial": d_ini, "dEmiFinal": d_fim,
            "tpNF": tp_nf, "tpAmb": "1",
        }, app_key, app_secret)
        todas.extend(r.get("nfCadastro", []))
        if pagina >= r.get("total_de_paginas", 1):
            break
        pagina += 1
        time.sleep(1.0)
    return todas


def buscar_nf():
    """Busca as notas do período corrente. Desde 03/09/2026 busca tpNF="1" (saída — vendas)
    E tpNF="0" (entrada) — antes só se buscava saída, e por isso NENHUMA devolução de venda
    de cliente (que é sempre uma nota de ENTRADA) jamais tinha sido capturada pelo robô, em
    nenhum mês (achado cruzando agosto com o relatório do financeiro, 03/09/2026)."""
    dados = {}
    d_ini = f"01/{MES:02d}/{ANO}"
    d_fim = HOJE.strftime("%d/%m/%Y")
    for empresa, (app_key, app_secret) in EMPRESAS.items():
        saida = _listar_nf_tipo(app_key, app_secret, d_ini, d_fim, "1")
        time.sleep(1.0)
        entrada = _listar_nf_tipo(app_key, app_secret, d_ini, d_fim, "0")
        dados[empresa] = {"saida": saida, "entrada": entrada}
        print(f"{empresa} NFs: {len(saida)} saída, {len(entrada)} entrada")
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
            # Só conta como "Previsto" do mês corrente o que tem data de previsão DENTRO do mês
            # (>= dia 1 e <= último dia). Pedido com previsão atrasada de mês anterior, ainda
            # aberto (não cancelado, não faturado), NÃO entra aqui — mesma lógica do que foi
            # decidido pra etapa "10" em agosto/2026: previsão vencida não é previsão confiável
            # do mês. Confirmado por Thais, 02/09/2026.
            if dp is None or dp > LIMITE_PREVISAO or dp < INICIO_PREVISAO:
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
                    "data_previsao": dp.strftime("%d/%m/%Y"),
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
    no histórico de pedidoetapas, um registro desatualizado mostrando uma etapa antiga —
    o estado ao vivo já tinha avançado, e o histórico paginado ficou "para trás". Essa função
    faz uma segunda checagem, ao vivo, pra pegar exatamente esse tipo de caso.

    Nota sobre a etapa "70" da Papéis (atualizado em 03/09/2026): até 02/09/2026 essa etapa
    era tratada como excluída do Realizado pra Papéis (só 60/80 contavam). Cruzando outro caso
    real (NF 00019902, R$309,12, pedido em etapa 70, Autorizada e presente no relatório oficial
    do financeiro) a Thais confirmou a regra de ouro do projeto: "siga o do financeiro, o dele
    é sempre o correto" — então a etapa 70 passou a contar também pra Papéis (ver
    REALIZADO_ETAPAS). Essa checagem ao vivo continua existindo pra pegar histórico desatualizado
    em qualquer etapa, não só a 70.
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
        for nf in nf_dados[empresa]["saida"]:
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
                    "is_devolucao": False, "data_fatura": nf["ide"].get("dEmi", ""),
                })

        # Devoluções de venda (nota de ENTRADA — cliente devolvendo mercadoria). Não passa
        # pelo filtro de etapa do pedido: a devolução, uma vez Autorizada, já é o fato fiscal
        # completo por si só (o pedido de origem pode até já não existir mais na etapa viva).
        # Adicionado em 03/09/2026 — antes essas notas nem eram buscadas (ver buscar_nf).
        devolucoes_achadas = 0
        for nf in nf_dados[empresa]["entrada"]:
            if nf["ide"].get("cDeneg") != "N" or nf["ide"].get("dCan"):
                continue
            cod_vend = None
            if nf.get("titulos"):
                cod_vend = nf["titulos"][0].get("nCodVendedor")
            for item in nf["det"]:
                cfop = item["prod"]["CFOP"]
                if cfop not in CFOP_DEVOLUCAO_VENDA:
                    continue
                linhas.append({
                    "empresa": empresa, "nota": nf["ide"]["nNF"], "cfop": cfop,
                    "valor": -abs(item["prod"]["vProd"]),
                    "cod_produto": item["nfProdInt"]["nCodProd"], "cod_vend": cod_vend,
                    "is_devolucao": True, "data_fatura": nf["ide"].get("dEmi", ""),
                })
                devolucoes_achadas += 1
        if devolucoes_achadas:
            print(f"{empresa}: {devolucoes_achadas} linha(s) de devolução de venda encontrada(s)")

    total = sum(l["valor"] for l in linhas)
    total_dev = sum(l["valor"] for l in linhas if l["is_devolucao"])
    print(f"Realizado — Linhas incluidas: {len(linhas)}  Total: {round(total, 2)} (devoluções: {round(total_dev, 2)})")
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
        # Antes de 03/09/2026 "operacao" vinha sempre fixo em "Orçamento", mesmo pra devolução
        # de venda — isso fazia a devolução (quando existia) cair junto do faturado em vez de
        # ser contada à parte, e a HUB nunca enxergava devolução nenhuma. Agora reflete o que
        # a linha realmente é.
        return {
            "familia": nome_familia(l["empresa"], l["cod_produto"]),
            "vendedor": "Jéssica" if is_ml else vend, "is_ml": is_ml,
            "nota_fiscal": l["nota"], "pedido": None, "situacao": "Autorizado",
            "empresa": l["empresa"],
            "operacao": "Devolução de Venda" if l.get("is_devolucao") else "Orçamento",
            "cfop": l["cfop"], "total": l["valor"],
            "data_previsao": "",  # não se aplica ao faturado — já tem nota fiscal emitida
            "data_fatura": l.get("data_fatura", ""),  # data de emissão da nota (venda ou devolução)
        }

    def montar_prev(l):
        vend = nome_vendedor(l["empresa"], l["cod_vend"])
        is_ml = (vend == "Mercado Livre")
        return {
            "familia": nome_familia(l["empresa"], l["cod_produto"]),
            "vendedor": "Jéssica" if is_ml else vend, "is_ml": is_ml,
            "nota_fiscal": "N/D", "pedido": l["pedido"], "situacao": "Aguardando faturamento",
            "empresa": l["empresa"], "operacao": "Orçamento", "cfop": l["cfop"], "total": l["valor"],
            "data_previsao": l.get("data_previsao", ""),
            "data_fatura": "",  # não se aplica ao previsto — ainda não tem nota emitida
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

    # HUB tem meta própria e NÃO entra no total geral da empresa (voltou pra regra original em
    # 02/09/2026 — só durou 1 dia a versão que somava). hub_fat/hub_prev_v/hub_dev continuam
    # calculados aqui só porque precisam existir antes, pro bloco "pigatto_hub" mais abaixo.
    tot_fat = sum(g["faturado_total"] for g in grupos_familia_out)
    tot_prev = sum(g["previsto_total"] for g in grupos_familia_out)
    tot_dev = sum(g["devolucoes_total"] for g in grupos_familia_out)
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

    raw_cols = ["familia", "vendedor", "nota_fiscal", "pedido", "situacao", "empresa", "operacao", "cfop", "total",
                "data_previsao", "data_fatura"]

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


# ----------------------------------------------------------------------------
# 8) Recomputo de mês fechado (desde 03/09/2026): quando o mês vira, além de congelar o
# último snapshot rodado, o robô refaz esse mês do zero com dados frescos da OMIE. Isso
# existe pra pegar nota emitida (ou pedido que avançou de etapa) DEPOIS do último horário
# programado do último dia do mês — o robô só roda até um horário fixo, a operação não.
# Usa monkeypatch temporário das globais de período (MES/ANO/HOJE/etc) e das metas, pra
# reaproveitar as mesmas funções de busca/montagem do mês corrente sem duplicar lógica —
# e desfaz tudo no final (bloco finally), mesmo se der erro no meio.
# ----------------------------------------------------------------------------
def recomputar_mes_fechado(ano, mes, meta_geral_hist, grupos_metas_hist, hub_meta_hist,
                            fam_nome_cache, vend_nome_cache, produto_familia):
    global MES, ANO, HOJE, ULTIMO_DIA_MES, INICIO_PREVISAO, LIMITE_PREVISAO
    global DIAS_UTEIS_TOTAL, DIAS_UTEIS_DECORRIDOS, DIAS_UTEIS_RESTANTES, ESPERADO_PCT
    global META_GERAL, HUB_META

    estado_anterior = dict(
        MES=MES, ANO=ANO, HOJE=HOJE, ULTIMO_DIA_MES=ULTIMO_DIA_MES,
        INICIO_PREVISAO=INICIO_PREVISAO, LIMITE_PREVISAO=LIMITE_PREVISAO,
        DIAS_UTEIS_TOTAL=DIAS_UTEIS_TOTAL, DIAS_UTEIS_DECORRIDOS=DIAS_UTEIS_DECORRIDOS,
        DIAS_UTEIS_RESTANTES=DIAS_UTEIS_RESTANTES, ESPERADO_PCT=ESPERADO_PCT,
        META_GERAL=META_GERAL, HUB_META=HUB_META,
    )
    metas_grupos_anteriores = [g["meta"] for g in GRUPOS]
    try:
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        MES, ANO = mes, ano
        ULTIMO_DIA_MES = ultimo_dia
        HOJE = datetime.date(ano, mes, ultimo_dia)  # janela de busca fecha no último dia DAQUELE mês
        INICIO_PREVISAO = datetime.datetime(ano, mes, 1)
        LIMITE_PREVISAO = datetime.datetime(ano, mes, ultimo_dia)
        DIAS_UTEIS_TOTAL = dias_uteis_no_intervalo(datetime.date(ano, mes, 1), datetime.date(ano, mes, ultimo_dia))
        DIAS_UTEIS_DECORRIDOS = DIAS_UTEIS_TOTAL  # mês fechado: decorrido = total
        DIAS_UTEIS_RESTANTES = 1  # mês fechado não tem "restante" de verdade — só evita divisão por zero
        ESPERADO_PCT = 1.0
        META_GERAL = meta_geral_hist
        for g in GRUPOS:
            if g["id"] in grupos_metas_hist:
                g["meta"] = grupos_metas_hist[g["id"]]
        HUB_META = hub_meta_hist

        nf_dados = buscar_nf()
        etapas_matriz = buscar_etapas("matriz")
        etapas_papeis = buscar_etapas("papeis")
        pedidos_previsao = buscar_previsao()

        linhas_prev = montar_linhas_previsao(pedidos_previsao)
        linhas_real = montar_linhas_realizado(nf_dados, etapas_matriz, etapas_papeis)

        produto_familia = atualizar_cache_familias(linhas_real, linhas_prev, produto_familia)
        real_rows, prev_rows = montar_parsed_rows(linhas_real, linhas_prev, fam_nome_cache, vend_nome_cache, produto_familia)
        data = montar_data(real_rows, prev_rows)
        return data, produto_familia
    finally:
        MES = estado_anterior["MES"]; ANO = estado_anterior["ANO"]; HOJE = estado_anterior["HOJE"]
        ULTIMO_DIA_MES = estado_anterior["ULTIMO_DIA_MES"]
        INICIO_PREVISAO = estado_anterior["INICIO_PREVISAO"]; LIMITE_PREVISAO = estado_anterior["LIMITE_PREVISAO"]
        DIAS_UTEIS_TOTAL = estado_anterior["DIAS_UTEIS_TOTAL"]
        DIAS_UTEIS_DECORRIDOS = estado_anterior["DIAS_UTEIS_DECORRIDOS"]
        DIAS_UTEIS_RESTANTES = estado_anterior["DIAS_UTEIS_RESTANTES"]
        ESPERADO_PCT = estado_anterior["ESPERADO_PCT"]
        META_GERAL = estado_anterior["META_GERAL"]; HUB_META = estado_anterior["HUB_META"]
        for g, meta_orig in zip(GRUPOS, metas_grupos_anteriores):
            g["meta"] = meta_orig


def refazer_fechamento_do_mes(mes_id, caminho_arquivo, fam_nome_cache, vend_nome_cache, produto_familia):
    """Lê o arquivo recém-congelado, pega as metas que ele já tinha (não usa a meta do mês
    novo!), reprocessa aquele mês do zero com dados frescos da OMIE e regrava só o bloco
    DATA desse arquivo — sem tocar em mais nada (layout, seletor de mês, etc)."""
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    if not m:
        raise RuntimeError("não achei o bloco 'const DATA = {...};' no arquivo congelado")
    data_antiga = json.loads(m.group(1))
    ano, mes = (int(x) for x in mes_id.split("-"))
    meta_geral_hist = data_antiga["totais"]["meta"]
    grupos_metas_hist = {g["id"]: g["meta"] for g in data_antiga["grupos_familia"] if g.get("meta")}
    hub_grp_antigo = next((g for g in data_antiga["grupos_familia"] if g["id"] == "pigatto_hub"), None)
    hub_meta_hist = hub_grp_antigo["meta"] if hub_grp_antigo else HUB_META

    data_novo, produto_familia = recomputar_mes_fechado(
        ano, mes, meta_geral_hist, grupos_metas_hist, hub_meta_hist,
        fam_nome_cache, vend_nome_cache, produto_familia,
    )

    # Mesma checagem de consistência do main() — se não bater, mantém o snapshot antigo
    # em vez de publicar um recomputo quebrado.
    hub_grp_novo = next((g for g in data_novo["grupos_familia"] if g["id"] == "pigatto_hub"), None)
    hub_fat_dev = (hub_grp_novo["faturado_total"] + hub_grp_novo["devolucoes_total"]) if hub_grp_novo else 0.0
    soma_vend = round(sum(v["total"] for v in data_novo["vend_real"]), 2)
    soma_fat_dev = round(data_novo["totais"]["faturado"] + data_novo["totais"]["devolucoes"] + hub_fat_dev, 2)
    if abs(soma_vend - soma_fat_dev) > 0.5:
        raise RuntimeError(f"validação falhou no recomputo de {mes_id} ({soma_vend} vs {soma_fat_dev})")

    novo_html, n = re.subn(
        r"const DATA = \{.*?\};\n", "const DATA = " + json.dumps(data_novo, ensure_ascii=False) + ";\n",
        html, count=1, flags=re.S,
    )
    if n != 1:
        raise RuntimeError(f"não consegui regravar o bloco DATA de {mes_id}")
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        f.write(novo_html)
    print(f"   {mes_id}: recomputado com dados frescos da OMIE (regras corrigidas em 03/09/2026).")
    return produto_familia


def main():
    fam_nome_cache = json.load(open(CACHE_FAM_NOME, encoding="utf-8"))
    vend_nome_cache = json.load(open(CACHE_VEND_NOME, encoding="utf-8"))
    produto_familia = json.load(open(CACHE_PRODUTO_FAMILIA, encoding="utf-8"))

    # Vira o mês? Congela o mês anterior, refaz esse fechamento com dados frescos da OMIE
    # e nasce um index.html novo — antes de mais nada. (Precisa dos caches carregados
    # acima porque o recomputo do mês fechado usa as mesmas funções de busca/montagem.)
    meses, produto_familia = checar_virada_de_mes(fam_nome_cache, vend_nome_cache, produto_familia)
    if meses:
        for m in meses:
            caminho = os.path.join(REPO_DIR, m["arquivo"])
            if os.path.exists(caminho):
                atualizar_seletor_mes_no_arquivo(caminho, meses)

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

    # soma_vend (vend_real) inclui TODO mundo, inclusive a HUB/Jéssica. Desde 02/09/2026 a HUB
    # tem meta própria e não entra em data["totais"] (total geral da empresa) — então o total
    # "esperado" pra bater com soma_vend precisa somar de volta o faturado+devolução da HUB.
    hub_grp = next((g for g in data["grupos_familia"] if g["id"] == "pigatto_hub"), None)
    hub_fat_dev = (hub_grp["faturado_total"] + hub_grp["devolucoes_total"]) if hub_grp else 0.0
    soma_vend = round(sum(v["total"] for v in data["vend_real"]), 2)
    soma_fat_dev = round(data["totais"]["faturado"] + data["totais"]["devolucoes"] + hub_fat_dev, 2)
    print(f"Total geral faturado: {data['totais']['faturado']} | previsto: {data['totais']['previsto']}")
    print(f"Soma vend_real: {soma_vend} vs faturado+dev (+HUB): {soma_fat_dev}")

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


def reprocessar_mes_manual(mes_id):
    """Caminho separado, disparado manualmente (ver workflow_dispatch, input
    'reprocessar_mes'): reprocessa do zero um mês JÁ FECHADO específico (ex: '2026-08'),
    usando dados frescos da OMIE com as regras corrigidas em 03/09/2026. Não mexe no
    index.html do mês corrente nem depende de ter havido virada de mês agora — serve pra
    corrigir um mês fechado sob demanda, uma vez, quando precisar (ex: cruzou com o
    financeiro e achou divergência)."""
    meses = carregar_meses()
    alvo = next((m for m in meses if m["id"] == mes_id), None)
    if alvo is None:
        print(f"!! Mês {mes_id} não encontrado em meses.json. Nada a fazer.")
        sys.exit(1)
    caminho = os.path.join(REPO_DIR, alvo["arquivo"])
    if not os.path.exists(caminho):
        print(f"!! Arquivo {alvo['arquivo']} não encontrado. Nada a fazer.")
        sys.exit(1)
    fam_nome_cache = json.load(open(CACHE_FAM_NOME, encoding="utf-8"))
    vend_nome_cache = json.load(open(CACHE_VEND_NOME, encoding="utf-8"))
    produto_familia = json.load(open(CACHE_PRODUTO_FAMILIA, encoding="utf-8"))
    produto_familia = refazer_fechamento_do_mes(mes_id, caminho, fam_nome_cache, vend_nome_cache, produto_familia)
    json.dump(produto_familia, open(CACHE_PRODUTO_FAMILIA, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Reprocessamento manual de {mes_id} concluído com sucesso.")


if __name__ == "__main__":
    _mes_manual = os.environ.get("REPROCESSAR_MES", "").strip()
    if _mes_manual:
        reprocessar_mes_manual(_mes_manual)
    else:
        main()
