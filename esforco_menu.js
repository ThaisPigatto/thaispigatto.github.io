/* MENU LATERAL do painel (esforco.html).
   Ordem do menu = ordem das linhas abaixo (para mudar a ordem, mova a linha).
   tipo:'painel'  -> abas feitas dentro do esforco.html (não mexer nas duas primeiras)
   tipo:'pagina'  -> abre um arquivo .html do repositório (src:'crm.html') OU um link completo (src:'https://...')
   tipo:'grupo'   -> título com subpáginas (filhos). Para acrescentar um relatório: copie uma linha de filhos e mude id, nome e src.
   restrito:true  -> pede a senha (0201) antes de abrir. Hoje só o grupo NÚMEROS PARA O TÁTICO abre sem senha.   src vazio ('') -> o item não aparece.
   O RELATÓRIO DE VENDAS lê os meses do meses.json: quando o robô do faturamento fecha um mês, o mês novo entra sozinho no menu. */
window.ESFORCO_MENU = [
  {id:'tv',      nome:'Esforço Comercial - Geral',            tipo:'painel', restrito:true},
  {id:'analise', nome:'Comercial - Performance CRM completa', tipo:'painel', restrito:true},
  // Resultado da Semana: abre SEM senha pelo link do e-mail do Gabriel; não aparece no menu para quem não digitou a senha (oculto:true)
  {id:'semana',  nome:'Resultado da Semana - CRM',            tipo:'painel', restrito:false, oculto:true},

  {id:'vendas', nome:'RELATÓRIO DE VENDAS', tipo:'grupo', restrito:true, filhosDeMeses:'meses.json', filhos:[
    {id:'vendas-atual',   nome:'Mês atual',      src:'index.html'},
    {id:'vendas-2026-09', nome:'Setembro 2026',  src:'2026-09.html'},
    {id:'vendas-2026-08', nome:'Agosto 2026',    src:'2026-08.html'}
  ]},

  {id:'crm', nome:'CRM - Acompanhamento', tipo:'grupo', restrito:true, filhos:[
    {id:'crm-atrasadas',     nome:'Tarefas Atrasadas',               src:'tarefas-atrasadas-crm.html'},
    {id:'crm-oportunidades', nome:'Oportunidades (Ganhas/Perdidas)', src:'oportunidades-crm.html'},
    {id:'crm-proximas',      nome:'Próximas Tarefas (7 dias)',       src:'proximas-tarefas-crm.html'}
  ]},

  {id:'diag', nome:'Diagnóstico Geral - Trimestre/Ano', tipo:'pagina', src:'resultados.html', restrito:true},

  // PORTAL DO VENDEDOR: dentro do dash abre no modo gestão (escolhe o vendedor no topo). Cada vendedor usa o próprio link (links-vendedores.txt).
  {id:'portal', nome:'Portal do Vendedor', tipo:'pagina', src:'vendedor.html', restrito:true},

  // ANÚNCIOS DO HUB: registra o link de cada anúncio (conta na meta de anúncios do Hub)
  {id:'anuncios', nome:'Anúncios do Hub (registrar)', tipo:'pagina', src:'anuncios-hub.html', restrito:true},

  // NÚMEROS PARA O TÁTICO: única área aberta SEM senha. Todas as famílias usam o mesmo arquivo numeros-tatico.html (?f=família).
  {id:'tatico', nome:'NÚMEROS PARA O TÁTICO', tipo:'grupo', restrito:false, filhos:[
    {id:'tatico-plasticos',      nome:'Plásticos de Engenharia', src:'numeros-tatico.html?f=plasticos'},
    {id:'tatico-adesivos',       nome:'Adesivos Estruturais',    src:'numeros-tatico.html?f=adesivos'},
    {id:'tatico-hub',            nome:'Pigatto Hub + Licitação', src:'numeros-tatico.html?f=hub'},
    {id:'tatico-especialidades', nome:'Especialidades',          src:'numeros-tatico.html?f=especialidades'},
    {id:'tatico-papeis',         nome:'Papéis + Etiquetas',      src:'numeros-tatico.html?f=papeis'}
  ]},

  // PAINEL COMERCIAL - VISÃO CSC: resultado geral de vendas do mês (sem família), aberto SEM senha
  {id:'csc', nome:'Painel Comercial - Visão CSC', tipo:'pagina', src:'painel-csc.html', restrito:false},

  // CHAMADOS/SUPORTE: abre SEM a senha 0201 — cada pessoa da equipe entra com o próprio usuário e senha (criada no 1º acesso)
  {id:'chamados', nome:'CHAMADOS/SUPORTE', tipo:'pagina', src:'chamados.html', restrito:false},

  // PROJETOS CLAUDE: aberto para todos; cadastrar/editar pede o usuário e senha do CHAMADOS/SUPORTE. destaque:true = fundo laranja no menu
  {id:'projetos', nome:'PROJETOS CLAUDE', tipo:'pagina', src:'projetos-claude.html', restrito:false, destaque:true}
];
