"""
Robô diário do painel GROWTH - GOOGLE ADS (Grupo Pigatto) — roda às 6h pelo GitHub Actions.

O que faz (SOMENTE LEITURA no Omie e no Tintim; nunca cria, altera ou exclui nada):
  1. Omie CRM (Matriz + Papeis): oportunidades com origem Google Ads, com cliente, CNPJ, contato e telefone.
  2. Omie Vendas: orçamentos e pedidos desses clientes, com itens, valores e se foi faturado.
  3. Tintim: conversas recebidas pelo webhook (via Apps Script).
  4. Google Ads (opcional): relatório agendado publicado em CSV.
Tudo é CRIPTOGRAFADO (AES-256-GCM, chave derivada da senha do painel) e gravado em
dados/growth-omie.enc.json. No repositório público fica só o arquivo cifrado.

Secrets (GitHub > Settings > Secrets and variables > Actions):
  OMIE_MATRIZ_APP_KEY, OMIE_MATRIZ_APP_SECRET, OMIE_PAPEIS_APP_KEY, OMIE_PAPEIS_APP_SECRET  (obrigatórios)
  PAINEL_SENHA        (obrigatório) a mesma senha usada para abrir o painel
  TINTIM_URL          (opcional) URL do Apps Script terminando em /exec?t=SENHA_DO_WEBHOOK
  GADS_CSV_URL        (opcional)
"""
import base64, csv, io, json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone
import urllib.request, urllib.error
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

API = "https://app.omie.com.br/api/v1/"
BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).date()
INICIO = date(2026, 6, 1)  # início do projeto Google Ads: histórico completo para recorrência e curva ABC
ITER = 600000
EMPRESAS = {
    "Matriz": (os.environ.get("OMIE_MATRIZ_APP_KEY"), os.environ.get("OMIE_MATRIZ_APP_SECRET")),
    "Papeis": (os.environ.get("OMIE_PAPEIS_APP_KEY"), os.environ.get("OMIE_PAPEIS_APP_SECRET")),
}
ETAPAS = {"10": "Orçamento / proposta", "20": "Separar estoque", "50": "Faturar", "60": "Faturado", "70": "Entrega"}

# ---------------- Omie ----------------
def omie(emp, path, call, param):
    key, secret = EMPRESAS[emp]
    body = json.dumps({"call": call, "app_key": key, "app_secret": secret, "param": [param]}).encode()
    for tentativa in range(4):
        req = urllib.request.Request(API + path + "/", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.35)
                return json.load(r)
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "ignore")
            if "Não existem registros" in txt or "não cadastrad" in txt.lower():
                return {}
            if tentativa == 3:
                print(f"AVISO {emp} {call}: {txt[:200]}", file=sys.stderr)
                return {}
            time.sleep(3 * (tentativa + 1))
    return {}

def listar_tudo(emp, path, call, chave, extra=None, por_pagina=100):
    pag, out = 1, []
    while True:
        p = {"pagina": pag, "registros_por_pagina": por_pagina}
        p.update(extra or {})
        r = omie(emp, path, call, p)
        out += r.get(chave, []) or []
        if pag >= int(r.get("total_de_paginas", 1) or 1):
            return out
        pag += 1

def d(s):
    try: return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception: return None

def so_digitos(s): return re.sub(r"\D", "", s or "")

def fone(ddd, num):
    n = so_digitos((ddd or "") + (num or ""))
    return n if len(n) >= 10 else ""

def familia(texto):
    t = (texto or "").lower()
    if re.search(r"pl[aá]stic|acr[ií]lic|petg|psai|\bps\b|chapa", t): return "Plásticos de Engenharia"
    if re.search(r"bio-?chem|limpador|desengrax|oxygen", t): return "Biochem"
    if "marbocote" in t: return "Marbocote"
    if re.search(r"chemlok|parker|lord|estrutural|tt-?bond|linha tt", t): return "Parker Lord (estrutural + Chemlok)"
    if re.search(r"papel|etiqueta|t[eé]rmic", t): return "Papéis e etiquetas"
    return "Outros"

def dados_conta(emp, op, cache):
    conta = op["identificacao"]["nCodConta"]
    if conta not in cache:
        r = omie(emp, "crm/contas", "ConsultarConta", {"nCod": conta})
        idf, tel = r.get("identificacao") or {}, r.get("telefone_email") or {}
        end = r.get("endereco") or {}
        cache[conta] = {"nome": idf.get("cNome", ""), "doc": so_digitos(idf.get("cDoc")),
                        "telefone": fone(tel.get("cDDDTel"), tel.get("cNumTel")), "email": tel.get("cEmail", ""),
                        "cidade": end.get("cCidade", ""), "uf": end.get("cUF", "")}
    c = dict(cache[conta])
    ct = omie(emp, "crm/contatos", "ConsultarContato", {"nCod": op["identificacao"]["nCodContato"]})
    ci, ctel = ct.get("identificacao") or {}, ct.get("telefone_email") or {}
    c["contato"] = " ".join(x for x in [ci.get("cNome", ""), ci.get("cSobrenome", "")] if x).strip()
    c["contato_tel"] = fone(ctel.get("cDDDCel1"), ctel.get("cNumCel1")) or fone(ctel.get("cDDDTel"), ctel.get("cNumTel"))
    if not c["contato_tel"] and ctel.get("cEmail"): c["email"] = c["email"] or ctel.get("cEmail")
    return c

