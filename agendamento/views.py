from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import horarios_livres, CadastroBarbeiroForm, CadastroClienteForm, ClienteForms, ServicoForms, AgendamentoForms, UsuarioForms, GaleriaForms
from .models import Barbeiro, Cliente, Agendamento, Galeria, Servico
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from datetime import date
from functools import wraps



# Create your views here.


"""     Cadastro   """
def eh_gerente(usuario):
        return usuario.is_superuser or usuario.tipo_usuario == 'GERENTE'


def eh_barbeiro(usuario):
        return usuario.tipo_usuario == 'BARBEIRO' and not usuario.is_superuser


def eh_equipe(usuario):
        return eh_gerente(usuario) or eh_barbeiro(usuario)


def painel_do_usuario(usuario):
        """Nome da URL do painel inicial de acordo com o tipo de usuário."""
        if eh_gerente(usuario):
                return 'dashboard_gerente'
        if eh_barbeiro(usuario):
                return 'dashboard_barbeiro'
        return 'dashboard'


def cliente_required(view_func):
        """Impede que contas internas usem as páginas destinadas a clientes."""
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
                if request.user.tipo_usuario != 'CLIENTE':
                        messages.error(request, 'Esta área é exclusiva para clientes.')
                        return redirect(painel_do_usuario(request.user))
                return view_func(request, *args, **kwargs)
        return wrapper


def perfil_required(permitido, aviso_login, publico):
        """Fábrica de decorators: barra no backend quem não passa em `permitido(usuario)`."""
        def decorator(view_func):
                @wraps(view_func)
                def wrapper(request, *args, **kwargs):
                        if not request.user.is_authenticated:
                                messages.warning(request, f'{aviso_login} para acessar esta página.')
                                return redirect_to_login(request.get_full_path(), 'login')
                        if not permitido(request.user):
                                messages.error(request, f'Acesso negado: esta área é exclusiva para {publico}.')
                                return redirect(painel_do_usuario(request.user))
                        return view_func(request, *args, **kwargs)
                return wrapper
        return decorator


barbeiro_required = perfil_required(eh_barbeiro, 'Faça login como barbeiro', 'barbeiros')
gerente_required = perfil_required(eh_gerente, 'Faça login como gerente', 'gerentes')
equipe_required = perfil_required(eh_equipe, 'Faça login com uma conta da equipe', 'a equipe da barbearia')


def login_cliente(request):

    if request.user.is_authenticated:
        return redirect(painel_do_usuario(request.user))

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)
            messages.success(request, f'Olá, {request.user.username}! Que bom ter você de volta.')

            proximo = request.POST.get('next') or request.GET.get('next')
            if proximo and url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(proximo)
            return redirect(painel_do_usuario(usuario))
        messages.error(request, 'Usuário ou senha inválidos. Tente novamente.')

    else:
        form = AuthenticationForm(request)
    return render(request, 'login.html', {'form': form, 'next': request.GET.get('next', '')})


@require_POST
def logout_cliente(request):
        logout(request)
        messages.success(request, 'Você saiu da sua conta com segurança.')
        return redirect('index')


@login_required(login_url='login')
@cliente_required
def dashboard(request):
        return render(request, 'dashboard.html', {'cliente': getattr(request.user, 'Cliente', None)})


@gerente_required
def dashboard_gerente(request):
        context = {
                'barbeiros': Barbeiro.objects.select_related('usuario').order_by('nome'),
                'total_clientes': Cliente.objects.count(),
                'total_servicos_ativos': Servico.objects.filter(ativo=True).count(),
                'total_agendamentos_futuros': Agendamento.objects.filter(filtro_futuros()).count(),
        }
        return render(request, 'dashboard_gerente.html', context)


@barbeiro_required
def dashboard_barbeiro(request):
        barbeiro = getattr(request.user, 'barbeiro', None)
        agendamentos = Agendamento.objects.none()
        if barbeiro:
                agendamentos = (barbeiro.agendamentos
                                .select_related('cliente', 'servico')
                                .order_by('data_agendamento', 'horario'))
        return render(request, 'dashboard_barbeiro.html', {'barbeiro': barbeiro, 'agendamentos': agendamentos})


