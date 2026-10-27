/* FOTOS DA EQUIPE: vêm da pasta do Drive (pelo Apps Script) e trocam as fotos embutidas nas listas.
   Ficam 24 h guardadas no navegador. Se algo falhar, continuam as fotos que já estão nos arquivos. Carregar DEPOIS de suporte.js, vendedores.js, esforco_menu.js e pd_config.js. */
(function () {
  var KEY = 'pig_fotos_v1', MAPA = { thais: ['S', 'thais'], saenz: ['S', 'gabriel-saenz'], adrian: ['S', 'adrian'], franco: ['S', 'gabriel-franco'], siqueira: ['S', 'lucas-siqueira'], felipe: ['S', 'lucas-felipe'], fernando: ['U', 'fernando'], gpigatto: ['U', 'gpigatto'], jfarias: ['V', 'jessica-farias'], mcardozo: ['V', 'maria-cardozo'], tiago: ['V', 'tiago-fruet'], wellington: ['V', 'wellington-azevedo'], mribeiro: ['V', 'marcelo-ribeiro'], jsantanna: ['V', 'jessica-santanna'], rhamayana: ['V', 'rhamayana'] };
  function lista(t) { return t === 'S' ? window.SUPORTE : t === 'V' ? window.VENDEDORES : window.ESFORCO_USUARIOS; }
  function aplicar(m) { Object.keys(MAPA).forEach(function (k) { if (!m[k]) return; (lista(MAPA[k][0]) || []).forEach(function (x) { if (x.id === MAPA[k][1]) x.foto = m[k]; }); }); }
  var c = null; try { c = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { }
  if (c && c.m && Date.now() - c.t < 864e5) { aplicar(c.m); return; }
  var api = (window.PD_CONFIG || {}).apiUrl; if (!api) { if (c && c.m) aplicar(c.m); return; }
  try {
    var x = new XMLHttpRequest(); x.open('POST', api, false); x.send(JSON.stringify({ a: 'fotos' }));
    var j = JSON.parse(x.responseText);
    if (j && j.ok && j.fotos && Object.keys(j.fotos).length) { try { localStorage.setItem(KEY, JSON.stringify({ t: Date.now(), m: j.fotos })); } catch (e) { } aplicar(j.fotos); return; }
  } catch (e) { }
  if (c && c.m) aplicar(c.m);
})();
