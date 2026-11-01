from django.contrib.messages import get_messages
import io
import re
import shutil
import tempfile

from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase, override_settings
from PIL import Image
from django.urls import reverse
from django.utils import timezone

import datetime
from decimal import Decimal

from .forms import HORARIOS_DISPONIVEIS, AgendamentoForms, CadastroBarbeiroForm, GaleriaForms, ServicoForms
from .models import Agendamento, Barbeiro, Cliente, Galeria, Servico, Usuario


# Rotas restritas por perfil: (urls, mensagem de login, mensagem de acesso negado)
URLS_DE_BARBEIRO = ['dashboard_barbeiro', 'CadastraGaleria']
URLS_DA_EQUIPE = ['ConsultaClientes', 'ConsultaAgendamentos']
URLS_DE_GERENTE = ['dashboard_gerente', 'CadastraBarbeiro', 'CadastraUsuario', 'CadastraServico', 'GerenciaServicos']

GRUPOS = [
        (URLS_DE_BARBEIRO, 'Faça login como barbeiro', 'exclusiva para barbeiros'),
        (URLS_DA_EQUIPE, 'Faça login com uma conta da equipe', 'exclusiva para a equipe da barbearia'),
        (URLS_DE_GERENTE, 'Faça login como gerente', 'exclusiva para gerentes'),
]


