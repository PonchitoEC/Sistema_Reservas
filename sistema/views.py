from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST, require_http_methods
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncMonth
import json
from .models import AgenteInmobiliario, Comprador, Propiedad, Visita, ContratoVenta
from .decoradores import _obtener_rol as obtener_rol, rol_requerido
from django.views.decorators.http import require_POST


def _parse_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _errores_validacion(exc):
    """Convierte errores de Django/BD en mensajes aptos para el usuario."""
    if isinstance(exc, ValidationError):
        if hasattr(exc, 'message_dict'):
            return [mensaje for mensajes in exc.message_dict.values() for mensaje in mensajes]
        return list(exc.messages)
    return ['No se pudieron guardar los datos. Revisa valores duplicados o inválidos.']


def _validar_modelo(instancia, exclude=None):
    instancia.full_clean(exclude=exclude or [])


def _mostrar_errores_guardado(request, exc):
    for error in _errores_validacion(exc):
        messages.error(request, error)


def _parse_entero_no_negativo(value, campo):
    try:
        numero = int(value or 0)
    except (TypeError, ValueError):
        raise ValidationError({campo: 'Debe ser un número entero.'})
    if numero < 0:
        raise ValidationError({campo: 'No puede ser negativo.'})
    return numero


def _obtener_o_crear_perfil_agente(user):
    if not user.is_authenticated:
        return None

    perfil_existente = getattr(user, 'agente', None)
    if perfil_existente:
        return perfil_existente

    rol = obtener_rol(user)
    if rol not in {'agente', 'vendedor'}:
        return None

    defaults = {
        'telefono': '0000000000',
        'cedula': f'VND{user.pk:06d}',
        'comision_pct': Decimal('0'),
        'estado': 'activo',
    }
    perfil, _ = AgenteInmobiliario.objects.get_or_create(user=user, defaults=defaults)
    return perfil


# ─────────────────────────────────────────────
# PÁGINA DE INICIO PÚBLICA
# ─────────────────────────────────────────────
def inicio(request):
    # Si el usuario ya está autenticado, ir directo al dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'inicio.html')


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────
def vista_login(request):
    # Si ya está autenticado redirige al dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f'Bienvenido, {user.get_full_name() or user.username}.')
            # Redirige a la URL solicitada antes del login o al dashboard
            siguiente = request.GET.get('next', 'dashboard')
            return redirect(siguiente)
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'login.html')


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────
def vista_logout(request):
    logout(request)
    messages.info(request, 'Has cerrado sesión correctamente.')
    return redirect('inicio')


# ─────────────────────────────────────────────
# REGISTRO (solo crea compradores)
# Los agentes los crea el administrador
# ─────────────────────────────────────────────
def vista_registro(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        nombre      = request.POST.get('nombre', '').strip()
        apellido    = request.POST.get('apellido', '').strip()
        username    = request.POST.get('username', '').strip()
        email       = request.POST.get('email', '').strip()
        cedula      = request.POST.get('cedula', '').strip()
        telefono    = request.POST.get('telefono', '').strip()
        password1   = request.POST.get('password1', '')
        password2   = request.POST.get('password2', '')

        # Validaciones
        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'registro.html', {'datos': request.POST})

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Ese nombre de usuario ya está en uso.')
            return render(request, 'registro.html', {'datos': request.POST})

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Ya existe una cuenta con ese correo.')
            return render(request, 'registro.html', {'datos': request.POST})

        if Comprador.objects.filter(cedula=cedula).exists():
            messages.error(request, 'Ya existe una cuenta con esa cédula.')
            return render(request, 'registro.html', {'datos': request.POST})

        if len(password1) < 6:
            messages.error(request, 'La contraseña debe tener al menos 6 caracteres.')
            return render(request, 'registro.html', {'datos': request.POST})

        # Usuario, grupo y perfil constituyen una sola operación: si cualquiera
        # falla, no queda una cuenta incompleta en la base.
        try:
            with transaction.atomic():
                user = User(
                    username=username, email=email,
                    first_name=nombre, last_name=apellido,
                )
                user.set_password(password1)
                _validar_modelo(user)
                user.save()

                comprador = Comprador(user=user, cedula=cedula, telefono=telefono)
                _validar_modelo(comprador)
                comprador.save()

                grupo_comprador, _ = Group.objects.get_or_create(name='Comprador')
                user.groups.add(grupo_comprador)
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
            return render(request, 'registro.html', {'datos': request.POST})

        # Login automático tras registro
        login(request, user)
        messages.success(request, f'¡Cuenta creada! Bienvenido, {nombre}.')
        return redirect('dashboard')

    return render(request, 'registro.html', {'datos': {}})


# ─────────────────────────────────────────────
# DASHBOARD (protegido — requiere login)
# ─────────────────────────────────────────────
@login_required
def dashboard(request):
    user = request.user
    rol  = obtener_rol(user)

    # KPIs según rol
    if rol == 'agente':
        try:
            agente = user.agente
            total_propiedades  = Propiedad.objects.filter(agente=agente).count()
            visitas_pendientes = Visita.objects.filter(agente=agente, estado='pendiente').count()
            total_compradores  = Comprador.objects.filter(agente=agente).count()
            contratos_firmados = ContratoVenta.objects.filter(agente=agente, estado='firmado').count()
            ultimas_visitas    = Visita.objects.filter(agente=agente, estado__in=['pendiente','confirmada']).select_related('propiedad','comprador__user','agente__user').order_by('fecha_hora')[:5]
        except AgenteInmobiliario.DoesNotExist:
            total_propiedades = visitas_pendientes = total_compradores = contratos_firmados = 0
            ultimas_visitas = []
    elif rol == 'comprador':
        try:
            comprador          = user.comprador
            total_propiedades  = Propiedad.objects.filter(estado='disponible').count()
            visitas_pendientes = Visita.objects.filter(comprador=comprador, estado='pendiente').count()
            total_compradores  = 0
            contratos_firmados = ContratoVenta.objects.filter(comprador=comprador, estado='firmado').count()
            ultimas_visitas    = Visita.objects.filter(comprador=comprador).select_related('propiedad','agente__user').order_by('fecha_hora')[:5]
        except Comprador.DoesNotExist:
            total_propiedades = visitas_pendientes = contratos_firmados = 0
            ultimas_visitas = []
    else:  # administrador
        total_propiedades  = Propiedad.objects.count()
        visitas_pendientes = Visita.objects.filter(estado='pendiente').count()
        total_compradores  = Comprador.objects.count()
        contratos_firmados = ContratoVenta.objects.filter(estado='firmado').count()
        ultimas_visitas    = Visita.objects.filter(estado__in=['pendiente','confirmada']).select_related('propiedad','comprador__user','agente__user').order_by('fecha_hora')[:5]

    return render(request, 'dashboard.html', {
        'rol': rol,
        'user': user,
        'total_propiedades':  total_propiedades,
        'visitas_pendientes': visitas_pendientes,
        'total_compradores':  total_compradores,
        'contratos_firmados': contratos_firmados,
        'ultimas_visitas':    ultimas_visitas,
    })



