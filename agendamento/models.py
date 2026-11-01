from datetime import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from stdimage.models import StdImageField

class Usuario(AbstractUser):
        TIPO_USUARIO_CHOICES = [
                ('CLIENTE', 'cliente'),
                ('BARBEIRO', 'barbeiro'),
                ('GERENTE', 'gerente'),
        ]
        
        tipo_usuario = models.CharField('Tipo de Usuário', max_length=8, choices=TIPO_USUARIO_CHOICES)

        def __str__(self):
                return self.username



class Cliente(models.Model):
          FAIXA_ETARIA_CHOICES = [
                    ('CRIANCA', 'Criança'),
                    ('ADOLESCENTE', 'Adolescente'),
                    ('ADULTO', 'Adulto'),
                    ('IDOSO', 'Idoso'),
          ]
          SEXO_CHOICES = [
                    ('MASCULINO', 'Masculino'),
                    ('FEMININO', 'Feminino'),         
          ]
          usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='Cliente')          
          cpf = models.CharField('CPF', max_length=11, primary_key=True)
          nome = models.CharField('Nome', max_length=60, null=False, blank=False)
          telefone = models.CharField('Telefone', max_length=13, null=False, unique=True, blank=False)
          email = models.EmailField('E-mail', null=False, unique=True, blank=False)
          faixa_etaria = models.CharField('Faixa Etária', max_length=15, choices=FAIXA_ETARIA_CHOICES, blank=False)
          sexo = models.CharField('Sexo', max_length=10, choices=SEXO_CHOICES, blank=False)
          
          def __str__(self):
                  return self.nome
          
class Barbeiro(models.Model):
          ESPECIALIDADE_CHOICES = [
                    ('CABELO', 'Cabelo'),
                    ('BARBA', 'Barba'),
                    ('DEPILACAO_NASAL', 'Depilação Nasal'),
                    ('CABELO_SOBRANCELHA', 'Cabelo + Sobrancelha'),
                    ]
          usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='barbeiro')          
          nome = models.CharField('Nome', max_length=60, null=False, blank=False)
          telefone = models.CharField('Telefone', max_length=13, null=False, unique=True, blank=False)
          especialidade = models.CharField('Especialidade', max_length=20, choices=ESPECIALIDADE_CHOICES)
          
          def __str__(self):
                  return self.nome

class Servico(models.Model):
          tipo = models.CharField('Serviço', max_length=60, blank=False, null=False, help_text='Nome livre, ex.: Corte degradê, Colocar peruca')
          duracao = models.PositiveIntegerField('Tempo de duração', help_text='Duração em minutos')
          preco = models.DecimalField('Preço do serviço', max_digits=5, decimal_places=2)
          ativo = models.BooleanField('Seriço Disponível', default=True)
          
          def __str__(self):
                  preco = f'{self.preco:.2f}'.replace('.', ',')
                  return f'{self.tipo} — R$ {preco} · {self.duracao} min'
          
          
class Agendamento(models.Model):
          STATUS_CHOICES = [
                    ('AGENDADO', 'Agendado'),
                    ('CANCELADO', 'Cancelado'),
                    ('CONCLUIDO', 'Concluído'),
                    ]
          cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='agendamentos')
          barbeiro = models.ForeignKey(Barbeiro, on_delete=models.PROTECT, related_name='agendamentos')
          servico = models.ForeignKey(Servico,on_delete=models.PROTECT, related_name='agendamentos') 
          idagendamento = models.BigAutoField('Identificador', primary_key=True, unique=True, blank=False, null=False)
          data_agendamento = models.DateField('Data do Agendamento')
          horario = models.TimeField('Horário Agendamento')
          observacao = models.TextField('Observação', max_length=200, blank=True)
          valor_total = models.DecimalField('Valor Total', max_digits=5, decimal_places=2)
          status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='AGENDADO')
         
          
          def __str__(self):
                    return self.observacao

          @property
          def inicio(self):
                    """Data e hora de início no fuso local (naive), comparável a timezone.localtime()."""
                    return datetime.combine(self.data_agendamento, self.horario)

          @property
          def ja_passou(self):
                    return self.inicio < timezone.localtime().replace(tzinfo=None)

          @property
          def cancelavel(self):
                    return self.status == 'AGENDADO' and not self.ja_passou

class Galeria(models.Model):
        barbeiro = models.ForeignKey(Barbeiro, on_delete=models.PROTECT, related_name='fotos_serviços')
        foto = StdImageField('Foto do Serviço', upload_to='fotos_servicos', variations={'thumb':(250,250)})
        descricao = models.CharField('Descrição do Serviço', max_length=200, blank=False, null=False)
        data = models.DateField('Data da publicação', blank=False, auto_now_add=True)
        
        def __str__(self):
                return self.descricao
          
