import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import models, IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# AGENTE INMOBILIARIO
# Extiende al User de Django con datos del agente
# ─────────────────────────────────────────────
class AgenteInmobiliario(models.Model):
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
    ]

    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agente')
    telefono    = models.CharField(max_length=20)
    cedula      = models.CharField(max_length=13, unique=True)
    foto        = models.FileField(upload_to='agentes/', null=True, blank=True)
    comision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=3.00,
                                       help_text='Porcentaje de comisión sobre la venta')
    estado      = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='activo')
    creado_en   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Agente Inmobiliario'
        verbose_name_plural = 'Agentes Inmobiliarios'
        ordering = ['user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.cedula}'

    def nombre_completo(self):
        return self.user.get_full_name()


# ─────────────────────────────────────────────
# COMPRADOR
# Persona interesada en adquirir un inmueble
# ─────────────────────────────────────────────
class Comprador(models.Model):
    ESTADO_CHOICES = [
        ('prospecto', 'Prospecto'),
        ('activo', 'Activo'),
        ('cerrado', 'Cerrado'),
        ('inactivo', 'Inactivo'),
    ]

    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='comprador')
    cedula          = models.CharField(max_length=13, unique=True)
    telefono        = models.CharField(max_length=20)
    presupuesto_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                          help_text='Presupuesto máximo en USD')
    estado          = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='prospecto')
    agente          = models.ForeignKey(AgenteInmobiliario, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='compradores',
                                        help_text='Agente asignado a este comprador')
    creado_en       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comprador'
        verbose_name_plural = 'Compradores'
        ordering = ['user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.cedula}'


# ─────────────────────────────────────────────
# PROPIEDAD
# Inmueble disponible para venta o arriendo
# ─────────────────────────────────────────────
class Propiedad(models.Model):
    TIPO_CHOICES = [
        ('casa', 'Casa'),
        ('departamento', 'Departamento'),
        ('terreno', 'Terreno'),
        ('local_comercial', 'Local Comercial'),
        ('oficina', 'Oficina'),
    ]
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('reservada', 'Reservada'),
        ('vendida', 'Vendida'),
        ('no_disponible', 'No Disponible'),
    ]

    titulo          = models.CharField(max_length=200)
    tipo            = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descripcion     = models.TextField(blank=True)
    precio          = models.DecimalField(max_digits=12, decimal_places=2)
    area_m2         = models.DecimalField(max_digits=8, decimal_places=2)
    dormitorios     = models.PositiveSmallIntegerField(default=0)
    banos           = models.PositiveSmallIntegerField(default=0)
    parqueaderos    = models.PositiveSmallIntegerField(default=0)
    direccion       = models.CharField(max_length=300)
    ciudad          = models.CharField(max_length=100)
    sector          = models.CharField(max_length=100, blank=True)
    latitud         = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud        = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    imagen_principal = models.FileField(upload_to='propiedades/', null=True, blank=True)
    estado          = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='disponible')
    agente          = models.ForeignKey(AgenteInmobiliario, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='propiedades',
                                        help_text='Agente captador de la propiedad')
    creado_en       = models.DateTimeField(auto_now_add=True)
    actualizado_en  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Propiedad'
        verbose_name_plural = 'Propiedades'
        ordering = ['-creado_en']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.titulo} (${self.precio:,.2f})'


# ─────────────────────────────────────────────
# VISITA
# Agendamiento de una visita a una propiedad
# ─────────────────────────────────────────────
class Visita(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('realizada', 'Realizada'),
        ('cancelada', 'Cancelada'),
        ('no_asistio', 'No Asistió'),
    ]

    propiedad       = models.ForeignKey(Propiedad, on_delete=models.CASCADE,
                                        related_name='visitas')
    comprador       = models.ForeignKey(Comprador, on_delete=models.CASCADE,
                                        related_name='visitas')
    agente          = models.ForeignKey(AgenteInmobiliario, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='visitas')
    fecha_hora      = models.DateTimeField()
    duracion_min    = models.PositiveSmallIntegerField(default=30,
                                                       help_text='Duración estimada en minutos')
    orden_ruta      = models.PositiveSmallIntegerField(default=1,
                                                       help_text='Posición en la ruta del día')
    estado          = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente')
    notas           = models.TextField(blank=True)
    confirmado_por_cliente = models.BooleanField(default=False)
    creado_en       = models.DateTimeField(auto_now_add=True)
    actualizado_en  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Visita'
        verbose_name_plural = 'Visitas'
        ordering = ['fecha_hora', 'orden_ruta']

    def __str__(self):
        return (f'Visita: {self.propiedad.titulo} — '
                f'{self.comprador.user.get_full_name()} — '
                f'{self.fecha_hora.strftime("%d/%m/%Y %H:%M")}')