def CadastraCliente(request):
        """Cadastro público que cria a conta e o perfil de cliente."""
        if request.method == 'POST':
                form = CadastroClienteForm(request.POST)
                if form.is_valid():
                        with transaction.atomic():
                                usuario = form.save()
                                Cliente.objects.create(
                                        usuario=usuario,
                                        cpf=form.cleaned_data['cpf'],
                                        nome=form.cleaned_data['nome'],
                                        telefone=form.cleaned_data['telefone'],
                                        email=form.cleaned_data['email'],
                                        faixa_etaria=form.cleaned_data['faixa_etaria'],
                                        sexo=form.cleaned_data['sexo'],
                                )
                        messages.success(request, 'Cadastro realizado com sucesso! Agora você faz parte da Barbearia do Oeste.')
                        return redirect('index')
                messages.error(request, 'Revise os campos destacados e tente novamente.')
        else:
                form = CadastroClienteForm()

        return render(request, 'cadastrocliente.html', {'form': form})


@gerente_required
def CadastraBarbeiro(request):
        """Gerente cria login e perfil de barbeiro de uma vez (ver CadastroBarbeiroForm.save)."""
        if request.method == 'POST':
                form = CadastroBarbeiroForm(request.POST)
                if form.is_valid():
                        usuario = form.save()
                        messages.success(request, f'Barbeiro {usuario.barbeiro.nome} cadastrado. Login: {usuario.username}')
                        return redirect('dashboard_gerente')
                messages.error(request, 'Revise os campos destacados e tente novamente.')
        else:
                form = CadastroBarbeiroForm()
        context = {'form':form}
        return render (request, 'cadastrobarbeiro.html', context )

@gerente_required
def CadastraServico(request):
        if request.method == 'POST':
                form = ServicoForms(request.POST, request.FILES)
                if form.is_valid():
                        form.save()
                        messages.success(request, 'Serviço Cadastrado com sucesso')
                        form = ServicoForms()
                else:
                        messages.error(request, 'Erro ao salvar os dados')
        else:
                form = ServicoForms()
        context = {'form':form}
        return render (request, 'cadastroservico.html', context )


@gerente_required
def GerenciaServicos(request):
        context = {'servicos': Servico.objects.order_by('-ativo', 'tipo')}
        return render(request, 'gerenciaservicos.html', context)


@gerente_required
def EditaServico(request, pk):
        servico = get_object_or_404(Servico, pk=pk)
        if request.method == 'POST':
                form = ServicoForms(request.POST, instance=servico)
                if form.is_valid():
                        form.save()
                        messages.success(request, 'Serviço atualizado com sucesso')
                        return redirect('GerenciaServicos')
                messages.error(request, 'Erro ao salvar os dados')
        else:
                form = ServicoForms(instance=servico)
        context = {'form': form, 'titulo': f'Editar serviço: {servico.tipo}', 'botao': 'Salvar alterações'}
        return render(request, 'cadastroservico.html', context)


@gerente_required
@require_POST
def AlternaServico(request, pk):
        """Ativa/desativa o serviço sem apagá-lo (agendamentos o referenciam com PROTECT)."""
        servico = get_object_or_404(Servico, pk=pk)
        servico.ativo = not servico.ativo
        servico.save(update_fields=['ativo'])
        estado = 'reativado' if servico.ativo else 'desativado'
        messages.success(request, f'Serviço {servico.tipo} {estado}.')
        return redirect('GerenciaServicos')
                    

@require_GET
def horarios_disponiveis(request):
        """API do formulário de agendamento: horários livres para barbeiro + serviço + data (?barbeiro=&servico=&data=AAAA-MM-DD)."""
        if not request.user.is_authenticated:
                return JsonResponse({'erro': 'Faça login para consultar os horários.'}, status=401)
        cliente = getattr(request.user, 'Cliente', None)
        if cliente is None:
                return JsonResponse({'erro': 'Apenas clientes podem consultar horários para agendar.'}, status=403)
        try:
                barbeiro_id = int(request.GET['barbeiro'])
                servico_id = int(request.GET['servico'])
                data = date.fromisoformat(request.GET['data'])
        except (KeyError, ValueError):
                return JsonResponse({'erro': 'Informe barbeiro, serviço e data (AAAA-MM-DD) válidos.'}, status=400)
        barbeiro = Barbeiro.objects.filter(pk=barbeiro_id).first()
        servico = Servico.objects.filter(pk=servico_id, ativo=True).first()
        if barbeiro is None or servico is None:
                return JsonResponse({'erro': 'Barbeiro ou serviço inexistente ou indisponível.'}, status=400)

        horarios = horarios_livres(barbeiro, servico, data, cliente=cliente)
        return JsonResponse({'horarios': horarios, 'total': len(horarios)})


