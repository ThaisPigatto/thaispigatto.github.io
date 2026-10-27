/* MENU DO PAINEL CENTRAL (esforco.html) — organizado por SETORES.

   COMO FUNCIONA
   1) A BARRA DE CIMA mostra os SETORES (lista ESFORCO_SETORES, logo abaixo). A ordem dos botões = a ordem das linhas.
      restrito:true -> o setor inteiro pede a senha (0201).   direita:true -> o botão fica no canto direito da barra.
   2) O MENU DA ESQUERDA mostra só os itens do setor escolhido (lista ESFORCO_MENU, mais embaixo).
      soVendedores:true / naoVendedores:true -> setor só para vendedores / escondido dos vendedores.   soUsuarios:['thais'] -> o botão do setor só aparece para esse(s) usuário(s) logado(s) na tela INÍCIO.   guia:'...' -> texto do cartão do setor no LOBBY.
      Cada item tem  setor:'comercial'  (ou 'growthads', 'operacao', 'rh', 'qualidade', 'compras', 'ceo', 'geral', 'suporte', 'claude').
   3) Para ACRESCENTAR UM PAINEL: copie uma linha da lista ESFORCO_MENU, mude id, nome, src e o setor.
      Para ACRESCENTAR UM SETOR NOVO: copie uma linha da lista ESFORCO_SETORES (id novo) e use esse id no campo setor dos itens.
   4) Setor sem nenhum item aparece como "em estruturação" (texto da linha descricao).
   5) SENHA DO SETOR: senhaHash + sal (a senha NÃO fica escrita aqui, só o código embaralhado dela; maiúsculas e acentos não importam).
      Quem digita a senha do setor entra em todos os painéis dele. Para trocar a senha, peça ao Claude para gerar um novo senhaHash.
      ATENÇÃO: o site é público; essa senha é um cadeado de cortesia, não segurança de verdade. Dados sensíveis (RH, financeiro) pedem login real.
   6) novaAba:true -> o item não tenta abrir dentro do dash (páginas que exigem login próprio, como os painéis do Claude): mostra um botão "Abrir".
   7) ESFORCO_USUARIOS: quem aparece na tela INÍCIO ("Quem é você?"). fonte 'S' = suporte.js, 'V' = vendedores.js (fotos e cargos vêm de lá).

   TIPOS DE ITEM
   tipo:'painel' -> abas feitas dentro do esforco.html (não mexer nas duas primeiras)
   tipo:'pagina' -> abre um arquivo .html do repositório (src:'crm.html') OU um link completo (src:'https://...')
   tipo:'grupo'  -> título com subpáginas (filhos). Para acrescentar um relatório: copie uma linha de filhos e mude id, nome e src.
   restrito:true -> pede a senha (0201) antes de abrir. No COMERCIAL só o CRM e o PORTAL DO VENDEDOR pedem a senha (decisão de 26/10/2026).   src vazio ('') -> o item não aparece.
   O RELATÓRIO DE VENDAS lê os meses do meses.json: quando o robô do faturamento fecha um mês, o mês novo entra sozinho no menu. */

