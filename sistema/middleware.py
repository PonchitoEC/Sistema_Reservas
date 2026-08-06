import uuid

from django.http import HttpResponse

from .models import OperacionOffline


class IdempotenciaOfflineMiddleware:
    """Evita duplicar formularios si una respuesta se perdió antes de sincronizar."""

    METODOS = {'POST', 'PUT', 'PATCH', 'DELETE'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-PWA-Request-ID', '').strip()
        if request.method not in self.METODOS or not request_id:
            return self.get_response(request)

        try:
            identificador = uuid.UUID(request_id)
        except (ValueError, AttributeError):
            return HttpResponse('Identificador de sincronización inválido.', status=400)

        existente = OperacionOffline.objects.filter(request_id=identificador).first()
        if existente:
            mismo_usuario = (
                existente.user_id == (request.user.pk if request.user.is_authenticated else None)
                and existente.session_key == (request.session.session_key or '')
            )
            if not mismo_usuario:
                return HttpResponse('La operación pertenece a otra sesión.', status=403)
            response = HttpResponse(
                bytes(existente.cuerpo_respuesta),
                status=existente.estado_http,
                content_type=existente.content_type or 'text/plain',
            )
            if existente.ubicacion:
                response['Location'] = existente.ubicacion
            response['X-PWA-Replayed'] = '1'
            return response

        response = self.get_response(request)
        content_type = response.get('Content-Type', '')
        aceptada = (
            300 <= response.status_code < 400
            or (response.status_code < 300 and 'application/json' in content_type)
        )
        # Un formulario HTML con status 200 puede contener errores de validación;
        # solo redirects y APIs JSON confirman que la mutación fue aceptada.
        if aceptada and not getattr(response, 'streaming', False):
            cuerpo = bytes(response.content[:65536])
            OperacionOffline.objects.get_or_create(
                request_id=identificador,
                defaults={
                    'user': request.user if request.user.is_authenticated else None,
                    'session_key': request.session.session_key or '',
                    'metodo': request.method,
                    'ruta': request.get_full_path()[:500],
                    'estado_http': response.status_code,
                    'ubicacion': response.get('Location', '')[:500],
                    'content_type': content_type[:100],
                    'cuerpo_respuesta': cuerpo,
                },
            )
            response['X-PWA-Request-ID'] = request_id
            response['X-PWA-Accepted'] = '1'
        return response
