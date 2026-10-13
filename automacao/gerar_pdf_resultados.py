"""
Gera o PDF "RESULTADOS - MÊS - ANO" de cada mês FECHADO do painel (pedido da Thais, 13/10/2026).

- Lê meses.json; só considera meses cujo arquivo NÃO é index.html (mês corrente não tem PDF).
- Os números vêm do bloco `const DATA = {...};` do próprio HTML do mês (mesma fonte do painel).
- Só regera quando o DATA do mês mudou (virada, "refazer fechamento", "reprocessar_mes"),
  comparando com o carimbo pdf/<mes>.carimbo — assim não gera commit a cada execução.
- Conteúdo (padrão aprovado em 13/10/2026): cards Meta/Faturado + tabela por família com prêmio
  conquistado (pág. 1), Corrida das Famílias (pág. 2) e lista completa de faturados (demais págs).
- Valida antes de gravar: grupos + linha "Licitação / Sem família" = Total Geral, e soma da
  lista de faturados = faturado líquido. Se não bater, NÃO grava o PDF daquele mês.
"""
import base64, hashlib, io, json, math, os, re, sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.shapes import Drawing, Polygon, String
from reportlab.platypus import (Flowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
PDF_DIR = os.path.join(REPO_DIR, "pdf")
NOME_MES = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho",
            8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}

PAGE = landscape(A4)
W = PAGE[0] - 24 * mm
VINHO = colors.HexColor("#6B1E28")
COR_GRUPO = {"adesivos": "#C0392B", "quimicos": "#1B6B3D", "papeis": "#8E3A9E", "plasticos": "#2E6F9E",
             "sem_familia": "#7F8C8D", "hub": "#C9A227", "total": "#122038"}
BG_GRUPO = {"adesivos": "#D7E7C6", "quimicos": "#FFFFFF", "papeis": "#D7E7C6", "plasticos": "#FFFFFF",
            "sem_familia": "#ECEEEF", "hub": "#F3EE9E", "total": "#A6C97E"}
GRUPOS = ("adesivos", "quimicos", "papeis", "plasticos")
MARCOS = (0.70, 0.85, 1.00, 1.50)


# ---------------------------------------------------------------- utilidades
def brl(v, zero_traco=True):
    if v is None:
        return "-"
    if zero_traco and abs(v) < 0.005:
        return "R$ -"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-R$ " if v < 0 else "R$ ") + s


def pct(v, casas=2):
    return f"{v*100:.{casas}f}%".replace(".", ",")


def cor_pct(p):
    return "#1B6B3D" if p >= 1.0 else ("#9C5A00" if p >= 0.70 else "#C0392B")


def marco_atingido(p):
    ok = [m for m in MARCOS if (p or 0) + 1e-9 >= m]
    return ok[-1] if ok else None


def st(size=8, bold=False, color="#111111", align=TA_LEFT, leading=None):
    return ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          textColor=colors.HexColor(color), alignment=align, leading=leading or size * 1.2)


def ler_html(caminho):
    html = open(caminho, encoding="utf-8").read()
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    if not m:
        raise RuntimeError("bloco 'const DATA = {...};' não encontrado")
    logo = re.search(r'<img src="data:image/png;base64,([^"]+)"', html)
    truck = re.search(r"const CORRIDA_TRUCK_IMG = 'data:image/png;base64,([^']+)'", html)
    return (json.loads(m.group(1)), m.group(1),
            base64.b64decode(logo.group(1)) if logo else None,
            base64.b64decode(truck.group(1)) if truck else None)


# ---------------------------------------------------------------- prêmio (estrelas na tabela)
def premio(p, largura):
    mk = marco_atingido(p)
    d = Drawing(largura, 16)
    x = 2
    for marco in MARCOS:
        pts = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            rr = 5.5 if i % 2 == 0 else 5.5 * 0.45
            pts += [x + 5 + rr * math.cos(ang), 8 + rr * math.sin(ang)]
        d.add(Polygon(pts, fillColor=colors.HexColor("#E0A800" if mk and marco <= mk else "#B8B8B8"), strokeColor=None))
        x += 13
    d.add(String(x + 4, 4.5, f"{int(mk*100)}%" if mk else "Não atingido",
                 fontName="Helvetica-Bold" if mk else "Helvetica", fontSize=8,
                 fillColor=colors.HexColor("#1B6B3D" if mk else "#8A8A8A")))
    return d


