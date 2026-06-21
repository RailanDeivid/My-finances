document.addEventListener('DOMContentLoaded', function () {
  var pwdSelectors = [
    'input[name="password1"]',
    'input[name="password2"]',
    'input[name="old_password"]',
    'input[name="new_password1"]',
    'input[name="new_password2"]',
  ];

  pwdSelectors.forEach(function (sel) {
    var input = document.querySelector(sel);
    if (!input) return;

    // Wrapper para posicionamento relativo
    var wrap = document.createElement('div');
    wrap.style.cssText = 'position:relative;display:flex;align-items:center;gap:6px;';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    // Garantir contraste: fundo branco/escuro explícito
    input.style.cssText += ';background:#1e2433!important;color:#e2e8f0!important;border:1px solid #334155!important;';

    // Botão olho
    var eyeBtn = document.createElement('button');
    eyeBtn.type = 'button';
    eyeBtn.title = 'Mostrar/ocultar senha';
    eyeBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    eyeBtn.style.cssText = 'flex-shrink:0;background:transparent;border:1px solid #334155;border-radius:6px;color:#94a3b8;cursor:pointer;padding:4px 8px;display:flex;align-items:center;';
    eyeBtn.addEventListener('click', function () {
      var isText = input.type === 'text';
      input.type = isText ? 'password' : 'text';
      eyeBtn.style.color = isText ? '#94a3b8' : '#6366f1';
    });
    wrap.appendChild(eyeBtn);

    // Botão gerador (somente para password1 / new_password1)
    if (sel === 'input[name="password1"]' || sel === 'input[name="new_password1"]') {
      var genBtn = document.createElement('button');
      genBtn.type = 'button';
      genBtn.title = 'Gerar senha segura';
      genBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
      genBtn.style.cssText = 'flex-shrink:0;background:transparent;border:1px solid #334155;border-radius:6px;color:#94a3b8;cursor:pointer;padding:4px 8px;display:flex;align-items:center;';
      genBtn.addEventListener('click', function () {
        var chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*';
        var arr = new Uint8Array(16);
        crypto.getRandomValues(arr);
        var pwd = Array.from(arr).map(function (b) { return chars[b % chars.length]; }).join('');
        input.value = pwd;
        // Preenche campo de confirmação automaticamente
        var confirm2 = document.querySelector('input[name="password2"]') || document.querySelector('input[name="new_password2"]');
        if (confirm2) confirm2.value = pwd;
        // Mostra a senha gerada
        input.type = 'text';
        if (confirm2) confirm2.type = 'text';
        eyeBtn.style.color = '#6366f1';
        // Copia para área de transferência
        navigator.clipboard && navigator.clipboard.writeText(pwd).then(function () {
          genBtn.title = 'Copiado!';
          genBtn.style.color = '#4ade80';
          setTimeout(function () { genBtn.style.color = '#94a3b8'; genBtn.title = 'Gerar senha segura'; }, 2000);
        });
      });
      wrap.appendChild(genBtn);
    }
  });
});
