from decimal import Decimal
from datetime import timedelta
import json
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AgenteInmobiliario, Comprador, ContratoVenta, Propiedad, Visita


class PersistenciaSeguraTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_guardado', 'guardado@example.com', 'password123')
        self.client.force_login(self.admin)

    def test_propiedad_invalida_no_produce_error_500_ni_se_guarda(self):
        response = self.client.post(reverse('propiedad_crear'), {
            'titulo': 'Propiedad inválida', 'tipo': 'casa',
            'precio': 'texto', 'area_m2': '100',
            'dormitorios': 'tres', 'banos': '2', 'parqueaderos': '1',
            'direccion': 'Calle prueba', 'ciudad': 'Quito',
            'estado': 'disponible',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Propiedad.objects.filter(titulo='Propiedad inválida').exists())

    def test_agente_duplicado_no_deja_usuario_huerfano(self):
        existente = User.objects.create_user('existente_guardado', password='password123')
        AgenteInmobiliario.objects.create(
            user=existente, cedula='0102030405', telefono='0999999999'
        )
        response = self.client.post(reverse('agente_crear'), {
            'nombre': 'Usuario', 'apellido': 'Temporal',
            'username': 'usuario_temporal', 'email': 'temporal@example.com',
            'password': 'password123', 'cedula': '0102030405',
            'telefono': '0988888888', 'comision_pct': '3', 'estado': 'activo',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='usuario_temporal').exists())

    def test_visita_invalida_no_se_guarda(self):
        response = self.client.post(
            reverse('visita_crear'),
            data=json.dumps({'propiedad': 999999, 'comprador': 999999, 'fecha_hora': 'fecha-mala'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Visita.objects.exists())
        self.assertNotIn('Traceback', response.json()['error'])

    def test_carga_demo_funciona_sin_variables_de_password(self):
        call_command('crear_usuarios_produccion', stdout=StringIO())
        self.assertEqual(AgenteInmobiliario.objects.filter(user__username__startswith='agente_').count(), 3)
        self.assertEqual(Comprador.objects.filter(user__username__in=['Ponchito', 'comprador_ana', 'comprador_luis']).count(), 3)
        self.assertEqual(Propiedad.objects.filter(descripcion__startswith='Propiedad demostrativa').count(), 6)
        self.assertEqual(Visita.objects.filter(notas__startswith='[VISITA-DEMO-').count(), 6)
        self.assertEqual(ContratoVenta.objects.filter(numero_contrato__startswith='DEMO-').count(), 4)
        self.assertEqual(Visita.objects.filter(fecha_hora__date=timezone.localdate()).count(), 3)

    def test_botones_editar_guardan_datos_demo(self):
        call_command('crear_usuarios_produccion', stdout=StringIO())
        propiedad = Propiedad.objects.get(titulo='Casa moderna en La Armenia')
        response = self.client.post(reverse('propiedad_editar', args=[propiedad.pk]), {
            'titulo': propiedad.titulo, 'tipo': propiedad.tipo,
            'descripcion': 'Descripción actualizada desde edición',
            'precio': '146000.00', 'area_m2': '181.00',
            'dormitorios': '3', 'banos': '2', 'parqueaderos': '2',
            'direccion': propiedad.direccion, 'ciudad': propiedad.ciudad,
            'sector': propiedad.sector, 'estado': propiedad.estado,
            'agente': propiedad.agente_id,
        })
        self.assertRedirects(response, reverse('propiedades_lista'))
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.precio, Decimal('146000.00'))

        contrato = ContratoVenta.objects.get(numero_contrato='DEMO-VENTA-004')
        response = self.client.post(reverse('contrato_editar', args=[contrato.pk]), {
            'propiedad': contrato.propiedad_id, 'comprador': contrato.comprador_id,
            'agente': contrato.agente_id, 'precio_acordado': '114500.00',
            'numero_contrato': contrato.numero_contrato, 'estado': 'en_revision',
            'observaciones': 'Edición verificada',
        })
        self.assertRedirects(response, reverse('contratos_lista'))
        contrato.refresh_from_db()
        self.assertEqual(contrato.precio_acordado, Decimal('114500.00'))

        visita = Visita.objects.get(notas__startswith='[VISITA-DEMO-01]')
        response = self.client.put(
            reverse('visita_editar_api', args=[visita.pk]),
            data=json.dumps({
                'propiedad': visita.propiedad_id, 'comprador': visita.comprador_id,
                'agente': visita.agente_id, 'fecha_hora': visita.fecha_hora.isoformat(),
                'duracion_min': 60, 'orden_ruta': 2, 'estado': 'confirmada',
                'notas': visita.notas,
            }), content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        visita.refresh_from_db()
        self.assertEqual(visita.duracion_min, 60)

    def test_contrato_recalcula_propiedad_al_editar_y_eliminar(self):
        call_command('crear_usuarios_produccion', stdout=StringIO())
        contrato = ContratoVenta.objects.get(numero_contrato='DEMO-VENTA-001')
        propiedad = contrato.propiedad
        contrato.estado = 'borrador'
        contrato.save()
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.estado, 'disponible')

        contrato.estado = 'en_revision'
        contrato.save()
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.estado, 'reservada')
        contrato.delete()
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.estado, 'disponible')

    def test_eliminar_objeto_protegido_no_genera_error_500(self):
        call_command('crear_usuarios_produccion', stdout=StringIO())
        contrato = ContratoVenta.objects.get(numero_contrato='DEMO-VENTA-001')
        response = self.client.post(reverse('propiedad_eliminar', args=[contrato.propiedad_id]))
        self.assertRedirects(response, reverse('propiedades_lista'))
        self.assertTrue(Propiedad.objects.filter(pk=contrato.propiedad_id).exists())


class FormulariosYContratosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'password123')
        self.client.force_login(self.admin)

    def test_crear_agente_renderiza_sin_objeto(self):
        response = self.client.get(reverse('agente_crear'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'agente_form.html')

    def test_crear_usuario_renderiza_sin_objeto(self):
        response = self.client.get(reverse('usuario_crear'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'usuario_form.html')

    def test_compradores_lista_renderiza(self):
        response = self.client.get(reverse('compradores_lista'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'compradores_lista.html')

    def test_contrato_save_convierte_precio_string_a_decimal(self):
        usuario = User.objects.create_user('agente', 'agente@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='1234567890',
            telefono='0999999999',
            comision_pct=Decimal('3.50'),
        )
        propietario = User.objects.create_user('propietario', 'propietario@example.com', 'password123')
        propiedad = Propiedad.objects.create(
            titulo='Casa prueba',
            tipo='casa',
            descripcion='test',
            precio=Decimal('100000.00'),
            area_m2=Decimal('120.00'),
            direccion='Calle 123',
            ciudad='Quito',
            sector='Centro',
            estado='disponible',
            agente=agente,
        )
        comprador_user = User.objects.create_user('comprador', 'comprador@example.com', 'password123')
        comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='0987654321',
            telefono='0988888888',
            agente=agente,
        )

        contrato = ContratoVenta(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado='125000.75',
            numero_contrato='CT-001',
            estado='borrador',
        )
        contrato.save()

        contrato.refresh_from_db()
        self.assertEqual(contrato.comision_calculada, Decimal('4375.03'))

    def test_contrato_con_numero_repetido_genera_otro_numero(self):
        usuario = User.objects.create_user('agente3', 'agente3@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='3234567890',
            telefono='0999999997',
            comision_pct=Decimal('3.00'),
        )
        propiedad = Propiedad.objects.create(
            titulo='Terreno repetido',
            tipo='terreno',
            descripcion='terreno de prueba',
            precio=Decimal('30000.00'),
            area_m2=Decimal('150.00'),
            direccion='Calle Repetida',
            ciudad='Ambato',
            sector='Centro',
            estado='disponible',
            agente=agente,
        )
        comprador_user = User.objects.create_user('comprador3', 'comprador3@example.com', 'password123')
        comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='1287654321',
            telefono='0988888886',
            agente=agente,
        )

        ContratoVenta.objects.create(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado=Decimal('28000.00'),
            numero_contrato='CONT-2026-001',
            estado='borrador',
        )

        contrato_nuevo = ContratoVenta.objects.create(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado=Decimal('29000.00'),
            numero_contrato='CONT-2026-001',
            estado='borrador',
        )

        self.assertEqual(contrato_nuevo.numero_contrato, 'CONT-2026-002')

    def test_contrato_con_fecha_firma_como_cadena_no_falla(self):
        usuario = User.objects.create_user('agente4', 'agente4@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='4234567890',
            telefono='0999999996',
            comision_pct=Decimal('3.00'),
        )
        propiedad = Propiedad.objects.create(
            titulo='Fecha firma cadena',
            tipo='departamento',
            descripcion='departamento prueba',
            precio=Decimal('60000.00'),
            area_m2=Decimal('100.00'),
            direccion='Avenida Prueba',
            ciudad='Cuenca',
            sector='Centro',
            estado='disponible',
            agente=agente,
        )
        comprador_user = User.objects.create_user('comprador4', 'comprador4@example.com', 'password123')
        comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='2287654321',
            telefono='0988888885',
            agente=agente,
        )

        contrato = ContratoVenta.objects.create(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado=Decimal('62000.00'),
            numero_contrato='CONT-2026-003',
            estado='firmado',
            fecha_firma='2026-07-31',
        )

        self.assertEqual(contrato.fecha_firma.year, 2026)
        self.assertTrue(contrato.numero_contrato.startswith('CONT-2026-'))

    def test_vendedor_puede_crear_y_ver_solo_sus_propiedades(self):
        grupo_vendedor, _ = Group.objects.get_or_create(name='Vendedor')
        vendedor_user = User.objects.create_user('vendedor1', 'vendedor1@example.com', 'password123')
        vendedor_user.groups.add(grupo_vendedor)
        self.client.force_login(vendedor_user)

        response = self.client.post(reverse('propiedad_crear'), {
            'titulo': 'Casa del vendedor',
            'tipo': 'casa',
            'descripcion': 'Propiedad creada por vendedor',
            'precio': '95000.00',
            'area_m2': '120.00',
            'dormitorios': '3',
            'banos': '2',
            'parqueaderos': '1',
            'direccion': 'Calle Vendedor',
            'ciudad': 'Quito',
            'sector': 'Centro',
            'estado': 'disponible',
        })

        self.assertEqual(response.status_code, 302)
        propiedad = Propiedad.objects.get(titulo='Casa del vendedor')
        self.assertIsNotNone(propiedad.agente)
        self.assertEqual(propiedad.agente.user, vendedor_user)

        response_lista = self.client.get(reverse('propiedades_lista'))
        self.assertContains(response_lista, 'Casa del vendedor')

    def test_contrato_crear_usa_el_agente_de_la_propiedad_si_no_se_envia(self):
        usuario = User.objects.create_user('agente5', 'agente5@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='5234567890',
            telefono='0999999995',
            comision_pct=Decimal('3.00'),
        )
        propiedad = Propiedad.objects.create(
            titulo='Casa para contrato',
            tipo='casa',
            descripcion='propiedad para test',
            precio=Decimal('90000.00'),
            area_m2=Decimal('140.00'),
            direccion='Calle Reserva',
            ciudad='Loja',
            sector='Centro',
            estado='disponible',
            agente=agente,
        )
        comprador_user = User.objects.create_user('comprador5', 'comprador5@example.com', 'password123')
        comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='3187654321',
            telefono='0988888884',
            agente=agente,
        )

        response = self.client.post(reverse('contrato_crear'), {
            'propiedad': propiedad.pk,
            'comprador': comprador.pk,
            'precio_acordado': '88000.00',
            'numero_contrato': 'CONT-2026-010',
            'estado': 'en_revision',
            'observaciones': 'Contrato creado desde flujo principal',
        })

        self.assertEqual(response.status_code, 302)
        contrato = ContratoVenta.objects.get(numero_contrato='CONT-2026-010')
        self.assertEqual(contrato.agente, agente)
        self.assertEqual(contrato.propiedad.estado, 'reservada')

    def test_formulario_contrato_muestra_propiedades_reservadas(self):
        usuario = User.objects.create_user('agente6', 'agente6@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='6234567890',
            telefono='0999999994',
            comision_pct=Decimal('3.00'),
        )
        propiedad = Propiedad.objects.create(
            titulo='Casa en revisión',
            tipo='casa',
            descripcion='propiedad para test',
            precio=Decimal('90000.00'),
            area_m2=Decimal('140.00'),
            direccion='Calle Reserva',
            ciudad='Loja',
            sector='Centro',
            estado='reservada',
            agente=agente,
        )

        response = self.client.get(reverse('contrato_crear'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Casa en revisión')
        self.assertContains(response, 'Reservada')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_contrato_firmado_envia_correo_al_comprador(self):
        usuario = User.objects.create_user('agente2', 'agente2@example.com', 'password123')
        agente = AgenteInmobiliario.objects.create(
            user=usuario,
            cedula='2234567890',
            telefono='0999999998',
            comision_pct=Decimal('3.00'),
        )
        propiedad = Propiedad.objects.create(
            titulo='Terreno prueba',
            tipo='terreno',
            descripcion='terreno de prueba',
            precio=Decimal('50000.00'),
            area_m2=Decimal('200.00'),
            direccion='Avenida Siempre Viva',
            ciudad='Guayaquil',
            sector='Sauces',
            estado='disponible',
            agente=agente,
        )
        comprador_user = User.objects.create_user('comprador2', 'comprador2@example.com', 'password123')
        comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='1987654321',
            telefono='0988888887',
            agente=agente,
        )

        contrato = ContratoVenta.objects.create(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado=Decimal('48000.00'),
            numero_contrato='CT-002',
            estado='firmado',
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [comprador_user.email])
        self.assertIn('Terreno prueba', mail.outbox[0].body)
        self.assertIn('firmado', mail.outbox[0].body.lower())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdministradorFlujoCompletoTests(TestCase):
    """Garantiza que César administre registros de cualquier agente sin cambiar de sesión."""

    def setUp(self):
        self.cesar = User.objects.create_superuser(
            username='cesar',
            email='cesar.unapucha6741@utc.edu.ec',
            password='contraseña-solo-pruebas',
        )
        agente_user = User.objects.create_user('agente_externo', 'externo@example.com')
        self.agente = AgenteInmobiliario.objects.create(
            user=agente_user,
            cedula='0503112345',
            telefono='0999999999',
            comision_pct=Decimal('3.00'),
        )
        comprador_user = User.objects.create_user(
            'comprador_externo', 'comprador@example.com', first_name='Cliente', last_name='Demo'
        )
        self.comprador = Comprador.objects.create(
            user=comprador_user,
            cedula='0550626741',
            telefono='0988888888',
            agente=self.agente,
        )
        self.client.force_login(self.cesar)

    def test_rol_administrador_disponible_en_todas_las_plantillas(self):
        response = self.client.get(reverse('propiedades_lista'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['rol'], 'administrador')
        self.assertContains(response, reverse('propiedad_crear'))
        self.assertContains(response, '/admin/')

    def test_cesar_ejecuta_flujo_de_otro_agente(self):
        response = self.client.post(reverse('propiedad_crear'), {
            'titulo': 'Casa administrada por César',
            'tipo': 'casa',
            'descripcion': 'Prueba del flujo administrativo',
            'precio': '100000.00',
            'area_m2': '120.00',
            'dormitorios': '3',
            'banos': '2',
            'parqueaderos': '1',
            'direccion': 'Dirección de prueba',
            'ciudad': 'Latacunga',
            'sector': 'Centro',
            'estado': 'disponible',
            'agente': self.agente.pk,
        })
        self.assertRedirects(response, reverse('propiedades_lista'))
        propiedad = Propiedad.objects.get(titulo='Casa administrada por César')
        self.assertEqual(propiedad.agente, self.agente)

        fecha = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse('visita_crear'),
            data=json.dumps({
                'propiedad': propiedad.pk,
                'comprador': self.comprador.pk,
                'agente': self.agente.pk,
                'fecha_hora': fecha.isoformat(),
                'duracion_min': 30,
                'orden_ruta': 1,
                'estado': 'pendiente',
                'notas': 'Creada por el administrador',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        visita_id = response.json()['id']

        response = self.client.post(
            reverse('reordenar_ruta'),
            data=json.dumps({'orden': [visita_id]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(
            reverse('confirmar_asistencia', args=[visita_id]),
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['estado'], 'confirmada')

        response = self.client.post(reverse('contrato_crear'), {
            'propiedad': propiedad.pk,
            'comprador': self.comprador.pk,
            'agente': self.agente.pk,
            'precio_acordado': '95000.00',
            'numero_contrato': 'ADMIN-FLUJO-001',
            'estado': 'en_revision',
            'observaciones': 'Creado por César',
        })
        self.assertRedirects(response, reverse('contratos_lista'))
        contrato = ContratoVenta.objects.get(numero_contrato='ADMIN-FLUJO-001')

        response = self.client.post(reverse('contrato_editar', args=[contrato.pk]), {
            'propiedad': propiedad.pk,
            'comprador': self.comprador.pk,
            'agente': self.agente.pk,
            'precio_acordado': '95000.00',
            'numero_contrato': contrato.numero_contrato,
            'estado': 'firmado',
            'fecha_firma': timezone.localdate().isoformat(),
            'observaciones': 'Firmado por César',
        })
        self.assertRedirects(response, reverse('contratos_lista'))
        contrato.refresh_from_db()
        propiedad.refresh_from_db()
        self.assertEqual(contrato.estado, 'firmado')
        self.assertEqual(propiedad.estado, 'vendida')
        self.assertEqual(contrato.comision_calculada, Decimal('2850.00'))
        self.assertEqual(len(mail.outbox), 1)

    def test_cesar_accede_al_panel_admin_y_gestion(self):
        for nombre in (
            'dashboard', 'propiedades_lista', 'propiedad_crear', 'agentes_lista',
            'agente_crear', 'compradores_lista', 'contratos_lista', 'contrato_crear',
            'calendario', 'ruta_del_dia', 'reportes', 'usuarios_lista', 'usuario_crear',
        ):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
