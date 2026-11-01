from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from agendamento.views import horarios_disponiveis, AlternaServico, CancelarAgendamento, ConcluirAgendamento, meus_agendamentos, EditaServico, GerenciaServicos, CadastraAgendamento, CadastraBarbeiro, CadastraCliente, CadastraGaleria, CadastraServico, CadastraUsuario, ConsultaAgendamentos, ConsultaClientes, ExcluiGaleria, ListaGaleria, dashboard, dashboard_barbeiro, dashboard_gerente, index, login_cliente, logout_cliente, servicos

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),
    path('servicos/', servicos, name='servicos'),
    path('servicos/gerenciar/', GerenciaServicos, name='GerenciaServicos'),
    path('servicos/<int:pk>/editar/', EditaServico, name='EditaServico'),
    path('servicos/<int:pk>/alternar/', AlternaServico, name='AlternaServico'),
    path('cadastro/cliente/', CadastraCliente, name='CadastraCliente'),
    path('login/', login_cliente, name='login'),
    path('logout/', logout_cliente, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('dashboard/barbeiro/', dashboard_barbeiro, name='dashboard_barbeiro'),
    path('dashboard/gerente/', dashboard_gerente, name='dashboard_gerente'),
    path('CadastraBarbeiro/', CadastraBarbeiro, name='CadastraBarbeiro'),
    path('CadastraServico/', CadastraServico, name='CadastraServico'),
    path('CadastraAgendamento/', CadastraAgendamento, name='CadastraAgendamento'),
    path('CadastraUsuario/', CadastraUsuario, name='CadastraUsuario'),
    path('CadastraGaleria/', CadastraGaleria, name='CadastraGaleria'),
    path('ConsultaClientes/', ConsultaClientes, name='ConsultaClientes'),
    path('ConsultaAgendamentos/', ConsultaAgendamentos, name='ConsultaAgendamentos'),
    path('agendamentos/meus/', meus_agendamentos, name='meus_agendamentos'),
    path('api/horarios-disponiveis/', horarios_disponiveis, name='horarios_disponiveis'),
    path('agendamentos/<int:pk>/cancelar/', CancelarAgendamento, name='CancelarAgendamento'),
    path('agendamentos/<int:pk>/concluir/', ConcluirAgendamento, name='ConcluirAgendamento'),
    path('listagaleria/', ListaGaleria, name='ListaGaleria'),
    path('galeria/<int:pk>/excluir/', ExcluiGaleria, name='ExcluiGaleria'),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
