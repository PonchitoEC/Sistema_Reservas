from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import AgenteInmobiliario, Comprador, Propiedad, Visita, ContratoVenta


# ─────────────────────────────────────────────
# Inline para mostrar AgenteInmobiliario dentro del User
# ─────────────────────────────────────────────
class AgenteInline(admin.StackedInline):
    model = AgenteInmobiliario
    can_delete = False
    verbose_name_plural = 'Datos de Agente Inmobiliario'
    extra = 0


class CompradorInline(admin.StackedInline):
    model = Comprador
    can_delete = False
    verbose_name_plural = 'Datos de Comprador'
    extra = 0


# Extender el UserAdmin de Django para mostrar los inlines
class UserAdmin(BaseUserAdmin):
    inlines = [AgenteInline, CompradorInline]


# Volver a registrar User con el UserAdmin extendido
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ─────────────────────────────────────────────
# AGENTE INMOBILIARIO
# ─────────────────────────────────────────────
@admin.register(AgenteInmobiliario)
class AgenteInmobiliarioAdmin(admin.ModelAdmin):
    list_display  = ('nombre_completo', 'cedula', 'telefono', 'comision_pct', 'estado', 'creado_en')
    list_filter   = ('estado',)
    search_fields = ('cedula', 'user__first_name', 'user__last_name', 'user__email')
    list_editable = ('estado',)
    readonly_fields = ('creado_en',)
    fieldsets = (
        ('Usuario del sistema', {
            'fields': ('user',)
        }),
        ('Datos del agente', {
            'fields': ('cedula', 'telefono', 'foto', 'comision_pct', 'estado')
        }),
        ('Auditoría', {
            'fields': ('creado_en',),
            'classes': ('collapse',)
        }),
    )


# ─────────────────────────────────────────────
# COMPRADOR
# ─────────────────────────────────────────────
@admin.register(Comprador)
class CompradorAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'telefono', 'presupuesto_max', 'estado', 'agente', 'creado_en')
    list_filter   = ('estado', 'agente')
    search_fields = ('cedula', 'user__first_name', 'user__last_name', 'user__email')
    list_editable = ('estado',)
    readonly_fields = ('creado_en',)
    autocomplete_fields = ('agente',)
    fieldsets = (
        ('Usuario del sistema', {
            'fields': ('user',)
        }),
        ('Datos del comprador', {
            'fields': ('cedula', 'telefono', 'presupuesto_max', 'estado', 'agente')
        }),
        ('Auditoría', {
            'fields': ('creado_en',),
            'classes': ('collapse',)
        }),
    )


# ─────────────────────────────────────────────
# PROPIEDAD
# ─────────────────────────────────────────────
@admin.register(Propiedad)
class PropiedadAdmin(admin.ModelAdmin):
    list_display  = ('titulo', 'tipo', 'ciudad', 'sector', 'precio', 'area_m2',
                     'dormitorios', 'banos', 'estado', 'agente', 'creado_en')
    list_filter   = ('tipo', 'estado', 'ciudad', 'agente')
    search_fields = ('titulo', 'direccion', 'ciudad', 'sector')
    list_editable = ('estado',)
    readonly_fields = ('creado_en', 'actualizado_en')
    fieldsets = (
        ('Información general', {
            'fields': ('titulo', 'tipo', 'descripcion', 'imagen_principal', 'estado', 'agente')
        }),
        ('Características', {
            'fields': ('precio', 'area_m2', 'dormitorios', 'banos', 'parqueaderos')
        }),
        ('Ubicación', {
            'fields': ('direccion', 'ciudad', 'sector', 'latitud', 'longitud')
        }),
        ('Auditoría', {
            'fields': ('creado_en', 'actualizado_en'),
            'classes': ('collapse',)
        }),
    )


# ─────────────────────────────────────────────
# VISITA
# ─────────────────────────────────────────────
@admin.register(Visita)
class VisitaAdmin(admin.ModelAdmin):
    list_display  = ('propiedad', 'comprador', 'agente', 'fecha_hora',
                     'duracion_min', 'orden_ruta', 'estado', 'confirmado_por_cliente')
    list_filter   = ('estado', 'agente', 'confirmado_por_cliente')
    search_fields = ('propiedad__titulo', 'comprador__user__first_name',
                     'comprador__user__last_name')
    list_editable = ('estado', 'orden_ruta', 'confirmado_por_cliente')
    readonly_fields = ('creado_en', 'actualizado_en')
    date_hierarchy = 'fecha_hora'
    fieldsets = (
        ('Datos de la visita', {
            'fields': ('propiedad', 'comprador', 'agente', 'fecha_hora', 'duracion_min', 'orden_ruta')
        }),
        ('Estado', {
            'fields': ('estado', 'confirmado_por_cliente', 'notas')
        }),
        ('Auditoría', {
            'fields': ('creado_en', 'actualizado_en'),
            'classes': ('collapse',)
        }),
    )


# ─────────────────────────────────────────────
# CONTRATO DE VENTA
# ─────────────────────────────────────────────
@admin.register(ContratoVenta)
class ContratoVentaAdmin(admin.ModelAdmin):
    list_display  = ('numero_contrato', 'propiedad', 'comprador', 'agente',
                     'precio_acordado', 'comision_calculada', 'fecha_firma', 'estado')
    list_filter   = ('estado', 'agente')
    search_fields = ('numero_contrato', 'propiedad__titulo',
                     'comprador__user__first_name', 'comprador__user__last_name')
    readonly_fields = ('comision_calculada', 'creado_en', 'actualizado_en')
    fieldsets = (
        ('Partes del contrato', {
            'fields': ('numero_contrato', 'propiedad', 'comprador', 'agente')
        }),
        ('Condiciones económicas', {
            'fields': ('precio_acordado', 'comision_calculada')
        }),
        ('Estado y documentación', {
            'fields': ('estado', 'fecha_firma', 'documento', 'observaciones')
        }),
        ('Auditoría', {
            'fields': ('creado_en', 'actualizado_en'),
            'classes': ('collapse',)
        }),
    )
