/* MENU DO PAINEL CENTRAL (esforco.html) — organizado por SETORES.

   COMO FUNCIONA
   1) A BARRA DE CIMA mostra os SETORES (lista ESFORCO_SETORES, logo abaixo). A ordem dos botões = a ordem das linhas.
      restrito:true -> o setor inteiro pede a senha (0201).   direita:true -> o botão fica no canto direito da barra.
   2) O MENU DA ESQUERDA mostra só os itens do setor escolhido (lista ESFORCO_MENU, mais embaixo).
      Cada item tem  setor:'comercial'  (ou 'operacao', 'rh', 'qualidade', 'compras', 'ceo', 'geral').
   3) Para ACRESCENTAR UM PAINEL: copie uma linha da lista ESFORCO_MENU, mude id, nome, src e o setor.
      Para ACRESCENTAR UM SETOR NOVO: copie uma linha da lista ESFORCO_SETORES (id novo) e use esse id no campo setor dos itens.
   4) Setor sem nenhum item aparece como "em estruturação" (texto da linha descricao).

   TIPOS DE ITEM
   tipo:'painel' -> abas feitas dentro do esforco.html (não mexer nas duas primeiras)
   tipo:'pagina' -> abre um arquivo .html do repositório (src:'crm.html') OU um link completo (src:'https://...')
   tipo:'grupo'  -> título com subpáginas (filhos). Para acrescentar um relatório: copie uma linha de filhos e mude id, nome e src.
   restrito:true -> pede a senha (0201) antes de abrir.   src vazio ('') -> o item não aparece.
   O RELATÓRIO DE VENDAS lê os meses do meses.json: quando o robô do faturamento fecha um mês, o mês novo entra sozinho no menu. */

window.ESFORCO_SETORES = [
  {id:'comercial', nome:'COMERCIAL'},
  {id:'operacao',  nome:'OPERAÇÃO',  descricao:'Aqui vão entrar os painéis da operação. Os que a operação já criou serão integrados por aqui, um a um.'},
  {id:'rh',        nome:'RH',        restrito:true, descricao:'Setor em estruturação. Por conter dados pessoais de colaboradores (LGPD), a entrada é restrita.'},
  {id:'qualidade', nome:'QUALIDADE', descricao:'Setor em estruturação. Quando houver painéis da qualidade, eles aparecem no menu à esquerda.'},
  {id:'compras',   nome:'COMPRAS',   descricao:'Setor em estruturação. O dash Gestão de Compras já está ligado aqui; os próximos painéis entram ao lado dele.'},
  {id:'ceo',       nome:'PAINEL CEO', restrito:true, descricao:'Área do Gabriel Pigatto. Ele vai alimentar este painel, e a estrutura será definida junto com ele.'},
  {id:'geral',     nome:'GERAL',     direita:true, suave:true}
];

