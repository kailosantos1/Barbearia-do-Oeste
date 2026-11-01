// Mostra só os horários livres para barbeiro + serviço + data. O backend (AgendamentoForms.clean) continua validando no envio.
// A URL da API vem do atributo data-api-horarios do <form> (gerado com {% url %} no template).
(function () {
    const formulario = document.querySelector('form[data-api-horarios]');
    if (!formulario) return;
    const API = formulario.dataset.apiHorarios;
    const barbeiro = document.getElementById('id_barbeiro');
    const servico = document.getElementById('id_servico');
    const data = document.getElementById('id_data_agendamento');
    const horario = document.getElementById('id_horario');
    if (!barbeiro || !servico || !data || !horario) return;

    const opcoesOriginais = Array.from(horario.options).map((o) => [o.value, o.text]);
    let controle = null;
    let escolhido = horario.value;  // lembrado à parte: durante o carregamento o select fica só com o aviso
    horario.addEventListener('change', () => { escolhido = horario.value; });

    function preencher(opcoes, selecionado) {
        horario.replaceChildren(...opcoes.map(([valor, texto, desabilitada]) => {
            const opcao = new Option(texto, valor, false, valor === selecionado);
            opcao.disabled = Boolean(desabilitada);
            return opcao;
        }));
    }

    async function atualizar() {
        const selecionado = escolhido;
        if (!(barbeiro.value && servico.value && data.value)) {
            preencher(opcoesOriginais, selecionado);
            horario.disabled = false;
            return;
        }
        if (controle) controle.abort();
        controle = new AbortController();
        horario.disabled = true;
        preencher([['', 'Carregando horários…', true]], '');
        try {
            const parametros = new URLSearchParams({ barbeiro: barbeiro.value, servico: servico.value, data: data.value });
            const resposta = await fetch(`${API}?${parametros}`, { signal: controle.signal, headers: { Accept: 'application/json' } });
            if (!resposta.ok) throw new Error(resposta.status);
            const { horarios } = await resposta.json();
            if (horarios.length) {
                preencher([['', 'Selecione um horário'], ...horarios.map((h) => [h, h])], selecionado);
            } else {
                preencher([['', 'Nenhum horário disponível para esta data', true]], '');
            }
        } catch (erro) {
            if (erro.name === 'AbortError') return;
            preencher(opcoesOriginais, selecionado);  // sem a API, volta à grade completa; o servidor valida no envio
        }
        horario.disabled = false;
    }

    [barbeiro, servico, data].forEach((campo) => campo.addEventListener('change', atualizar));
    if (barbeiro.value && servico.value && data.value) atualizar();  // ex.: formulário reexibido após erro
})();