window.ESFORCO_SETORES = [
  {id:'lobby',    nome:'LOBBY'},
  {id:'meupainel', nome:'MEU PAINEL', soVendedores:true, guia:'Seu painel de vendedor: esforço no CRM, vendas, seu resultado e números.'},   // só os vendedores; abre o portal deles por dentro do dash
  {id:'comercial', nome:'COMERCIAL', guia:'CRM e esforço comercial, relatório de vendas, P&D, diagnóstico geral e portal do vendedor.'},
  {id:'growthads', nome:'GROWTH / GOOGLE ADS', guia:'Resultados e campanhas do Google Ads.'},
  {id:'operacao',  nome:'OPERAÇÃO',  restrito:true, sal:'pigatto-operacao-v1:', senhaHash:'0daa92fa188e7fe8ea006c0e9ef1b8f5cf32a48ea46e1583d6b1a81ab5765ef3', descricao:'Aqui vão entrar os painéis da operação. Os que a operação já criou serão integrados por aqui, um a um.', guia:'Logística e lotes.'},
  {id:'rh',        nome:'RH',        restrito:true, sal:'pigatto-rh-v1:', senhaHash:'0c70788e4a5eb5a5abb3c96bc8da6415fc145de98e0e22f83e00103080424f49', descricao:'Setor em estruturação. Por conter dados pessoais de colaboradores (LGPD), a entrada é restrita.', guia:'Em estruturação.'},
  {id:'qualidade', nome:'QUALIDADE', restrito:true, sal:'pigatto-qualidade-v1:', senhaHash:'ceb9398b5297a71c9514e4a8e9c58734fbaef0653dad9d2396e445dab98ac907', descricao:'Setor em estruturação. Quando houver painéis da qualidade, eles aparecem no menu à esquerda.', guia:'Em estruturação.'},
  {id:'compras',   nome:'COMPRAS',   restrito:true, sal:'pigatto-compras-v1:', senhaHash:'e39a1ac59964321d3b9ef9570865fcb0fc37b734625dff68df82fc354cfb3251', descricao:'Setor em estruturação. O dash Gestão de Compras já está ligado aqui; os próximos painéis entram ao lado dele.', guia:'Gestão de Compras e precificação.'},
  {id:'ceo',       nome:'PAINEL CEO', descricao:'Área do Gabriel Pigatto. Ele entra com a senha que ele mesmo criou no primeiro acesso.', guia:'Área reservada ao Gabriel Pigatto.', naoVendedores:true},
  {id:'minha',     nome:'MINHA ÁREA', direita:true, suave:true, soUsuarios:['thais','saenz','gpigatto']},   // área pessoal: só aparece para a Thais, o Gabriel Saenz e o Gabriel Pigatto
  {id:'geral',     nome:'GERAL',     direita:true, suave:true, guia:'Visão CSC: o resultado geral de vendas do mês.'},
  {id:'suporte',   nome:'SUPORTE',   direita:true, suave:true, guia:'Abra e acompanhe chamados para o time de operação.'},
  {id:'claude',    nome:'CLAUDE - PROJETOS', direita:true, suave:true, guia:'Projetos e ferramentas criados com o Claude.', naoVendedores:true}
];

