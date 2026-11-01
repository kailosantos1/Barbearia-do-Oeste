from datetime import datetime, time, timedelta

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Agendamento, Barbeiro, Cliente, Galeria, Servico, Usuario


class CadastroClienteForm(UserCreationForm):
    """Formulário público: cria a conta e o cadastro de cliente juntos."""

    email = forms.EmailField(label='E-mail', widget=forms.EmailInput(attrs={'placeholder': 'voce@exemplo.com'}))
    cpf = forms.CharField(label='CPF', max_length=11, widget=forms.TextInput(attrs={'placeholder': 'Somente números'}))
    nome = forms.CharField(label='Nome completo', max_length=60, widget=forms.TextInput(attrs={'placeholder': 'Como devemos chamar você?'}))
    telefone = forms.CharField(label='Telefone', max_length=13, widget=forms.TextInput(attrs={'placeholder': 'DDD + número'}))
    faixa_etaria = forms.ChoiceField(label='Faixa etária', choices=Cliente.FAIXA_ETARIA_CHOICES)
    sexo = forms.ChoiceField(label='Sexo', choices=Cliente.SEXO_CHOICES)

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username',)
        labels = {'username': 'Nome de usuário'}
        help_texts = {'username': 'Use letras, números e os símbolos @/./+/-/_.'}

    def clean_cpf(self):
        cpf = ''.join(filter(str.isdigit, self.cleaned_data['cpf']))
        if len(cpf) != 11:
            raise forms.ValidationError('Informe um CPF com 11 dígitos.')
        if Cliente.objects.filter(cpf=cpf).exists():
            raise forms.ValidationError('Já existe um cadastro com este CPF.')
        return cpf

    def clean_telefone(self):
        telefone = ''.join(filter(str.isdigit, self.cleaned_data['telefone']))
        if Cliente.objects.filter(telefone=telefone).exists():
            raise forms.ValidationError('Já existe um cadastro com este telefone.')
        return telefone

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Cliente.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Já existe um cadastro com este e-mail.')
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data['email']
        usuario.tipo_usuario = 'CLIENTE'
        if commit:
            usuario.save()
        return usuario

class ClienteForms(forms.ModelForm):
          class Meta:
                    model = Cliente
                    fields = ['usuario', 'cpf', 'nome', 'telefone', 'email', 'faixa_etaria', 'sexo' ]

class CadastroBarbeiroForm(UserCreationForm):
          """Cria a conta de acesso e o perfil de barbeiro numa única transação."""

          nome = forms.CharField(label='Nome completo', max_length=60)
          telefone = forms.CharField(label='Telefone', max_length=15, widget=forms.TextInput(attrs={'placeholder': '(49) 99999-0000'}))
          especialidade = forms.ChoiceField(label='Especialidade', choices=Barbeiro.ESPECIALIDADE_CHOICES)

          class Meta(UserCreationForm.Meta):
                    model = Usuario
                    fields = ('username',)
                    labels = {'username': 'Nome de usuário (login)'}

          def clean_telefone(self):
                    telefone = ''.join(filter(str.isdigit, self.cleaned_data['telefone']))
                    if not 10 <= len(telefone) <= 13:
                              raise forms.ValidationError('Informe DDD + número (10 a 13 dígitos).')
                    if Barbeiro.objects.filter(telefone=telefone).exists():
                              raise forms.ValidationError('Já existe um barbeiro com este telefone.')
                    return telefone

          def save(self, commit=True):
                    with transaction.atomic():
                              usuario = super().save(commit=False)
                              usuario.tipo_usuario = 'BARBEIRO'
                              usuario.save()
                              Barbeiro.objects.create(
                                        usuario=usuario,
                                        nome=self.cleaned_data['nome'],
                                        telefone=self.cleaned_data['telefone'],
                                        especialidade=self.cleaned_data['especialidade'],
                              )
                    return usuario