@login_required(login_url='login')
@cliente_required
def CadastraAgendamento(request):
        cliente = getattr(request.user, 'Cliente', None)
        if cliente is None:
                messages.warning(request, 'Sua conta ainda não tem um perfil de cliente. Fale com a barbearia para concluir seu cadastro antes de agendar.')
                return redirect('dashboard')

        if request.method == 'POST':
                form = AgendamentoForms(request.POST, cliente=cliente)
                if form.is_valid():
                        agendamento = form.save(commit=False)
                        agendamento.cliente = cliente
                        agendamento.valor_total = agendamento.servico.preco
                        agendamento.status = 'AGENDADO'
                        agendamento.save()
                        messages.success(request, f'Agendamento confirmado para {agendamento.data_agendamento:%d/%m/%Y} às {agendamento.horario:%H:%M}.')
                        return redirect('dashboard')
                messages.error(request, 'Não foi possível agendar. Revise os dados abaixo.')
        else:
                form = AgendamentoForms(cliente=cliente, initial={'servico': request.GET.get('servico')})
        context = {'form':form}
        return render (request, 'cadastroagendamento.html', context )          


@gerente_required
def CadastraUsuario(request):
        if request.method == 'POST':
                form = UsuarioForms(request.POST, request.FILES)
                if form.is_valid():
                        form.save()
                        messages.success(request, 'Usuário Cadastrado com sucesso')
                        form = UsuarioForms()
                else:
                        messages.error(request, 'Erro ao salvar os dados')
        else:
                form = UsuarioForms()
        context = {'form':form}
        return render (request, 'cadastrousuario1.html', context ) 
 
  
@barbeiro_required
def CadastraGaleria(request):
        barbeiro = getattr(request.user, 'barbeiro', None)
        if barbeiro is None:
                messages.error(request, 'Sua conta não está vinculada a um perfil de barbeiro, então não pode publicar na galeria.')
                return redirect('dashboard_barbeiro')

        if request.method == 'POST':
                form = GaleriaForms(request.POST, request.FILES)
                if form.is_valid():
                        galeria = form.save(commit=False)
                        galeria.barbeiro = barbeiro
                        galeria.save()
                        messages.success(request, 'Foto publicada na galeria com sucesso')
                        return redirect('ListaGaleria')
                messages.error(request, 'Erro ao salvar os dados')
        else:
                form = GaleriaForms()
        context = {'form':form}
        return render (request, 'cadastragaleria.html', context )  

          
"""     Consultas  """

"""def ConsultaClientes (request):
        context = {
                'clientes': Cliente.objects.all()
        }
        return render (request, 'consultaclientes.html', context)"""

def filtro_futuros():
        """Agendamentos ainda pendentes: status AGENDADO e início >= agora (fuso local)."""
        agora = timezone.localtime()
        return Q(status='AGENDADO') & (
                Q(data_agendamento__gt=agora.date()) |
                Q(data_agendamento=agora.date(), horario__gte=agora.time().replace(microsecond=0))
        )


@equipe_required
def ConsultaAgendamentos (request):
        """Gerente vê todos os agendamentos; barbeiro, só os seus. ?ordem=asc mostra os mais antigos primeiro."""
        visao_gerente = eh_gerente(request.user)
        barbeiro = None if visao_gerente else getattr(request.user, 'barbeiro', None)
        ordem = 'asc' if request.GET.get('ordem') == 'asc' else 'desc'
        campos = ('data_agendamento', 'horario') if ordem == 'asc' else ('-data_agendamento', '-horario')
        agendamentos = Agendamento.objects.select_related('cliente', 'barbeiro', 'servico').order_by(*campos)
        if not visao_gerente:
                agendamentos = agendamentos.filter(barbeiro=barbeiro) if barbeiro else agendamentos.none()
        context = {'visao_gerente': visao_gerente, 'barbeiro': barbeiro, 'agendamentos': agendamentos, 'ordem': ordem}
        return render (request, 'consultagendamentos.html', context)


