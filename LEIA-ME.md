# Growth — Google Ads (painel protegido por senha)

Tudo que tem nome, telefone, CNPJ e pedidos fica CRIPTOGRAFADO (AES-256) no GitHub.
Sem a senha do painel, os arquivos em `dados/` são ilegíveis, mesmo com o repositório público.

| Arquivo | Para quê |
|---|---|
| `growth-google-ads.html` | A página (pede a senha ao abrir) |
| `dados/growth-ads.enc.json` | Números editáveis, criptografados (você gera pela própria página) |
| `dados/growth-omie.enc.json` | Gerado pelo robô às 6h: Omie CRM + Vendas + Tintim, criptografado |
| `automacao/atualizar_growth.py` | Robô (só leitura) |
| `.github/workflows/atualizar-growth.yml` | Agenda do robô |

NUNCA suba o arquivo `NAO-SUBIR-growth-ads.json` nem o pacote do conector do Omie.