class ServicoForms(forms.ModelForm):
          class Meta:
                    model = Servico
                    fields = ['tipo', 'duracao', 'preco', 'ativo']
                    widgets = {'tipo': forms.TextInput(attrs={'placeholder': 'Ex.: Corte degradê, Colocar peruca'})}

          def clean_tipo(self):
                    tipo = ' '.join(self.cleaned_data['tipo'].split())
                    if Servico.objects.filter(tipo__iexact=tipo).exclude(pk=self.instance.pk).exists():
                              raise forms.ValidationError('Já existe um serviço com este nome.')
                    return tipo

          def clean_preco(self):
                    preco = self.cleaned_data['preco']
                    if preco <= 0:
                              raise forms.ValidationError('O preço deve ser maior que zero.')
                    return preco

          def clean_duracao(self):
                    duracao = self.cleaned_data['duracao']
                    if duracao <= 0:
                              raise forms.ValidationError('A duração deve ser maior que zero.')
                    return duracao

# Expediente: o atendimento inteiro [início, fim) precisa caber em um dos turnos.
TURNOS = [(time(8, 0), time(12, 0)), (time(13, 30), time(22, 0))]
INTERVALO_SLOTS = 30  # minutos
# Inícios oferecidos ao cliente; o último de cada turno só vale se a duração do serviço couber (validado no clean).
ULTIMOS_INICIOS = [time(11, 30), time(21, 30)]
TEXTO_EXPEDIENTE = 'Atendemos das ' + ' e das '.join(f'{a:%H:%M} às {f:%H:%M}' for a, f in TURNOS)


def gerar_slots():
          slots = []
          for (abertura, _), ultimo in zip(TURNOS, ULTIMOS_INICIOS):
                    atual = datetime.combine(datetime.min, abertura)
                    while atual.time() <= ultimo:
                              slots.append(atual.strftime('%H:%M'))
                              atual += timedelta(minutes=INTERVALO_SLOTS)
          return slots


HORARIOS_DISPONIVEIS = gerar_slots()