# ─────────────────────────────────────────────
# CONTRATO DE VENTA
# Cierre formal de la negociación
# ─────────────────────────────────────────────
class ContratoVenta(models.Model):
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('en_revision', 'En Revisión'),
        ('firmado', 'Firmado'),
        ('anulado', 'Anulado'),
    ]

    propiedad           = models.ForeignKey(Propiedad, on_delete=models.PROTECT,
                                            related_name='contratos')
    comprador           = models.ForeignKey(Comprador, on_delete=models.PROTECT,
                                            related_name='contratos')
    agente              = models.ForeignKey(AgenteInmobiliario, on_delete=models.PROTECT,
                                            related_name='contratos')
    precio_acordado     = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_firma         = models.DateField(null=True, blank=True)
    numero_contrato     = models.CharField(max_length=50, unique=True)
    comision_calculada  = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                              help_text='Comisión en USD calculada al firmar')
    estado              = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='borrador')
    documento           = models.FileField(upload_to='contratos/', null=True, blank=True)
    observaciones       = models.TextField(blank=True)
    creado_en           = models.DateTimeField(auto_now_add=True)
    actualizado_en      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Contrato de Venta'
        verbose_name_plural = 'Contratos de Venta'
        ordering = ['-creado_en']

    def __str__(self):
        return f'Contrato #{self.numero_contrato} — {self.propiedad.titulo}'

    def _generar_numero_contrato(self):
        if isinstance(self.fecha_firma, str):
            try:
                fecha = date.fromisoformat(self.fecha_firma)
            except ValueError:
                fecha = None
        elif isinstance(self.fecha_firma, date):
            fecha = self.fecha_firma
        else:
            fecha = None

        year = fecha.year if fecha else timezone.now().date().year
        prefijo = f'CONT-{year}-'
        contratos = ContratoVenta.objects.filter(numero_contrato__startswith=prefijo)
        max_numero = 0

        for numero in contratos.values_list('numero_contrato', flat=True):
            try:
                suffix = numero[len(prefijo):]
                max_numero = max(max_numero, int(suffix))
            except (TypeError, ValueError):
                continue

        return f'{prefijo}{max_numero + 1:03d}'

    def _asegurar_numero_contrato(self):
        if not self.numero_contrato:
            self.numero_contrato = self._generar_numero_contrato()
            return

        qs = ContratoVenta.objects.filter(numero_contrato=self.numero_contrato)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if qs.exists():
            self.numero_contrato = self._generar_numero_contrato()

    @classmethod
    def _recalcular_estado_propiedad(cls, propiedad):
        if not propiedad:
            return
        contratos = cls.objects.filter(propiedad=propiedad)
        if contratos.filter(estado='firmado').exists():
            propiedad.estado = 'vendida'
        elif contratos.filter(estado='en_revision').exists():
            propiedad.estado = 'reservada'
        else:
            propiedad.estado = 'disponible'
        propiedad.save(update_fields=['estado'])

    def _sincronizar_estado_propiedad(self):
        if getattr(self, 'propiedad_id', None):
            self._recalcular_estado_propiedad(self.propiedad)

    def _enviar_notificacion_compra(self):
        comprador_user = getattr(self.comprador, 'user', None)
        if not comprador_user or not comprador_user.email:
            logger.warning('El comprador no tiene email registrado. usuario=%s contrato=%s', getattr(comprador_user, 'username', None), self.numero_contrato)
            return False

        usa_smtp = settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
        if usa_smtp and (not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD):
            logger.error('SMTP no configurado; no se puede enviar el contrato %s', self.numero_contrato)
            return False

        tipo_propiedad = self.propiedad.get_tipo_display()
        asunto = f'Confirmación de compra: {self.propiedad.titulo}'
        mensaje = (
            f'Estimado/a {comprador_user.get_full_name() or comprador_user.username},\n\n'
            f'El contrato de venta para {self.propiedad.titulo} ({tipo_propiedad}) ha quedado firmado '
            f'y registrado. Ahora este inmueble ya forma parte de su propiedad.\n\n'
            f'Número de contrato: {self.numero_contrato}\n'
            f'Precio acordado: ${self.precio_acordado:,.2f}\n\n'
            'Gracias por confiar en nosotros.\n\n'
            'Equipo de Inmobiliaria'
        )

        try:
            send_mail(
                asunto,
                mensaje,
                settings.DEFAULT_FROM_EMAIL,
                [comprador_user.email],
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception('No se pudo enviar el correo de confirmación al comprador %s', comprador_user.email)
            return False

    def save(self, *args, **kwargs):
        propiedad_anterior_id = None
        if self.pk:
            propiedad_anterior_id = ContratoVenta.objects.filter(pk=self.pk).values_list(
                'propiedad_id', flat=True
            ).first()
        try:
            precio = Decimal(str(self.precio_acordado or 0))
        except (InvalidOperation, TypeError, ValueError):
            precio = Decimal('0')

        self.precio_acordado = precio

        if isinstance(self.fecha_firma, str):
            try:
                self.fecha_firma = date.fromisoformat(self.fecha_firma)
            except ValueError:
                self.fecha_firma = None

        self._asegurar_numero_contrato()

        # Calcula la comisión automáticamente al guardar
        if self.agente:
            try:
                comision_pct = Decimal(str(self.agente.comision_pct or 0))
            except (InvalidOperation, TypeError, ValueError):
                comision_pct = Decimal('0')
            self.comision_calculada = (precio * comision_pct / Decimal('100'))
        else:
            self.comision_calculada = Decimal('0')

        if self.estado == 'firmado' and not self.fecha_firma:
            self.fecha_firma = timezone.now().date()

        was_firmado = False
        if self.pk:
            previous = ContratoVenta.objects.filter(pk=self.pk).values_list('estado', flat=True).first()
            was_firmado = previous == 'firmado'
        else:
            was_firmado = False

        # Intentar guardar, reintentando si hay colisión en el número de contrato
        attempts = 0
        max_attempts = 5
        while True:
            try:
                # El savepoint permite reintentar una colision UNIQUE también
                # cuando la vista se ejecuta dentro de una transacción.
                with transaction.atomic():
                    super().save(*args, **kwargs)
                break
            except IntegrityError as e:
                # Solo reintentar si es por número de contrato duplicado
                msg = str(e).lower()
                if 'unique constraint' in msg or 'unique' in msg or 'numero_contrato' in msg:
                    attempts += 1
                    logger.warning('Colisión UNIQUE al guardar Contrato (intento %s): %s', attempts, e)
                    if attempts >= max_attempts:
                        logger.exception('Máximos reintentos alcanzados al guardar Contrato. Abortar.')
                        raise
                    # regenerar número y reintentar
                    self.numero_contrato = self._generar_numero_contrato()
                    continue
                # Re-raise si no es el caso esperado
                raise

        # Cambiar el estado solo después de que el contrato exista realmente.
        # La vista envuelve ambas escrituras en una misma transacción.
        self._sincronizar_estado_propiedad()
        if propiedad_anterior_id and propiedad_anterior_id != self.propiedad_id:
            propiedad_anterior = Propiedad.objects.filter(pk=propiedad_anterior_id).first()
            self._recalcular_estado_propiedad(propiedad_anterior)

        if self.estado == 'firmado' and not was_firmado:
            # El envío ya captura sus propios errores y no debe impedir el save.
            self._enviar_notificacion_compra()

    def delete(self, *args, **kwargs):
        propiedad = self.propiedad
        resultado = super().delete(*args, **kwargs)
        self._recalcular_estado_propiedad(propiedad)
        return resultado
