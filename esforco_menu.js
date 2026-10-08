/* MENU LATERAL do painel (esforco.html).
   Ordem do menu = ordem das linhas abaixo (para mudar a ordem, mova a linha).
   tipo:'painel'  -> abas feitas dentro do esforco.html (não mexer nas duas primeiras)
   tipo:'pagina'  -> abre um arquivo .html do repositório (src:'crm.html') OU um link completo (src:'https://...')
   tipo:'grupo'   -> título com subpáginas (filhos). Para acrescentar um relatório: copie uma linha de filhos e mude id, nome e src.
   restrito:true  -> pede a senha antes de abrir.   src vazio ('') -> o item não aparece.
   O RELATÓRIO DE VENDAS lê os meses do meses.json: quando o robô do faturamento fecha um mês, o mês novo entra sozinho no menu. */
window.ESFORCO_MENU = [
  {id:'tv',      nome:'Esforço Comercial - Geral',            tipo:'painel'},
  {id:'analise', nome:'Comercial - Performance CRM completa', tipo:'painel', restrito:true},

  {id:'vendas', nome:'RELATÓRIO DE VENDAS', tipo:'grupo', filhosDeMeses:'meses.json', filhos:[
    {id:'vendas-atual',   nome:'Mês atual',      src:'index.html'},
    {id:'vendas-2026-09', nome:'Setembro 2026',  src:'2026-09.html'},
    {id:'vendas-2026-08', nome:'Agosto 2026',    src:'2026-08.html'}
  ]},

  {id:'crm', nome:'CRM - Acompanhamento', tipo:'grupo', filhos:[
    {id:'crm-atrasadas',     nome:'Tarefas Atrasadas',               src:'tarefas-atrasadas-crm.html'},
    {id:'crm-oportunidades', nome:'Oportunidades (Ganhas/Perdidas)', src:'oportunidades-crm.html'},
    {id:'crm-proximas',      nome:'Próximas Tarefas (7 dias)',       src:'proximas-tarefas-crm.html'}
  ]},

  {id:'diag', nome:'Diagnóstico Geral - Trimestre/Ano', tipo:'pagina', src:'resultados.html'}
];