class AgendamentoForms(forms.ModelForm):
          """Agendamento feito pelo cliente logado; cliente, valor e status são definidos na view."""

          horario = forms.TimeField(
                    label='Horário',
                    input_formats=['%H:%M'],
                    widget=forms.Select(choices=[('', 'Selecione um horário')] + [(h, h) for h in HORARIOS_DISPONIVEIS]),
                    help_text=TEXTO_EXPEDIENTE,
          )

          class Meta:
                    model = Agendamento
                    fields = ['barbeiro', 'servico', 'data_agendamento', 'horario', 'observacao']
                    widgets = {
                              'data_agendamento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                              'observacao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Opcional. Ex.: corte mais baixo nas laterais'}),
                    }

          def __init__(self, *args, cliente=None, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.cliente = cliente
                    self.fields['servico'].queryset = Servico.objects.filter(ativo=True)

          @staticmethod
          def intervalo(data, horario, duracao):
                    inicio = datetime.combine(data, horario)
                    return inicio, inicio + timedelta(minutes=duracao)

          @staticmethod
          def erro_de_expediente(inicio, fim, duracao):
                    """Mensagem explicando por que [inicio, fim) não cabe no expediente, ou None se couber."""
                    for abertura, fechamento in TURNOS:
                              if datetime.combine(inicio.date(), abertura) <= inicio and fim <= datetime.combine(inicio.date(), fechamento):
                                        return None
                    (abre_manha, almoco_ini), (almoco_fim, fecha_noite) = TURNOS
                    faixa = f'{inicio:%H:%M}–{fim:%H:%M}, {duracao} min'
                    if inicio.time() < abre_manha or inicio.time() >= fecha_noite:
                              return f'Horário fora do expediente ({faixa}). {TEXTO_EXPEDIENTE}.'
                    if inicio.time() < almoco_fim:
                              return f'Esse atendimento ({faixa}) cairia no intervalo de almoço ({almoco_ini:%H:%M} às {almoco_fim:%H:%M}). Escolha outro horário.'
                    return f'Esse atendimento ({faixa}) terminaria após as {fecha_noite:%H:%M}, quando a barbearia fecha. Escolha um horário mais cedo.'

          def clean(self):
                    cleaned_data = super().clean()
                    barbeiro = cleaned_data.get('barbeiro')
                    servico = cleaned_data.get('servico')
                    data = cleaned_data.get('data_agendamento')
                    horario = cleaned_data.get('horario')
                    if not (servico and data and horario):
                              return cleaned_data

                    if not servico.ativo:
                              self.add_error('servico', 'Este serviço não está disponível no momento.')
                              return cleaned_data

                    inicio, fim = self.intervalo(data, horario, servico.duracao)
                    agora = timezone.localtime().replace(tzinfo=None)
                    if inicio < agora:
                              raise forms.ValidationError('Escolha uma data e um horário futuros.')

                    erro = self.erro_de_expediente(inicio, fim, servico.duracao)
                    if erro:
                              raise forms.ValidationError(erro)
                    if horario.strftime('%H:%M') not in HORARIOS_DISPONIVEIS:
                              self.add_error('horario', 'Escolha um dos horários da lista (intervalos de 30 minutos).')
                              return cleaned_data

                    if not barbeiro:
                              return cleaned_data

                    for agendamento, ag_inicio, ag_fim in ocupacoes(data, barbeiro, self.cliente, excluir_pk=self.instance.pk):
                              if not (inicio < ag_fim and ag_inicio < fim):
                                        continue
                              faixa = f"{ag_inicio:%d/%m %H:%M}–{ag_fim:%H:%M}"
                              if agendamento.barbeiro_id == barbeiro.pk:
                                        raise forms.ValidationError(f'{barbeiro.nome} já tem um atendimento das {faixa}. Escolha outro horário.')
                              raise forms.ValidationError(f'Você já tem um agendamento das {faixa} nesse intervalo.')

                    return cleaned_data


def ocupacoes(data, barbeiro, cliente=None, excluir_pk=None):
          """Agendamentos AGENDADO do barbeiro (e do cliente, se informado) que podem cruzar `data`, com seus intervalos."""
          envolvidos = Q(barbeiro=barbeiro)
          if cliente is not None:
                    envolvidos |= Q(cliente=cliente)
          # Considera o dia anterior para pegar agendamentos que atravessam a meia-noite.
          candidatos = (Agendamento.objects
                        .filter(envolvidos, status='AGENDADO', data_agendamento__range=(data - timedelta(days=1), data))
                        .select_related('servico'))
          if excluir_pk is not None:
                    candidatos = candidatos.exclude(pk=excluir_pk)
          return [(ag, *AgendamentoForms.intervalo(ag.data_agendamento, ag.horario, ag.servico.duracao)) for ag in candidatos]


def horarios_livres(barbeiro, servico, data, cliente=None):
          """Slots da grade em que o atendimento cabe no turno, ainda não passou e não conflita com barbeiro nem cliente.

          Mesmas regras do AgendamentoForms.clean (que continua sendo a validação definitiva).
          """
          agora = timezone.localtime().replace(tzinfo=None)
          ocupado = [(ag_inicio, ag_fim) for _, ag_inicio, ag_fim in ocupacoes(data, barbeiro, cliente)]
          livres = []
          for slot in HORARIOS_DISPONIVEIS:
                    inicio, fim = AgendamentoForms.intervalo(data, time.fromisoformat(slot), servico.duracao)
                    if inicio < agora or AgendamentoForms.erro_de_expediente(inicio, fim, servico.duracao):
                              continue
                    if any(inicio < ag_fim and ag_inicio < fim for ag_inicio, ag_fim in ocupado):
                              continue
                    livres.append(slot)
          return livres


class UsuarioForms(UserCreationForm):
          class Meta:
                    model = Usuario
                    fields = ['username', 'tipo_usuario']
                    
class GaleriaForms(forms.ModelForm):
          """O barbeiro é definido na view a partir do usuário logado."""
          class Meta:
                    model = Galeria
                    fields = ['foto', 'descricao']
