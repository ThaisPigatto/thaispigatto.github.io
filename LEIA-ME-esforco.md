# Painel de Esforço Comercial — como funciona

**Arquivos (todos na raiz do repositório, menos os de `automacao/` e `.github/`):**
- `esforco.html` — o painel (3 abas). Só lê `esforco_data.js`. Quem mexe no visual é ele.
- `esforco_menu.js` — (menu com grupos: RELATÓRIO DE VENDAS lê o `meses.json` e cria o mês novo sozinho; CRM - Acompanhamento e Diagnóstico abrem os .html do repositório)
- `esforco_menu.js` — o menu da esquerda. Para acrescentar uma seção (CRM, Diagnóstico, relatórios novos): preencher o `src` de uma linha (arquivo .html do repositório ou link). Seção sem `src` não aparece.
- `esforco_data.js` — os dados. O robô reescreve este arquivo todo dia. (Hoje contém DADOS DE EXEMPLO.)
- `automacao/esforco_crm.py` — o robô (CRM do Omie → `esforco_data.js`).
- `automacao/esforco_config.json` — metas semanais, famílias, feriados, regras. Editável direto no GitHub.
- `.github/workflows/esforco-crm.yml` — agenda: roda todo dia 06:30 e avisa por e-mail se falhar.

**Primeira vez:**
1. Subir os arquivos acima no repositório.
2. Aba **Actions → Atualizar Esforço Comercial (CRM) → Run workflow** (os Secrets `OMIE_*` e `SMTP_APP_PASSWORD` já existem no repositório).
3. Se der erro, abrir a execução e mandar o log pro Claude.
4. Abrir `…github.io/esforco.html` (senha da aba de análise: 0201).

**ATENÇÃO:** suba o `esforco_data.js` só na primeira vez. Se subir de novo depois, ele volta para os dados de exemplo até o robô rodar outra vez.

**Mudar uma meta:** editar `automacao/esforco_config.json` (valores são POR SEMANA; o mês é calculado sozinho = meta semanal × dias úteis ÷ 5).
**Novo feriado:** acrescentar em `feriados` no mesmo arquivo.