# ---------------------------------------------------------------- cards
class Cards(Flowable):
    def __init__(self, D):
        super().__init__()
        self.D, self.h = D, 92

    def wrap(self, *a):
        return W, self.h

    def _card(self, x, w):
        c = self.canv
        c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#DADDE1")); c.setLineWidth(0.8)
        c.roundRect(x, 0, w, self.h, 8, fill=1, stroke=1)

    def draw(self):
        c, t, mi = self.canv, self.D["totais"], self.D["meta_info"]
        w = (W - 12) / 2
        self._card(0, w)
        c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica-Bold", 9)
        c.drawString(14, self.h - 22, "META DO MÊS")
        c.setFillColor(colors.HexColor("#111111")); c.setFont("Helvetica-Bold", 20)
        c.drawString(14, self.h - 48, brl(t["meta"]))
        c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica", 9)
        c.drawString(14, self.h - 64, f"{mi['inicio_mes'][:5]} a {mi['fim_mes'][:5]}")
        x = w + 12
        self._card(x, w)
        liq = (t["faturado"] or 0) + (t["devolucoes"] or 0)
        c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 14, self.h - 22, "FATURADO")
        c.setFillColor(colors.HexColor("#0F5132")); c.setFont("Helvetica-Bold", 20)
        c.drawString(x + 14, self.h - 48, brl(liq))
        c.setFillColor(colors.HexColor("#0F4D2C")); c.roundRect(x + 14, self.h - 70, 120, 16, 8, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 22, self.h - 65, f"{pct(t['realizado_pct'], 1)} da meta")
        notas = len({(r["empresa"], r["nota_fiscal"]) for r in self.D["raw_real"] if r["operacao"] != "Devolução de Venda"})
        linhas = [f"{notas} notas fiscais"]
        if t["devolucoes"]:
            linhas += [f"bruto {brl(t['faturado'])}", f"devoluções -{brl(abs(t['devolucoes']))}"]
        tx = x + 14 + max(c.stringWidth(brl(liq), "Helvetica-Bold", 20), 120) + 24
        c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica", 8.5)
        for i, l in enumerate(linhas):
            c.drawString(tx, self.h - 40 - i * 12, l)


