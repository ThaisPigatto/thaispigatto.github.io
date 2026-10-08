#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robô do Painel de Esforço Comercial (CRM Omie -> esforco_data.js)

Roda no GitHub Actions (workflow esforco-crm.yml), no mesmo padrão do robô do painel de
faturamento (atualizar_painel.py): credenciais vêm dos Secrets do repositório, nada fica no código.

O que faz, em ordem:
  1) Lê do CRM do Omie (Matriz e Pápeis): tarefas (ligação, WhatsApp, e-mail, visita...) e oportunidades,
     mais as tabelas auxiliares (soluções, tipos de cliente, origens, usuários, tipos de tarefa).
  2) Liga cada tarefa à sua oportunidade (nCodOp) -> descobre família, cliente novo x carteira, origem
     e se a oportunidade virou venda.
  3) Lê o ticket médio de VENDAS direto dos arquivos mensais do painel de faturamento que já estão no
     repositório (2026-08.html, 2026-09.html, index.html...). Assim o número é o mesmo do faturamento oficial.
  4) Escreve esforco_data.js (window.ESFORCO_DATA = {...}). O painel (esforco.html) só lê esse arquivo.

Uso:
  python automacao/esforco_crm.py             # produção (precisa dos 4 Secrets OMIE_*)
  python automacao/esforco_crm.py --amostra   # gera dados de EXEMPLO (sem Omie), só pra testar o visual

As metas e regras ficam em automacao/esforco_config.json (editável direto no GitHub).
"""
import datetime
import html as htmllib
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zoneinfo
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "esforco_config.json")
SAIDA_JS = os.path.join(REPO_DIR, "esforco_data.js")
MESES_JSON = os.path.join(REPO_DIR, "meses.json")

TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")

# Ordem fixa: o painel lê os números pelo índice. Se mudar aqui, mude no esforco.html também.
CANAIS = ["ligacao", "ligacao_nao", "whatsapp", "email", "visita", "reuniao", "cotacao"]
TIPOS = ["carteira", "novo"]

# Grupos do painel de faturamento (atualizar_painel.py) -> famílias deste painel.
# (no faturamento o grupo "quimicos" é o que aqui se chama "Especialidades")
GRUPO_FATURAMENTO_PARA_FAMILIA = {
    "adesivos": "adesivos",
    "quimicos": "especialidades",
    "papeis": "papeis",
    "plasticos": "plasticos",
    "pigatto_hub": "hub",
}


# Fases do funil do CRM (definições do próprio Omie da Pigatto). O robô lê as reais todo dia; esta lista é só reserva/amostra.
FASES_PADRAO = [
    {"n": 1, "nome": "01 Prospect", "descricao": "Oportunidade identificada e qualificada: o cliente precisa da solução e tem condições de adquirir. Faz-se o levantamento detalhado das necessidades e mapeia-se quem decide e influencia na empresa."},
    {"n": 2, "nome": "02 Qualificação", "descricao": "Filtro para entender se o negócio realmente existe e deve seguir adiante no processo comercial."},
    {"n": 3, "nome": "03 Apresentação", "descricao": "Apresentação personalizada da solução, focada no que interessa a cada pessoa da cadeia de decisão do cliente."},
    {"n": 4, "nome": "04 Amostra/Cotação", "descricao": "Elabora-se e entrega-se ao cliente a proposta comercial e técnica (amostra/cotação)."},
    {"n": 5, "nome": "05 Negociação", "descricao": "Fase final de decisão: negociação com o cliente para fechar o negócio. Podem existir várias versões da proposta."},
    {"n": 6, "nome": "06 Conclusão", "descricao": "Registra-se a conquista ou a perda da oportunidade, indicando o motivo."},
]


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------
def norm(s):
    """minúsculo, sem acento, sem espaços nas pontas — pra comparar nomes sem erro de digitação."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def nome_bonito(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s.title() if s.isupper() else s


