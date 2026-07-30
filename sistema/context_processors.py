from .decoradores import _obtener_rol


def rol_usuario(request):
    """
    Inyecta la variable `rol` en todos los templates.
    Valores posibles: 'administrador', 'agente', 'comprador', 'sin_rol'
    """
    if request.user.is_authenticated:
        return {'rol': _obtener_rol(request.user)}
    return {'rol': 'anonimo'}
