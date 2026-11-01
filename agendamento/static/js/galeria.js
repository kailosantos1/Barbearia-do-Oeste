// Modal da galeria: preenche a foto ampliada a partir dos data-* da miniatura clicada (consultagaleria.html).
(function () {
    const modalFoto = document.getElementById('modalFoto');
    if (!modalFoto) return;
    modalFoto.addEventListener('show.bs.modal', function (evento) {
        const dados = evento.relatedTarget.dataset;
        const imagem = document.getElementById('modalFotoImagem');
        imagem.src = dados.foto;
        imagem.alt = dados.descricao;
        document.getElementById('modalFotoDescricao').textContent = dados.descricao;
        document.getElementById('modalFotoBarbeiro').textContent = dados.barbeiro;
        document.getElementById('modalFotoData').textContent = dados.data;
    });
    modalFoto.addEventListener('hidden.bs.modal', function () {
        document.getElementById('modalFotoImagem').src = '';
    });
})();