def achar_cliente(emp, conta, desc):
    """Liga a conta do CRM ao cadastro de clientes (Vendas): primeiro por CNPJ, depois por razão social."""
    doc = conta.get("doc", "")
    if len(doc) == 14:
        cnpj = f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        r = omie(emp, "geral/clientes", "ListarClientesResumido", {"pagina": 1, "registros_por_pagina": 5, "clientesFiltro": {"cnpj_cpf": cnpj}})
        lst = r.get("clientes_cadastro_resumido") or []
        if lst: return lst[0]["codigo_cliente"], "Alta (CNPJ)"
    nome = (conta.get("nome") or desc.split(" - ")[0]).strip()[:60]
    if nome and not nome.lower().startswith("pessoa f"):
        r = omie(emp, "geral/clientes", "ListarClientesResumido", {"pagina": 1, "registros_por_pagina": 5, "clientesFiltro": {"razao_social": nome}})
        lst = r.get("clientes_cadastro_resumido") or []
        if lst: return lst[0]["codigo_cliente"], "Média (nome)"
    return None, "Sem cadastro de cliente"

def pedidos_cliente(emp, cod, desde):
    """Todos os pedidos do cliente a partir da data do lead (com paginação)."""
    out, pag = [], 1
    while True:
        r = omie(emp, "produtos/pedido", "ListarPedidos", {"pagina": pag, "registros_por_pagina": 50, "filtrar_por_cliente": cod,
                                                            "filtrar_por_data_de": desde.strftime("%d/%m/%Y")})
        for p in r.get("pedido_venda_produto", []) or []:
            cab, info, tot = p.get("cabecalho", {}), p.get("infoCadastro", {}), p.get("total_pedido", {})
            itens = [{"produto": (i.get("produto") or {}).get("descricao", ""),
                      "qtd": (i.get("produto") or {}).get("quantidade"),
                      "unitario": (i.get("produto") or {}).get("valor_unitario"),
                      "total": (i.get("produto") or {}).get("valor_total")} for i in p.get("det", []) or []]
            faturado, cancelado = info.get("faturado") == "S", info.get("cancelado") == "S"
            dfat = d(info.get("dFat", "")) if faturado else None
            out.append({"empresa": emp, "numero": cab.get("numero_pedido"), "data": (d(info.get("dInc", "")) or HOJE).isoformat(),
                        "data_faturamento": dfat.isoformat() if dfat else "",
                        "etapa": "Cancelado" if cancelado else ("Faturado" if faturado else ETAPAS.get(str(cab.get("etapa")), "Etapa " + str(cab.get("etapa")))),
                        "faturado": faturado, "cancelado": cancelado, "valor": tot.get("valor_total_pedido"), "itens": itens,
                        "obs": ((p.get("observacoes") or {}).get("obs_venda") or "")[:300]})
        if pag >= int(r.get("total_de_paginas", 1) or 1):
            return out
        pag += 1