# ---------------------------------------------------------------- tabela por família
def tabela(D):
    gf = {g["id"]: g for g in D["grupos_familia"] if not g.get("is_spacer")}
    FS = 8.6
    H = lambda s: Paragraph(s, st(8, True, "#FFFFFF", TA_CENTER, 9.5))
    R = lambda v, b=False, c="#111111": Paragraph(v, st(FS, b, c, TA_RIGHT))
    L = lambda v, b=False: Paragraph(v, st(FS, b))
    cw_fam, cw_pr = 42 * mm, 40 * mm
    cw_num = (W - 3 * mm - cw_fam - cw_pr) / 7
    PR = lambda p: premio(p, cw_pr - 8)

    def dif(d, b=False):
        if d < 0:
            return Paragraph(f"Superou {brl(-d)}", st(7.6, True, "#1B6B3D", TA_RIGHT))
        return R(brl(d), b)

    def dv(v, b=False):
        return R(brl(v), b, "#C0392B" if v else "#111111")

    data = [["", H("Família de Produto"), H("Meta"), H("Faturado"), H("Devoluções"), H("Faturamento atrasado"),
             H("Faturado líquido<br/>do grupo"), H("Falta p/ meta"), H("% Atingido"),
             H("Prêmio conquistado<br/><font size=6.5>70% · 85% · 100% · 150%</font>")]]
    stl = [("BACKGROUND", (0, 0), (-1, 0), VINHO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("GRID", (1, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
           ("LEFTPADDING", (1, 0), (-1, -1), 4), ("RIGHTPADDING", (1, 0), (-1, -1), 4),
           ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 0)]
    r = 1
    for gid in GRUPOS:
        g = gf[gid]; n = len(g["linhas"]); p = g["realizado_pct"]
        for i, l in enumerate(g["linhas"]):
            data.append(["", L(l["familia"]), R(brl(g["meta"])) if i == 0 else "", R(brl(l["faturado"])),
                         dv(l["devolucoes"]), R(brl(0)), R(brl(g["prev_fat_total"]), True) if i == 0 else "",
                         dif(round(g["meta"] - g["prev_fat_total"], 2)) if i == 0 else "",
                         R(pct(p), True, cor_pct(p)) if i == 0 else "", PR(p) if i == 0 else ""])
        for col in (2, 6, 7, 8, 9):
            stl.append(("SPAN", (col, r), (col, r + n - 1)))
        stl += [("BACKGROUND", (1, r), (-1, r + n - 1), colors.HexColor(BG_GRUPO[gid])),
                ("BACKGROUND", (0, r), (0, r + n - 1), colors.HexColor(COR_GRUPO[gid])),
                ("SPAN", (0, r), (0, r + n - 1)),
                ("LINEBELOW", (1, r + n - 1), (-1, r + n - 1), 1.2, colors.HexColor("#7F7F7F"))]
        r += n
    if "sem_familia" in gf:  # venda HUB de produto sem família de grupo: entra no total, sem meta própria
        s = gf["sem_familia"]; l = s["linhas"][0]
        data.append(["", L(l["familia"]), R("—"), R(brl(l["faturado"])), dv(l["devolucoes"]), R(brl(0)),
                     R(brl(s["prev_fat_total"]), True), R("—"), R("—"), R("—")])
        stl += [("BACKGROUND", (1, r), (-1, r), colors.HexColor(BG_GRUPO["sem_familia"])),
                ("BACKGROUND", (0, r), (0, r), colors.HexColor(COR_GRUPO["sem_familia"]))]
        r += 1
    T = D["totais"]; tp = T["realizado_pct"]
    data.append(["", L("Total Geral", True), R(brl(T["meta"]), True), R(brl(T["faturado"]), True),
                 dv(T["devolucoes"], True), R(brl(0), True), R(brl(T["prev_fat"]), True),
                 dif(round(T["meta"] - T["prev_fat"], 2), True), R(pct(tp), True, cor_pct(tp)), PR(tp)])
    stl += [("BACKGROUND", (1, r), (-1, r), colors.HexColor(BG_GRUPO["total"])),
            ("BACKGROUND", (0, r), (0, r), colors.HexColor(COR_GRUPO["total"]))]
    r += 1
    data.append([""] * 10)
    stl += [("BACKGROUND", (0, r), (-1, r), colors.white), ("SPAN", (0, r), (-1, r)),
            ("LINEBELOW", (0, r), (-1, r), 0.4, colors.HexColor("#BFBFBF")),
            ("LINEBEFORE", (1, r), (-1, r), 0, colors.white), ("LINEAFTER", (-1, r), (-1, r), 0, colors.white),
            ("TOPPADDING", (0, r), (-1, r), 0), ("BOTTOMPADDING", (0, r), (-1, r), 0)]
    spacer = r; r += 1
    h = gf["pigatto_hub"]; hp = h["realizado_pct"]
    data.append(["", L(h["linhas"][0]["familia"], True), R(brl(h["meta"])), R(brl(h["faturado_total"])),
                 dv(h["devolucoes_total"]), R(brl(h.get("faturamento_atrasado") or 0)), R(brl(h["prev_fat_total"]), True),
                 dif(round(h["meta"] - h["prev_fat_total"], 2)), R(pct(hp), True, cor_pct(hp)), PR(hp)])
    stl += [("BACKGROUND", (1, r), (-1, r), colors.HexColor(BG_GRUPO["hub"])),
            ("BACKGROUND", (0, r), (0, r), colors.HexColor(COR_GRUPO["hub"]))]
    alturas = [34] + [None] * (len(data) - 1); alturas[spacer] = 10
    t = Table(data, colWidths=[3 * mm, cw_fam] + [cw_num] * 7 + [cw_pr], rowHeights=alturas)
    t.setStyle(TableStyle(stl))
    return t


# ---------------------------------------------------------------- Corrida das Famílias
LABELS = {"adesivos": "ADESIVOS ESTRUTURAIS", "quimicos": "QUÍMICOS (CHEMLOK + BIO-CHEM + MARBOCOTE)",
          "papeis": "PAPEL TÉRMICO + ETIQUETAS", "plasticos": "PLÁSTICOS DE ENGENHARIA",
          "pigatto_hub": "PIGATTO HUB + LICITAÇÃO"}
CORES = {"adesivos": "#FFC9C9", "quimicos": "#C9F2CE", "papeis": "#F0CAED", "plasticos": "#BAE2F7", "pigatto_hub": "#FFF176"}
COR_NUM = {"adesivos": "#D32F2F"}


def cor_legivel(hexc):
    c = hexc.lstrip("#"); r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    if (0.299 * r + 0.587 * g + 0.114 * b) / 255 <= 0.62:
        return hexc
    return "#%02x%02x%02x" % (round(r * .55), round(g * .55), round(b * .55))


class Corrida(Flowable):
    def __init__(self, D, truck_png):
        super().__init__()
        g = {x["id"]: x for x in D["grupos_familia"] if x["id"] in LABELS}
        self.linhas = sorted(({"id": k, "pct": v["realizado_pct"] or 0} for k, v in g.items()), key=lambda l: -l["pct"])
        self.truck = ImageReader(io.BytesIO(truck_png)) if truck_png else None
        self.row_h = 74
        self.h = 50 + self.row_h * len(self.linhas)

    def wrap(self, *a):
        return W, self.h

    def _estrela(self, cx, cy, r, fill, stroke):
        c = self.canv; p = c.beginPath()
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
        p.close()
        c.setFillColor(colors.HexColor(fill)); c.setStrokeColor(colors.HexColor(stroke)); c.setLineWidth(0.7)
        c.drawPath(p, fill=1, stroke=1)

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor("#202124")); c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(W / 2, self.h - 16, "Corrida das Famílias — Atingimento da Meta Por Família")
        c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica", 9)
        c.drawCentredString(W / 2, self.h - 31, "Considerando somente o Faturado")
        esq, prem = 150, 150
        tx0, tw = esq + 12, W - esq - prem - 24
        for i, l in enumerate(self.linhas):
            yb = self.h - 50 - i * self.row_h - self.row_h + 10
            bh = 26
            c.setFillColor(colors.HexColor(COR_NUM.get(l["id"], cor_legivel(CORES[l["id"]])))); c.setFont("Helvetica-Bold", 11)
            c.drawString(0, yb + 30, f"{i+1}º")
            c.setFillColor(colors.HexColor("#111111")); c.setFont("Helvetica-Bold", 8.5)
            linha, partes = "", []
            for p in LABELS[l["id"]].split():
                tst = (linha + " " + p).strip()
                if c.stringWidth(tst, "Helvetica-Bold", 8.5) > esq - 4:
                    partes.append(linha); linha = p
                else:
                    linha = tst
            partes.append(linha)
            for j, t in enumerate(partes):
                c.drawString(0, yb + 18 - j * 10, t)
            pc = max(0, min(l["pct"], 1))
            c.setFillColor(colors.HexColor(CORES[l["id"]])); c.roundRect(tx0, yb, tw, bh, 7, fill=1, stroke=0)
            if pc > 0:
                p = c.beginPath(); p.roundRect(tx0, yb, tw, bh, 7)
                c.saveState(); c.clipPath(p, stroke=0, fill=0)
                c.setFillColor(colors.HexColor("#47D45A")); c.rect(tx0, yb, tw * pc, bh, fill=1, stroke=0)
                c.restoreState()
            if self.truck:
                th = 22; twk = th * 500 / 185
                c.drawImage(self.truck, tx0 + tw * pc - twk * 0.91, yb + bh - 1, width=twk, height=th, mask="auto")
            c.setFillColor(colors.HexColor("#111111")); c.setFont("Helvetica-Bold", 12)
            if pc * 100 > 78:
                c.drawRightString(tx0 + tw - 10, yb + 9, pct(l["pct"], 1))
            else:
                c.drawString(tx0 + tw * pc + 12, yb + 9, pct(l["pct"], 1))
            px0, pw = W - prem + 10, prem - 20
            conq = sum(1 for mk in MARCOS if l["pct"] + 1e-9 >= mk)
            c.setFillColor(colors.HexColor("#5F6368")); c.setFont("Helvetica-Bold", 6.5)
            c.drawCentredString(px0 + pw / 2, yb + 36, "PRÊMIO CONQUISTADO")
            xs = [px0 + 10 + k * (pw - 20) / 3 for k in range(4)]
            for k in range(3):
                c.setStrokeColor(colors.HexColor("#F2B84B" if (k + 1) <= conq else "#CBD0D6")); c.setLineWidth(2)
                c.line(xs[k], yb + 20, xs[k + 1], yb + 20)
            for k, mk in enumerate(MARCOS):
                on = k < conq
                self._estrela(xs[k], yb + 20, 6.5, "#F2B84B" if on else "#E7E9EC", "#C98A1B" if on else "#B7BCC2")
                c.setFillColor(colors.HexColor("#8A6412" if on else "#5F6368")); c.setFont("Helvetica-Bold", 6.5)
                c.drawCentredString(xs[k], yb + 4, f"{int(mk*100)}%")


# ---------------------------------------------------------------- lista de faturados
def lista_faturados(D):
    rr = D["raw_real"]
    cab = ["Família de Produto", "Vendedor", "Nota Fiscal", "Pedido", "Situação", "Empresa", "Operação", "CFOP",
           "Data Faturamento", "Total de Mercadoria"]
    data = [[Paragraph(x.upper(), st(6.5, True, "#FFFFFF", TA_RIGHT if x.startswith("Total") else TA_LEFT, 8)) for x in cab]]
    C = lambda v: Paragraph("" if v is None else str(v), st(6.8, leading=8))
    for r in rr:
        v = r["total"] or 0
        data.append([C(r["familia"]), C(r["vendedor"]), C(r["nota_fiscal"]), C(r["pedido"]), C(r["situacao"]),
                     C(r["empresa"]), C(r["operacao"]), C(r["cfop"]), C(r.get("data_previsao") or r.get("data_fatura")),
                     Paragraph(brl(v, zero_traco=False), st(6.8, False, "#C0392B" if v < 0 else "#111111", TA_RIGHT, 8))])
    total = round(sum((r["total"] or 0) for r in rr), 2)
    data.append([Paragraph(f"Total ({len(rr)} linhas)", st(7.2, True, leading=9))] + [""] * 8 +
                [Paragraph(brl(total), st(7.2, True, align=TA_RIGHT, leading=9))])
    cw = [x * mm for x in (42, 30, 30, 16, 20, 17, 30, 18, 25)]
    cw.append(W - sum(cw))
    n = len(data)
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VINHO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LINEBELOW", (0, 1), (-1, n - 2), 0.3, colors.HexColor("#E3E3E3")),
        ("SPAN", (0, n - 1), (8, n - 1)), ("BACKGROUND", (0, n - 1), (-1, n - 1), colors.HexColor("#A6C97E")),
        ("LINEABOVE", (0, n - 1), (-1, n - 1), 1, colors.HexColor("#7F7F7F"))]))
    return [Paragraph("Faturados (Realizado) — dados brutos do OMIE", st(12, True, "#6B1E28", leading=15)),
            Spacer(1, 5), t], total