# ═══════════════════════════════════════════════════════════
# PROPIEDADES
# ═══════════════════════════════════════════════════════════

@login_required
def propiedades_lista(request):
    tipo   = request.GET.get('tipo', '')
    estado = request.GET.get('estado', '')
    q      = request.GET.get('q', '')

    qs = Propiedad.objects.select_related('agente__user').all()
    rol = obtener_rol(request.user)
    if rol in {'agente', 'vendedor'}:
        perfil = _obtener_o_crear_perfil_agente(request.user)
        if perfil:
            qs = qs.filter(agente=perfil)

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(titulo__icontains=q) | qs.filter(ciudad__icontains=q) | qs.filter(sector__icontains=q)

    return render(request, 'propiedades_lista.html', {
        'propiedades': qs,
        'tipo_choices': Propiedad.TIPO_CHOICES,
        'estado_choices': Propiedad.ESTADO_CHOICES,
        'filtro_tipo': tipo,
        'filtro_estado': estado,
        'filtro_q': q,
    })


@rol_requerido('administrador', 'agente', 'vendedor')
def propiedad_crear(request):
    rol     = obtener_rol(request.user)
    agentes = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                p = Propiedad()
                _propiedad_desde_post(request, p)
                # Si es agente o vendedor, solo puede crear propiedades asignadas a sí mismo
                if rol in {'agente', 'vendedor'}:
                    perfil = _obtener_o_crear_perfil_agente(request.user)
                    if not perfil:
                        messages.error(request, 'Tu perfil de agente/vendedor no existe.')
                        return redirect('dashboard')
                    p.agente = perfil
                _validar_modelo(p)
                p.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
        else:
            messages.success(request, f'Propiedad "{p.titulo}" creada correctamente.')
            return redirect('propiedades_lista')
    return render(request, 'propiedad_form.html', {
        'accion': 'Crear',
        'agentes': agentes,
        'rol': rol,
        'tipo_choices': Propiedad.TIPO_CHOICES,
        'estado_choices': Propiedad.ESTADO_CHOICES,
    })


@rol_requerido('administrador', 'agente', 'vendedor')
def propiedad_editar(request, pk):
    propiedad = get_object_or_404(Propiedad, pk=pk)
    rol       = obtener_rol(request.user)
    agentes   = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')

    # El agente o vendedor solo puede editar propiedades que le pertenecen
    if rol in {'agente', 'vendedor'}:
        perfil = _obtener_o_crear_perfil_agente(request.user)
        if not perfil:
            messages.error(request, 'Tu perfil de agente/vendedor no existe.')
            return redirect('dashboard')
        if propiedad.agente != perfil:
            messages.error(request, 'No tienes permiso para editar esta propiedad.')
            return redirect('propiedades_lista')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                _propiedad_desde_post(request, propiedad)
                # El agente o vendedor no puede reasignar la propiedad a otro agente
                if rol in {'agente', 'vendedor'}:
                    propiedad.agente = _obtener_o_crear_perfil_agente(request.user)
                _validar_modelo(propiedad)
                propiedad.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
        else:
            messages.success(request, f'Propiedad "{propiedad.titulo}" actualizada.')
            return redirect('propiedades_lista')
    return render(request, 'propiedad_form.html', {
        'accion': 'Editar',
        'propiedad': propiedad,
        'agentes': agentes,
        'rol': rol,
        'tipo_choices': Propiedad.TIPO_CHOICES,
        'estado_choices': Propiedad.ESTADO_CHOICES,
    })


@rol_requerido('administrador')
def propiedad_eliminar(request, pk):
    propiedad = get_object_or_404(Propiedad, pk=pk)
    if request.method == 'POST':
        titulo = propiedad.titulo
        try:
            propiedad.delete()
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la propiedad porque tiene contratos asociados.')
            return redirect('propiedades_lista')
        messages.success(request, f'Propiedad "{titulo}" eliminada.')
        return redirect('propiedades_lista')
    return render(request, 'confirmar_eliminar.html', {
        'objeto': propiedad,
        'titulo': 'Eliminar Propiedad',
        'cancelar_url': reverse('propiedades_lista'),
    })


def _propiedad_desde_post(request, p):
    p.titulo      = request.POST.get('titulo', '').strip()
    p.tipo        = request.POST.get('tipo', '')
    p.descripcion = request.POST.get('descripcion', '').strip()
    p.precio      = request.POST.get('precio', 0) or 0
    p.area_m2     = request.POST.get('area_m2', 0) or 0
    p.dormitorios = _parse_entero_no_negativo(request.POST.get('dormitorios'), 'dormitorios')
    p.banos       = _parse_entero_no_negativo(request.POST.get('banos'), 'banos')
    p.parqueaderos = _parse_entero_no_negativo(request.POST.get('parqueaderos'), 'parqueaderos')
    p.direccion   = request.POST.get('direccion', '').strip()
    p.ciudad      = request.POST.get('ciudad', '').strip()
    p.sector      = request.POST.get('sector', '').strip()
    p.latitud     = request.POST.get('latitud') or None
    p.longitud    = request.POST.get('longitud') or None
    p.estado      = request.POST.get('estado', 'disponible')
    agente_id     = request.POST.get('agente')
    p.agente      = AgenteInmobiliario.objects.filter(pk=agente_id).first() if agente_id else None
    if request.FILES.get('imagen_principal'):
        p.imagen_principal = request.FILES['imagen_principal']


# ═══════════════════════════════════════════════════════════
# AGENTES
# ═══════════════════════════════════════════════════════════

@rol_requerido('administrador')
def agentes_lista(request):
    agentes = AgenteInmobiliario.objects.select_related('user').all()
    return render(request, 'agentes_lista.html', {'agentes': agentes})


@rol_requerido('administrador')
def agente_crear(request):
    if request.method == 'POST':
        # Crear User primero
        username  = request.POST.get('username', '').strip()
        email     = request.POST.get('email', '').strip()
        nombre    = request.POST.get('nombre', '').strip()
        apellido  = request.POST.get('apellido', '').strip()
        password  = request.POST.get('password', '')
        cedula    = request.POST.get('cedula', '').strip()
        telefono  = request.POST.get('telefono', '').strip()
        comision  = request.POST.get('comision_pct', 3.0) or 3.0
        estado    = request.POST.get('estado', 'activo')

        try:
            with transaction.atomic():
                if len(password) < 6:
                    raise ValidationError('La contraseña debe tener al menos 6 caracteres.')
                user = User(
                    username=username, email=email,
                    first_name=nombre, last_name=apellido
                )
                user.set_password(password)
                _validar_modelo(user)
                user.save()

                agente = AgenteInmobiliario(
                    user=user, cedula=cedula, telefono=telefono,
                    comision_pct=comision, estado=estado
                )
                if request.FILES.get('foto'):
                    agente.foto = request.FILES['foto']
                _validar_modelo(agente)
                agente.save()

                grupo, _ = Group.objects.get_or_create(name='Agente')
                user.groups.add(grupo)
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
            return render(request, 'agente_form.html', {
                'accion': 'Crear', 'datos': request.POST, 'agente': None,
            })

        messages.success(request, f'Agente {nombre} {apellido} creado correctamente.')
        return redirect('agentes_lista')

    return render(request, 'agente_form.html', {'accion': 'Crear', 'datos': {}, 'agente': None})


