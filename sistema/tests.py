from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AgenteInmobiliario, Comprador, ContratoVenta, Propiedad


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