# ---------------------------------------------------------------- validação + montagem
def validar(D, total_lista):
    gf = {g["id"]: g for g in D["grupos_familia"] if not g.get("is_spacer")}
    extras = [k for k in gf if k not in GRUPOS + ("total_geral", "pigatto_hub", "sem_familia")]
    if extras:
        raise RuntimeError(f"grupo não previsto no PDF: {extras}")
    T = D["totais"]
    soma = sum(gf[g]["prev_fat_total"] for g in GRUPOS) + (gf["sem_familia"]["prev_fat_total"] if "sem_familia" in gf else 0)
    for nome, a, b in (("grupos x Total Geral", soma, T["prev_fat"]),
                       ("faturado + devoluções x Total Geral", T["faturado"] + T["devolucoes"], T["prev_fat"]),
                       ("lista de faturados x Total Geral", total_lista, T["prev_fat"])):
        if abs(a - b) > 0.01:
            raise RuntimeError(f"validação falhou ({nome}): {a:.2f} vs {b:.2f}")
    for g in GRUPOS:
        soma_l = sum(l["faturado"] + l["devolucoes"] for l in gf[g]["linhas"])
        if abs(soma_l - gf[g]["prev_fat_total"]) > 0.01:
            raise RuntimeError(f"validação falhou (famílias x grupo {g})")