def data_br_para_iso(d):
    try:
        return datetime.datetime.strptime(d, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def carregar_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------
# API do Omie
# ----------------------------------------------------------------------------
def omie_call(url_path, call_name, param, app_key, app_secret, retries=6):
    url = f"https://app.omie.com.br/api/v1/{url_path}/"
    payload = {"call": call_name, "app_key": app_key, "app_secret": app_secret, "param": [param]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    for tentativa in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            corpo = e.read().decode(errors="replace")
            # Omie responde erro quando não há registros / página inexistente: tratamos como lista vazia
            if "Client-5113" in corpo or "Client-5094" in corpo or "Não existem registros" in corpo:
                return {"total_de_paginas": 0, "cadastros": []}
            if tentativa < retries - 1:
                time.sleep(4 * (tentativa + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if tentativa < retries - 1:
                time.sleep(4 * (tentativa + 1))
                continue
            raise


def _lista_da_resposta(resp):
    """As APIs do CRM devolvem os itens em 'cadastros'; por segurança aceita a primeira lista da resposta."""
    if isinstance(resp.get("cadastros"), list):
        return resp["cadastros"]
    for v in resp.values():
        if isinstance(v, list):
            return v
    return []


def paginar(url_path, call_name, param_base, app_key, app_secret, por_pagina=100, pausa=0.4):
    itens, pagina = [], 1
    while True:
        param = dict(param_base, pagina=pagina, registros_por_pagina=por_pagina)
        resp = omie_call(url_path, call_name, param, app_key, app_secret)
        itens.extend(_lista_da_resposta(resp))
        total = resp.get("total_de_paginas", 1) or 1
        if pagina >= total:
            break
        pagina += 1
        time.sleep(pausa)
    return itens


def _mapa(itens, chave_id, chaves_nome):
    mapa = {}
    for it in itens:
        cod = it.get(chave_id)
        nome = next((it[k] for k in chaves_nome if it.get(k)), None)
        if cod is not None and nome:
            mapa[cod] = str(nome).strip()
    return mapa


def carregar_lookups(app_key, app_secret):
    """Tabelas auxiliares do CRM de UMA empresa (os códigos mudam de uma empresa para outra)."""
    def lista(path, call):
        return paginar(path, call, {}, app_key, app_secret, por_pagina=100)

    solucoes = _mapa(lista("crm/solucoes", "ListarSolucoes"), "nCodigo", ["cDescricao"])
    tipos_cli = _mapa(lista("crm/tipos", "ListarTipos"), "nCodigo", ["cDescricao"])
    origens = _mapa(lista("crm/origens", "ListarOrigens"), "nCodigo", ["cDescricao"])
    usuarios = _mapa(lista("crm/usuarios", "ListarUsuarios"), "nCodigo", ["cNome", "cDescricao", "cNomeUsuario", "cLogin"])
    tipos_tarefa = _mapa(lista("crm/tipostarefa", "ListarTiposTarefa"), "nIdTipoTarefa", ["cDescricao"])
    status = _mapa(lista("crm/status", "ListarStatus"), "nCodigo", ["cDescricao"])
    fases_raw = lista("crm/fases", "ListarFases")
    fases, fases_info = {}, {}
    for f in fases_raw:
        cod = f.get("nCodigo", f.get("nCodFase"))
        nome = f.get("cDescrUsuario") or f.get("cDescrPadrao") or ""
        m = re.match(r"\s*(\d+)", nome)
        if cod is not None and m:
            fases[cod] = int(m.group(1))
            fases_info[cod] = {"n": int(m.group(1)), "nome": nome.strip(),
                               "descricao": htmllib.unescape(f.get("cObservacao") or "").strip()}
    contas = {}
    for c in lista("crm/contas", "ListarContas"):
        ident = c.get("identificacao", {})
        nome_conta = (ident.get("cNome") or ident.get("cNomeFantasia") or "").strip()
        if ident.get("nCod") is not None and nome_conta:
            contas[ident["nCod"]] = nome_conta
    return {"solucoes": solucoes, "tipos_cli": tipos_cli, "origens": origens, "usuarios": usuarios,
            "tipos_tarefa": tipos_tarefa, "status": status, "fases": fases,
            "fases_info": fases_info, "contas": contas}


# ----------------------------------------------------------------------------
# classificação
# ----------------------------------------------------------------------------
def canal_da_tarefa(nome_tipo):
    """Nome do tipo de tarefa -> canal de esforço. None = não é esforço comercial (nota, prazo, projeto...).
    Funciona com os nomes da Matriz ('Ligar', 'Whatsapp', 'Visita'...) e da Pápeis ('Whatsapp Enviado',
    'Reunião Presencial'...)."""
    n = norm(nome_tipo)
    if not n:
        return None
    if "nao atendida" in n:
        return "ligacao_nao"
    if "ligacao" in n or n.startswith("ligar"):
        return "ligacao"
    if "whats" in n:
        return "whatsapp"
    if "e-mail" in n or "email" in n:
        return "email"
    if "visita" in n or "presencial" in n:
        return "visita"
    if "reuniao" in n:
        return "reuniao"          # online/genérica: aparece na análise, não conta na meta de teste/visita
    if "cotacao" in n:
        return "cotacao"
    return None                   # Nota, Tarefa, Tarefa Futura, Prazo Final, Projeto, Pedido faturado


def familia_da_solucao(nome_solucao, cfg):
    n = norm(nome_solucao)
    for fam in cfg["familias"] + [cfg["hub"]]:
        if any(norm(s) == n for s in fam.get("solucoes", [])):
            return fam["id"]
    return None


def tipo_cliente(nome_tipo, cfg):
    n = norm(nome_tipo)
    if "novo" in n:
        return "novo"
    if "reciclado" in n:
        return cfg.get("cliente_reciclado_conta_como", "novo")
    return "carteira"             # 'Cliente Corrente' e qualquer outro


def status_oportunidade(nome_status):
    n = norm(nome_status)
    if "conquist" in n:
        return "ganha"
    if "perdid" in n:
        return "perdida"
    if "ativo" in n:
        return "ativa"
    return "outra"                # cancelada / suspensa


def vendedor_canonico(nome, cfg):
    nome = nome_bonito(nome)
    alias = {norm(k): v for k, v in cfg.get("vendedor_alias", {}).items()}
    return alias.get(norm(nome), nome)


# ----------------------------------------------------------------------------
# vendas (lê os arquivos mensais do painel de faturamento que já estão no repositório)
# ----------------------------------------------------------------------------
def _extrair_data_js(html):
    m = re.search(r"const DATA\s*=\s*(\{)", html)
    if not m:
        return None
    i = m.start(1)
    prof, j, em_texto, esc = 0, i, False, False
    while j < len(html):
        c = html[j]
        if em_texto:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                em_texto = False
        else:
            if c == '"':
                em_texto = True
            elif c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
                if prof == 0:
                    return json.loads(html[i:j + 1])
        j += 1
    return None


def extrair_vendas(repo_dir):
    """Ticket médio por NOTA FISCAL faturada, por família, por mês — das mesmas linhas do painel de faturamento."""
    caminho = os.path.join(repo_dir, "meses.json")
    if not os.path.exists(caminho):
        print("AVISO vendas: meses.json não encontrado — seção de vendas fica vazia")
        return {"fonte": "indisponível", "meses": []}
    with open(caminho, encoding="utf-8") as f:
        meses = json.load(f)
    saida = []
    for m in meses:
        arq = os.path.join(repo_dir, m.get("arquivo", ""))
        if not os.path.exists(arq):
            continue
        try:
            with open(arq, encoding="utf-8") as f:
                data = _extrair_data_js(f.read())
            if not data:
                continue
            fam2grupo = {}
            for g in data.get("grupos_familia", []):
                for linha in g.get("linhas", []):
                    fam2grupo[linha["familia"]] = g["id"]
            fam2grupo.update({"Silquim": "adesivos", "SILQUIM": "adesivos"})
            valor, notas = defaultdict(float), defaultdict(set)
            for r in data.get("raw_real", []):
                if r.get("total", 0) <= 0:       # devolução (negativa) não entra no ticket
                    continue
                grupo = GRUPO_FATURAMENTO_PARA_FAMILIA.get(fam2grupo.get(r["familia"]))
                if not grupo:
                    continue
                valor[grupo] += r["total"]
                notas[grupo].add((r.get("empresa"), r.get("nota_fiscal")))
            por_fam = {}
            for fid in valor:
                n = len(notas[fid])
                por_fam[fid] = {"nfs": n, "valor": round(valor[fid], 2), "ticket": round(valor[fid] / n, 2) if n else 0}
            saida.append({"id": m["id"], "label": m.get("label", m["id"]), "porFamilia": por_fam})
        except Exception as e:  # um arquivo ruim não derruba o robô inteiro
            print(f"AVISO vendas: não consegui ler {m.get('arquivo')}: {e}")
    return {"fonte": "Painel de faturamento (NF-e autorizadas, Matriz + Pápeis) — ticket médio por nota fiscal",
            "meses": saida}


# ----------------------------------------------------------------------------
# montagem dos dados (função pura: recebe o que veio do Omie, devolve o dicionário do painel)
# ----------------------------------------------------------------------------
def montar_dados(empresas, cfg, vendas, hoje, agora_iso=None):
    """
    empresas = { 'matriz': {'lookups': {...}, 'oportunidades': [...], 'tarefas': [...]}, 'papeis': {...} }
    hoje     = datetime.date (data de hoje em São Paulo)
    """
    fam_ids = [f["id"] for f in cfg["familias"]]
    fam_idx = {fid: i for i, fid in enumerate(fam_ids)}
    inicio = cfg.get("inicio_dados", "2026-01-01")
    hoje_iso = hoje.isoformat()

    vendedores = []
    def idx_vend(nome):
        if nome not in vendedores:
            vendedores.append(nome)
        return vendedores.index(nome)

    contagem = defaultdict(int)               # (data, fam, vend, canal, tipo) -> qtd
    hub_cont = defaultdict(int)               # (data, 'anuncio'|'licitacao') -> qtd
    opp_info = {}                             # (empresa, nCodOp) -> dict
    toques = defaultdict(lambda: defaultdict(int))   # (empresa, nCodOp) -> canal -> qtd
    ultima_tarefa = {}                        # (empresa, nCodOp) -> data iso
    recentes = []
    q = defaultdict(int)                      # contadores de qualidade
    solucoes_sem_familia = defaultdict(int)
    tipos_ignorados = defaultdict(int)

    for emp, dados in empresas.items():
        lk = dados["lookups"]
        # --- oportunidades
        for o in dados["oportunidades"]:
            ident = o.get("identificacao", {})
            fs = o.get("fasesStatus", {})
            ou = o.get("outrasInf", {})
            cod = ident.get("nCodOp")
            sol = lk["solucoes"].get(ident.get("nCodSolucao"), "")
            fam = familia_da_solucao(sol, cfg)
            if sol and fam is None:
                solucoes_sem_familia[sol] += 1
            origem_nome = lk["origens"].get(ident.get("nCodOrigem"), "") or "Sem origem"
            opp_info[(emp, cod)] = {
                "fam": fam, "sol": sol,
                "vend": vendedor_canonico(lk["usuarios"].get(ident.get("nCodVendedor"), f"Vendedor {ident.get('nCodVendedor')}"), cfg),
                "tipo": tipo_cliente(lk["tipos_cli"].get(ou.get("nCodTipo"), ""), cfg),
                "origem": origem_nome,
                "status": status_oportunidade(lk["status"].get(fs.get("nCodStatus"), "")),
                "criada": data_br_para_iso(ou.get("dInclusao", "")),
                "concluida": data_br_para_iso(fs.get("dConclusao", "")),
                "fase": lk["fases"].get(fs.get("nCodFase")),
                "nome": re.sub(r"\s*-\s*[^-]*$", "", ident.get("cDesOp", "")).strip() or ident.get("cDesOp", ""),
                "ticket_ok": (o.get("ticket", {}).get("nTicket") or 0) > 0,
                "sem_origem": not ident.get("nCodOrigem"),
                "num": ident.get("cNumOp", ""),
                "emp": "Matriz" if emp == "matriz" else "Pápeis",
                "cliente": lk.get("contas", {}).get(ident.get("nCodConta"), ""),
                "fase_nome": lk.get("fases_info", {}).get(fs.get("nCodFase"), {}).get("nome", ""),
            }
        # --- tarefas
        for t in dados["tarefas"]:
            d_iso = data_br_para_iso(t.get("dData", ""))
            if not d_iso or d_iso < inicio or d_iso > hoje_iso:
                continue
            nome_tipo = lk["tipos_tarefa"].get(t.get("nCodAtividade"), "")
            canal = canal_da_tarefa(nome_tipo)
            if canal is None:
                tipos_ignorados[nome_tipo or "(sem tipo)"] += 1
                continue
            q["tarefas_total"] += 1
            chave = (emp, t.get("nCodOp"))
            info = opp_info.get(chave)
            vend = vendedor_canonico(lk["usuarios"].get(t.get("nCodUsuario"), f"Usuário {t.get('nCodUsuario')}"), cfg)
            descr = norm(f"{t.get('cDescricao', '')} {info['nome'] if info else ''}")
            # Hub: por solução do Hub ou por palavra na descrição
            for regra, palavras in cfg["hub"].get("regras_texto", {}).items():
                if any(norm(p) in descr for p in palavras) and (info is None or info["fam"] in (None, "hub")):
                    hub_cont[(d_iso, regra)] += 1
            if info is None or info["fam"] is None or info["fam"] == "hub":
                if info is None:
                    q["tarefas_sem_oportunidade"] += 1
                continue
            contagem[(d_iso, fam_idx[info["fam"]], idx_vend(vend), CANAIS.index(canal), TIPOS.index(info["tipo"]))] += 1
            toques[chave][canal] += 1
            if d_iso > ultima_tarefa.get(chave, ""):
                ultima_tarefa[chave] = d_iso
            recentes.append((d_iso, t.get("cHora", "00:00"), vend, canal, info["fam"]))

    atividades = [[d, f, v, c, ti, qtd] for (d, f, v, c, ti), qtd in sorted(contagem.items())]
    hub_regs = [[d, r, qtd] for (d, r), qtd in sorted(hub_cont.items())]

    # --- bloco de oportunidades (análise canal x resultado, origem, projetos, qualidade)
    oportunidades, projetos = [], []
    paradas = ativas = sem_origem = ativas_sem_ticket = 0
    limite_parada = (hoje - datetime.timedelta(days=cfg.get("dias_oportunidade_parada", 14))).isoformat()
    fases_cfg = cfg.get("projetos", {})
    for (emp, cod), info in opp_info.items():
        if info["fam"] is None or info["fam"] == "hub":
            continue
        criada = info["criada"] or ""
        k = toques.get((emp, cod), {})
        if info["status"] == "ativa":
            ativas += 1
            if ultima_tarefa.get((emp, cod), criada) < limite_parada:
                paradas += 1
            if not info["ticket_ok"]:
                ativas_sem_ticket += 1
            if info["fam"] == fases_cfg.get("familia") and info["fase"]:
                projetos.append({"nome": info["nome"], "cliente": info["cliente"], "fase": info["fase"],
                                 "faseNome": info["fase_nome"], "vend": info["vend"], "nOp": info["num"], "emp": info["emp"]})
        if info["sem_origem"]:
            sem_origem += 1
        if criada and criada >= inicio or info["status"] != "ativa":
            oportunidades.append({
                "f": fam_idx[info["fam"]], "v": idx_vend(info["vend"]), "t": info["tipo"], "o": info["origem"],
                "s": info["status"], "c": info["criada"], "x": info["concluida"],
                "k": {c: k.get(c, 0) for c in CANAIS if k.get(c, 0)},
            })

    # --- últimas atualizações
    recentes.sort(reverse=True)
    nomes_canal = {"ligacao": "ligação", "ligacao_nao": "ligação não atendida", "whatsapp": "WhatsApp", "email": "e-mail",
                   "visita": "visita", "reuniao": "reunião", "cotacao": "cotação"}
    nome_fam = {f["id"]: f["nome"] for f in cfg["familias"]}
    ult = []
    for d_iso, hora, vend, canal, fid in recentes[:8]:
        quando = hora if d_iso == hoje_iso else datetime.date.fromisoformat(d_iso).strftime("%d/%m")
        ult.append({"h": quando, "t": f"{vend.split()[0]} registrou {nomes_canal[canal]} ({nome_fam[fid]})", "f": fid})

    qualidade = {
        "tarefasTotal": q["tarefas_total"],
        "tarefasSemOportunidade": q["tarefas_sem_oportunidade"],
        "oportunidadesAtivas": ativas,
        "ativasParadas": paradas,
        "diasParada": cfg.get("dias_oportunidade_parada", 14),
        "oportunidadesSemOrigem": sem_origem,
        "ativasSemTicket": ativas_sem_ticket,
        "solucoesSemFamilia": dict(solucoes_sem_familia),
        "tiposIgnorados": dict(tipos_ignorados),
    }

    fases_crm = []
    for emp_pref in ("matriz", "papeis"):
        info_f = empresas.get(emp_pref, {}).get("lookups", {}).get("fases_info", {})
        if info_f:
            fases_crm = sorted(info_f.values(), key=lambda x: x["n"])
            break
    if not fases_crm:
        fases_crm = FASES_PADRAO

    return {
        "meta": {"geradoEm": agora_iso or datetime.datetime.now(TZ_SP).isoformat(timespec="seconds"),
                 "hoje": hoje_iso, "amostra": False, "fonte": "CRM Omie (Matriz + Pápeis)", "versao": 1},
        "config": {"feriados": cfg["feriados"], "inicio": inicio,
                   "ligacaoContaComoContato": cfg.get("ligacao_conta_em_contato_se_familia_sem_meta_de_ligacao", True)},
        "canais": CANAIS, "tipos": TIPOS,
        "familias": [{"id": f["id"], "nome": f["nome"], "cor": f["cor"], "metas": f["metas"]} for f in cfg["familias"]],
        "hub": {"id": cfg["hub"]["id"], "nome": cfg["hub"]["nome"], "cor": cfg["hub"]["cor"], "metas": cfg["hub"]["metas"]},
        "vendedores": vendedores,
        "atividades": atividades,
        "hubRegistros": hub_regs,
        "oportunidades": oportunidades,
        "vendas": vendas,
        "qualidade": qualidade,
        "projetos": projetos,
        "fasesCrm": fases_crm,
        "recentes": ult,
        "alertasExtra": [],
    }


# ----------------------------------------------------------------------------
# dados de EXEMPLO (só para testar o visual; o painel mostra uma faixa avisando)
# ----------------------------------------------------------------------------
def gerar_amostra(cfg, vendas, hoje):
    rnd = random.Random(2026)
    fam_ids = [f["id"] for f in cfg["familias"]]
    time_por_fam = {  # vendedor(es) de cada família (exemplo)
        "adesivos": ["Wellington Azevedo", "Tiago Fruet"],
        "especialidades": ["Tiago Fruet", "Marcelo Ribeiro", "Wellington Azevedo"],
        "plasticos": ["Maria Cristina Cardozo"],
        "papeis": ["Rhamayana Ramos"],
    }
    vendedores = ["Wellington Azevedo", "Tiago Fruet", "Marcelo Ribeiro", "Maria Cristina Cardozo", "Rhamayana Ramos", "Jéssica Sant'Anna"]
    feriados = {datetime.date.fromisoformat(d) for d in cfg["feriados"]}
    ini = datetime.date.fromisoformat(cfg["inicio_dados"])
    dias = [ini + datetime.timedelta(days=i) for i in range((hoje - ini).days + 1)]
    dias = [d for d in dias if d.weekday() < 5 and d not in feriados]
    contagem = defaultdict(int)
    for di, d in enumerate(dias):
        tendencia = 0.55 + 0.35 * di / max(1, len(dias) - 1)           # equipe vai melhorando ao longo do tempo
        for fi, fam in enumerate(cfg["familias"]):
            m = fam["metas"]
            time_ = time_por_fam[fam["id"]]
            for nome in time_:
                vi = vendedores.index(nome)
                peso = 1 / len(time_) * (1.15 if nome == time_[0] else 0.85 if len(time_) > 1 else 1)
                fator = max(0.1, rnd.gauss(tendencia, 0.22))
                def n(meta_sem):
                    return max(0, round(meta_sem / 5 * peso * fator + rnd.random() * 0.6 - 0.3)) if meta_sem else 0
                lig_conta = m["ligacao"] is None
                # contato carteira / novo (WhatsApp + e-mail; ligação se a família não tem meta própria)
                for tipo, chave in ((0, "carteira"), (1, "novos")):
                    tot = n(m[chave])
                    for _ in range(tot):
                        r = rnd.random()
                        canal = ("whatsapp" if r < .66 else "email" if r < .9 else "ligacao") if lig_conta else ("whatsapp" if r < .72 else "email")
                        contagem[(d.isoformat(), fi, vi, CANAIS.index(canal), tipo)] += 1
                for _ in range(n(m["ligacao"] or 0)):
                    atendida = rnd.random() < 0.58
                    contagem[(d.isoformat(), fi, vi, CANAIS.index("ligacao" if atendida else "ligacao_nao"),
                              0 if rnd.random() < .7 else 1)] += 1
                for _ in range(n(m["visita"] or 0)):
                    contagem[(d.isoformat(), fi, vi, CANAIS.index("visita"), 0 if rnd.random() < .6 else 1)] += 1
                if rnd.random() < 0.18 * fator:
                    contagem[(d.isoformat(), fi, vi, CANAIS.index("cotacao"), 0)] += 1
                if rnd.random() < 0.10 * fator:
                    contagem[(d.isoformat(), fi, vi, CANAIS.index("reuniao"), 1)] += 1
    atividades = [[d, f, v, c, t, q] for (d, f, v, c, t), q in sorted(contagem.items())]
    hub = []
    for d in dias:
        if rnd.random() < 0.55:
            hub.append([d.isoformat(), "anuncio", rnd.choice([1, 1, 2])])
        if rnd.random() < 0.28:
            hub.append([d.isoformat(), "licitacao", 1])
    origens = ["Google Ads", "Indicação Cliente", "Ativo", "Site", "Feira / Evento"]
    opps = []
    for _ in range(260):
        fi = rnd.choices(range(len(fam_ids)), weights=[3, 2, 5, 9])[0]
        nome = rnd.choice(time_por_fam[fam_ids[fi]])
        tipo = "novo" if rnd.random() < 0.35 else "carteira"
        criada = ini + datetime.timedelta(days=rnd.randrange(0, (hoje - ini).days))
        r = rnd.random()
        status = "ganha" if r < .38 else "perdida" if r < .50 else "ativa"
        k = {}
        lig_pref = rnd.random() < .45
        for canal, base in (("ligacao", 3 if lig_pref else 1), ("whatsapp", 4), ("email", 2), ("visita", 1)):
            bonus = 1 if (status == "ganha" and canal in ("ligacao", "visita")) else 0
            v = max(0, round(rnd.gauss(base + bonus, 1.4)))
            if v:
                k[canal] = v
        opps.append({"f": fi, "v": vendedores.index(nome), "t": tipo, "o": rnd.choices(origens, weights=[3, 2, 4, 2, 1])[0],
                     "s": status, "c": criada.isoformat(),
                     "x": (criada + datetime.timedelta(days=rnd.randrange(3, 40))).isoformat() if status != "ativa" else None, "k": k})
    projetos = [{"nome": n, "cliente": c, "fase": f, "faseNome": FASES_PADRAO[f - 1]["nome"], "vend": v, "nOp": o, "emp": "Matriz"}
                for n, c, f, v, o in [
        ("Colagem passadeira", "Indústria Exemplo A Ltda", 4, "Tiago Fruet", "2026/00024"),
        ("Linha de montagem", "Metalúrgica Exemplo B S.A.", 2, "Tiago Fruet", "2026/00031"),
        ("Fixação de painéis", "Fábrica Exemplo C Ltda", 5, "Wellington Azevedo", "2026/00040"),
        ("Vedação estrutural", "Exemplo D Comércio", 1, "Tiago Fruet", "2026/00044"),
        ("Colagem de componentes", "Exemplo E Indústria", 3, "Wellington Azevedo", "2026/00052")]]
    return {
        "meta": {"geradoEm": datetime.datetime.now(TZ_SP).isoformat(timespec="seconds"), "hoje": hoje.isoformat(),
                 "amostra": True, "fonte": "DADOS DE EXEMPLO (gerados pelo robô em modo --amostra)", "versao": 1},
        "config": {"feriados": cfg["feriados"], "inicio": cfg["inicio_dados"],
                   "ligacaoContaComoContato": cfg.get("ligacao_conta_em_contato_se_familia_sem_meta_de_ligacao", True)},
        "canais": CANAIS, "tipos": TIPOS,
        "familias": [{"id": f["id"], "nome": f["nome"], "cor": f["cor"], "metas": f["metas"]} for f in cfg["familias"]],
        "hub": {"id": cfg["hub"]["id"], "nome": cfg["hub"]["nome"], "cor": cfg["hub"]["cor"], "metas": cfg["hub"]["metas"]},
        "vendedores": vendedores, "atividades": atividades, "hubRegistros": hub, "oportunidades": opps,
        "vendas": vendas,
        "qualidade": {"tarefasTotal": sum(a[5] for a in atividades), "tarefasSemOportunidade": 690, "oportunidadesAtivas": 112,
                      "ativasParadas": 31, "diasParada": 14, "oportunidadesSemOrigem": 9, "ativasSemTicket": 38,
                      "solucoesSemFamilia": {"TEXYEAR": 4}, "tiposIgnorados": {"Nota": 120, "Tarefa Futura": 35}},
        "projetos": projetos,
        "fasesCrm": FASES_PADRAO,
        "recentes": [{"h": "10:24", "t": "Rhamayana registrou WhatsApp (Papel Térmico + Etiquetas)", "f": "papeis"},
                     {"h": "10:12", "t": "Maria registrou visita (Plásticos de Engenharia)", "f": "plasticos"},
                     {"h": "09:58", "t": "Tiago registrou ligação (Químicos - Adesivo Estrutural)", "f": "adesivos"},
                     {"h": "09:41", "t": "Marcelo registrou e-mail (Especialidades)", "f": "especialidades"}],
        "alertasExtra": [{"nivel": "info", "texto": "Exemplo de alerta enviado pelo robô: oportunidades grandes paradas há mais de 14 dias.", "quando": "hoje"}],
    }


# ----------------------------------------------------------------------------
# saída
# ----------------------------------------------------------------------------
def gravar_js(dados, caminho=None):
    caminho = caminho or SAIDA_JS
    texto = "/* Gerado automaticamente por automacao/esforco_crm.py — não editar à mão. */\n"
    texto += "window.ESFORCO_DATA = " + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(tmp, caminho)
    print(f"Gravado {os.path.basename(caminho)}: {len(texto) / 1024:.0f} KB, {len(dados['atividades'])} linhas de atividade")


def main():
    cfg = carregar_config()
    hoje = datetime.datetime.now(TZ_SP).date()
    vendas = extrair_vendas(REPO_DIR)
    if "--amostra" in sys.argv:
        gravar_js(gerar_amostra(cfg, vendas, hoje))
        return

    empresas_cred = {
        "matriz": (os.environ["OMIE_MATRIZ_APP_KEY"], os.environ["OMIE_MATRIZ_APP_SECRET"]),
        "papeis": (os.environ["OMIE_PAPEIS_APP_KEY"], os.environ["OMIE_PAPEIS_APP_SECRET"]),
    }
    empresas = {}
    for emp, (key, secret) in empresas_cred.items():
        print(f"== {emp}: lendo CRM")
        lookups = carregar_lookups(key, secret)
        oportunidades = paginar("crm/oportunidades", "ListarOportunidades", {}, key, secret)
        tarefas = paginar("crm/tarefas", "ListarTarefas", {}, key, secret)
        print(f"{emp}: {len(oportunidades)} oportunidades, {len(tarefas)} tarefas")
        empresas[emp] = {"lookups": lookups, "oportunidades": oportunidades, "tarefas": tarefas}

    dados = montar_dados(empresas, cfg, vendas, hoje)
    # trava de segurança: nunca sobrescreve o arquivo bom com um vazio
    if not dados["atividades"]:
        print("VALIDAÇÃO FALHOU: nenhuma atividade encontrada — esforco_data.js NÃO foi alterado.")
        sys.exit(1)
    sem_fam = dados["qualidade"]["solucoesSemFamilia"]
    if sem_fam:
        print(f"AVISO: soluções do CRM sem família no config (ficam fora do painel): {sem_fam}")
    gravar_js(dados)


if __name__ == "__main__":
    main()
