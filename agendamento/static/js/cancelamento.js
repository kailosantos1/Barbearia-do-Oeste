// Modal de confirmação de cancelamento (includes/modal_cancelamento.html):
// copia a URL e a descrição do botão que abriu o modal para o formulário de POST.
(function () {
    const modal = document.getElementById('modalCancelamento');
    if (!modal) return;
    modal.addEventListener('show.bs.modal', function (evento) {
        const botao = evento.relatedTarget;
        document.getElementById('formCancelamento').action = botao.dataset.url;
        document.getElementById('modalCancelamentoDescricao').textContent = botao.dataset.descricao;
    });
})();