class ControleDeAcessoTests(TestCase):
        def setUp(self):
                self.cliente = Usuario.objects.create_user('cliente', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.barbeiro = Usuario.objects.create_user('barbeiro', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.gerente = Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')

        def mensagens(self, response):
                return ' '.join(str(m) for m in get_messages(response.wsgi_request))

        def entra(self, username):
                return self.client.post(reverse('login'), {'username': username, 'password': 'senha-forte-123'})

        def test_login_barbeiro_vai_para_painel_do_barbeiro(self):
                self.assertRedirects(self.entra('barbeiro'), reverse('dashboard_barbeiro'))

        def test_login_cliente_vai_para_dashboard(self):
                self.assertRedirects(self.entra('cliente'), reverse('dashboard'))

        def test_login_gerente_vai_para_painel_gerencial(self):
                self.assertRedirects(self.entra('gerente'), reverse('dashboard_gerente'))

        def test_login_superusuario_vai_para_painel_gerencial(self):
                Usuario.objects.create_superuser('admin', 'admin@exemplo.com', 'senha-forte-123')
                self.assertRedirects(self.entra('admin'), reverse('dashboard_gerente'))

        def test_login_respeita_next(self):
                destino = reverse('ConsultaAgendamentos')
                response = self.client.post(f"{reverse('login')}?next={destino}", {'username': 'barbeiro', 'password': 'senha-forte-123', 'next': destino})
                self.assertRedirects(response, destino)

        def test_login_ignora_next_externo(self):
                response = self.client.post(reverse('login'), {'username': 'barbeiro', 'password': 'senha-forte-123', 'next': 'https://malicioso.com/'})
                self.assertRedirects(response, reverse('dashboard_barbeiro'))

        def test_anonimo_e_barrado_e_enviado_ao_login(self):
                for urls, aviso, _ in GRUPOS:
                        for nome in urls:
                                with self.subTest(url=nome):
                                        url = reverse(nome)
                                        response = self.client.get(url)
                                        self.assertRedirects(response, f"{reverse('login')}?next={url}")
                                        self.assertIn(aviso, self.mensagens(response))

        def test_cliente_e_barrado_com_mensagem(self):
                self.client.force_login(self.cliente)
                for urls, _, negado in GRUPOS:
                        for nome in urls:
                                with self.subTest(url=nome):
                                        response = self.client.get(reverse(nome))
                                        self.assertRedirects(response, reverse('dashboard'))
                                        self.assertIn(f'Acesso negado: esta área é {negado}.', self.mensagens(response))

        def test_barbeiro_acessa_areas_de_barbeiro_e_da_equipe(self):
                Barbeiro.objects.create(usuario=self.barbeiro, nome='Zé', telefone='49999990000', especialidade='CABELO')
                self.client.force_login(self.barbeiro)
                for nome in URLS_DE_BARBEIRO + URLS_DA_EQUIPE:
                        with self.subTest(url=nome):
                                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

        def test_barbeiro_nao_acessa_area_gerencial(self):
                self.client.force_login(self.barbeiro)
                for nome in URLS_DE_GERENTE:
                        with self.subTest(url=nome):
                                response = self.client.get(reverse(nome))
                                self.assertRedirects(response, reverse('dashboard_barbeiro'))
                                self.assertIn('Acesso negado: esta área é exclusiva para gerentes.', self.mensagens(response))

        def test_gerente_acessa_areas_gerenciais_e_da_equipe(self):
                self.client.force_login(self.gerente)
                for nome in URLS_DE_GERENTE + URLS_DA_EQUIPE:
                        with self.subTest(url=nome):
                                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

        def test_gerente_nao_acessa_areas_exclusivas_de_barbeiro_nem_de_cliente(self):
                self.client.force_login(self.gerente)
                for nome in URLS_DE_BARBEIRO + ['dashboard', 'CadastraAgendamento', 'meus_agendamentos']:
                        with self.subTest(url=nome):
                                self.assertRedirects(self.client.get(reverse(nome)), reverse('dashboard_gerente'))

        def test_barbeiro_nao_acessa_area_do_cliente(self):
                self.client.force_login(self.barbeiro)
                for nome in ['dashboard', 'CadastraAgendamento']:
                        with self.subTest(url=nome):
                                response = self.client.get(reverse(nome))
                                self.assertRedirects(response, reverse('dashboard_barbeiro'))
                                self.assertIn('Esta área é exclusiva para clientes.', self.mensagens(response))

        def test_painel_lista_agendamentos_do_barbeiro(self):
                barbeiro = Barbeiro.objects.create(usuario=self.barbeiro, nome='Zé Navalha', telefone='49999990000', especialidade='BARBA')
                cliente = Cliente.objects.create(usuario=self.cliente, cpf='12345678901', nome='Ana Cliente', telefone='49988880000',
                                                 email='ana@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                servico = Servico.objects.create(tipo='BARBA', duracao=30, preco=Decimal('30.00'))
                Agendamento.objects.create(cliente=cliente, barbeiro=barbeiro, servico=servico, data_agendamento=datetime.date(2026, 11, 10),
                                           horario=datetime.time(14, 30), observacao='Primeira vez', valor_total=Decimal('30.00'))
                self.client.force_login(self.barbeiro)
                response = self.client.get(reverse('dashboard_barbeiro'))
                self.assertContains(response, 'Zé Navalha')
                self.assertContains(response, 'Ana Cliente')
                self.assertContains(response, '10/11/2026')
                self.assertContains(response, 'Agendado')


class ServicoFormsTests(TestCase):
        def dados(self, **kwargs):
                return {'tipo': 'CABELO', 'duracao': 30, 'preco': '45.00', 'ativo': True, **kwargs}

        def test_aceita_valores_validos(self):
                self.assertTrue(ServicoForms(self.dados()).is_valid())

        def test_rejeita_preco_menor_ou_igual_a_zero(self):
                for preco in ['0', '0.00', '-10.00']:
                        with self.subTest(preco=preco):
                                form = ServicoForms(self.dados(preco=preco))
                                self.assertFalse(form.is_valid())
                                self.assertIn('O preço deve ser maior que zero.', form.errors['preco'])

        def test_rejeita_duracao_menor_ou_igual_a_zero(self):
                form = ServicoForms(self.dados(duracao=0))
                self.assertFalse(form.is_valid())
                self.assertIn('A duração deve ser maior que zero.', form.errors['duracao'])

                form = ServicoForms(self.dados(duracao=-5))
                self.assertFalse(form.is_valid())
                self.assertIn('duracao', form.errors)


class ServicosPublicosTests(TestCase):
        def setUp(self):
                self.corte = Servico.objects.create(tipo='CABELO', duracao=30, preco=Decimal('45.00'))
                self.barba = Servico.objects.create(tipo='BARBA', duracao=20, preco=Decimal('40.00'), ativo=False)

        def test_lista_apenas_servicos_ativos_sem_autenticacao(self):
                response = self.client.get(reverse('servicos'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context['servicos']), [self.corte])
                self.assertContains(response, 'R$ 45,00')
                self.assertContains(response, '30 min')
                self.assertContains(response, f"{reverse('CadastraAgendamento')}?servico={self.corte.pk}")
                self.assertNotContains(response, 'R$ 40,00')

        def test_mensagem_quando_nao_ha_servicos_ativos(self):
                Servico.objects.update(ativo=False)
                self.assertContains(self.client.get(reverse('servicos')), 'Nenhum serviço disponível no momento.')


class GerenciaServicosTests(TestCase):
        def setUp(self):
                self.servico = Servico.objects.create(tipo='CABELO', duracao=30, preco=Decimal('45.00'))
                self.gerente = Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')
                self.barbeiro = Usuario.objects.create_user('barbeiro', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.cliente = Usuario.objects.create_user('cliente', password='senha-forte-123', tipo_usuario='CLIENTE')

        def test_gerente_edita_servico(self):
                self.client.force_login(self.gerente)
                url = reverse('EditaServico', args=[self.servico.pk])
                self.assertEqual(self.client.get(url).status_code, 200)
                response = self.client.post(url, {'tipo': 'CABELO', 'duracao': 40, 'preco': '50.00', 'ativo': True})
                self.assertRedirects(response, reverse('GerenciaServicos'))
                self.servico.refresh_from_db()
                self.assertEqual((self.servico.duracao, self.servico.preco), (40, Decimal('50.00')))

        def test_edicao_com_preco_invalido_nao_salva(self):
                self.client.force_login(self.gerente)
                response = self.client.post(reverse('EditaServico', args=[self.servico.pk]), {'tipo': 'CABELO', 'duracao': 30, 'preco': '0', 'ativo': True})
                self.assertEqual(response.status_code, 200)
                self.servico.refresh_from_db()
                self.assertEqual(self.servico.preco, Decimal('45.00'))

        def test_gerente_desativa_e_reativa_servico(self):
                self.client.force_login(self.gerente)
                url = reverse('AlternaServico', args=[self.servico.pk])
                self.assertRedirects(self.client.post(url), reverse('GerenciaServicos'))
                self.servico.refresh_from_db()
                self.assertFalse(self.servico.ativo)
                self.client.post(url)
                self.servico.refresh_from_db()
                self.assertTrue(self.servico.ativo)

        def test_alternar_exige_post(self):
                self.client.force_login(self.gerente)
                self.assertEqual(self.client.get(reverse('AlternaServico', args=[self.servico.pk])).status_code, 405)

        def test_cliente_nao_edita_nem_desativa(self):
                self.client.force_login(self.cliente)
                for url in [reverse('EditaServico', args=[self.servico.pk]), reverse('AlternaServico', args=[self.servico.pk])]:
                        with self.subTest(url=url):
                                self.assertRedirects(self.client.post(url, {'tipo': 'BARBA', 'duracao': 1, 'preco': '1.00'}), reverse('dashboard'))
                self.servico.refresh_from_db()
                self.assertEqual((self.servico.tipo, self.servico.ativo), ('CABELO', True))

        def test_gerente_cadastra_servico_com_nome_personalizado(self):
                self.client.force_login(self.gerente)
                response = self.client.post(reverse('CadastraServico'), {'tipo': '  Colocar   peruca ', 'duracao': 60, 'preco': '120.00', 'ativo': True})
                self.assertEqual(response.status_code, 200)
                servico = Servico.objects.get(tipo='Colocar peruca')
                self.assertEqual(str(servico), 'Colocar peruca — R$ 120,00 · 60 min')

                self.client.logout()
                publica = self.client.get(reverse('servicos'))
                self.assertContains(publica, 'Colocar peruca')
                self.assertContains(publica, 'R$ 120,00')

        def test_rejeita_nome_de_servico_duplicado(self):
                form = ServicoForms({'tipo': 'cabelo', 'duracao': 30, 'preco': '40.00', 'ativo': True})
                self.assertFalse(form.is_valid())
                self.assertIn('Já existe um serviço com este nome.', form.errors['tipo'])
                edicao = ServicoForms({'tipo': 'CABELO', 'duracao': 35, 'preco': '40.00', 'ativo': True}, instance=self.servico)
                self.assertTrue(edicao.is_valid(), edicao.errors)

        def test_servico_personalizado_aparece_no_select_do_agendamento(self):
                Servico.objects.create(tipo='Colocar peruca', duracao=60, preco=Decimal('120.00'))
                rotulos = [rotulo for _, rotulo in AgendamentoForms().fields['servico'].choices]
                self.assertIn('Colocar peruca — R$ 120,00 · 60 min', rotulos)

        def test_barbeiro_e_barrado_nas_rotas_de_servico(self):
                self.client.force_login(self.barbeiro)
                rotas = [
                        ('get', reverse('GerenciaServicos'), {}),
                        ('get', reverse('CadastraServico'), {}),
                        ('post', reverse('CadastraServico'), {'tipo': 'BARBA', 'duracao': 20, 'preco': '30.00', 'ativo': True}),
                        ('get', reverse('EditaServico', args=[self.servico.pk]), {}),
                        ('post', reverse('EditaServico', args=[self.servico.pk]), {'tipo': 'BARBA', 'duracao': 1, 'preco': '1.00'}),
                        ('post', reverse('AlternaServico', args=[self.servico.pk]), {}),
                ]
                for metodo, url, dados in rotas:
                        with self.subTest(metodo=metodo, url=url):
                                response = getattr(self.client, metodo)(url, dados)
                                self.assertRedirects(response, reverse('dashboard_barbeiro'))
                                mensagens = ' '.join(str(m) for m in get_messages(response.wsgi_request))
                                self.assertIn('Acesso negado: esta área é exclusiva para gerentes.', mensagens)
                self.servico.refresh_from_db()
                self.assertEqual((self.servico.tipo, self.servico.duracao, self.servico.ativo), ('CABELO', 30, True))
                self.assertEqual(Servico.objects.count(), 1)

        def test_menu_do_barbeiro_nao_mostra_servicos(self):
                Barbeiro.objects.create(usuario=self.barbeiro, nome='Zé', telefone='49999990000', especialidade='CABELO')
                self.client.force_login(self.barbeiro)
                response = self.client.get(reverse('dashboard_barbeiro'))
                self.assertNotContains(response, reverse('GerenciaServicos'))
                self.assertNotContains(response, reverse('CadastraServico'))


class AgendamentoTests(TestCase):
        def setUp(self):
                self.dia = timezone.localdate() + datetime.timedelta(days=7)
                self.usuario_cliente = Usuario.objects.create_user('ana', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.cliente = Cliente.objects.create(usuario=self.usuario_cliente, cpf='12345678901', nome='Ana', telefone='49988880000',
                                                      email='ana@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                outro = Usuario.objects.create_user('bia', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.outro_cliente = Cliente.objects.create(usuario=outro, cpf='10987654321', nome='Bia', telefone='49977770000',
                                                            email='bia@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                self.ze = self.cria_barbeiro('ze', 'Zé', '49999990001')
                self.rui = self.cria_barbeiro('rui', 'Rui', '49999990002')
                self.combo = Servico.objects.create(tipo='CABELO_SOBRANCELHA', duracao=45, preco=Decimal('60.00'))
                self.barba = Servico.objects.create(tipo='BARBA', duracao=30, preco=Decimal('40.00'))

        def cria_barbeiro(self, username, nome, telefone):
                usuario = Usuario.objects.create_user(username, password='senha-forte-123', tipo_usuario='BARBEIRO')
                return Barbeiro.objects.create(usuario=usuario, nome=nome, telefone=telefone, especialidade='CABELO')

        def agenda_existente(self, cliente, barbeiro, servico, hora, minuto=0, status='AGENDADO'):
                return Agendamento.objects.create(cliente=cliente, barbeiro=barbeiro, servico=servico, data_agendamento=self.dia,
                                                  horario=datetime.time(hora, minuto), observacao='-', valor_total=servico.preco, status=status)

        def form(self, barbeiro, servico, horario, data=None, cliente=None):
                dados = {'barbeiro': barbeiro.pk, 'servico': servico.pk, 'data_agendamento': data or self.dia,
                         'horario': horario, 'observacao': 'Teste'}
                return AgendamentoForms(dados, cliente=cliente or self.cliente)

        def erros(self, form):
                self.assertFalse(form.is_valid())
                return ' '.join(form.non_field_errors())

        def test_aceita_horario_livre(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.barba, 14)  # 14:00–14:30
                self.assertTrue(self.form(self.ze, self.barba, '14:30').is_valid())

        def test_rejeita_agendamento_no_passado(self):
                ontem = timezone.localdate() - datetime.timedelta(days=1)
                self.assertIn('futuros', self.erros(self.form(self.ze, self.barba, '10:00', data=ontem)))

                uma_hora_atras = timezone.localtime() - datetime.timedelta(hours=1)
                form = self.form(self.ze, self.barba, uma_hora_atras.strftime('%H:%M'), data=uma_hora_atras.date())
                self.assertIn('futuros', self.erros(form))

        def test_rejeita_servico_inativo(self):
                self.barba.ativo = False
                self.barba.save()
                form = self.form(self.ze, self.barba, '10:00')
                self.assertFalse(form.is_valid())
                self.assertIn('servico', form.errors)
                self.assertNotIn(self.barba, form.fields['servico'].queryset)

        def test_conflito_exato_mesmo_barbeiro(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.barba, 14)
                self.assertIn('Zé já tem um atendimento', self.erros(self.form(self.ze, self.barba, '14:00')))

        def test_conflito_sobreposto_pela_duracao(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.combo, 14)  # 14:00–14:45
                self.assertIn('Zé já tem um atendimento', self.erros(self.form(self.ze, self.barba, '14:30')))

        def test_novo_que_termina_dentro_de_existente_conflita(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.barba, 14)  # 14:00–14:30
                self.assertIn('Zé já tem um atendimento', self.erros(self.form(self.ze, self.combo, '13:30')))  # 13:30–14:15

        def test_cliente_nao_agenda_dois_barbeiros_no_mesmo_intervalo(self):
                self.agenda_existente(self.cliente, self.ze, self.combo, 14)
                self.assertIn('Você já tem um agendamento', self.erros(self.form(self.rui, self.barba, '14:30')))

        def test_outro_cliente_pode_usar_outro_barbeiro_no_mesmo_horario(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.combo, 14)
                self.assertTrue(self.form(self.rui, self.barba, '14:00').is_valid())

        def test_agendamento_cancelado_nao_bloqueia(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.combo, 14, status='CANCELADO')
                self.assertTrue(self.form(self.ze, self.barba, '14:00').is_valid())

        def test_campo_horario_e_select_com_slots_de_30_minutos(self):
                campo = AgendamentoForms(cliente=self.cliente).fields['horario']
                opcoes = [valor for valor, _ in campo.widget.choices if valor]
                self.assertEqual(opcoes, HORARIOS_DISPONIVEIS)
                self.assertEqual(len(opcoes), 25)
                self.assertEqual((opcoes[0], opcoes[7], opcoes[8], opcoes[-1]), ('08:00', '11:30', '13:30', '21:30'))
                for horario in ['12:00', '12:30', '13:00']:
                        self.assertNotIn(horario, opcoes)
                self.assertEqual(campo.help_text, 'Atendemos das 08:00 às 12:00 e das 13:30 às 22:00')

        def test_aceita_atendimentos_que_terminam_exatamente_no_fim_do_turno(self):
                self.assertTrue(self.form(self.ze, self.barba, '11:30').is_valid())   # 11:30–12:00
                self.assertTrue(self.form(self.rui, self.combo, '11:00').is_valid())  # 11:00–11:45
                self.assertTrue(self.form(self.ze, self.barba, '21:30').is_valid())   # 21:30–22:00
                self.assertTrue(self.form(self.rui, self.combo, '08:00').is_valid())  # 08:00–08:45

        def test_rejeita_madrugada(self):
                for horario in ['03:00', '07:30']:
                        with self.subTest(horario=horario):
                                erro = self.erros(self.form(self.ze, self.barba, horario))
                                self.assertIn('fora do expediente', erro)
                                self.assertIn('Atendemos das 08:00 às 12:00 e das 13:30 às 22:00', erro)

        def test_rejeita_intervalo_do_almoco(self):
                for horario in ['12:00', '13:00']:  # começa no almoço
                        with self.subTest(horario=horario):
                                self.assertIn('intervalo de almoço (12:00 às 13:30)', self.erros(self.form(self.ze, self.barba, horario)))
                self.assertIn('intervalo de almoço', self.erros(self.form(self.ze, self.combo, '11:30')))   # 11:30–12:15 invade

        def test_rejeita_termino_apos_as_22h(self):
                self.assertIn('terminaria após as 22:00', self.erros(self.form(self.ze, self.combo, '21:30')))  # 21:30–22:15
                self.assertIn('fora do expediente', self.erros(self.form(self.ze, self.barba, '22:00')))

        def test_rejeita_horario_fora_da_grade(self):
                form = self.form(self.ze, self.barba, '14:15')
                self.assertFalse(form.is_valid())
                self.assertIn('horario', form.errors)

        def test_agendamento_sem_observacao(self):
                self.client.force_login(self.usuario_cliente)
                response = self.client.post(reverse('CadastraAgendamento'), {
                        'barbeiro': self.ze.pk, 'servico': self.barba.pk, 'data_agendamento': self.dia,
                        'horario': '10:00', 'observacao': ''})
                self.assertRedirects(response, reverse('dashboard'))
                self.assertEqual(Agendamento.objects.get().observacao, '')

        def test_view_define_cliente_valor_e_status(self):
                self.client.force_login(self.usuario_cliente)
                response = self.client.post(reverse('CadastraAgendamento'), {
                        'barbeiro': self.ze.pk, 'servico': self.combo.pk, 'data_agendamento': self.dia,
                        'horario': '09:00', 'observacao': 'Primeira vez',
                        'valor_total': '0.01', 'status': 'CONCLUIDO', 'cliente': self.outro_cliente.pk,
                })
                self.assertRedirects(response, reverse('dashboard'))
                agendamento = Agendamento.objects.get()
                self.assertEqual(agendamento.cliente, self.cliente)
                self.assertEqual(agendamento.valor_total, Decimal('60.00'))
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_view_rejeita_conflito_sem_salvar(self):
                self.agenda_existente(self.outro_cliente, self.ze, self.combo, 14)
                self.client.force_login(self.usuario_cliente)
                response = self.client.post(reverse('CadastraAgendamento'), {
                        'barbeiro': self.ze.pk, 'servico': self.barba.pk, 'data_agendamento': self.dia,
                        'horario': '14:30', 'observacao': 'x'})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Zé já tem um atendimento')
                self.assertEqual(Agendamento.objects.count(), 1)

        def test_cliente_sem_perfil_e_orientado(self):
                sem_perfil = Usuario.objects.create_user('semperfil', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.client.force_login(sem_perfil)
                response = self.client.get(reverse('CadastraAgendamento'))
                self.assertRedirects(response, reverse('dashboard'))
                self.assertIn('perfil de cliente', ' '.join(str(m) for m in get_messages(response.wsgi_request)))


class ConsultaECancelamentoTests(TestCase):
        def setUp(self):
                self.futuro = timezone.localdate() + datetime.timedelta(days=3)
                self.passado = timezone.localdate() - datetime.timedelta(days=3)
                self.servico = Servico.objects.create(tipo='CABELO', duracao=30, preco=Decimal('45.00'))
                self.ana, self.usuario_ana = self.cria_cliente('ana', '11111111111', '49911110000')
                self.bia, self.usuario_bia = self.cria_cliente('bia', '22222222222', '49922220000')
                self.ze, self.usuario_ze = self.cria_barbeiro('ze', '49999990001')
                self.rui, self.usuario_rui = self.cria_barbeiro('rui', '49999990002')

        def cria_cliente(self, nome, cpf, telefone):
                usuario = Usuario.objects.create_user(nome, password='senha-forte-123', tipo_usuario='CLIENTE')
                cliente = Cliente.objects.create(usuario=usuario, cpf=cpf, nome=nome.title(), telefone=telefone,
                                                 email=f'{nome}@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                return cliente, usuario

        def cria_barbeiro(self, nome, telefone):
                usuario = Usuario.objects.create_user(nome, password='senha-forte-123', tipo_usuario='BARBEIRO')
                return Barbeiro.objects.create(usuario=usuario, nome=nome.title(), telefone=telefone, especialidade='CABELO'), usuario

        def agenda(self, cliente, barbeiro, data, hora=10, status='AGENDADO'):
                return Agendamento.objects.create(cliente=cliente, barbeiro=barbeiro, servico=self.servico, data_agendamento=data,
                                                  horario=datetime.time(hora, 0), observacao='-', valor_total=self.servico.preco, status=status)

        def mensagens(self, response):
                return ' '.join(str(m) for m in get_messages(response.wsgi_request))

        def cancela(self, agendamento):
                return self.client.post(reverse('CancelarAgendamento', args=[agendamento.pk]))

        def test_cliente_ve_apenas_seus_agendamentos_separados(self):
                proximo = self.agenda(self.ana, self.ze, self.futuro)
                antigo = self.agenda(self.ana, self.ze, self.passado, status='CONCLUIDO')
                cancelado_futuro = self.agenda(self.ana, self.rui, self.futuro, hora=15, status='CANCELADO')
                da_bia = self.agenda(self.bia, self.ze, self.futuro, hora=11)

                self.client.force_login(self.usuario_ana)
                response = self.client.get(reverse('meus_agendamentos'))
                self.assertEqual(list(response.context['futuros']), [proximo])
                self.assertCountEqual(list(response.context['historico']), [antigo, cancelado_futuro])
                todos = list(response.context['futuros']) + list(response.context['historico'])
                self.assertNotIn(da_bia, todos)

        def test_barbeiro_ve_apenas_agendamentos_vinculados_a_ele(self):
                do_ze_1 = self.agenda(self.ana, self.ze, self.passado)
                do_ze_2 = self.agenda(self.bia, self.ze, self.futuro)
                self.agenda(self.ana, self.rui, self.futuro, hora=14)

                self.client.force_login(self.usuario_ze)
                response = self.client.get(reverse('ConsultaAgendamentos'))
                self.assertEqual(list(response.context['agendamentos']), [do_ze_2, do_ze_1])
                response = self.client.get(reverse('ConsultaAgendamentos'), {'ordem': 'asc'})
                self.assertEqual(list(response.context['agendamentos']), [do_ze_1, do_ze_2])

        def cria_gerente(self):
                return Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')

        def test_gerente_ve_todos_os_agendamentos(self):
                antigo = self.agenda(self.ana, self.ze, self.passado)
                do_rui = self.agenda(self.bia, self.rui, self.futuro, hora=9)
                do_ze = self.agenda(self.ana, self.ze, self.futuro, hora=15, status='CANCELADO')
                self.client.force_login(self.cria_gerente())
                response = self.client.get(reverse('ConsultaAgendamentos'))
                self.assertEqual(list(response.context['agendamentos']), [do_ze, do_rui, antigo])
                self.assertTrue(response.context['visao_gerente'])
                self.assertContains(response, 'Todos os agendamentos')
                self.assertContains(response, '<th>Barbeiro</th>', html=False)
                for nome in ['Ze', 'Rui']:
                        self.assertContains(response, f'<td>{nome}</td>', html=True)
                response = self.client.get(reverse('ConsultaAgendamentos'), {'ordem': 'asc'})
                self.assertEqual(list(response.context['agendamentos']), [antigo, do_rui, do_ze])

        def test_gerente_ve_acoes_de_qualquer_barbeiro(self):
                agendamento = self.agenda(self.bia, self.rui, self.futuro)
                self.client.force_login(self.cria_gerente())
                response = self.client.get(reverse('ConsultaAgendamentos'))
                self.assertContains(response, reverse('ConcluirAgendamento', args=[agendamento.pk]))
                self.assertContains(response, f'data-url="{reverse("CancelarAgendamento", args=[agendamento.pk])}"')

        def test_gerente_cancela_agendamento_de_qualquer_barbeiro(self):
                agendamento = self.agenda(self.bia, self.rui, self.futuro)
                self.client.force_login(self.cria_gerente())
                self.assertRedirects(self.cancela(agendamento), reverse('ConsultaAgendamentos'))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CANCELADO')

        def test_gerente_nao_cancela_agendamento_passado(self):
                agendamento = self.agenda(self.bia, self.rui, self.passado)
                self.client.force_login(self.cria_gerente())
                self.assertIn('já aconteceu', self.mensagens(self.cancela(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_cliente_cancela_agendamento_futuro(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                self.client.force_login(self.usuario_ana)
                response = self.cancela(agendamento)
                self.assertRedirects(response, reverse('meus_agendamentos'))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CANCELADO')
                self.assertIn('cancelado', self.mensagens(response))

        def test_cliente_nao_cancela_agendamento_de_outro_cliente(self):
                agendamento = self.agenda(self.bia, self.ze, self.futuro)
                self.client.force_login(self.usuario_ana)
                response = self.cancela(agendamento)
                self.assertRedirects(response, reverse('meus_agendamentos'))
                self.assertIn('não tem permissão', self.mensagens(response))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_nao_cancela_agendamento_concluido(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro, status='CONCLUIDO')
                self.client.force_login(self.usuario_ana)
                self.assertIn('não pode ser cancelado', self.mensagens(self.cancela(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CONCLUIDO')

        def test_nao_cancela_agendamento_passado(self):
                agendamento = self.agenda(self.ana, self.ze, self.passado)
                for usuario in [self.usuario_ana, self.usuario_ze]:
                        with self.subTest(usuario=usuario.username):
                                self.client.force_login(usuario)
                                self.assertIn('já aconteceu', self.mensagens(self.cancela(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_barbeiro_cancela_agendamento_vinculado(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                self.client.force_login(self.usuario_ze)
                self.assertRedirects(self.cancela(agendamento), reverse('ConsultaAgendamentos'))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CANCELADO')

        def test_barbeiro_nao_cancela_agendamento_de_outro_barbeiro(self):
                agendamento = self.agenda(self.ana, self.rui, self.futuro)
                self.client.force_login(self.usuario_ze)
                self.assertIn('não tem permissão', self.mensagens(self.cancela(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_cancelamento_exige_post_e_login(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                url = reverse('CancelarAgendamento', args=[agendamento.pk])
                self.assertRedirects(self.client.post(url), f"{reverse('login')}?next={url}")
                self.client.force_login(self.usuario_ana)
                self.assertEqual(self.client.get(url).status_code, 405)
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_cancelamento_exige_csrf(self):
                from django.test import Client
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                cliente_http = Client(enforce_csrf_checks=True)
                cliente_http.force_login(self.usuario_ana)
                self.assertEqual(cliente_http.post(reverse('CancelarAgendamento', args=[agendamento.pk])).status_code, 403)

        def conclui(self, agendamento, **dados):
                return self.client.post(reverse('ConcluirAgendamento', args=[agendamento.pk]), dados)

        def test_barbeiro_conclui_agendamento_vinculado(self):
                agendamento = self.agenda(self.ana, self.ze, self.passado)
                self.client.force_login(self.usuario_ze)
                response = self.conclui(agendamento)
                self.assertRedirects(response, reverse('ConsultaAgendamentos'))
                self.assertIn('concluído', self.mensagens(response))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CONCLUIDO')

        def test_gerente_conclui_agendamento_de_qualquer_barbeiro(self):
                agendamento = self.agenda(self.ana, self.rui, self.futuro)
                gerente = Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')
                self.client.force_login(gerente)
                self.assertRedirects(self.conclui(agendamento), reverse('ConsultaAgendamentos'))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CONCLUIDO')

        def test_conclusao_volta_para_a_pagina_de_origem(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                self.client.force_login(self.usuario_ze)
                self.assertRedirects(self.conclui(agendamento, next=reverse('dashboard_barbeiro')), reverse('dashboard_barbeiro'))
                outro = self.agenda(self.bia, self.ze, self.futuro, hora=15)
                self.assertRedirects(self.conclui(outro, next='https://malicioso.com/'), reverse('ConsultaAgendamentos'))

        def test_conclusao_negada_para_outro_barbeiro_e_cliente(self):
                agendamento = self.agenda(self.ana, self.rui, self.futuro)
                for usuario in [self.usuario_ze, self.usuario_ana]:
                        with self.subTest(usuario=usuario.username):
                                self.client.force_login(usuario)
                                self.assertIn('não tem permissão para concluir', self.mensagens(self.conclui(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_nao_conclui_agendamento_cancelado(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro, status='CANCELADO')
                self.client.force_login(self.usuario_ze)
                self.assertIn('não pode ser concluído', self.mensagens(self.conclui(agendamento)))
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'CANCELADO')

        def test_conclusao_exige_post_e_login(self):
                agendamento = self.agenda(self.ana, self.ze, self.futuro)
                url = reverse('ConcluirAgendamento', args=[agendamento.pk])
                self.assertRedirects(self.client.post(url), f"{reverse('login')}?next={url}")
                self.client.force_login(self.usuario_ze)
                self.assertEqual(self.client.get(url).status_code, 405)
                agendamento.refresh_from_db()
                self.assertEqual(agendamento.status, 'AGENDADO')

        def test_botoes_concluir_e_cancelar_nas_telas_do_barbeiro(self):
                futuro = self.agenda(self.ana, self.ze, self.futuro)
                passado = self.agenda(self.bia, self.ze, self.passado)
                self.agenda(self.ana, self.ze, self.futuro, hora=15, status='CONCLUIDO')
                self.client.force_login(self.usuario_ze)
                for nome in ['ConsultaAgendamentos', 'dashboard_barbeiro']:
                        with self.subTest(pagina=nome):
                                response = self.client.get(reverse(nome))
                                self.assertContains(response, reverse('ConcluirAgendamento', args=[futuro.pk]))
                                self.assertContains(response, reverse('ConcluirAgendamento', args=[passado.pk]))
                                self.assertContains(response, 'btn-outline-success', count=2)
                                self.assertContains(response, f'data-url="{reverse("CancelarAgendamento", args=[futuro.pk])}"')
                                self.assertNotContains(response, f'data-url="{reverse("CancelarAgendamento", args=[passado.pk])}"')

        def test_paginas_exibem_modal_de_confirmacao(self):
                self.agenda(self.ana, self.ze, self.futuro)
                self.client.force_login(self.usuario_ana)
                response = self.client.get(reverse('meus_agendamentos'))
                self.assertContains(response, 'id="modalCancelamento"')
                self.assertContains(response, 'data-bs-target="#modalCancelamento"')
                self.assertContains(response, 'csrfmiddlewaretoken')


MEDIA_TESTES = tempfile.mkdtemp()


def imagem_png(nome='corte.png'):
        buffer = io.BytesIO()
        Image.new('RGB', (600, 400), (16, 24, 32)).save(buffer, 'PNG')
        return SimpleUploadedFile(nome, buffer.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=MEDIA_TESTES)
class GaleriaTests(TestCase):
        @classmethod
        def tearDownClass(cls):
                super().tearDownClass()
                shutil.rmtree(MEDIA_TESTES, ignore_errors=True)

        def setUp(self):
                self.usuario_ze = Usuario.objects.create_user('ze', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.ze = Barbeiro.objects.create(usuario=self.usuario_ze, nome='Zé Navalha', telefone='49999990001', especialidade='CABELO')
                outro = Usuario.objects.create_user('rui', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.rui = Barbeiro.objects.create(usuario=outro, nome='Rui', telefone='49999990002', especialidade='BARBA')
                self.cliente = Usuario.objects.create_user('ana', password='senha-forte-123', tipo_usuario='CLIENTE')

        def mensagens(self, response):
                return ' '.join(str(m) for m in get_messages(response.wsgi_request))

        def test_formulario_tem_apenas_foto_e_descricao(self):
                self.assertEqual(list(GaleriaForms().fields), ['foto', 'descricao'])

        def test_barbeiro_publica_foto_vinculada_automaticamente(self):
                self.client.force_login(self.usuario_ze)
                response = self.client.post(reverse('CadastraGaleria'), {
                        'foto': imagem_png(), 'descricao': 'Degradê com risco', 'barbeiro': self.rui.pk,
                })
                self.assertRedirects(response, reverse('ListaGaleria'))
                galeria = Galeria.objects.get()
                self.assertEqual(galeria.barbeiro, self.ze)
                self.assertTrue(galeria.foto.thumb.url.endswith('.thumb.png'))
                self.assertTrue(galeria.foto.storage.exists(galeria.foto.thumb.name))

        def test_cliente_e_barrado_de_publicar(self):
                self.client.force_login(self.cliente)
                response = self.client.post(reverse('CadastraGaleria'), {'foto': imagem_png(), 'descricao': 'Tentativa'})
                self.assertRedirects(response, reverse('dashboard'))
                self.assertIn('exclusiva para barbeiros', self.mensagens(response))
                self.assertFalse(Galeria.objects.exists())

        def test_anonimo_e_barrado_de_publicar(self):
                response = self.client.post(reverse('CadastraGaleria'), {'foto': imagem_png(), 'descricao': 'Tentativa'})
                self.assertRedirects(response, f"{reverse('login')}?next={reverse('CadastraGaleria')}")
                self.assertFalse(Galeria.objects.exists())

        def test_conta_barbeiro_sem_perfil_e_barrada(self):
                sem_perfil = Usuario.objects.create_user('novo', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.client.force_login(sem_perfil)
                response = self.client.post(reverse('CadastraGaleria'), {'foto': imagem_png(), 'descricao': 'Tentativa'})
                self.assertRedirects(response, reverse('dashboard_barbeiro'))
                self.assertIn('não está vinculada', self.mensagens(response))
                self.assertFalse(Galeria.objects.exists())

        def test_galeria_publica_sem_autenticacao(self):
                primeira = Galeria.objects.create(barbeiro=self.ze, foto=imagem_png('a.png'), descricao='Barba desenhada')
                segunda = Galeria.objects.create(barbeiro=self.rui, foto=imagem_png('b.png'), descricao='Corte social')
                Galeria.objects.filter(pk=primeira.pk).update(data=timezone.localdate() - datetime.timedelta(days=5))

                response = self.client.get(reverse('ListaGaleria'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context['galerias']), [segunda, primeira])
                self.assertContains(response, segunda.foto.thumb.url)
                self.assertContains(response, f'data-foto="{segunda.foto.url}"')
                self.assertContains(response, 'Zé Navalha')
                self.assertContains(response, 'Corte social')
                self.assertContains(response, 'id="modalFoto"')

        def test_galeria_vazia(self):
                self.assertContains(self.client.get(reverse('ListaGaleria')), 'Ainda não há fotos publicadas.')

        # Exclusão de fotos
        def publica(self, barbeiro, nome='corte.png'):
                return Galeria.objects.create(barbeiro=barbeiro, foto=imagem_png(nome), descricao=f'Foto de {barbeiro.nome}')

        def exclui(self, galeria):
                return self.client.post(reverse('ExcluiGaleria', args=[galeria.pk]))

        def test_barbeiro_exclui_propria_foto_e_arquivos(self):
                galeria = self.publica(self.ze)
                storage, original, thumb = galeria.foto.storage, galeria.foto.name, galeria.foto.thumb.name
                self.assertTrue(storage.exists(original) and storage.exists(thumb))

                self.client.force_login(self.usuario_ze)
                response = self.exclui(galeria)
                self.assertRedirects(response, reverse('ListaGaleria'))
                self.assertIn('Foto excluída', self.mensagens(response))
                self.assertFalse(Galeria.objects.filter(pk=galeria.pk).exists())
                self.assertFalse(storage.exists(original))
                self.assertFalse(storage.exists(thumb))

        def test_barbeiro_nao_exclui_foto_de_outro(self):
                galeria = self.publica(self.rui)
                self.client.force_login(self.usuario_ze)
                response = self.exclui(galeria)
                self.assertRedirects(response, reverse('ListaGaleria'))
                self.assertIn('Acesso negado', self.mensagens(response))
                self.assertTrue(Galeria.objects.filter(pk=galeria.pk).exists())
                self.assertTrue(galeria.foto.storage.exists(galeria.foto.name))

        def test_gerente_exclui_qualquer_foto(self):
                gerente = Usuario.objects.create_user('chefe', password='senha-forte-123', tipo_usuario='GERENTE')
                fotos = [self.publica(self.ze, 'a.png'), self.publica(self.rui, 'b.png')]
                self.client.force_login(gerente)
                for galeria in fotos:
                        with self.subTest(barbeiro=galeria.barbeiro.nome):
                                self.assertRedirects(self.exclui(galeria), reverse('ListaGaleria'))
                                self.assertFalse(galeria.foto.storage.exists(galeria.foto.name))
                self.assertFalse(Galeria.objects.exists())

        def test_cliente_nao_exclui_foto(self):
                galeria = self.publica(self.ze)
                self.client.force_login(self.cliente)
                response = self.exclui(galeria)
                self.assertRedirects(response, reverse('ListaGaleria'))
                self.assertIn('Acesso negado', self.mensagens(response))
                self.assertTrue(Galeria.objects.filter(pk=galeria.pk).exists())

        def test_visitante_nao_exclui_foto(self):
                galeria = self.publica(self.ze)
                url = reverse('ExcluiGaleria', args=[galeria.pk])
                self.assertRedirects(self.client.post(url), f"{reverse('login')}?next={url}")
                self.assertTrue(Galeria.objects.filter(pk=galeria.pk).exists())

        def test_exclusao_exige_post(self):
                galeria = self.publica(self.ze)
                self.client.force_login(self.usuario_ze)
                self.assertEqual(self.client.get(reverse('ExcluiGaleria', args=[galeria.pk])).status_code, 405)
                self.assertTrue(Galeria.objects.filter(pk=galeria.pk).exists())

        def test_exclusao_exige_csrf(self):
                from django.test import Client
                galeria = self.publica(self.ze)
                cliente_http = Client(enforce_csrf_checks=True)
                cliente_http.force_login(self.usuario_ze)
                self.assertEqual(cliente_http.post(reverse('ExcluiGaleria', args=[galeria.pk])).status_code, 403)
                self.assertTrue(Galeria.objects.filter(pk=galeria.pk).exists())

        def test_exclusao_de_foto_inexistente(self):
                self.client.force_login(self.usuario_ze)
                self.assertEqual(self.client.post(reverse('ExcluiGaleria', args=[999])).status_code, 404)

        def test_botao_excluir_so_para_autor_e_gerente(self):
                minha = self.publica(self.ze, 'a.png')
                alheia = self.publica(self.rui, 'b.png')
                url_minha = reverse('ExcluiGaleria', args=[minha.pk])
                url_alheia = reverse('ExcluiGaleria', args=[alheia.pk])
                gerente = Usuario.objects.create_user('chefe', password='senha-forte-123', tipo_usuario='GERENTE')

                casos = [(None, []), (self.cliente, []), (self.usuario_ze, [url_minha]), (gerente, [url_minha, url_alheia])]
                for usuario, visiveis in casos:
                        with self.subTest(usuario=getattr(usuario, 'username', 'anônimo')):
                                self.client.logout()
                                if usuario:
                                        self.client.force_login(usuario)
                                response = self.client.get(reverse('ListaGaleria'))
                                self.assertContains(response, 'btn-outline-danger', count=len(visiveis))
                                for url in [url_minha, url_alheia]:
                                        if url in visiveis:
                                                self.assertContains(response, f'data-url="{url}"')
                                        else:
                                                self.assertNotContains(response, f'data-url="{url}"')

        def test_modal_de_exclusao_tem_form_post_com_csrf(self):
                self.publica(self.ze)
                self.client.force_login(self.usuario_ze)
                response = self.client.get(reverse('ListaGaleria'))
                self.assertContains(response, 'id="modalExclusao"')
                self.assertContains(response, 'data-bs-target="#modalExclusao"')
                self.assertContains(response, 'method="POST" id="formExclusao"')
                self.assertContains(response, 'csrfmiddlewaretoken')
                self.assertContains(response, 'Sim, excluir')


class GerenteTests(TestCase):
        def setUp(self):
                self.gerente = Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')
                self.usuario_ze = Usuario.objects.create_user('ze', password='senha-forte-123', tipo_usuario='BARBEIRO')
                self.ze = Barbeiro.objects.create(usuario=self.usuario_ze, nome='Zé Navalha', telefone='49999990001', especialidade='CABELO')
                self.novo = {
                        'nome': 'Rui Tesoura', 'telefone': '(49) 98888-0000', 'especialidade': 'BARBA',
                        'username': 'rui', 'password1': 'Navalha#2026', 'password2': 'Navalha#2026',
                }

        def mensagens(self, response):
                return ' '.join(str(m) for m in get_messages(response.wsgi_request))

        def test_painel_gerencial_mostra_visao_administrativa(self):
                self.client.force_login(self.gerente)
                response = self.client.get(reverse('dashboard_gerente'))
                self.assertContains(response, 'Zé Navalha')
                for nome in ['CadastraBarbeiro', 'GerenciaServicos', 'ConsultaClientes']:
                        self.assertContains(response, f'href="{reverse(nome)}"')

        def test_gerente_cadastra_usuario_e_perfil_de_barbeiro_numa_acao(self):
                self.client.force_login(self.gerente)
                response = self.client.post(reverse('CadastraBarbeiro'), self.novo)
                self.assertRedirects(response, reverse('dashboard_gerente'))
                usuario = Usuario.objects.get(username='rui')
                self.assertEqual(usuario.tipo_usuario, 'BARBEIRO')
                self.assertTrue(usuario.check_password('Navalha#2026'))
                self.assertEqual((usuario.barbeiro.nome, usuario.barbeiro.telefone, usuario.barbeiro.especialidade),
                                 ('Rui Tesoura', '49988880000', 'BARBA'))

                self.client.logout()
                login = self.client.post(reverse('login'), {'username': 'rui', 'password': 'Navalha#2026'})
                self.assertRedirects(login, reverse('dashboard_barbeiro'))

        def test_cadastro_de_barbeiro_e_atomico(self):
                with mock.patch.object(Barbeiro.objects, 'create', side_effect=IntegrityError('falha simulada')):
                        with self.assertRaises(IntegrityError):
                                form = CadastroBarbeiroForm(self.novo)
                                self.assertTrue(form.is_valid(), form.errors)
                                form.save()
                self.assertFalse(Usuario.objects.filter(username='rui').exists())

        def test_rejeita_telefone_de_barbeiro_duplicado(self):
                form = CadastroBarbeiroForm({**self.novo, 'telefone': '49999990001'})
                self.assertFalse(form.is_valid())
                self.assertIn('telefone', form.errors)

        def test_barbeiro_nao_cadastra_outros_barbeiros(self):
                self.client.force_login(self.usuario_ze)
                for url in [reverse('CadastraBarbeiro'), reverse('CadastraUsuario')]:
                        with self.subTest(url=url):
                                response = self.client.post(url, {**self.novo, 'tipo_usuario': 'BARBEIRO'})
                                self.assertRedirects(response, reverse('dashboard_barbeiro'))
                                self.assertIn('exclusiva para gerentes', self.mensagens(response))
                self.assertFalse(Usuario.objects.filter(username='rui').exists())
                self.assertEqual(Barbeiro.objects.count(), 1)

        def test_cliente_e_anonimo_nao_acessam_painel_gerencial(self):
                url = reverse('dashboard_gerente')
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
                cliente = Usuario.objects.create_user('ana', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.client.force_login(cliente)
                self.assertRedirects(self.client.get(url), reverse('dashboard'))


class NavbarTests(TestCase):
        def marca(self, response):
                html = response.content.decode()
                inicio = html.index('class="navbar-brand"')
                return html[html.rindex('<a', 0, inicio):html.index('>', inicio)]

        def test_logo_e_inicio_conforme_o_perfil(self):
                casos = [
                        (None, 'index', True),
                        ('CLIENTE', 'dashboard', False),
                        ('BARBEIRO', 'dashboard_barbeiro', False),
                        ('GERENTE', 'dashboard_gerente', False),
                ]
                for tipo, destino, mostra_inicio in casos:
                        with self.subTest(perfil=tipo or 'anônimo'):
                                self.client.logout()
                                if tipo:
                                        usuario = Usuario.objects.create_user(tipo.lower(), password='senha-forte-123', tipo_usuario=tipo)
                                        self.client.force_login(usuario)
                                response = self.client.get(reverse('servicos'))
                                self.assertIn(f'href="{reverse(destino)}"', self.marca(response))
                                link_inicio = f'<a class="nav-link" href="{reverse("index")}">Início</a>'
                                if mostra_inicio:
                                        self.assertContains(response, link_inicio)
                                else:
                                        self.assertNotContains(response, link_inicio)

        def itens_do_menu(self, response):
                html = response.content.decode()
                menu = html[html.index('id="navbarPrincipal"'):html.index('</nav>')]
                return [texto.strip() for texto in re.findall(r'<(?:a|button)[^>]*>([^<]+)</(?:a|button)>', menu)]

        def test_itens_do_menu_por_perfil_com_painel_primeiro(self):
                casos = [
                        (None, ['Início', 'Serviços', 'Galeria', 'Entrar', 'Cadastrar']),
                        ('GERENTE', ['Painel gerencial', 'Cadastrar barbeiro', 'Gerenciar serviços', 'Clientes', 'Galeria', 'Sair']),
                        ('BARBEIRO', ['Painel do barbeiro', 'Atendimentos', 'Publicar foto', 'Galeria', 'Sair']),
                        ('CLIENTE', ['Dashboard', 'Meus agendamentos', 'Serviços', 'Galeria', 'Sair']),
                ]
                for tipo, esperado in casos:
                        with self.subTest(perfil=tipo or 'anônimo'):
                                self.client.logout()
                                if tipo:
                                        self.client.force_login(Usuario.objects.create_user(tipo.lower(), password='senha-forte-123', tipo_usuario=tipo))
                                self.assertEqual(self.itens_do_menu(self.client.get(reverse('ListaGaleria'))), esperado)

        def test_superusuario_ve_menu_de_gerente(self):
                self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@exemplo.com', 'senha-forte-123'))
                self.assertEqual(self.itens_do_menu(self.client.get(reverse('ListaGaleria')))[0], 'Painel gerencial')


class RequisitosSenhaTests(TestCase):
        def setUp(self):
                self.gerente = Usuario.objects.create_user('gerente', password='senha-forte-123', tipo_usuario='GERENTE')

        def verifica_checklist(self, response):
                html = response.content.decode()
                self.assertEqual(html.count('id="requisitosSenha"'), 1)
                for regra, texto in [('tamanho', 'Mínimo de 8 caracteres'), ('numerica', 'Não ser inteiramente numérica'),
                                     ('usuario', 'Não ser similar ao nome de usuário'), ('comum', 'Não ser uma senha comumente utilizada')]:
                        self.assertIn(f'data-regra="{regra}"', html)
                        self.assertIn(texto, html)
                self.assertIn(f'<script src="{static("js/senha.js")}" defer></script>', html)
                self.assertIn("addEventListener('input', atualizar)", open(finders.find('js/senha.js'), encoding='utf-8').read())
                # logo abaixo do campo de senha e antes da confirmação
                self.assertLess(html.index('id="id_password1"'), html.index('id="requisitosSenha"'))
                self.assertLess(html.index('id="requisitosSenha"'), html.index('id="id_password2"'))

        def test_checklist_no_cadastro_de_cliente(self):
                self.verifica_checklist(self.client.get(reverse('CadastraCliente')))

        def test_checklist_no_cadastro_de_barbeiro(self):
                self.client.force_login(self.gerente)
                self.verifica_checklist(self.client.get(reverse('CadastraBarbeiro')))

        def test_servidor_continua_validando_a_senha(self):
                self.client.force_login(self.gerente)
                response = self.client.post(reverse('CadastraBarbeiro'), {
                        'nome': 'Rui', 'telefone': '49988880000', 'especialidade': 'BARBA',
                        'username': 'rui', 'password1': '12345678', 'password2': '12345678'})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Usuario.objects.filter(username='rui').exists())
                self.assertTrue(response.context['form'].errors.get('password2'))


class HorariosDisponiveisTests(TestCase):
        def setUp(self):
                self.dia = timezone.localdate() + datetime.timedelta(days=7)
                self.usuario_ana = Usuario.objects.create_user('ana', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.ana = Cliente.objects.create(usuario=self.usuario_ana, cpf='11111111111', nome='Ana', telefone='49911110000',
                                                  email='ana@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                bia = Usuario.objects.create_user('bia', password='senha-forte-123', tipo_usuario='CLIENTE')
                self.bia = Cliente.objects.create(usuario=bia, cpf='22222222222', nome='Bia', telefone='49922220000',
                                                  email='bia@exemplo.com', faixa_etaria='ADULTO', sexo='FEMININO')
                self.ze = self.cria_barbeiro('ze', 'Zé', '49999990001')
                self.rui = self.cria_barbeiro('rui', 'Rui', '49999990002')
                self.barba = Servico.objects.create(tipo='Barba', duracao=30, preco=Decimal('40.00'))
                self.combo = Servico.objects.create(tipo='Combo', duracao=45, preco=Decimal('60.00'))
                self.client.force_login(self.usuario_ana)

        def cria_barbeiro(self, username, nome, telefone):
                usuario = Usuario.objects.create_user(username, password='senha-forte-123', tipo_usuario='BARBEIRO')
                return Barbeiro.objects.create(usuario=usuario, nome=nome, telefone=telefone, especialidade='CABELO')

        def agenda(self, cliente, barbeiro, servico, hora, minuto=0, status='AGENDADO', data=None):
                return Agendamento.objects.create(cliente=cliente, barbeiro=barbeiro, servico=servico, data_agendamento=data or self.dia,
                                                  horario=datetime.time(hora, minuto), observacao='', valor_total=servico.preco, status=status)

        def consulta(self, barbeiro=None, servico=None, data=None, **extra):
                params = {'barbeiro': (barbeiro or self.ze).pk, 'servico': (servico or self.barba).pk, 'data': (data or self.dia).isoformat(), **extra}
                return self.client.get(reverse('horarios_disponiveis'), params)

        def horarios(self, **kwargs):
                response = self.consulta(**kwargs)
                self.assertEqual(response.status_code, 200, response.content)
                corpo = response.json()
                self.assertEqual(corpo['total'], len(corpo['horarios']))
                return corpo['horarios']

        def test_dia_livre_retorna_toda_a_grade_que_cabe_no_turno(self):
                self.assertEqual(self.horarios(), HORARIOS_DISPONIVEIS)  # 30 min cabe até 11:30 e 21:30
                com_combo = self.horarios(servico=self.combo)            # 45 min não cabe às 11:30 nem às 21:30
                self.assertEqual(com_combo, [h for h in HORARIOS_DISPONIVEIS if h not in ('11:30', '21:30')])

        def test_exclui_horarios_ocupados_do_barbeiro(self):
                self.agenda(self.bia, self.ze, self.combo, 14)  # Zé ocupado 14:00–14:45
                livres = self.horarios()
                self.assertNotIn('14:00', livres)
                self.assertNotIn('14:30', livres)
                self.assertIn('13:30', livres)   # 13:30–14:00 encosta mas não sobrepõe
                self.assertIn('15:00', livres)
                self.assertNotIn('13:30', self.horarios(servico=self.combo))  # 13:30–14:15 sobrepõe pela duração

        def test_exclui_horarios_ocupados_do_proprio_cliente_com_outro_barbeiro(self):
                self.agenda(self.ana, self.rui, self.barba, 10)  # Ana ocupada 10:00–10:30 com o Rui
                livres = self.horarios(barbeiro=self.ze)
                self.assertNotIn('10:00', livres)
                self.assertIn('10:30', livres)
                self.assertNotIn('09:30', self.horarios(barbeiro=self.ze, servico=self.combo))  # 09:30–10:15

        def test_isolamento_entre_barbeiros_e_clientes(self):
                self.agenda(self.bia, self.rui, self.barba, 16)   # outro barbeiro com outra cliente
                self.assertIn('16:00', self.horarios(barbeiro=self.ze))
                self.assertNotIn('16:00', self.horarios(barbeiro=self.rui))

        def test_cancelados_e_concluidos_nao_bloqueiam(self):
                self.agenda(self.bia, self.ze, self.barba, 9, status='CANCELADO')
                self.agenda(self.bia, self.ze, self.barba, 9, 30, status='CONCLUIDO')
                livres = self.horarios()
                self.assertIn('09:00', livres)
                self.assertIn('09:30', livres)

        def test_remove_horarios_que_ja_passaram_hoje(self):
                agora = timezone.make_aware(datetime.datetime.combine(self.dia, datetime.time(14, 10)))
                with mock.patch('django.utils.timezone.localtime', return_value=agora):
                        livres = self.horarios()
                self.assertEqual(livres[0], '14:30')
                self.assertNotIn('14:00', livres)

        def test_data_passada_nao_tem_horarios(self):
                self.assertEqual(self.horarios(data=timezone.localdate() - datetime.timedelta(days=1)), [])

        def test_todos_os_horarios_retornados_sao_aceitos_pelo_formulario(self):
                self.agenda(self.bia, self.ze, self.combo, 14)
                self.agenda(self.ana, self.rui, self.barba, 10)
                livres = self.horarios(servico=self.combo)
                for horario in livres:
                        with self.subTest(horario=horario):
                                form = AgendamentoForms({'barbeiro': self.ze.pk, 'servico': self.combo.pk, 'data_agendamento': self.dia,
                                                         'horario': horario, 'observacao': ''}, cliente=self.ana)
                                self.assertTrue(form.is_valid(), form.errors)
                for horario in set(HORARIOS_DISPONIVEIS) - set(livres):
                        with self.subTest(recusado=horario):
                                form = AgendamentoForms({'barbeiro': self.ze.pk, 'servico': self.combo.pk, 'data_agendamento': self.dia,
                                                         'horario': horario, 'observacao': ''}, cliente=self.ana)
                                self.assertFalse(form.is_valid())

        def test_formulario_continua_barrando_horario_ocupado_mesmo_sem_a_api(self):
                self.agenda(self.bia, self.ze, self.barba, 14)
                response = self.client.post(reverse('CadastraAgendamento'), {
                        'barbeiro': self.ze.pk, 'servico': self.barba.pk, 'data_agendamento': self.dia, 'horario': '14:00', 'observacao': ''})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Zé já tem um atendimento')
                self.assertEqual(Agendamento.objects.count(), 1)

        def test_parametros_invalidos(self):
                for extra in [{'data': '20-11-2026'}, {'data': ''}, {'barbeiro': 'abc'}, {'servico': ''}, {'barbeiro': 9999}]:
                        with self.subTest(**{k: str(v) for k, v in extra.items()}):
                                params = {'barbeiro': self.ze.pk, 'servico': self.barba.pk, 'data': self.dia.isoformat(), **extra}
                                response = self.client.get(reverse('horarios_disponiveis'), params)
                                self.assertEqual(response.status_code, 400)
                                self.assertIn('erro', response.json())
                self.assertEqual(self.client.get(reverse('horarios_disponiveis')).status_code, 400)

        def test_servico_inativo_e_rejeitado(self):
                self.barba.ativo = False
                self.barba.save()
                self.assertEqual(self.consulta().status_code, 400)

        def test_exige_cliente_autenticado(self):
                self.client.logout()
                self.assertEqual(self.consulta().status_code, 401)
                self.client.force_login(self.ze.usuario)
                self.assertEqual(self.consulta().status_code, 403)

        def test_aceita_apenas_get(self):
                self.assertEqual(self.client.post(reverse('horarios_disponiveis')).status_code, 405)

        def test_formulario_de_agendamento_usa_a_api(self):
                response = self.client.get(reverse('CadastraAgendamento'))
                self.assertContains(response, f'data-api-horarios="{reverse("horarios_disponiveis")}"')
                self.assertContains(response, f'<script src="{static("js/agendamento.js")}" defer></script>')
                self.assertNotContains(response, '<script>')
                script = open(finders.find('js/agendamento.js'), encoding='utf-8').read()
                self.assertIn('dataset.apiHorarios', script)
                self.assertIn("addEventListener('change', atualizar)", script)
                self.assertIn('Nenhum horário disponível para esta data', script)