def coletar_omie():
    orcs = []
    for emp, (k, s) in EMPRESAS.items():
        if not k or not s:
            print(f"Sem chave para {emp}; pulando.", file=sys.stderr); continue
        origens = listar_tudo(emp, "crm/origens", "ListarOrigens", "cadastros")
        ads = {o["nCodigo"] for o in origens if re.search(r"google ads|adwords", o.get("cDescricao", ""), re.I)}
        status = {x["nCodigo"]: x["cDescricao"] for x in listar_tudo(emp, "crm/status", "ListarStatus", "cadastros")}
        cache, cli_cache, ped_cache = {}, {}, {}
        for op in listar_tudo(emp, "crm/oportunidades", "ListarOportunidades", "cadastros"):
            ident, outras = op["identificacao"], op["outrasInf"]
            inc = d(outras["dInclusao"])
            if ident["nCodOrigem"] not in ads or not inc or inc < INICIO:
                continue
            conta = dados_conta(emp, op, cache)
            st = status.get(op["fasesStatus"]["nCodStatus"], "Sem status")
            st = "Em aberto" if st == "Ativo" else st
            ck = ident["nCodConta"]
            if ck not in cli_cache:
                cli_cache[ck] = achar_cliente(emp, conta, ident["cDesOp"])
            cod_cli, vinculo = cli_cache[ck]
            chave_ped = (cod_cli, inc)
            if cod_cli and chave_ped not in ped_cache:
                ped_cache[chave_ped] = pedidos_cliente(emp, cod_cli, inc)  # só pedidos a partir da data do lead
            peds = ped_cache.get(chave_ped, []) if cod_cli else []
            valor = op.get("ticket", {}).get("nTicket") or None
            alt = d(outras["dAlteracao"])
            obs = []
            if not valor: obs.append("Sem valor no CRM")
            if st == "Em aberto" and alt and (HOJE - alt).days > 7: obs.append(f"Sem atualização há {(HOJE - alt).days} dias")
            if st == "Conquistado" and not any(p["faturado"] for p in peds): obs.append("Conquistado no CRM sem pedido faturado")
            if any(p["faturado"] for p in peds) and st != "Conquistado": obs.append("Tem pedido faturado mas o CRM não está como conquistado")
            doc = conta["doc"]
            orcs.append({"empresa": emp, "cod_cliente": cod_cli, "n_op": ident["cNumOp"], "descricao": ident["cDesOp"],
                         "cliente": conta["nome"] if not conta["nome"].lower().startswith("pessoa f") else (conta["contato"] or "Pessoa física"),
                         "cnpj": doc if len(doc) == 14 else "",  # CPF não é exibido
                         "contato": conta["contato"], "telefone": conta["contato_tel"] or conta["telefone"],
                         "email": conta["email"], "cidade": conta["cidade"], "uf": conta["uf"],
                         "familia": familia(ident["cDesOp"]), "valor": valor, "status": st,
                         "data": inc.isoformat(), "atualizado": alt.isoformat() if alt else "",
                         "vinculo_cliente": vinculo, "pedidos": peds,
                         "valor_pedidos": sum(p["valor"] or 0 for p in peds if not p["cancelado"]),
                         "valor_faturado": sum(p["valor"] or 0 for p in peds if p["faturado"]),
                         "obs": "; ".join(obs)})
    return orcs

# ---------------- Tintim e Google Ads ----------------
def coletar_tintim():
    url = os.environ.get("TINTIM_URL")
    if not url: return None
    sep = "&" if "?" in url else "?"
    with urllib.request.urlopen(url + sep + "completo=1", timeout=60) as r:
        dados = json.load(r)
    return dados if isinstance(dados, dict) and "conversas" in dados else None

def coletar_google_ads():
    url = os.environ.get("GADS_CSV_URL")
    if not url: return []
    with urllib.request.urlopen(url, timeout=60) as r:
        linhas = list(csv.reader(io.StringIO(r.read().decode("utf-8-sig"))))
    ini = next(i for i, l in enumerate(linhas) if any(c.strip().lower() in ("campanha", "campaign") for c in l))
    cab = [c.strip().lower() for c in linhas[ini]]
    col = lambda *n: next((cab.index(x) for x in n if x in cab), None)
    ic, icl, icu, icv = col("campanha", "campaign"), col("cliques", "clicks"), col("custo", "cost"), col("conversões", "conversions")
    num = lambda s: float(re.sub(r"[^\d,.-]", "", s).replace(".", "").replace(",", ".") or 0)
    return [{"campanha": l[ic], "familia": familia(l[ic]), "cliques": num(l[icl]) if icl is not None else None,
             "custo": num(l[icu]) if icu is not None else None, "conversoes": num(l[icv]) if icv is not None else None}
            for l in linhas[ini + 1:] if l and ic is not None and l[ic].strip() and not l[ic].lower().startswith("total")]

# ---------------- Criptografia ----------------
def cifrar(obj, senha):
    salt, iv = os.urandom(16), os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER)
    chave = kdf.derive(senha.encode("utf-8"))
    ct = AESGCM(chave).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "alg": "AES-256-GCM", "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b(salt), "iv": b(iv), "dados": b(ct)}

if __name__ == "__main__":
    senha = os.environ.get("PAINEL_SENHA")
    if not senha or len(senha) < 12:
        sys.exit("PAINEL_SENHA ausente ou curta (mínimo 12 caracteres). Nada foi gravado.")
    orcs = coletar_omie()
    try: tintim = coletar_tintim()
    except Exception as e: print("Tintim: falha:", e, file=sys.stderr); tintim = None
    try: camps = coletar_google_ads()
    except Exception as e: print("Google Ads: falha:", e, file=sys.stderr); camps = []
    saida = {"atualizado_em": datetime.now(BRT).isoformat(timespec="minutes"), "periodo_desde": INICIO.isoformat(),
             "orcamentos": orcs, "tintim": tintim, "google_ads": {"campanhas": camps},
             "log": {"quem": "robô GitHub Actions",
                     "o_que": f"{len(orcs)} oportunidades Google Ads, {sum(len(o['pedidos']) for o in orcs)} pedidos, "
                              f"{len((tintim or {}).get('conversas', []))} conversas Tintim, {len(camps)} campanhas"}}
    os.makedirs("dados", exist_ok=True)
    json.dump(cifrar(saida, senha), open("dados/growth-omie.enc.json", "w"), indent=0)
    print(saida["log"]["o_que"])