window.ESFORCO_MENU = [
  // MEU PAINEL (só vendedores): o portal do vendedor por dentro do dash. O endereço é montado na hora, com a chave do login.
  {id:'meupainel', setor:'meupainel', nome:'Meu painel', titulo:'Meu painel', tipo:'pagina', src:'about:blank', restrito:false},
  // LOBBY: a primeira tela depois do login (guia do painel, resultado da semana, destaques, OKRs e sugestões)
  {id:'lobby', setor:'lobby', nome:'Lobby', tipo:'painel', restrito:false},
  // MINHA ÁREA: enviar recado à equipe (os 3) e sugestões de melhoria (os 3). O servidor também confere quem pode.
  {id:'recados', setor:'minha', nome:'Enviar recado à equipe', tipo:'painel', restrito:false},
  {id:'sugestoes', setor:'minha', nome:'Sugestões de melhoria', tipo:'painel', restrito:false, soUsuarios:['thais','saenz','gpigatto']},

  // ============================== GERAL (por enquanto só a Visão CSC) ==============================
  // PAINEL COMERCIAL - VISÃO CSC: resultado geral de vendas do mês (sem família), aberto SEM senha. É a página de entrada do dash.
  {id:'csc', setor:'geral', nome:'Painel Comercial - Visão CSC', tipo:'pagina', src:'painel-csc.html', restrito:false},

  // ============================== COMERCIAL ==============================
  // CRM: um item só no menu. Dentro dele há uma barra de abas (ESFORCO_ABAS, no fim do arquivo) com:
  //   CRM - Acompanhamento (Tarefas Atrasadas / Oportunidades / Próximas Tarefas) | Performance CRM - Completa | Esforço Comercial - Geral
  // As páginas abaixo ficam escondidas do menu (escondido:true) e continuam abrindo por link (#tv, #analise, #crm-atrasadas...).
  {id:'crm', setor:'comercial', nome:'CRM', tipo:'alias', alvo:'crm-atrasadas', restrito:true},
  {id:'crm-atrasadas',     setor:'comercial', nome:'Tarefas Atrasadas',               tipo:'pagina', src:'tarefas-atrasadas-crm.html', restrito:true, escondido:true, abaGrupo:'crm'},
  {id:'crm-oportunidades', setor:'comercial', nome:'Oportunidades (Ganhas/Perdidas)', tipo:'pagina', src:'oportunidades-crm.html',     restrito:true, escondido:true, abaGrupo:'crm'},
  {id:'crm-proximas',      setor:'comercial', nome:'Próximas Tarefas (7 dias)',       tipo:'pagina', src:'proximas-tarefas-crm.html', restrito:true, escondido:true, abaGrupo:'crm'},
  {id:'analise', setor:'comercial', nome:'Performance CRM - Completa', tipo:'painel', restrito:true, escondido:true, abaGrupo:'crm'},
  {id:'tv',      setor:'comercial', nome:'Esforço Comercial - Geral',  tipo:'painel', restrito:true, escondido:true, abaGrupo:'crm'},
  // Resultado da Semana: abre SEM senha pelo link do e-mail do Gabriel; nunca aparece no menu (escondido:true)
  {id:'semana',  setor:'comercial', nome:'Resultado da Semana - CRM',  tipo:'painel', restrito:false, oculto:true, escondido:true},

  {id:'vendas', setor:'comercial', nome:'RELATÓRIO DE VENDAS', tipo:'grupo', restrito:false, filhosDeMeses:'meses.json', filhos:[
    {id:'vendas-atual',   nome:'Mês atual',      src:'index.html'},
    {id:'vendas-2026-09', nome:'Setembro 2026',  src:'2026-09.html'},
    {id:'vendas-2026-08', nome:'Agosto 2026',    src:'2026-08.html'}
  ]},

  // P&D - ACOMPANHAMENTO: projetos de novos produtos (tarefas, atas, progresso e alertas de prazo). Sem a senha 0201: a própria página pede o login da empresa (Google).
  {id:'pd', setor:'comercial', nome:'P&D - Acompanhamento', titulo:'P&D — Acompanhamento', tipo:'pagina', src:'pd-acompanhamento.html', restrito:false},

  {id:'diag', setor:'comercial', nome:'Diagnóstico Geral - Trimestre/Ano', tipo:'pagina', src:'resultados.html', restrito:false},

  // PORTAL DO VENDEDOR: dentro do dash abre no modo gestão (escolhe o vendedor no topo). Cada vendedor usa o próprio link (links-vendedores.txt).
  {id:'portal', setor:'comercial', nome:'Portal do Vendedor', tipo:'pagina', src:'vendedor.html', restrito:true},

  // ANÚNCIOS DO HUB: saiu do menu lateral. Agora fica na aba "Anúncios do Hub" do link individual da Jéssica Sant'Anna (vendedor.html); a página é a anuncios-hub.html.

  // NÚMEROS PARA O TÁTICO: saiu do menu (pedido de 23/10/2026). Fica só nos links individuais dos vendedores (vendedor.html, aba "Números para o Tático").

  // ============================== OPERAÇÃO (senha do setor) ==============================
  {id:'logistica', setor:'operacao', nome:'Logística', titulo:'Operação — Logística', tipo:'pagina', src:'https://claude.ai/artifact/GYEb3xAjK81tZUhBERLAek', novaAba:true, restrito:false},
  {id:'lotes',     setor:'operacao', nome:'Lotes', titulo:'Operação — Lotes', tipo:'pagina', src:'https://painel-pigatto.github.io/pigatto-lotes-dashboard/', restrito:false},

  // ============================== COMPRAS (senha do setor) ==============================
  // GESTÃO DE COMPRAS: dash do Adrian (já existia). Se não aparecer dentro do painel, use o botão "Abrir em nova aba".
  {id:'compras-dash', setor:'compras', nome:'Gestão de Compras', tipo:'pagina', src:'https://omie-compras-dashboard.vercel.app/', restrito:false},

  // PRECIFICAÇÃO: painel feito no Claude (abre em nova aba; precisa da conta do Claude da empresa). Saiu do COMERCIAL em 23/10/2026.
  {id:'precificacao', setor:'compras', nome:'Precificação', titulo:'Comercial — Precificação', tipo:'pagina', src:'https://claude.ai/artifact/PD4u6xfBuD9kAHrr1zLifQ?open_in_browser=1&via=user_open&org=2a25c44d-3cc5-4c1b-9451-bea2c2c2fc54', novaAba:true, restrito:false},

  // ============================== PAINEL CEO ==============================
  // A página tem login próprio (a senha é criada pelo Gabriel no primeiro acesso, pelo link do e-mail).
  {id:'painel-ceo', setor:'ceo', nome:'Painel do CEO', titulo:'Painel CEO — Gabriel Pigatto', tipo:'pagina', src:'painel-ceo.html', restrito:false, inicial:false},   // inicial:false: o dash nunca abre sozinho no painel do CEO

  // ============================== GROWTH / GOOGLE ADS ==============================
  // A própria página pede a senha dela. inicial:false = o dash nunca abre sozinho nesta página (a entrada padrão é a Visão CSC).
  {id:'growth', setor:'growthads', nome:'GROWTH - GOOGLE ADS', titulo:'Growth — Google Ads', tipo:'pagina', src:'growth-google-ads.html', restrito:false, inicial:false},

  // ============================== SUPORTE ==============================
  // CHAMADOS/SUPORTE: abre SEM a senha 0201 — cada pessoa da equipe entra com o próprio usuário e senha (criada no 1º acesso)
  {id:'chamados', setor:'suporte', nome:'CHAMADOS/SUPORTE', tipo:'pagina', src:'chamados.html', restrito:false},

  // ============================== CLAUDE - PROJETOS ==============================
  // PROJETOS CLAUDE: aberto para todos; cadastrar/editar pede o usuário e senha do CHAMADOS/SUPORTE
  {id:'projetos', setor:'claude', nome:'PROJETOS CLAUDE', tipo:'pagina', src:'projetos-claude.html', restrito:false}
];