@login_required(login_url='login')
@cliente_required
def meus_agendamentos(request):
        cliente = getattr(request.user, 'Cliente', None)
        if cliente is None:
                messages.warning(request, 'Sua conta ainda não tem um perfil de cliente. Fale com a barbearia para concluir seu cadastro.')
                return redirect('dashboard')
        base = (Agendamento.objects
                .filter(cliente=cliente)
                .select_related('barbeiro', 'servico'))
        context = {
                'futuros': base.filter(filtro_futuros()).order_by('data_agendamento', 'horario'),
                'historico': base.exclude(filtro_futuros()).order_by('-data_agendamento', '-horario'),
        }
        return render(request, 'meus_agendamentos.html', context)


def voltar_para(request, padrao):
        """Redireciona para o `next` do formulário (se for interno e seguro) ou para a URL padrão."""
        proximo = request.POST.get('next')
        if proximo and url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(proximo)
        return redirect(padrao)


@login_required(login_url='login')
@require_POST
def CancelarAgendamento(request, pk):
        agendamento = get_object_or_404(Agendamento.objects.select_related('cliente', 'barbeiro'), pk=pk)
        usuario = request.user
        eh_cliente_dono = agendamento.cliente.usuario_id == usuario.pk
        eh_barbeiro_dono = agendamento.barbeiro.usuario_id == usuario.pk
        destino = 'ConsultaAgendamentos' if eh_equipe(usuario) else 'meus_agendamentos'

        if not (eh_cliente_dono or eh_barbeiro_dono or eh_gerente(usuario)):
                messages.error(request, 'Você não tem permissão para cancelar este agendamento.')
                return voltar_para(request, destino)
        if agendamento.status != 'AGENDADO':
                messages.error(request, f'Este agendamento não pode ser cancelado: ele já está {agendamento.get_status_display().lower()}.')
                return voltar_para(request, destino)
        if agendamento.ja_passou:
                messages.error(request, 'Este agendamento já aconteceu e não pode mais ser cancelado.')
                return voltar_para(request, destino)

        agendamento.status = 'CANCELADO'
        agendamento.save(update_fields=['status'])
        messages.success(request, f'Agendamento de {agendamento.data_agendamento:%d/%m/%Y} às {agendamento.horario:%H:%M} cancelado.')
        return voltar_para(request, destino)


@login_required(login_url='login')
@require_POST
def ConcluirAgendamento(request, pk):
        """Barbeiro responsável ou gerente marca o atendimento como realizado."""
        agendamento = get_object_or_404(Agendamento.objects.select_related('barbeiro', 'cliente'), pk=pk)
        usuario = request.user
        destino = 'ConsultaAgendamentos' if eh_equipe(usuario) else painel_do_usuario(usuario)

        if not (eh_gerente(usuario) or agendamento.barbeiro.usuario_id == usuario.pk):
                messages.error(request, 'Você não tem permissão para concluir este agendamento.')
                return voltar_para(request, destino)
        if agendamento.status != 'AGENDADO':
                messages.error(request, f'Este agendamento não pode ser concluído: ele já está {agendamento.get_status_display().lower()}.')
                return voltar_para(request, destino)

        agendamento.status = 'CONCLUIDO'
        agendamento.save(update_fields=['status'])
        messages.success(request, f'Atendimento de {agendamento.cliente.nome} em {agendamento.data_agendamento:%d/%m/%Y} às {agendamento.horario:%H:%M} concluído.')
        return voltar_para(request, destino)

"""def ConsultaClientes (request):
        context = {
                'clientes': Cliente.objects.filter( Q(faixa_etaria='ADULTO') | Q(sexo='MASCULINO'))
        }
        return render (request, 'consultaclientes.html', context)"""

@equipe_required
def ConsultaClientes (request):
        context = {
                'clientes': Cliente.objects.select_related('usuario').order_by('nome')
        }
        return render (request, 'consultaclientes.html', context)

def ListaGaleria (request):
        context = {
                'galerias': Galeria.objects.select_related('barbeiro').order_by('-data')
        }
        return render (request, 'consultagaleria.html', context)









def index(request):
          return render (request, 'index.html')

def servicos(request):
          context = {'servicos': Servico.objects.filter(ativo=True).order_by('preco')}
          return render (request, 'servicos.html', context)
