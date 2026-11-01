from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from agendamento.models import *

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
          list_display = ('username', 'tipo_usuario', 'is_staff', 'is_active')

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
          list_display = ('cpf', 'nome', 'telefone', 'email', 'faixa_etaria', 'sexo')

@admin.register(Barbeiro)
class BarbeiroAdmin(admin.ModelAdmin):
          list_display = ('nome', 'telefone', 'especialidade')
          
@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
          list_display = ('tipo', 'duracao', 'preco', 'ativo')


@admin.register(Galeria)
class GaleriaAdmin(admin.ModelAdmin):
          list_display = ('barbeiro', 'foto', 'data', 'descricao')
