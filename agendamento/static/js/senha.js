// Checklist de requisitos de senha em tempo real (includes/requisitos_senha.html).
// É só um guia: quem decide é o AUTH_PASSWORD_VALIDATORS do Django ao enviar.
(function () {
    const senha = document.getElementById('id_password1');
    const usuario = document.getElementById('id_username');
    const lista = document.getElementById('requisitosSenha');
    if (!senha || !lista) return;
    senha.setAttribute('aria-describedby', 'requisitosSenha');

    // Amostra das senhas mais comuns; a lista completa (~20 mil) é checada pelo servidor.
    const comuns = new Set(['12345678', '123456789', '1234567890', '87654321', '11111111', '00000000', '12341234', '11223344',
        'password', 'password1', 'password123', 'senha123', 'senha1234', 'senhasenha', 'mudar123', 'qwerty123', 'qwertyuiop',
        'abc12345', 'abcd1234', 'q1w2e3r4', '1q2w3e4r', 'iloveyou', 'admin123', 'welcome1', 'sunshine', 'princess',
        'football', 'baseball', 'letmein1', 'brasil123', 'flamengo', 'corinthians', 'palmeiras', 'barbearia']);
    const normalizar = (texto) => texto.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

    const regras = {
        tamanho: (s) => s.length >= 8,
        numerica: (s) => s.length > 0 && !/^\d+$/.test(s),
        usuario: (s) => {
            const nome = normalizar(usuario ? usuario.value.trim() : '');
            const valor = normalizar(s);
            if (!valor) return false;
            if (nome.length < 3) return true;
            return !valor.includes(nome) && !nome.includes(valor);
        },
        comum: (s) => s.length > 0 && !comuns.has(normalizar(s)),
    };

    function atualizar() {
        lista.querySelectorAll('[data-regra]').forEach(function (item) {
            const ok = regras[item.dataset.regra](senha.value);
            item.classList.toggle('text-success', ok);
            item.classList.toggle('fw-semibold', ok);
            item.classList.toggle('text-muted', !ok);
            item.querySelector('.req-icone').textContent = ok ? '✓' : '•';
            item.querySelector('.visually-hidden').textContent = ok ? ' (atendido)' : ' (pendente)';
        });
    }

    senha.addEventListener('input', atualizar);
    if (usuario) usuario.addEventListener('input', atualizar);
    atualizar();
})();
