from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def rol_requerido(*roles_permitidos):
    """
    Decorador que restringe una vista a uno o más roles.
    Uso:
        @rol_requerido('administrador', 'agente')
        def mi_vista(request): ...

    Roles disponibles: 'administrador', 'agente', 'vendedor', 'comprador'
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            rol = _obtener_rol(request.user)

            if rol not in roles_permitidos:
                messages.error(
                    request,
                    'No tienes permiso para acceder a esa sección.'
                )
                return redirect('dashboard')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _obtener_rol(user):
    if user.is_superuser:
        return 'administrador'
    grupos = user.groups.values_list('name', flat=True)
    if 'Agente' in grupos:
        return 'agente'
    if 'Vendedor' in grupos:
        return 'vendedor'
    if 'Comprador' in grupos:
        return 'comprador'
    return 'sin_rol'