window.ESFORCO_MENU = [
  // ============================== COMERCIAL ==============================
  {id:'tv',      setor:'comercial', nome:'Esforço Comercial - Geral',            tipo:'painel', restrito:true},
  {id:'analise', setor:'comercial', nome:'Comercial - Performance CRM completa', tipo:'painel', restrito:true},
  // Resultado da Semana: abre SEM senha pelo link do e-mail do Gabriel; não aparece no menu para quem não digitou a senha (oculto:true)
  {id:'semana',  setor:'comercial', nome:'Resultado da Semana - CRM',            tipo:'painel', restrito:false, oculto:true},

  {id:'vendas', setor:'comercial', nome:'RELATÓRIO DE VENDAS', tipo:'grupo', restrito:true, filhosDeMeses:'meses.json', filhos:[
    {id:'vendas-atual',   nome:'Mês atual',      src:'index.html'},
    {id:'vendas-2026-09', nome:'Setembro 2026',  src:'2026-09.html'},
    {id:'vendas-2026-08', nome:'Agosto 2026',    src:'2026-08.html'}
  ]},

  {id:'crm', setor:'comercial', nome:'CRM - Acompanhamento', tipo:'grupo', restrito:true, filhos:[
    {id:'crm-atrasadas',     nome:'Tarefas Atrasadas',               src:'tarefas-atrasadas-crm.html'},
    {id:'crm-oportunidades', nome:'Oportunidades (Ganhas/Perdidas)', src:'oportunidades-crm.html'},
    {id:'crm-proximas',      nome:'Próximas Tarefas (7 dias)',       src:'proximas-tarefas-crm.html'}
  ]},

  // P&D - ACOMPANHAMENTO: projetos de novos produtos (tarefas, atas, progresso e alertas de prazo). Pede a senha por enquanto.
  {id:'pd', setor:'comercial', nome:'P&D - Acompanhamento', titulo:'P&D — Acompanhamento', tipo:'pagina', src:'pd-acompanhamento.html', restrito:true},

  {id:'diag', setor:'comercial', nome:'Diagnóstico Geral - Trimestre/Ano', tipo:'pagina', src:'resultados.html', restrito:true},

  // PORTAL DO VENDEDOR: dentro do dash abre no modo gestão (escolhe o vendedor no topo). Cada vendedor usa o próprio link (links-vendedores.txt).
  {id:'portal', setor:'comercial', nome:'Portal do Vendedor', tipo:'pagina', src:'vendedor.html', restrito:true},

  // ANÚNCIOS DO HUB: registra o link de cada anúncio (conta na meta de anúncios do Hub)
  {id:'anuncios', setor:'comercial', nome:'Anúncios do Hub (registrar)', tipo:'pagina', src:'anuncios-hub.html', restrito:true},

  // GROWTH - GOOGLE ADS: sem cadeado no menu, fundo laranja. A própria página pede a senha dela. inicial:false = o dash continua abrindo no NÚMEROS PARA O TÁTICO.
  {id:'growth', setor:'comercial', nome:'GROWTH - GOOGLE ADS', titulo:'Growth — Google Ads', tipo:'pagina', src:'growth-google-ads.html', restrito:false, destaque:true, inicial:false},

  // NÚMEROS PARA O TÁTICO: única área do COMERCIAL aberta SEM senha. Todas as famílias usam o mesmo arquivo numeros-tatico.html (?f=família).
  {id:'tatico', setor:'comercial', nome:'NÚMEROS PARA O TÁTICO', tipo:'grupo', restrito:false, filhos:[
    {id:'tatico-plasticos',      nome:'Plásticos de Engenharia', src:'numeros-tatico.html?f=plasticos'},
    {id:'tatico-adesivos',       nome:'Adesivos Estruturais',    src:'numeros-tatico.html?f=adesivos'},
    {id:'tatico-hub',            nome:'Pigatto Hub + Licitação', src:'numeros-tatico.html?f=hub'},
    {id:'tatico-especialidades', nome:'Especialidades',          src:'numeros-tatico.html?f=especialidades'},
    {id:'tatico-papeis',         nome:'Papéis + Etiquetas',      src:'numeros-tatico.html?f=papeis'}
  ]},

  // PAINEL COMERCIAL - VISÃO CSC: resultado geral de vendas do mês (sem família), aberto SEM senha
  {id:'csc', setor:'comercial', nome:'Painel Comercial - Visão CSC', tipo:'pagina', src:'painel-csc.html', restrito:false},

  // ============================== COMPRAS ==============================
  // GESTÃO DE COMPRAS: dash do Adrian (já existia). Se não aparecer dentro do painel, use o botão "Abrir em nova aba".
  {id:'compras-dash', setor:'compras', nome:'Gestão de Compras', tipo:'pagina', src:'https://omie-compras-dashboard.vercel.app/', restrito:true},

  // ============================== GERAL (todos) ==============================
  // CHAMADOS/SUPORTE: abre SEM a senha 0201 — cada pessoa da equipe entra com o próprio usuário e senha (criada no 1º acesso)
  {id:'chamados', setor:'geral', nome:'CHAMADOS/SUPORTE', tipo:'pagina', src:'chamados.html', restrito:false},

  // PROJETOS CLAUDE: aberto para todos; cadastrar/editar pede o usuário e senha do CHAMADOS/SUPORTE. destaque:true = fundo laranja no menu
  {id:'projetos', setor:'geral', nome:'PROJETOS CLAUDE', tipo:'pagina', src:'projetos-claude.html', restrito:false, destaque:true}
];