@rol_requerido('administrador')
def agente_editar(request, pk):
    agente = get_object_or_404(AgenteInmobiliario, pk=pk)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                agente.user.first_name = request.POST.get('nombre', '').strip()
                agente.user.last_name  = request.POST.get('apellido', '').strip()
                agente.user.email      = request.POST.get('email', '').strip()
                _validar_modelo(agente.user)
                agente.user.save()
                agente.cedula      = request.POST.get('cedula', '').strip()
                agente.telefono    = request.POST.get('telefono', '').strip()
                agente.comision_pct = request.POST.get('comision_pct', 3.0) or 3.0
                agente.estado      = request.POST.get('estado', 'activo')
                if request.FILES.get('foto'):
                    agente.foto = request.FILES['foto']
                _validar_modelo(agente)
                agente.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
        else:
            messages.success(request, 'Agente actualizado correctamente.')
            return redirect('agentes_lista')

    return render(request, 'agente_form.html', {'accion': 'Editar', 'agente': agente, 'datos': {}})


@rol_requerido('administrador')
def agente_eliminar(request, pk):
    agente = get_object_or_404(AgenteInmobiliario, pk=pk)
    if request.method == 'POST':
        nombre = agente.nombre_completo()
        try:
            agente.user.delete()  # Elimina también el User por CASCADE
        except ProtectedError:
            messages.error(request, 'No se puede eliminar el agente porque tiene contratos asociados.')
            return redirect('agentes_lista')
        messages.success(request, f'Agente {nombre} eliminado.')
        return redirect('agentes_lista')
    return render(request, 'confirmar_eliminar.html', {
        'objeto': agente,
        'titulo': 'Eliminar Agente',
        'cancelar_url': reverse('agentes_lista'),
    })


# ═══════════════════════════════════════════════════════════
# COMPRADORES
# ═══════════════════════════════════════════════════════════

@rol_requerido('administrador', 'agente')
def compradores_lista(request):
    rol  = obtener_rol(request.user)
    qs   = Comprador.objects.select_related('user', 'agente__user').all()
    # El agente solo ve sus compradores asignados
    if rol == 'agente':
        qs = qs.filter(agente=request.user.agente)
    return render(request, 'compradores_lista.html', {'compradores': qs, 'rol': rol})


@rol_requerido('administrador', 'agente')
def comprador_editar(request, pk):
    comprador = get_object_or_404(Comprador, pk=pk)
    rol       = obtener_rol(request.user)
    agentes   = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')

    # El agente solo puede editar compradores asignados a él
    if rol == 'agente':
        try:
            if comprador.agente != request.user.agente:
                messages.error(request, 'No tienes permiso para editar este comprador.')
                return redirect('compradores_lista')
        except AgenteInmobiliario.DoesNotExist:
            messages.error(request, 'Tu perfil de agente no existe.')
            return redirect('dashboard')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                comprador.user.first_name = request.POST.get('nombre', '').strip()
                comprador.user.last_name  = request.POST.get('apellido', '').strip()
                comprador.user.email      = request.POST.get('email', '').strip()
                _validar_modelo(comprador.user)
                comprador.user.save()
                comprador.cedula          = request.POST.get('cedula', '').strip()
                comprador.telefono        = request.POST.get('telefono', '').strip()
                comprador.presupuesto_max = request.POST.get('presupuesto_max') or None
                comprador.estado          = request.POST.get('estado', 'prospecto')
                agente_id                 = request.POST.get('agente')
                comprador.agente = AgenteInmobiliario.objects.filter(pk=agente_id).first() if agente_id else None
                _validar_modelo(comprador)
                comprador.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
        else:
            messages.success(request, 'Comprador actualizado correctamente.')
            return redirect('compradores_lista')

    return render(request, 'comprador_form.html', {
        'accion': 'Editar',
        'comprador': comprador,
        'agentes': agentes,
        'estado_choices': Comprador.ESTADO_CHOICES,
    })


@rol_requerido('administrador')
def comprador_eliminar(request, pk):
    comprador = get_object_or_404(Comprador, pk=pk)
    if request.method == 'POST':
        nombre = comprador.user.get_full_name()
        try:
            comprador.user.delete()
        except ProtectedError:
            messages.error(request, 'No se puede eliminar el comprador porque tiene contratos asociados.')
            return redirect('compradores_lista')
        messages.success(request, f'Comprador {nombre} eliminado.')
        return redirect('compradores_lista')
    return render(request, 'confirmar_eliminar.html', {
        'objeto': comprador,
        'titulo': 'Eliminar Comprador',
        'cancelar_url': reverse('compradores_lista'),
    })


# ═══════════════════════════════════════════════════════════
# CONTRATOS DE VENTA
# ═══════════════════════════════════════════════════════════

@rol_requerido('administrador', 'agente')
def contratos_lista(request):
    rol = obtener_rol(request.user)
    qs  = ContratoVenta.objects.select_related(
        'propiedad', 'comprador__user', 'agente__user'
    ).all()
    if rol == 'agente':
        qs = qs.filter(agente=request.user.agente)
    return render(request, 'contratos_lista.html', {'contratos': qs, 'rol': rol})


