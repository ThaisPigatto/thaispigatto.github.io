/* Configuração do painel P&D (e do Painel CEO).
   geradorUrl: gerador automático de atas (robô gratuito na Cloudflare). Vazio = só o plano B (Claude).
   apiUrl / loginUrl: base compartilhada (Google Apps Script). Sem eles, o painel funciona só neste navegador.
   voltaUrl: para onde a chave de login volta (precisa ser igual ao RETORNOS do script). */
window.PD_CONFIG = {
  geradorUrl: 'https://gerador-atas-pd.thais-brito.workers.dev/',
  apiUrl: 'https://script.google.com/macros/s/AKfycbxzZTK646AojmDgSAlNlSUqhyHaavo6zClcoDc3I4BrMnuCNiuT7f-ltoC7nBEEhPNm/exec',
  loginUrl: 'https://script.google.com/a/macros/pigattodistribuidora.com.br/s/AKfycbykkpr7m7sg_nPNGsoK_Q_jbtI5me0gnh7rxi7FDgoFegCkW7FPNQ3oFX3dTKlaIkuD/exec',
  voltaUrl: 'https://thaispigatto.github.io/pd-acompanhamento.html'
};
