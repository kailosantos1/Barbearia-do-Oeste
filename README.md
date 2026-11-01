# Barbearia do Oeste — Sistema de Agendamento

Sistema web em Django para uma barbearia. Clientes se cadastram, consultam os serviços e agendam horários com os barbeiros. Barbeiros acompanham ou cancelam seus atendimentos e publicam fotos na galeria. O gerente cadastra a equipe, gerencia os serviços e tem uma visão administrativa da barbearia.

Projeto da disciplina **Back-end I**, IFSC.

---

## Sumário

1. [Funcionalidades](#funcionalidades)
2. [Arquitetura (MTV)](#arquitetura-mtv)
3. [Tecnologias](#tecnologias)
4. [Instalação](#instalação)
5. [Banco de dados (MySQL) e arquivo .env](#banco-de-dados-mysql-e-arquivo-env)
6. [Primeiro barbeiro e primeiro cliente](#primeiro-barbeiro-e-primeiro-cliente)
7. [Evidências: 13 cenários obrigatórios de teste](#evidências-13-cenários-obrigatórios-de-teste)
8. [Equipe](#equipe)

---

## Funcionalidades

| Perfil | O que pode fazer |
|---|---|
| **Visitante** | Ver a página inicial, a lista de serviços ativos (preço e duração) e a galeria de trabalhos; criar conta de cliente. |
| **Cliente** | Agendar horário (barbeiro, serviço, data e hora); ver seus agendamentos separados em *Próximos* e *Histórico*; cancelar agendamentos futuros. |
| **Barbeiro** | Ver os atendimentos vinculados a ele e concluí-los ou cancelá-los; publicar fotos na galeria; consultar clientes. |
| **Gerente** | Painel gerencial com números da barbearia e lista da equipe; cadastrar barbeiros (login + perfil numa única etapa) e usuários; cadastrar serviços com nome livre (ex.: "Colocar peruca"), editar e ativar/desativar; ver **todos** os agendamentos e concluí-los ou cancelá-los; consultar clientes. O superusuário do Django é tratado como gerente. |

Regras de negócio principais:

- Preço e duração de um serviço precisam ser **maiores que zero**.
- Um agendamento **não pode ser no passado** e só aceita **serviços ativos**. A observação é opcional.
- **Expediente:** atendemos das 08:00 às 12:00 e das 13:30 às 22:00. Os horários são escolhidos numa lista de intervalos de 30 min (08:00–11:30 e 13:30–21:30), e o atendimento inteiro precisa caber no turno. Horários na madrugada, que invadam o almoço (12:00–13:30) ou que terminem depois das 22:00 são recusados com uma mensagem explicando o motivo.
- **Horários livres na tela:** ao escolher barbeiro, serviço e data, o formulário consulta `/api/horarios-disponiveis/` e mostra só os horários em que o atendimento cabe no turno, ainda não passou e não conflita com o barbeiro nem com o próprio cliente. A API e o `AgendamentoForms.clean` usam as mesmas funções (`ocupacoes`/`horarios_livres`), e o `clean` continua sendo a validação definitiva no envio.
- **Não há conflito de horário**: o intervalo `[início, início + duração do serviço)` não pode se sobrepor a outro agendamento `AGENDADO` do **mesmo barbeiro** nem do **mesmo cliente**.
- Cliente, valor (preço do serviço) e status (`AGENDADO`) são definidos pelo servidor, nunca pelo formulário.
- Concluir muda o status para `CONCLUIDO`. Pode concluir o barbeiro responsável pelo atendimento ou o gerente.
- Cancelar muda o status para `CANCELADO`. Nada é apagado. Só o cliente ou o barbeiro do agendamento pode cancelar, e só enquanto ele ainda não aconteceu.
- A foto da galeria é vinculada automaticamente ao barbeiro logado.
- Só o gerente cadastra barbeiros. O cadastro cria o usuário e o perfil de barbeiro numa **transação atômica**: se uma parte falhar, nada é gravado.

---

## Arquitetura (MTV)

O Django segue o padrão **MTV (Model–Template–View)**:

```
Navegador ──► urls.py ──► View ──► Model ◄──► Banco (MySQL)
                           │
                           └──► Template (HTML + Bootstrap) ──► Navegador
```

| Camada | Onde fica | Responsabilidade |
|---|---|---|
| **Model** | `agendamento/models.py` | Entidades e regras ligadas aos dados: `Usuario` (usuário customizado com `tipo_usuario` CLIENTE/BARBEIRO/GERENTE), `Cliente`, `Barbeiro`, `Servico`, `Agendamento` (com `status` AGENDADO/CANCELADO/CONCLUIDO) e `Galeria` (foto com miniatura gerada pelo *stdimage*). |
| **View** | `agendamento/views.py` | Recebe a requisição, aplica o controle de acesso (`@login_required`, `@cliente_required`, `@barbeiro_required`, `@equipe_required`, `@gerente_required`), consulta os models e escolhe o template. |
| **Template** | `agendamento/templates/` | HTML com Django Template Language e Bootstrap 5. Fragmentos reutilizados ficam em `templates/includes/` (barra de navegação, modal de cancelamento e requisitos de senha). O JavaScript fica em arquivos separados em `static/js/`, carregados com `{% static %}` e `defer`, sem scripts inline. |
| **Forms** | `agendamento/forms.py` | Validação de entrada: preço/duração positivos, data futura, serviço ativo e conflito de horários (`AgendamentoForms.clean`). |
| **URLs** | `barbearia/urls.py` | Liga cada endereço à sua view. |
| **Configuração** | `barbearia/settings.py` | Apps instalados, usuário customizado, fuso `America/Sao_Paulo`, conexão MySQL e leitura do `.env` (segredos fora do código). |

### Estrutura de pastas

```
BackendI/
├── barbearia/            # projeto (settings, urls, wsgi)
├── agendamento/          # app principal
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── tests.py          # 49 testes automatizados
│   ├── migrations/
│   ├── static/js/        # agendamento.js, senha.js, galeria.js, cancelamento.js
│   └── templates/
│       └── includes/     # navbar e modal de cancelamento
├── media/fotos_servicos/ # uploads da galeria (fora do Git)
├── manage.py
└── requirements.txt
```

### Principais rotas

| Rota | Acesso | Descrição |
|---|---|---|
| `/` | público | Página inicial |
| `/servicos/` | público | Serviços ativos com preço, duração e botão de agendar |
| `/listagaleria/` | público | Galeria em grid com modal de foto ampliada |
| `/cadastro/cliente/` | público | Cadastro de cliente |
| `/login/` · `/logout/` | público / logado | Login único: cada perfil vai para o seu painel (cliente, barbeiro ou gerente) |
| `/dashboard/` | cliente | Painel do cliente |
| `/CadastraAgendamento/` | cliente | Novo agendamento |
| `/agendamentos/meus/` | cliente | Próximos e histórico, com cancelamento |
| `/api/horarios-disponiveis/?barbeiro=&servico=&data=AAAA-MM-DD` | cliente | JSON com os horários livres: `{"horarios": ["08:00", …], "total": N}` |
| `/agendamentos/<id>/cancelar/` | cliente ou barbeiro do agendamento, ou gerente | Cancelamento (POST + CSRF) |
| `/agendamentos/<id>/concluir/` | barbeiro do agendamento ou gerente | Marca como concluído (POST + CSRF) |
| `/dashboard/barbeiro/` · `/CadastraGaleria/` | barbeiro | Painel e publicação de fotos |
| `/ConsultaAgendamentos/` | barbeiro ou gerente | Barbeiro: seus atendimentos. Gerente: todos os agendamentos |
| `/ConsultaClientes/` | barbeiro ou gerente | Consulta de clientes |
| `/dashboard/gerente/` | gerente | Painel gerencial |
| `/servicos/gerenciar/` · `/CadastraServico/` · `/servicos/<id>/editar/` · `/servicos/<id>/alternar/` | gerente | Serviços: listar, cadastrar, editar, ativar/desativar |
| `/CadastraBarbeiro/` · `/CadastraUsuario/` | gerente | Cadastro de barbeiro (login + perfil) e de usuários |
| `/admin/` | superusuário | Admin do Django |

Quem tenta abrir uma rota sem permissão é barrado no servidor e redirecionado com uma mensagem: para o login, se não estiver logado, ou para o próprio painel, se o perfil não tiver acesso.

---

## Tecnologias

| Tecnologia | Versão | Uso |
|---|---|---|
| Python | 3.9+ | Linguagem |
| Django | 4.2 (LTS) | Framework web (MTV, ORM, autenticação, migrações, testes) |
| django-bootstrap5 | 25.2 | Formulários, mensagens e CSS/JS do Bootstrap 5 nos templates |
| django-stdimage | 6.0 | Campo de imagem com miniatura automática (`thumb` 250×250) |
| Pillow | 11.3 | Processamento de imagens (usado pelo stdimage) |
| mysqlclient | 2.2 | Driver do MySQL |
| MySQL | 8 ou superior | Banco de dados (testado localmente com o servidor 26.7) |
| Bootstrap | 5 | Layout responsivo, cards, tabelas e modais |

---

## Instalação

> Pré-requisitos: **Python 3.9 ou superior**, **Git** e um servidor **MySQL** em execução.

### 1. Obter o código

```bash
git clone <url-do-repositorio>
cd BackendI
```

### 2. Criar e ativar o ambiente virtual

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar as dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Erro ao instalar `mysqlclient`?** Ele precisa das bibliotecas do MySQL no sistema.
> - macOS: `brew install mysql-client pkg-config`
> - Ubuntu/Debian: `sudo apt install python3-dev default-libmysqlclient-dev build-essential pkg-config`
> - Windows: normalmente instala direto pelo *wheel* do `pip`.

### 4. Configurar o banco e o `.env`

Crie o banco no MySQL e o arquivo `.env` a partir do `.env.example`, como mostra a [próxima seção](#banco-de-dados-mysql-e-arquivo-env).

### 5. Criar as tabelas e iniciar o servidor

```bash
python manage.py migrate
python manage.py runserver
```

Acesse **http://127.0.0.1:8000/**.

---

## Banco de dados (MySQL) e arquivo .env

O projeto usa **somente MySQL**. Credenciais e chave secreta **não ficam no código**: o `barbearia/settings.py` lê o arquivo `.env` na raiz do projeto, se ele existir, e as variáveis de ambiente do sistema têm prioridade sobre ele. O `.env` está no `.gitignore` e nunca deve ser enviado ao repositório.

### 1. Criar o banco

```sql
CREATE DATABASE barbearia CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Criar o `.env` a partir do modelo

**macOS / Linux**
```bash
cp .env.example .env
```

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
```

Depois, edite o `.env` com os seus dados:

```dotenv
SECRET_KEY=sua-chave-secreta-django
MYSQL_DATABASE=barbearia
MYSQL_USER=root
MYSQL_PASSWORD=sua-senha
MYSQL_HOST=localhost
MYSQL_PORT=3306
```

| Variável | Para que serve | Se ausente |
|---|---|---|
| `SECRET_KEY` | Chave criptográfica do Django (sessões, CSRF, senhas) | usa `django-insecure-dev-key` (**só para desenvolvimento**) |
| `MYSQL_DATABASE` | Nome do banco | **obrigatória**: sem valor padrão |
| `MYSQL_USER` | Usuário do MySQL | **obrigatória** |
| `MYSQL_PASSWORD` | Senha do MySQL | **obrigatória** |
| `MYSQL_HOST` | Servidor | **obrigatória** |
| `MYSQL_PORT` | Porta | **obrigatória** |

> As cinco variáveis `MYSQL_*` não têm valor padrão no código: se faltar alguma no `.env`, a conexão com o banco falha.

Para gerar uma `SECRET_KEY` nova:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Criar as tabelas

```bash
python manage.py migrate
```

> - Com `MYSQL_HOST=localhost`, a conexão é feita pelo *socket* local e `MYSQL_PORT` é ignorada. Para conectar por TCP em outra porta, use `MYSQL_HOST=127.0.0.1`.
> - Para rodar os testes, o usuário do MySQL precisa de permissão para criar e apagar o banco temporário `test_barbearia`. O `root` já tem.
> - Erro `Access denied for user`: confira `MYSQL_USER` e `MYSQL_PASSWORD` no `.env`. Erro `Unknown database`: faltou o passo 1.

---

## Primeiro barbeiro e primeiro cliente

Clientes se cadastram sozinhos pelo site. Barbeiros são criados por alguém da equipe, porque não existe cadastro público de barbeiro.

### Primeiro gerente

Use um superusuário. Ele é tratado como gerente:

```bash
python manage.py createsuperuser
```

Ao entrar em **http://127.0.0.1:8000/login/**, ele cai no **Painel gerencial**. Para ter um gerente que não seja superusuário, crie a conta em `/CadastraUsuario/` com **Tipo de Usuário = gerente**.

### Primeiro barbeiro

**Opção A: pela interface (recomendado)**

1. Entre como gerente. No **Painel gerencial**, clique em **Cadastrar barbeiro** (`/CadastraBarbeiro/`).
2. Preencha nome, telefone, especialidade, usuário e senha. O login e o perfil de barbeiro são criados juntos.
3. Saia e entre com a conta do barbeiro. Ele cai no **Painel do barbeiro** e já pode publicar fotos (`/CadastraGaleria/`) e acompanhar seus atendimentos. Os serviços que os clientes agendam são cadastrados pelo gerente (`/CadastraServico/`).

> Barbeiros **não** cadastram outros barbeiros nem mexem nos serviços: `/CadastraBarbeiro/`, `/CadastraUsuario/` e as rotas de serviço são exclusivas do gerente.

**Opção B: pelo shell do Django**

```bash
python manage.py shell
```
```python
from agendamento.models import Usuario, Barbeiro, Servico

u = Usuario.objects.create_user('joao.barbeiro', password='Barbearia@2026', tipo_usuario='BARBEIRO')
Barbeiro.objects.create(usuario=u, nome='João Silva', telefone='49999990000', especialidade='CABELO')

# Pelo menos um serviço ativo, para os clientes conseguirem agendar
Servico.objects.create(tipo='Corte de cabelo', duracao=30, preco=45)
Servico.objects.create(tipo='Barba completa', duracao=45, preco=40)
```

### Primeiro cliente

1. Abra **http://127.0.0.1:8000/cadastro/cliente/** (ou clique em **Cadastrar** no menu).
2. Preencha usuário, senha, nome, CPF (11 dígitos), telefone, e-mail, faixa etária e sexo. Abaixo da senha, uma lista mostra em tempo real quais requisitos já foram atendidos. A verificação definitiva é feita pelo servidor ao enviar.
3. Entre em **/login/**. O cliente cai no **Painel do cliente**.
4. Clique em **Novo agendamento**, escolha barbeiro, serviço, data e horário futuros e confirme.
5. Em **Meus agendamentos** aparecem os próximos horários (com o botão **Cancelar**) e o histórico.

### Roteiro rápido de teste manual

| Passo | Resultado esperado |
|---|---|
| Cliente agenda 14:00 com João num serviço de 45 min | Agendamento criado com status *Agendado* |
| Outro cliente tenta 14:30 com João | Recusado: "João Silva já tem um atendimento das … 14:00–14:45" |
| Cliente tenta uma data de ontem | Recusado: "Escolha uma data e um horário futuros." |
| Cliente ou barbeiro abre `/CadastraServico/` | Barrado: "Acesso negado: esta área é exclusiva para gerentes." |
| Cliente cancela o agendamento futuro | Confirmação no modal e depois status *Cancelado* |
| Visitante sem login abre `/listagaleria/` e clica numa foto | Foto ampliada no modal, sem recarregar a página |

---

## Evidências: 13 cenários obrigatórios de teste

Os testes automatizados ficam em `agendamento/tests.py` e usam o `TestCase` do Django. Cada teste roda num banco temporário, criado e apagado automaticamente. Os uploads de imagem dos testes vão para uma pasta temporária, então a pasta `media/` não é alterada.

### Como executar

```bash
python manage.py test
```

Para ver o nome de cada teste: `python manage.py test agendamento -v 2`.

### Resultado obtido

```text
$ python manage.py test
Creating test database for alias 'default'...
Found 103 test(s).
System check identified no issues (0 silenced).
.......................................................................................................
----------------------------------------------------------------------
Ran 103 tests in 69.710s

OK
Destroying test database for alias 'default'...
```

> Os testes rodam no MySQL configurado no `.env`, em um banco temporário `test_barbearia` que o Django cria e apaga sozinho. Os dados do banco `barbearia` não são alterados.

### Mapeamento cenário → testes

| # | Cenário obrigatório | Classe de teste | Testes (`test_…`) | Qtd |
|---|---|---|---|---|
| 1 | **Login e controle de acesso por perfil**: cliente, barbeiro e gerente vão para painéis diferentes; acessos indevidos são barrados no servidor com mensagem | `ControleDeAcessoTests` | `login_cliente_vai_para_dashboard`, `login_barbeiro_vai_para_painel_do_barbeiro`, `login_gerente_vai_para_painel_gerencial`, `login_superusuario_vai_para_painel_gerencial`, `login_respeita_next`, `login_ignora_next_externo`, `anonimo_e_barrado_e_enviado_ao_login`, `cliente_e_barrado_com_mensagem`, `barbeiro_acessa_areas_de_barbeiro_e_da_equipe`, `barbeiro_nao_acessa_area_gerencial`, `barbeiro_nao_acessa_area_do_cliente`, `gerente_acessa_areas_gerenciais_e_da_equipe`, `gerente_nao_acessa_areas_exclusivas_de_barbeiro_nem_de_cliente` | 13 |
| 2 | **Validação de serviço**: rejeição de preço ≤ 0 e de duração ≤ 0 | `ServicoFormsTests`, `GerenciaServicosTests` | `aceita_valores_validos`, `rejeita_preco_menor_ou_igual_a_zero`, `rejeita_duracao_menor_ou_igual_a_zero`, `edicao_com_preco_invalido_nao_salva` | 4 |
| 3 | **Consulta pública de serviços ativos** sem autenticação | `ServicosPublicosTests` | `lista_apenas_servicos_ativos_sem_autenticacao`, `mensagem_quando_nao_ha_servicos_ativos` | 2 |
| 4 | **Gestão de serviços pelo gerente** (nome livre, editar, desativar/reativar); barbeiro e cliente barrados | `GerenciaServicosTests` | `gerente_edita_servico`, `gerente_desativa_e_reativa_servico`, `alternar_exige_post`, `cliente_nao_edita_nem_desativa`, `barbeiro_e_barrado_nas_rotas_de_servico`, `menu_do_barbeiro_nao_mostra_servicos`, `gerente_cadastra_servico_com_nome_personalizado`, `rejeita_nome_de_servico_duplicado`, `servico_personalizado_aparece_no_select_do_agendamento` | 9 |
| 5 | **Agendamento válido pelo cliente** (cliente, valor e status definidos pelo servidor; observação opcional) | `AgendamentoTests` | `aceita_horario_livre`, `view_define_cliente_valor_e_status`, `cliente_sem_perfil_e_orientado`, `agendamento_sem_observacao` | 4 |
| 6 | **Rejeição de agendamento no passado** | `AgendamentoTests` | `rejeita_agendamento_no_passado` | 1 |
| 7 | **Rejeição de serviço inativo** no agendamento | `AgendamentoTests` | `rejeita_servico_inativo` | 1 |
| 8 | **Conflito de horário do barbeiro**: horário exato e sobreposição pela duração (ex.: 45 min às 14:00 bloqueia 14:30) | `AgendamentoTests` | `conflito_exato_mesmo_barbeiro`, `conflito_sobreposto_pela_duracao`, `novo_que_termina_dentro_de_existente_conflita`, `view_rejeita_conflito_sem_salvar`, `agendamento_cancelado_nao_bloqueia` | 5 |
| 9 | **Conflito de horário do cliente**: o mesmo cliente com dois barbeiros no mesmo intervalo | `AgendamentoTests` | `cliente_nao_agenda_dois_barbeiros_no_mesmo_intervalo`, `outro_cliente_pode_usar_outro_barbeiro_no_mesmo_horario` | 2 |
| 10 | **Consulta de agendamentos por perfil** (cliente: próximos e histórico; barbeiro: seus atendimentos; gerente: todos) | `ConsultaECancelamentoTests`, `ControleDeAcessoTests` | `cliente_ve_apenas_seus_agendamentos_separados`, `barbeiro_ve_apenas_agendamentos_vinculados_a_ele`, `painel_lista_agendamentos_do_barbeiro`, `gerente_ve_todos_os_agendamentos`, `gerente_ve_acoes_de_qualquer_barbeiro` | 5 |
| 11 | **Cancelamento de agendamento futuro** com confirmação | `ConsultaECancelamentoTests` | `cliente_cancela_agendamento_futuro`, `barbeiro_cancela_agendamento_vinculado`, `gerente_cancela_agendamento_de_qualquer_barbeiro`, `paginas_exibem_modal_de_confirmacao` | 4 |
| 12 | **Cancelamento indevido rejeitado** (de outro usuário, já concluído, passado, sem POST/CSRF) | `ConsultaECancelamentoTests` | `cliente_nao_cancela_agendamento_de_outro_cliente`, `barbeiro_nao_cancela_agendamento_de_outro_barbeiro`, `nao_cancela_agendamento_concluido`, `nao_cancela_agendamento_passado`, `gerente_nao_cancela_agendamento_passado`, `cancelamento_exige_post_e_login`, `cancelamento_exige_csrf` | 7 |
| 13 | **Galeria**: barbeiro publica com vínculo automático, cliente é barrado, exibição pública sem login | `GaleriaTests` | `barbeiro_publica_foto_vinculada_automaticamente`, `cliente_e_barrado_de_publicar`, `galeria_publica_sem_autenticacao`, `anonimo_e_barrado_de_publicar`, `conta_barbeiro_sem_perfil_e_barrada`, `formulario_tem_apenas_foto_e_descricao`, `galeria_vazia` | 7 |
| + | *Complementar:* **Painel gerencial e cadastro unificado de barbeiro** (transação atômica; barbeiro não cadastra barbeiros) | `GerenteTests` | `painel_gerencial_mostra_visao_administrativa`, `gerente_cadastra_usuario_e_perfil_de_barbeiro_numa_acao`, `cadastro_de_barbeiro_e_atomico`, `rejeita_telefone_de_barbeiro_duplicado`, `barbeiro_nao_cadastra_outros_barbeiros`, `cliente_e_anonimo_nao_acessam_painel_gerencial` | 6 |
| + | *Complementar:* **Menu de navegação por perfil** (logo leva ao painel do perfil; painel sempre como primeiro item; itens exatos de cada perfil) | `NavbarTests` | `logo_e_inicio_conforme_o_perfil`, `itens_do_menu_por_perfil_com_painel_primeiro`, `superusuario_ve_menu_de_gerente` | 3 |
| + | *Complementar:* **Horário de expediente** (grade de 30 min; madrugada, almoço e término após 22h recusados) | `AgendamentoTests` | `campo_horario_e_select_com_slots_de_30_minutos`, `aceita_atendimentos_que_terminam_exatamente_no_fim_do_turno`, `rejeita_madrugada`, `rejeita_intervalo_do_almoco`, `rejeita_termino_apos_as_22h`, `rejeita_horario_fora_da_grade` | 6 |
| + | *Complementar:* **Conclusão de atendimento** por barbeiro responsável ou gerente | `ConsultaECancelamentoTests` | `barbeiro_conclui_agendamento_vinculado`, `gerente_conclui_agendamento_de_qualquer_barbeiro`, `conclusao_volta_para_a_pagina_de_origem`, `conclusao_negada_para_outro_barbeiro_e_cliente`, `nao_conclui_agendamento_cancelado`, `conclusao_exige_post_e_login`, `botoes_concluir_e_cancelar_nas_telas_do_barbeiro` | 7 |
| + | *Complementar:* **Validador interativo de senha** nos cadastros de cliente e barbeiro (o servidor continua validando) | `RequisitosSenhaTests` | `checklist_no_cadastro_de_cliente`, `checklist_no_cadastro_de_barbeiro`, `servidor_continua_validando_a_senha` | 3 |
| + | *Complementar:* **API de horários disponíveis** (exclui horários ocupados do barbeiro e do cliente; coerente com a validação do formulário) | `HorariosDisponiveisTests` | `dia_livre_retorna_toda_a_grade_que_cabe_no_turno`, `exclui_horarios_ocupados_do_barbeiro`, `exclui_horarios_ocupados_do_proprio_cliente_com_outro_barbeiro`, `isolamento_entre_barbeiros_e_clientes`, `cancelados_e_concluidos_nao_bloqueiam`, `remove_horarios_que_ja_passaram_hoje`, `data_passada_nao_tem_horarios`, `todos_os_horarios_retornados_sao_aceitos_pelo_formulario`, `formulario_continua_barrando_horario_ocupado_mesmo_sem_a_api`, `parametros_invalidos`, `servico_inativo_e_rejeitado`, `exige_cliente_autenticado`, `aceita_apenas_get`, `formulario_de_agendamento_usa_a_api` | 14 |
| | | | **Total** | **103** |

---

## Equipe

**Instituto Federal de Santa Catarina (IFSC)**, Câmpus: Xanxere

**Curso:** Analise e Desenvolvimento de Sistemas **Disciplina:** Back-end I **Professor(a):** Michel Kremer

| Integrante |
|Kailo Santos|