@rol_requerido('administrador', 'agente')
def contrato_crear(request):
    propiedades = Propiedad.objects.select_related('agente__user').all().order_by('estado', 'titulo')
    compradores = Comprador.objects.select_related('user').all()
    agentes     = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')

    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad') or None
        comprador_id = request.POST.get('comprador') or None
        agente_id = request.POST.get('agente') or None

        propiedad = Propiedad.objects.filter(pk=propiedad_id).first() if propiedad_id else None
        comprador = Comprador.objects.filter(pk=comprador_id).first() if comprador_id else None
        agente = AgenteInmobiliario.objects.filter(pk=agente_id).first() if agente_id else None
        if not agente and propiedad and propiedad.agente:
            agente = propiedad.agente
        if not agente and getattr(request.user, 'agente', None):
            agente = request.user.agente
        precio = _parse_decimal(request.POST.get('precio_acordado'))

        if not propiedad or not comprador:
            messages.error(request, 'Debes seleccionar una propiedad y un comprador válidos.')
            return render(request, 'contrato_form.html', {
                'accion': 'Crear',
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        if not agente:
            messages.error(request, 'No fue posible asignar un vendedor/agente al contrato. Selecciona uno o asigna la propiedad a un agente.')
            return render(request, 'contrato_form.html', {
                'accion': 'Crear',
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        if precio is None:
            messages.error(request, 'El precio acordado debe ser un valor numérico.')
            return render(request, 'contrato_form.html', {
                'accion': 'Crear',
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        contrato = ContratoVenta(
            propiedad=propiedad,
            comprador=comprador,
            agente=agente,
            precio_acordado=precio,
            numero_contrato=request.POST.get('numero_contrato', '').strip(),
            estado=request.POST.get('estado', 'borrador'),
            fecha_firma=request.POST.get('fecha_firma') or None,
            observaciones=request.POST.get('observaciones', '').strip(),
        )
        if request.FILES.get('documento'):
            contrato.documento = request.FILES['documento']
        try:
            with transaction.atomic():
                contrato._asegurar_numero_contrato()
                _validar_modelo(contrato)
                contrato.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
            return render(request, 'contrato_form.html', {
                'accion': 'Crear',
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })
        messages.success(request, f'Contrato #{contrato.numero_contrato} creado.')
        return redirect('contratos_lista')

    return render(request, 'contrato_form.html', {
        'accion': 'Crear',
        'propiedades': propiedades,
        'compradores': compradores,
        'agentes': agentes,
        'estado_choices': ContratoVenta.ESTADO_CHOICES,
    })


@rol_requerido('administrador', 'agente')
@require_POST
def contrato_enviar_correo(request, pk):
    contrato = get_object_or_404(ContratoVenta, pk=pk)
    try:
        contrato._enviar_notificacion_compra()
        messages.success(request, f'Correo enviado al comprador ({getattr(contrato.comprador.user, "email", "—")}).')
    except Exception:
        messages.error(request, 'Error al intentar enviar el correo. Revisa los registros.')
    return redirect('contratos_lista')


@rol_requerido('administrador', 'agente')
def contrato_editar(request, pk):
    contrato    = get_object_or_404(ContratoVenta, pk=pk)
    propiedades = Propiedad.objects.select_related('agente__user').all().order_by('estado', 'titulo')
    compradores = Comprador.objects.select_related('user').all()
    agentes     = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')

    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad') or None
        comprador_id = request.POST.get('comprador') or None
        agente_id = request.POST.get('agente') or None
        propiedad = Propiedad.objects.filter(pk=propiedad_id).first() if propiedad_id else None
        comprador = Comprador.objects.filter(pk=comprador_id).first() if comprador_id else None
        agente = AgenteInmobiliario.objects.filter(pk=agente_id).first() if agente_id else None
        if not agente and propiedad and propiedad.agente:
            agente = propiedad.agente
        if not agente and getattr(request.user, 'agente', None):
            agente = request.user.agente
        precio = _parse_decimal(request.POST.get('precio_acordado'))

        if not propiedad or not comprador:
            messages.error(request, 'Debes seleccionar una propiedad y un comprador válidos.')
            return render(request, 'contrato_form.html', {
                'accion': 'Editar',
                'contrato': contrato,
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        if not agente:
            messages.error(request, 'No fue posible asignar un vendedor/agente al contrato. Selecciona uno o asigna la propiedad a un agente.')
            return render(request, 'contrato_form.html', {
                'accion': 'Editar',
                'contrato': contrato,
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        if precio is None:
            messages.error(request, 'El precio acordado debe ser un valor numérico.')
            return render(request, 'contrato_form.html', {
                'accion': 'Editar',
                'contrato': contrato,
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })

        contrato.propiedad = propiedad
        contrato.comprador = comprador
        contrato.agente = agente
        contrato.precio_acordado = precio
        contrato.numero_contrato = request.POST.get('numero_contrato', '').strip()
        contrato.estado = request.POST.get('estado', 'borrador')
        contrato.fecha_firma = request.POST.get('fecha_firma') or None
        contrato.observaciones = request.POST.get('observaciones', '').strip()
        if request.FILES.get('documento'):
            contrato.documento = request.FILES['documento']
        try:
            with transaction.atomic():
                contrato._asegurar_numero_contrato()
                _validar_modelo(contrato)
                contrato.save()
        except (ValidationError, IntegrityError, ValueError) as exc:
            _mostrar_errores_guardado(request, exc)
            return render(request, 'contrato_form.html', {
                'accion': 'Editar',
                'contrato': contrato,
                'propiedades': propiedades,
                'compradores': compradores,
                'agentes': agentes,
                'estado_choices': ContratoVenta.ESTADO_CHOICES,
                'datos': request.POST,
            })
        messages.success(request, f'Contrato #{contrato.numero_contrato} actualizado.')
        return redirect('contratos_lista')

    return render(request, 'contrato_form.html', {
        'accion': 'Editar',
        'contrato': contrato,
        'propiedades': propiedades,
        'compradores': compradores,
        'agentes': agentes,
        'estado_choices': ContratoVenta.ESTADO_CHOICES,
    })


@rol_requerido('administrador')
def contrato_eliminar(request, pk):
    contrato = get_object_or_404(ContratoVenta, pk=pk)
    if request.method == 'POST':
        num = contrato.numero_contrato
        contrato.delete()
        messages.success(request, f'Contrato #{num} eliminado.')
        return redirect('contratos_lista')
    return render(request, 'confirmar_eliminar.html', {
        'objeto': contrato,
        'titulo': 'Eliminar Contrato',
        'cancelar_url': reverse('contratos_lista'),
    })

# ═══════════════════════════════════════════════════════════
# CALENDARIO DE VISITAS — FULLCALENDAR
# ═══════════════════════════════════════════════════════════

@login_required
def calendario(request):
    rol       = obtener_rol(request.user)
    agentes   = AgenteInmobiliario.objects.filter(estado='activo').select_related('user')
    propiedades = Propiedad.objects.filter(estado__in=['disponible', 'reservada']).order_by('titulo')
    compradores = Comprador.objects.select_related('user').order_by('user__last_name')

    # Agente solo ve sus datos
    if rol == 'agente':
        try:
            agente      = request.user.agente
            propiedades = propiedades.filter(agente=agente)
            compradores = compradores.filter(agente=agente)
        except AgenteInmobiliario.DoesNotExist:
            pass

    return render(request, 'calendario.html', {
        'rol':          rol,
        'agentes':      agentes,
        'propiedades':  propiedades,
        'compradores':  compradores,
        'estado_choices': Visita.ESTADO_CHOICES,
    })


# ─────────────────────────────────────────────
# API JSON — alimenta FullCalendar
# GET /visitas/api/?start=...&end=...
# ─────────────────────────────────────────────
@login_required
def visitas_api(request):
    rol = obtener_rol(request.user)
    qs  = Visita.objects.select_related(
        'propiedad', 'comprador__user', 'agente__user'
    ).all()

    # Filtrar por rango de fechas que envía FullCalendar
    start = request.GET.get('start')
    end   = request.GET.get('end')
    if start:
        qs = qs.filter(fecha_hora__gte=start)
    if end:
        qs = qs.filter(fecha_hora__lte=end)

    # Filtrar por agente si corresponde
    if rol == 'agente':
        try:
            qs = qs.filter(agente=request.user.agente)
        except AgenteInmobiliario.DoesNotExist:
            qs = qs.none()
    elif rol == 'comprador':
        try:
            qs = qs.filter(comprador=request.user.comprador)
        except Comprador.DoesNotExist:
            qs = qs.none()

    # Colores por estado
    COLORES = {
        'pendiente':  '#3b82f6',
        'confirmada': '#22c55e',
        'realizada':  '#6b7280',
        'cancelada':  '#ef4444',
        'no_asistio': '#f97316',
    }

    eventos = []
    for v in qs:
        from datetime import timedelta
        fin = v.fecha_hora + timedelta(minutes=v.duracion_min)
        eventos.append({
            'id':    v.pk,
            'title': f'{v.propiedad.titulo} — {v.comprador.user.get_full_name()}',
            'start': v.fecha_hora.isoformat(),
            'end':   fin.isoformat(),
            'color': COLORES.get(v.estado, '#3b82f6'),
            'extendedProps': {
                'propiedad':   v.propiedad.pk,
                'propiedad_nombre': v.propiedad.titulo,
                'comprador':   v.comprador.pk,
                'comprador_nombre': v.comprador.user.get_full_name(),
                'agente':      v.agente.pk if v.agente else None,
                'agente_nombre': v.agente.nombre_completo() if v.agente else '',
                'estado':      v.estado,
                'duracion_min': v.duracion_min,
                'orden_ruta':  v.orden_ruta,
                'notas':       v.notas,
                'confirmado_por_cliente': v.confirmado_por_cliente,
            }
        })

    return JsonResponse(eventos, safe=False)


# ─────────────────────────────────────────────
# CREAR VISITA (POST desde modal del calendario)
# ─────────────────────────────────────────────
@login_required
@require_POST
def visita_crear(request):
    rol = obtener_rol(request.user)
    # Los compradores no pueden crear visitas directamente
    if rol == 'comprador':
        return JsonResponse({'ok': False, 'error': 'No tienes permiso para crear visitas.'}, status=403)
    try:
        from django.utils import timezone
        data = json.loads(request.body)

        # Validar que la fecha no sea pasada
        from django.utils.dateparse import parse_datetime
        from zoneinfo import ZoneInfo
        from django.conf import settings as dj_settings
        fecha_hora_raw = data.get('fecha_hora', '')
        fecha_hora_dt  = parse_datetime(fecha_hora_raw)
        if fecha_hora_dt is None:
            return JsonResponse({'ok': False, 'error': 'Fecha y hora no válidas.'}, status=400)

        # El browser envía datetime naive → localizarlo con la zona del proyecto
        if timezone.is_naive(fecha_hora_dt):
            tz = ZoneInfo(dj_settings.TIME_ZONE)
            fecha_hora_dt = fecha_hora_dt.replace(tzinfo=tz)

        if fecha_hora_dt < timezone.now():
            return JsonResponse({
                'ok': False,
                'error': 'No puedes agendar una visita en una fecha u hora pasada.'
            }, status=400)

        visita = Visita(
            propiedad    = get_object_or_404(Propiedad,  pk=data['propiedad']),
            comprador    = get_object_or_404(Comprador,  pk=data['comprador']),
            agente       = AgenteInmobiliario.objects.filter(pk=data.get('agente')).first(),
            fecha_hora   = fecha_hora_dt,
            duracion_min = int(data.get('duracion_min', 30)),
            orden_ruta   = int(data.get('orden_ruta', 1)),
            estado       = data.get('estado', 'pendiente'),
            notas        = data.get('notas', ''),
        )
        _validar_modelo(visita)
        visita.save()
        return JsonResponse({'ok': True, 'id': visita.pk}, status=201)
    except ValidationError as e:
        return JsonResponse({'ok': False, 'error': ' '.join(_errores_validacion(e))}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'No se pudo guardar la visita. Revisa los datos enviados.'}, status=400)


# ─────────────────────────────────────────────
# EDITAR VISITA (PUT desde modal del calendario)
# ─────────────────────────────────────────────
@login_required
@require_http_methods(['PUT'])
def visita_editar_api(request, pk):
    rol    = obtener_rol(request.user)
    visita = get_object_or_404(Visita, pk=pk)

    # Compradores no pueden editar visitas
    if rol == 'comprador':
        return JsonResponse({'ok': False, 'error': 'No tienes permiso para editar visitas.'}, status=403)

    # Agentes solo pueden editar sus propias visitas
    if rol == 'agente':
        try:
            if visita.agente != request.user.agente:
                return JsonResponse({'ok': False, 'error': 'No tienes permiso para editar esta visita.'}, status=403)
        except AgenteInmobiliario.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Tu perfil de agente no existe.'}, status=403)

    try:
        data   = json.loads(request.body)

        visita.propiedad    = get_object_or_404(Propiedad, pk=data['propiedad'])
        visita.comprador    = get_object_or_404(Comprador, pk=data['comprador'])
        visita.agente       = AgenteInmobiliario.objects.filter(pk=data.get('agente')).first()
        visita.fecha_hora   = data['fecha_hora']
        visita.duracion_min = int(data.get('duracion_min', 30))
        visita.orden_ruta   = int(data.get('orden_ruta', 1))
        visita.estado       = data.get('estado', visita.estado)
        visita.notas        = data.get('notas', visita.notas)
        _validar_modelo(visita)
        visita.save()

        return JsonResponse({'ok': True})
    except ValidationError as e:
        return JsonResponse({'ok': False, 'error': ' '.join(_errores_validacion(e))}, status=400)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'No se pudo actualizar la visita. Revisa los datos enviados.'}, status=400)


# ─────────────────────────────────────────────
# ARRASTRAR evento en el calendario (PATCH)
# Actualiza solo fecha_hora cuando se arrastra
# ─────────────────────────────────────────────
@login_required
@require_http_methods(['PATCH'])
def visita_mover(request, pk):
    rol    = obtener_rol(request.user)
    visita = get_object_or_404(Visita, pk=pk)

    # Compradores no pueden mover visitas
    if rol == 'comprador':
        return JsonResponse({'ok': False, 'error': 'No tienes permiso para mover visitas.'}, status=403)

    # Agentes solo pueden mover sus propias visitas
    if rol == 'agente':
        try:
            if visita.agente != request.user.agente:
                return JsonResponse({'ok': False, 'error': 'No tienes permiso para mover esta visita.'}, status=403)
        except AgenteInmobiliario.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Tu perfil de agente no existe.'}, status=403)

    try:
        data   = json.loads(request.body)
        visita.fecha_hora = data['fecha_hora']
        _validar_modelo(visita)
        visita.save(update_fields=['fecha_hora', 'actualizado_en'])
        return JsonResponse({'ok': True})
    except ValidationError as e:
        return JsonResponse({'ok': False, 'error': ' '.join(_errores_validacion(e))}, status=400)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'No se pudo mover la visita. Revisa la fecha enviada.'}, status=400)


# ─────────────────────────────────────────────
# ELIMINAR VISITA (DELETE)
# ─────────────────────────────────────────────
@login_required
@require_http_methods(['DELETE'])
def visita_eliminar_api(request, pk):
    rol    = obtener_rol(request.user)
    visita = get_object_or_404(Visita, pk=pk)

    # Compradores no pueden eliminar visitas
    if rol == 'comprador':
        return JsonResponse({'ok': False, 'error': 'No tienes permiso para eliminar visitas.'}, status=403)

    # Agentes solo pueden eliminar sus propias visitas
    if rol == 'agente':
        try:
            if visita.agente != request.user.agente:
                return JsonResponse({'ok': False, 'error': 'No tienes permiso para eliminar esta visita.'}, status=403)
        except AgenteInmobiliario.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Tu perfil de agente no existe.'}, status=403)

    try:
        visita.delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ═══════════════════════════════════════════════════════════
# ETAPA 4 — RUTA DEL DÍA (jQuery UI sortable)
# ═══════════════════════════════════════════════════════════

@login_required
def ruta_del_dia(request):
    from datetime import date
    rol = obtener_rol(request.user)

    # Fecha seleccionada (por defecto hoy)
    fecha_str = request.GET.get('fecha', date.today().isoformat())
    try:
        from datetime import datetime
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        fecha = date.today()

    # Filtrar visitas del día ordenadas por orden_ruta
    qs = Visita.objects.filter(
        fecha_hora__date=fecha
    ).select_related(
        'propiedad', 'comprador__user', 'agente__user'
    ).order_by('orden_ruta', 'fecha_hora')

    # Agente solo ve las suyas
    if rol == 'agente':
        try:
            qs = qs.filter(agente=request.user.agente)
        except AgenteInmobiliario.DoesNotExist:
            qs = qs.none()
    elif rol == 'comprador':
        try:
            qs = qs.filter(comprador=request.user.comprador)
        except Comprador.DoesNotExist:
            qs = qs.none()

    return render(request, 'ruta_dia.html', {
        'visitas': qs,
        'fecha':   fecha,
        'rol':     rol,
    })


# ─────────────────────────────────────────────
# API: guardar nuevo orden de la ruta (POST JSON)
# Body: { "orden": [id1, id2, id3, ...] }
# ─────────────────────────────────────────────
@login_required
@require_POST
def reordenar_ruta(request):
    rol = obtener_rol(request.user)
    # Los compradores no pueden reordenar la ruta
    if rol == 'comprador':
        return JsonResponse({'ok': False, 'error': 'No tienes permiso para reordenar la ruta.'}, status=403)
    try:
        data  = json.loads(request.body)
        orden = data.get('orden', [])   # lista de PKs en el nuevo orden
        # Si es agente, verificar que todas las visitas a reordenar le pertenecen
        if rol == 'agente':
            try:
                agente = request.user.agente
                for pk in orden:
                    if not Visita.objects.filter(pk=pk, agente=agente).exists():
                        return JsonResponse({'ok': False, 'error': 'No tienes permiso para reordenar estas visitas.'}, status=403)
            except AgenteInmobiliario.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Tu perfil de agente no existe.'}, status=403)
        for pos, pk in enumerate(orden, start=1):
            Visita.objects.filter(pk=pk).update(orden_ruta=pos)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ─────────────────────────────────────────────
# API: confirmar asistencia del cliente (PATCH)
# Usado por Hotkeys-js (tecla C)
# ─────────────────────────────────────────────
@login_required
@require_http_methods(['PATCH'])
def confirmar_asistencia(request, pk):
    rol    = obtener_rol(request.user)
    visita = get_object_or_404(Visita, pk=pk)

    # Compradores no pueden confirmar asistencia de otros — solo la suya propia
    if rol == 'comprador':
        try:
            if visita.comprador != request.user.comprador:
                return JsonResponse({'ok': False, 'error': 'Solo puedes confirmar tu propia asistencia.'}, status=403)
        except Comprador.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Tu perfil de comprador no existe.'}, status=403)

    # Agentes solo pueden confirmar asistencia en sus visitas
    if rol == 'agente':
        try:
            if visita.agente != request.user.agente:
                return JsonResponse({'ok': False, 'error': 'No tienes permiso para confirmar esta visita.'}, status=403)
        except AgenteInmobiliario.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Tu perfil de agente no existe.'}, status=403)

    try:
        visita.confirmado_por_cliente = True
        visita.estado = 'confirmada'
        visita.save(update_fields=['confirmado_por_cliente', 'estado', 'actualizado_en'])
        return JsonResponse({
            'ok':    True,
            'estado': visita.estado,
            'confirmado': visita.confirmado_por_cliente,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ═══════════════════════════════════════════════════════════
# ETAPA 6 — DASHBOARD REPORTES
# ═══════════════════════════════════════════════════════════

from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncMonth


@rol_requerido('administrador', 'agente')
def reportes(request):
    rol = obtener_rol(request.user)
    return render(request, 'reportes.html', {'rol': rol})


# ─────────────────────────────────────────────
# API JSON — datos para los gráficos Chart.js
# GET /reportes/api/?tipo=efectividad|comisiones|visitas_cierre|mensual
# ─────────────────────────────────────────────
@rol_requerido('administrador', 'agente')
def reportes_api(request):
    tipo = request.GET.get('tipo', 'efectividad')
    rol  = obtener_rol(request.user)

    # Si es agente, restringir a su propio perfil
    filtro_agente = {}
    if rol == 'agente':
        try:
            filtro_agente = {'agente': request.user.agente}
        except AgenteInmobiliario.DoesNotExist:
            return JsonResponse({})

    # ── 1. Efectividad por agente ─────────────────────
    if tipo == 'efectividad':
        agentes = AgenteInmobiliario.objects.filter(
            estado='activo', **filtro_agente
        ).select_related('user').annotate(
            total_visitas=Count('visitas', distinct=True),
            visitas_realizadas=Count(
                'visitas',
                filter=Q(visitas__estado='realizada'),
                distinct=True
            ),
            contratos_firmados=Count(
                'contratos',
                filter=Q(contratos__estado='firmado'),
                distinct=True
            ),
        )

        data = []
        for a in agentes:
            tasa = round(
                (a.contratos_firmados / a.visitas_realizadas * 100)
                if a.visitas_realizadas > 0 else 0, 1
            )
            data.append({
                'agente':             a.nombre_completo(),
                'total_visitas':      a.total_visitas,
                'visitas_realizadas': a.visitas_realizadas,
                'contratos_firmados': a.contratos_firmados,
                'tasa_cierre':        tasa,
            })
        return JsonResponse({'data': data})

    # ── 2. Comisiones por agente ──────────────────────
    elif tipo == 'comisiones':
        agentes = AgenteInmobiliario.objects.filter(
            estado='activo', **filtro_agente
        ).select_related('user').annotate(
            total_comision=Sum(
                'contratos__comision_calculada',
                filter=Q(contratos__estado='firmado')
            ),
            num_contratos=Count(
                'contratos',
                filter=Q(contratos__estado='firmado'),
                distinct=True
            ),
        )

        data = []
        for a in agentes:
            data.append({
                'agente':        a.nombre_completo(),
                'comision':      float(a.total_comision or 0),
                'contratos':     a.num_contratos,
                'comision_pct':  float(a.comision_pct),
            })
        return JsonResponse({'data': data})

    # ── 3. Visitas requeridas para cerrar una venta ───
    elif tipo == 'visitas_cierre':
        agentes = AgenteInmobiliario.objects.filter(
            estado='activo', **filtro_agente
        ).select_related('user').annotate(
            visitas_realizadas=Count(
                'visitas',
                filter=Q(visitas__estado='realizada'),
                distinct=True
            ),
            contratos_firmados=Count(
                'contratos',
                filter=Q(contratos__estado='firmado'),
                distinct=True
            ),
        )

        data = []
        for a in agentes:
            visitas_por_cierre = round(
                a.visitas_realizadas / a.contratos_firmados
                if a.contratos_firmados > 0 else a.visitas_realizadas, 1
            )
            data.append({
                'agente':             a.nombre_completo(),
                'visitas_por_cierre': visitas_por_cierre,
                'visitas_realizadas': a.visitas_realizadas,
                'contratos_firmados': a.contratos_firmados,
            })

        # Promedio global
        total_visitas   = sum(d['visitas_realizadas'] for d in data)
        total_contratos = sum(d['contratos_firmados']  for d in data)
        promedio_global = round(
            total_visitas / total_contratos if total_contratos > 0 else 0, 1
        )
        return JsonResponse({'data': data, 'promedio_global': promedio_global})

    # ── 4. Visitas y contratos por mes ────────────────
    elif tipo == 'mensual':
        visitas_mes = (
            Visita.objects
            .filter(**{k.replace('agente', 'agente'): v for k, v in filtro_agente.items()})
            .annotate(mes=TruncMonth('fecha_hora'))
            .values('mes')
            .annotate(total=Count('id'))
            .order_by('mes')
        )
        contratos_mes = (
            ContratoVenta.objects
            .filter(estado='firmado', **filtro_agente)
            .annotate(mes=TruncMonth('fecha_firma'))
            .values('mes')
            .annotate(total=Count('id'))
            .order_by('mes')
        )

        meses_v = {
            item['mes'].strftime('%Y-%m'): item['total']
            for item in visitas_mes if item['mes']
        }
        meses_c = {
            item['mes'].strftime('%Y-%m'): item['total']
            for item in contratos_mes if item['mes']
        }
        # Unir etiquetas
        etiquetas = sorted(set(list(meses_v.keys()) + list(meses_c.keys())))

        return JsonResponse({
            'etiquetas':  etiquetas,
            'visitas':    [meses_v.get(m, 0) for m in etiquetas],
            'contratos':  [meses_c.get(m, 0) for m in etiquetas],
        })

    # ── 5. Resumen general (KPIs texto) ───────────────
    elif tipo == 'resumen':
        total_propiedades  = Propiedad.objects.count()
        total_visitas      = Visita.objects.filter(**filtro_agente).count()
        visitas_realizadas = Visita.objects.filter(
            estado='realizada', **filtro_agente).count()
        contratos_firmados = ContratoVenta.objects.filter(
            estado='firmado', **filtro_agente).count()
        comision_total     = ContratoVenta.objects.filter(
            estado='firmado', **filtro_agente
        ).aggregate(total=Sum('comision_calculada'))['total'] or 0
        tasa_global = round(
            contratos_firmados / visitas_realizadas * 100
            if visitas_realizadas > 0 else 0, 1
        )
        visitas_por_cierre = round(
            visitas_realizadas / contratos_firmados
            if contratos_firmados > 0 else 0, 1
        )
        return JsonResponse({
            'total_propiedades':  total_propiedades,
            'total_visitas':      total_visitas,
            'visitas_realizadas': visitas_realizadas,
            'contratos_firmados': contratos_firmados,
            'comision_total':     float(comision_total),
            'tasa_global':        tasa_global,
            'visitas_por_cierre': visitas_por_cierre,
        })

    return JsonResponse({'error': 'tipo no reconocido'}, status=400)


# ═══════════════════════════════════════════════════════════
# GESTIÓN DE USUARIOS Y ROLES  — solo administrador
# ═══════════════════════════════════════════════════════════

ROLES_DISPONIBLES = [
    ('administrador', 'Administrador'),
    ('Agente',        'Agente'),
    ('Comprador',     'Comprador'),
]


@rol_requerido('administrador')
def usuarios_lista(request):
    q     = request.GET.get('q', '').strip()
    rol_f = request.GET.get('rol', '')

    qs = User.objects.prefetch_related('groups').order_by('last_name', 'first_name')

    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )

    if rol_f == 'administrador':
        qs = qs.filter(is_superuser=True)
    elif rol_f == 'Agente':
        qs = qs.filter(is_superuser=False, groups__name='Agente')
    elif rol_f == 'Comprador':
        qs = qs.filter(is_superuser=False, groups__name='Comprador')
    elif rol_f == 'sin_rol':
        qs = qs.filter(is_superuser=False, groups__isnull=True)

    usuarios = []
    for u in qs:
        usuarios.append({
            'user': u,
            'rol':  obtener_rol(u),
        })

    return render(request, 'usuarios_lista.html', {
        'usuarios':        usuarios,
        'filtro_q':        q,
        'filtro_rol':      rol_f,
        'roles_disponibles': ROLES_DISPONIBLES,
    })


@rol_requerido('administrador')
@transaction.atomic
def usuario_crear(request):
    if request.method == 'POST':
        nombre   = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        username = request.POST.get('username', '').strip()
        email    = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        rol_sel  = request.POST.get('rol', '')
        activo   = request.POST.get('activo', '1') == '1'

        errores = []

        if password1 != password2:
            errores.append('Las contraseñas no coinciden.')
        if len(password1) < 6:
            errores.append('La contraseña debe tener al menos 6 caracteres.')
        if User.objects.filter(username=username).exists():
            errores.append('Ese nombre de usuario ya está en uso.')
        if email and User.objects.filter(email=email).exists():
            errores.append('Ya existe una cuenta con ese correo electrónico.')
        if not rol_sel:
            errores.append('Debes seleccionar un rol.')

        # Validaciones adicionales para perfiles de rol
        cedula   = request.POST.get('cedula', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        if rol_sel == 'Agente':
            if not cedula:
                errores.append('La cédula es obligatoria para crear un agente.')
            elif AgenteInmobiliario.objects.filter(cedula=cedula).exists():
                errores.append('Ya existe un agente con esa cédula.')
        elif rol_sel == 'Comprador':
            if not cedula:
                errores.append('La cédula es obligatoria para crear un comprador.')
            elif Comprador.objects.filter(cedula=cedula).exists():
                errores.append('Ya existe un comprador con esa cédula.')

        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'usuario_form.html', {
                'accion':           'Crear',
                'roles_disponibles': ROLES_DISPONIBLES,
                'rol_actual':        request.POST.get('rol', ''),
                'usuario':           None,
                'val_nombre':        request.POST.get('nombre', ''),
                'val_apellido':      request.POST.get('apellido', ''),
                'val_username':      request.POST.get('username', ''),
                'val_email':         request.POST.get('email', ''),
            })

        # Crear usuario
        is_superuser = rol_sel == 'administrador'
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=nombre,
            last_name=apellido,
        )
        user.is_active    = activo
        user.is_staff     = is_superuser
        user.is_superuser = is_superuser
        _validar_modelo(user)
        user.save()

        # Asignar grupo y crear perfil de rol si corresponde
        if not is_superuser and rol_sel in ('Agente', 'Comprador'):
            grupo, _ = Group.objects.get_or_create(name=rol_sel)
            user.groups.set([grupo])

            # Crear perfil de agente si el rol es Agente
            if rol_sel == 'Agente':
                perfil = AgenteInmobiliario(
                    user=user,
                    cedula=cedula or f'0000{user.pk:06d}',
                    telefono=telefono or '',
                    comision_pct=3.00,
                    estado='activo',
                )
                _validar_modelo(perfil)
                perfil.save()
            # Crear perfil de comprador si el rol es Comprador
            elif rol_sel == 'Comprador':
                perfil = Comprador(
                    user=user,
                    cedula=cedula or f'0000{user.pk:06d}',
                    telefono=telefono or '',
                    estado='prospecto',
                )
                _validar_modelo(perfil)
                perfil.save()

        messages.success(request, f'Usuario {nombre} {apellido} creado correctamente.')
        return redirect('usuarios_lista')

    return render(request, 'usuario_form.html', {
        'accion':           'Crear',
        'roles_disponibles': ROLES_DISPONIBLES,
        'rol_actual':        '',
        'usuario':           None,
        'val_nombre':        '',
        'val_apellido':      '',
        'val_username':      '',
        'val_email':         '',
    })


@rol_requerido('administrador')
@transaction.atomic
def usuario_editar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    rol_actual = obtener_rol(usuario)

    if request.method == 'POST':
        usuario.first_name = request.POST.get('nombre', '').strip()
        usuario.last_name  = request.POST.get('apellido', '').strip()
        nuevo_username     = request.POST.get('username', usuario.username).strip()
        nuevo_email        = request.POST.get('email', '').strip()
        rol_sel            = request.POST.get('rol', rol_actual)
        activo             = request.POST.get('activo', '1') == '1'
        nueva_password     = request.POST.get('password1', '').strip()
        password2          = request.POST.get('password2', '').strip()

        # Validar email único (excluyendo al propio usuario)
        if nuevo_email and User.objects.filter(email=nuevo_email).exclude(pk=pk).exists():
            messages.error(request, 'Ya existe una cuenta con ese correo electrónico.')
            return render(request, 'usuario_form.html', {
                'accion':           'Editar',
                'usuario':           usuario,
                'rol_actual':        request.POST.get('rol', rol_actual),
                'roles_disponibles': ROLES_DISPONIBLES,
                'val_nombre':        request.POST.get('nombre', usuario.first_name),
                'val_apellido':      request.POST.get('apellido', usuario.last_name),
                'val_username':      nuevo_username,
                'val_email':         nuevo_email,
            })

        # Validar contraseña si se quiere cambiar
        if nueva_password:
            if nueva_password != password2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return render(request, 'usuario_form.html', {
                    'accion':           'Editar',
                    'usuario':           usuario,
                    'rol_actual':        request.POST.get('rol', rol_actual),
                    'roles_disponibles': ROLES_DISPONIBLES,
                    'val_nombre':        request.POST.get('nombre', usuario.first_name),
                    'val_apellido':      request.POST.get('apellido', usuario.last_name),
                    'val_username':      nuevo_username,
                    'val_email':         nuevo_email,
                })
            if len(nueva_password) < 6:
                messages.error(request, 'La contraseña debe tener al menos 6 caracteres.')
                return render(request, 'usuario_form.html', {
                    'accion':           'Editar',
                    'usuario':           usuario,
                    'rol_actual':        request.POST.get('rol', rol_actual),
                    'roles_disponibles': ROLES_DISPONIBLES,
                    'val_nombre':        request.POST.get('nombre', usuario.first_name),
                    'val_apellido':      request.POST.get('apellido', usuario.last_name),
                    'val_username':      nuevo_username,
                    'val_email':         nuevo_email,
                })
            usuario.set_password(nueva_password)

        # Validar username único (excluyendo al propio usuario)
        if nuevo_username and User.objects.filter(username=nuevo_username).exclude(pk=pk).exists():
            messages.error(request, 'Ese nombre de usuario ya está en uso por otro usuario.')
            return render(request, 'usuario_form.html', {
                'accion':           'Editar',
                'usuario':           usuario,
                'rol_actual':        request.POST.get('rol', rol_actual),
                'roles_disponibles': ROLES_DISPONIBLES,
                'val_nombre':        request.POST.get('nombre', usuario.first_name),
                'val_apellido':      request.POST.get('apellido', usuario.last_name),
                'val_username':      nuevo_username,
                'val_email':         nuevo_email,
            })

        usuario.username  = nuevo_username
        usuario.email     = nuevo_email
        usuario.is_active = activo

        # Actualizar rol
        is_superuser = rol_sel == 'administrador'
        usuario.is_superuser = is_superuser
        usuario.is_staff     = is_superuser

        _validar_modelo(usuario)
        usuario.save()

        # Actualizar grupos
        if is_superuser:
            usuario.groups.clear()
        elif rol_sel in ('Agente', 'Comprador'):
            grupo, _ = Group.objects.get_or_create(name=rol_sel)
            usuario.groups.set([grupo])
        else:
            usuario.groups.clear()

        messages.success(request, f'Usuario {usuario.get_full_name() or usuario.username} actualizado correctamente.')
        return redirect('usuarios_lista')

    return render(request, 'usuario_form.html', {
        'accion':           'Editar',
        'usuario':           usuario,
        'rol_actual':        rol_actual,
        'roles_disponibles': ROLES_DISPONIBLES,
        'val_nombre':        usuario.first_name,
        'val_apellido':      usuario.last_name,
        'val_username':      usuario.username,
        'val_email':         usuario.email,
    })


@rol_requerido('administrador')
def usuario_eliminar(request, pk):
    usuario = get_object_or_404(User, pk=pk)

    # Proteger: no eliminar al propio administrador logueado
    if usuario == request.user:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('usuarios_lista')

    if request.method == 'POST':
        nombre = usuario.get_full_name() or usuario.username
        usuario.delete()
        messages.success(request, f'Usuario {nombre} eliminado correctamente.')
        return redirect('usuarios_lista')

    return render(request, 'confirmar_eliminar.html', {
        'objeto': usuario,
        'titulo': 'Eliminar Usuario',
        'cancelar_url': reverse('usuarios_lista'),
    })


@rol_requerido('administrador')
def usuario_toggle_activo(request, pk):
    """Activar / desactivar usuario sin eliminarlo (POST rápido)."""
    if request.method == 'POST':
        usuario = get_object_or_404(User, pk=pk)
        if usuario == request.user:
            messages.error(request, 'No puedes desactivar tu propia cuenta.')
        else:
            usuario.is_active = not usuario.is_active
            usuario.save(update_fields=['is_active'])
            estado = 'activado' if usuario.is_active else 'desactivado'
            messages.success(request, f'Usuario {usuario.get_full_name() or usuario.username} {estado}.')
    return redirect('usuarios_lista')