/* Quem aparece na tela INÍCIO. Fotos e cargos vêm do suporte.js (equipe) e do vendedores.js (vendedores). */
window.ESFORCO_USUARIOS = [
  {id:'thais',      fonte:'S', ref:'thais'},
  {id:'saenz',      fonte:'S', ref:'gabriel-saenz'},
  {id:'adrian',     fonte:'S', ref:'adrian'},
  {id:'franco',     fonte:'S', ref:'gabriel-franco'},
  {id:'siqueira',   fonte:'S', ref:'lucas-siqueira'},
  {id:'felipe',     fonte:'S', ref:'lucas-felipe'},
  {id:'gpigatto',   nome:'Gabriel Pigatto', cargo:'CEO · Grupo Pigatto', foto:'data:image/jpeg;base64,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'},
  {id:'jfarias',    fonte:'V', ref:'jessica-farias'},
  {id:'mcardozo',   fonte:'V', ref:'maria-cardozo'},
  {id:'tiago',      fonte:'V', ref:'tiago-fruet'},
  {id:'wellington', fonte:'V', ref:'wellington-azevedo'},
  {id:'mribeiro',   fonte:'V', ref:'marcelo-ribeiro'},
  {id:'jsantanna',  fonte:'V', ref:'jessica-santanna'},
  {id:'rhamayana',  fonte:'V', ref:'rhamayana'}
];

/* Barra de abas dos itens do menu. A chave (crm) é o id do item do menu; cada aba lista as páginas dela (ids de ESFORCO_MENU). */
window.ESFORCO_ABAS = {
  crm: [
    { nome:'CRM - Acompanhamento', paginas:[ {id:'crm-atrasadas', nome:'Tarefas Atrasadas'}, {id:'crm-oportunidades', nome:'Oportunidades (Ganhas/Perdidas)'}, {id:'crm-proximas', nome:'Próximas Tarefas (7 dias)'} ] },
    { nome:'Performance CRM - Completa', paginas:[ {id:'analise'} ] },
    { nome:'Esforço Comercial - Geral',  paginas:[ {id:'tv'} ] }
  ]
};
