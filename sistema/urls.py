from django.urls import path
from . import views

urlpatterns = [
    # ── Página pública ───────────────────────────────────
    path('', views.inicio, name='inicio'),

    # ── Autenticación ────────────────────────────────────
    path('login/',    views.vista_login,    name='login'),
    path('logout/',   views.vista_logout,   name='logout'),
    path('registro/', views.vista_registro, name='registro'),

    # ── Dashboard ────────────────────────────────────────
    path('dashboard/', views.dashboard, name='dashboard'),

    # ── Propiedades ──────────────────────────────────────
    path('propiedades/',                views.propiedades_lista,  name='propiedades_lista'),
    path('propiedades/nueva/',          views.propiedad_crear,    name='propiedad_crear'),
    path('propiedades/<int:pk>/editar/', views.propiedad_editar,   name='propiedad_editar'),
    path('propiedades/<int:pk>/eliminar/', views.propiedad_eliminar, name='propiedad_eliminar'),

    # ── Agentes ──────────────────────────────────────────
    path('agentes/',                  views.agentes_lista,   name='agentes_lista'),
    path('agentes/nuevo/',            views.agente_crear,    name='agente_crear'),
    path('agentes/<int:pk>/editar/',  views.agente_editar,   name='agente_editar'),
    path('agentes/<int:pk>/eliminar/', views.agente_eliminar, name='agente_eliminar'),

    # ── Compradores ──────────────────────────────────────
    path('compradores/',                   views.compradores_lista,   name='compradores_lista'),
    path('compradores/<int:pk>/editar/',   views.comprador_editar,    name='comprador_editar'),
    path('compradores/<int:pk>/eliminar/', views.comprador_eliminar,  name='comprador_eliminar'),

    # ── Contratos ────────────────────────────────────────
    path('contratos/',                   views.contratos_lista,   name='contratos_lista'),
    path('contratos/nuevo/',             views.contrato_crear,    name='contrato_crear'),
    path('contratos/<int:pk>/editar/',   views.contrato_editar,   name='contrato_editar'),
    path('contratos/<int:pk>/eliminar/', views.contrato_eliminar, name='contrato_eliminar'),
    path('contratos/<int:pk>/enviar-correo/', views.contrato_enviar_correo, name='contrato_enviar_correo'),
    path('facturas/<int:pk>/pdf/', views.factura_pdf, name='factura_pdf'),

    # ── Calendario de visitas ────────────────────────────
    path('calendario/',                       views.calendario,          name='calendario'),
    path('visitas/api/',                      views.visitas_api,         name='visitas_api'),
    path('visitas/crear/',                    views.visita_crear,        name='visita_crear'),
    path('visitas/<int:pk>/editar/',          views.visita_editar_api,   name='visita_editar_api'),
    path('visitas/<int:pk>/mover/',           views.visita_mover,        name='visita_mover'),
    path('visitas/<int:pk>/eliminar/',        views.visita_eliminar_api, name='visita_eliminar_api'),

    # ── Ruta del día (Etapa 4) ───────────────────────────
    path('ruta/',                             views.ruta_del_dia,        name='ruta_del_dia'),
    path('ruta/reordenar/',                   views.reordenar_ruta,      name='reordenar_ruta'),
    path('visitas/<int:pk>/confirmar/',       views.confirmar_asistencia, name='confirmar_asistencia'),

    # ── Reportes (Etapa 6) ───────────────────────────────
    path('reportes/',                         views.reportes,            name='reportes'),
    path('reportes/api/',                     views.reportes_api,        name='reportes_api'),

    # ── Gestión de Usuarios y Roles (solo administrador) ─
    path('usuarios/',                          views.usuarios_lista,         name='usuarios_lista'),
    path('usuarios/nuevo/',                    views.usuario_crear,          name='usuario_crear'),
    path('usuarios/<int:pk>/editar/',          views.usuario_editar,         name='usuario_editar'),
    path('usuarios/<int:pk>/eliminar/',        views.usuario_eliminar,       name='usuario_eliminar'),
    path('usuarios/<int:pk>/toggle-activo/',   views.usuario_toggle_activo,  name='usuario_toggle_activo'),
]
