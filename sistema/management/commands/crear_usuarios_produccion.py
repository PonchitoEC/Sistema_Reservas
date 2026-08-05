"""
Comando de gestión: crear_usuarios_produccion
=============================================
Crea o actualiza los usuarios y datos demostrativos del sistema.
Las contraseñas solo se leen desde variables de entorno. La ausencia de una
contraseña no impide crear los registros demostrativos: las cuentas nuevas
quedan sin acceso hasta configurar la variable correspondiente.

Variables de entorno requeridas:
    ADMIN_PASSWORD           → contraseña del administrador (cesar)
    AGENTE_PAREDES_PASSWORD  → contraseña de agente_paredes
    AGENTE_TOAPANTA_PASSWORD → contraseña de agente_toapanta
    PONCHITO_PASSWORD        → contraseña del comprador Ponchito
    AGENTE_SALAZAR_PASSWORD  → contraseña de agente_salazar (opcional)
    COMPRADOR_ANA_PASSWORD   → contraseña de comprador_ana (opcional)
    COMPRADOR_LUIS_PASSWORD  → contraseña de comprador_luis (opcional)

Uso:
    python manage.py crear_usuarios_produccion
"""

import os
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from sistema.models import AgenteInmobiliario, Comprador, ContratoVenta, Propiedad, Visita