def gerar_pdf(mes_id, D, logo_png, truck_png, destino):
    ano, mes = (int(x) for x in mes_id.split("-"))
    nome_mes = NOME_MES[mes]
    lista, total_lista = lista_faturados(D)
    validar(D, total_lista)
    mi = D["meta_info"]
    doc = SimpleDocTemplate(destino, pagesize=PAGE, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"RESULTADOS - {nome_mes.upper()} - {ano}", author="Pigatto Distribuidora")
    cab_esq = Image(io.BytesIO(logo_png), width=44 * mm, height=44 * mm * 455 / 1566) if logo_png else ""
    cab = Table([[cab_esq, Paragraph(f"RESULTADOS — {nome_mes.upper()}/{ano}", st(17, True, "#6B1E28", TA_CENTER, 21)),
                  Paragraph(f"Período: <b>{mi['inicio_mes']} a {mi['fim_mes']}</b>", st(8.5, False, "#333333", TA_RIGHT))]],
                colWidths=[W * 0.24, W * 0.52, W * 0.24])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, VINHO),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story = [cab, Spacer(1, 10), Cards(D), Spacer(1, 12), tabela(D), PageBreak(), Corrida(D, truck_png), PageBreak()] + lista
    atualizado = mi.get("atualizado_em", "").split(" (")[0]

    def rodape(c, d):
        c.saveState(); c.setFont("Helvetica", 7); c.setFillColor(colors.HexColor("#777777"))
        c.drawString(12 * mm, 5 * mm, f"Pigatto Distribuidora · Resultados {nome_mes}/{ano}")
        c.drawRightString(PAGE[0] - 12 * mm, 5 * mm, f"Dados de {atualizado}  ·  Página {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)


def main():
    meses = json.load(open(os.path.join(REPO_DIR, "meses.json"), encoding="utf-8"))
    os.makedirs(PDF_DIR, exist_ok=True)
    falhas = 0
    for m in meses:
        if m["arquivo"] == "index.html":
            continue  # mês corrente: sem PDF até fechar
        caminho = os.path.join(REPO_DIR, m["arquivo"])
        if not os.path.exists(caminho):
            continue
        try:
            D, data_txt, logo, truck = ler_html(caminho)
            carimbo = hashlib.sha256(data_txt.encode("utf-8")).hexdigest()
            arq_pdf = os.path.join(PDF_DIR, f"{m['id']}.pdf")
            arq_car = os.path.join(PDF_DIR, f"{m['id']}.carimbo")
            if os.path.exists(arq_pdf) and os.path.exists(arq_car) and open(arq_car).read().strip() == carimbo:
                continue  # nada mudou nesse mês
            tmp = arq_pdf + ".tmp"
            gerar_pdf(m["id"], D, logo, truck, tmp)
            os.replace(tmp, arq_pdf)
            open(arq_car, "w").write(carimbo + "\n")
            print(f"PDF de {m['id']} gerado ({m['label']}).")
        except Exception as e:
            falhas += 1
            print(f"!! PDF de {m['id']} NÃO gerado: {e}")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