class Command(BaseCommand):
    help = "Crea o actualiza los usuarios de prueba para el entorno de producción."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_or_create_group(self, nombre: str) -> Group:
        group, _ = Group.objects.get_or_create(name=nombre)
        return group

    def _password(self, variable: str) -> str:
        return os.environ.get(variable, "")

    def _upsert_user(self, username, email, password, first_name="", last_name="",
                     is_staff=False, is_superuser=False) -> tuple[User, bool]:
        """
        Crea el usuario si no existe; si existe actualiza email, nombre y contraseña.
        Devuelve (user, created).
        """
        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        if password:
            user.set_password(password)
        elif created:
            user.set_unusable_password()
        user.save()
        return user, created

    def _upsert_agente(self, user: User, cedula: str, telefono: str,
                       comision: float) -> tuple[AgenteInmobiliario, bool]:
        agente, created = AgenteInmobiliario.objects.get_or_create(
            user=user,
            defaults={
                "cedula": cedula,
                "telefono": telefono,
                "comision_pct": comision,
                "estado": "activo",
            },
        )
        if not created:
            agente.cedula = cedula
            agente.telefono = telefono
            agente.comision_pct = comision
            agente.estado = "activo"
            agente.save()
        return agente, created

    def _upsert_comprador(self, user: User, cedula: str,
                          telefono: str) -> tuple[Comprador, bool]:
        comprador, created = Comprador.objects.get_or_create(
            user=user,
            defaults={
                "cedula": cedula,
                "telefono": telefono,
                "estado": "activo",
            },
        )
        if not created:
            comprador.cedula = cedula
            comprador.telefono = telefono
            comprador.estado = "activo"
            comprador.save()
        return comprador, created

    def _log(self, label: str, username: str, created: bool):
        accion = "creado" if created else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(f"  [{accion.upper()}] {label}: {username}")
        )

    def _cargar_datos_operativos(self):
        """Crea datos enlazados para dashboard, calendario, rutas y reportes."""
        agentes = {
            a.user.username: a
            for a in AgenteInmobiliario.objects.select_related("user").filter(
                user__username__in=["agente_paredes", "agente_toapanta", "agente_salazar"]
            )
        }
        compradores = {
            c.user.username: c
            for c in Comprador.objects.select_related("user").filter(
                user__username__in=["Ponchito", "comprador_ana", "comprador_luis"]
            )
        }
        if len(agentes) < 3 or len(compradores) < 3:
            self.stdout.write(self.style.WARNING(
                "  [ADVERTENCIA] Datos operativos omitidos: se requieren los 3 agentes y 3 compradores."
            ))
            return

        asignaciones = {
            "Ponchito": agentes["agente_paredes"],
            "comprador_ana": agentes["agente_salazar"],
            "comprador_luis": agentes["agente_toapanta"],
        }
        for username, comprador in compradores.items():
            comprador.agente = asignaciones[username]
            comprador.presupuesto_max = Decimal("220000.00")
            comprador.estado = "activo"
            comprador.save(update_fields=["agente", "presupuesto_max", "estado"])

        propiedades_data = [
            ("Casa moderna en La Armenia", "casa", "145000.00", "180.00", "Quito", "La Armenia", agentes["agente_paredes"]),
            ("Departamento en La Carolina", "departamento", "118000.00", "96.00", "Quito", "La Carolina", agentes["agente_paredes"]),
            ("Terreno residencial en Tumbaco", "terreno", "89000.00", "420.00", "Quito", "Tumbaco", agentes["agente_toapanta"]),
            ("Casa familiar en Cumbayá", "casa", "210000.00", "235.00", "Quito", "Cumbayá", agentes["agente_toapanta"]),
            ("Oficina equipada en Iñaquito", "oficina", "97000.00", "75.00", "Quito", "Iñaquito", agentes["agente_salazar"]),
            ("Local comercial en El Bosque", "local_comercial", "132000.00", "110.00", "Quito", "El Bosque", agentes["agente_salazar"]),
        ]
        propiedades = {}
        for indice, (titulo, tipo, precio, area, ciudad, sector, agente) in enumerate(propiedades_data, 1):
            propiedad, _ = Propiedad.objects.update_or_create(
                titulo=titulo,
                defaults={
                    "tipo": tipo,
                    "descripcion": "Propiedad demostrativa con información completa para probar el sistema.",
                    "precio": Decimal(precio), "area_m2": Decimal(area),
                    "dormitorios": 0 if tipo in {"terreno", "oficina", "local_comercial"} else 3,
                    "banos": 1 if tipo in {"terreno", "oficina", "local_comercial"} else 2,
                    "parqueaderos": 2, "direccion": f"Dirección demostrativa #{indice}",
                    "ciudad": ciudad, "sector": sector, "estado": "disponible",
                    "agente": agente,
                },
            )
            propiedades[titulo] = propiedad

        hoy = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
        visitas_data = [
            ("VISITA-DEMO-01", "Casa moderna en La Armenia", "Ponchito", "agente_paredes", 0, 0, "confirmada", 1),
            ("VISITA-DEMO-02", "Departamento en La Carolina", "comprador_ana", "agente_paredes", 0, 2, "pendiente", 2),
            ("VISITA-DEMO-03", "Terreno residencial en Tumbaco", "comprador_luis", "agente_toapanta", 0, 5, "confirmada", 3),
            ("VISITA-DEMO-04", "Casa familiar en Cumbayá", "Ponchito", "agente_toapanta", -12, 1, "realizada", 1),
            ("VISITA-DEMO-05", "Oficina equipada en Iñaquito", "comprador_ana", "agente_salazar", -8, 3, "realizada", 1),
            ("VISITA-DEMO-06", "Local comercial en El Bosque", "comprador_luis", "agente_salazar", 5, 1, "pendiente", 1),
        ]
        for marca, titulo, comprador_user, agente_user, dias, horas, estado, orden in visitas_data:
            Visita.objects.update_or_create(
                notas=f"[{marca}] Visita cargada para demostración.",
                defaults={
                    "propiedad": propiedades[titulo], "comprador": compradores[comprador_user],
                    "agente": agentes[agente_user],
                    "fecha_hora": hoy + timedelta(days=dias, hours=horas),
                    "duracion_min": 45, "orden_ruta": orden, "estado": estado,
                    "confirmado_por_cliente": estado in {"confirmada", "realizada"},
                },
            )

        contratos_data = [
            ("DEMO-VENTA-001", "Casa familiar en Cumbayá", "Ponchito", "agente_toapanta", "198000.00", "firmado", -5),
            ("DEMO-VENTA-002", "Oficina equipada en Iñaquito", "comprador_ana", "agente_salazar", "93000.00", "en_revision", None),
            ("DEMO-VENTA-003", "Terreno residencial en Tumbaco", "comprador_luis", "agente_toapanta", "85000.00", "borrador", None),
            ("DEMO-VENTA-004", "Departamento en La Carolina", "Ponchito", "agente_paredes", "115000.00", "en_revision", None),
        ]
        for numero, titulo, comprador_user, agente_user, precio, estado, dias_firma in contratos_data:
            agente = agentes[agente_user]
            contrato, _ = ContratoVenta.objects.update_or_create(
                numero_contrato=numero,
                defaults={
                    "propiedad": propiedades[titulo], "comprador": compradores[comprador_user],
                    "agente": agente, "precio_acordado": Decimal(precio),
                    "estado": "borrador", "fecha_firma": None,
                    "observaciones": "Contrato demostrativo generado automáticamente.",
                },
            )
            fecha_firma = timezone.localdate() + timedelta(days=dias_firma) if dias_firma else None
            comision = Decimal(precio) * Decimal(str(agente.comision_pct)) / Decimal("100")
            ContratoVenta.objects.filter(pk=contrato.pk).update(
                estado=estado, fecha_firma=fecha_firma,
                comision_calculada=comision.quantize(Decimal("0.01")),
            )

        # Reflejar los estados finales de los contratos en las propiedades.
        Propiedad.objects.filter(titulo="Casa familiar en Cumbayá").update(estado="vendida")
        Propiedad.objects.filter(titulo="Oficina equipada en Iñaquito").update(estado="reservada")
        Propiedad.objects.filter(titulo="Departamento en La Carolina").update(estado="reservada")
        self.stdout.write(self.style.SUCCESS(
            "  [DATOS DEMO] 6 propiedades, 6 visitas y 4 contratos procesados."
        ))

    # ------------------------------------------------------------------
    # Handler principal
    # ------------------------------------------------------------------

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n==> Creando / actualizando usuarios de producción...\n"
        ))

        # ── Grupos ──────────────────────────────────────────────────────
        grupo_agente    = self._get_or_create_group("Agente")
        grupo_comprador = self._get_or_create_group("Comprador")

        # ── 1. ADMINISTRADOR ────────────────────────────────────────────
        pwd_admin = self._password("ADMIN_PASSWORD")
        user, created = self._upsert_user(
                username="cesar",
                email="cesar.unapucha6741@utc.edu.ec",
                password=pwd_admin,
                first_name="Cesar",
                last_name="Unapucha",
                is_staff=True,
                is_superuser=True,
        )
        # El superusuario no pertenece a ningún grupo de rol
        user.groups.clear()
        self._log("ADMINISTRADOR", "cesar", created)

        # ── 2. AGENTE Marco Paredes ──────────────────────────────────────
        pwd_paredes = self._password("AGENTE_PAREDES_PASSWORD")
        user, created = self._upsert_user(
                username="agente_paredes",
                email="marco.paredes@conexion.ec",
                password=pwd_paredes,
                first_name="Marco",
                last_name="Paredes",
        )
        user.groups.set([grupo_agente])
        self._upsert_agente(user, cedula="0503112345", telefono="0987654321", comision=3.00)
        self._log("AGENTE", "agente_paredes", created)

        # ── 3. AGENTE Verónica Toapanta ──────────────────────────────────
        pwd_toapanta = self._password("AGENTE_TOAPANTA_PASSWORD")
        user, created = self._upsert_user(
                username="agente_toapanta",
                email="veronica.toapanta@conexion.ec",
                password=pwd_toapanta,
                first_name="Verónica",
                last_name="Toapanta",
        )
        user.groups.set([grupo_agente])
        self._upsert_agente(user, cedula="0502998765", telefono="0976543210", comision=4.00)
        self._log("AGENTE", "agente_toapanta", created)

        # ── 4. COMPRADOR César Tenorio (Ponchito) ────────────────────────
        pwd_ponchito = self._password("PONCHITO_PASSWORD")
        user, created = self._upsert_user(
                username="Ponchito",
                email="cesar.unapucha2005@gmail.com",
                password=pwd_ponchito,
                first_name="César",
                last_name="Tenorio",
        )
        user.groups.set([grupo_comprador])
        self._upsert_comprador(user, cedula="0550626741", telefono="0998311869")
        self._log("COMPRADOR", "Ponchito", created)

        # ── Datos adicionales para demostrar listados y asignaciones ────
        usuarios_demo = [
            {
                "label": "AGENTE", "username": "agente_salazar",
                "email": "diego.salazar@conexion.ec", "first_name": "Diego",
                "last_name": "Salazar", "password_env": "AGENTE_SALAZAR_PASSWORD",
                "cedula": "0503456789", "telefono": "0965432109",
                "comision": 3.50, "grupo": grupo_agente,
            },
            {
                "label": "COMPRADOR", "username": "comprador_ana",
                "email": "ana.morales@example.com", "first_name": "Ana",
                "last_name": "Morales", "password_env": "COMPRADOR_ANA_PASSWORD",
                "cedula": "0504567890", "telefono": "0954321098",
                "grupo": grupo_comprador,
            },
            {
                "label": "COMPRADOR", "username": "comprador_luis",
                "email": "luis.herrera@example.com", "first_name": "Luis",
                "last_name": "Herrera", "password_env": "COMPRADOR_LUIS_PASSWORD",
                "cedula": "0505678901", "telefono": "0943210987",
                "grupo": grupo_comprador,
            },
        ]

        for datos in usuarios_demo:
            password = self._password(datos["password_env"])

            user, created = self._upsert_user(
                username=datos["username"], email=datos["email"],
                password=password, first_name=datos["first_name"],
                last_name=datos["last_name"],
            )
            user.groups.set([datos["grupo"]])
            if datos["label"] == "AGENTE":
                self._upsert_agente(
                    user, datos["cedula"], datos["telefono"], datos["comision"]
                )
            else:
                self._upsert_comprador(user, datos["cedula"], datos["telefono"])
            self._log(datos["label"], datos["username"], created)

        self._cargar_datos_operativos()

        # ── Resumen ──────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("==> Usuarios de producción procesados.\n"))
