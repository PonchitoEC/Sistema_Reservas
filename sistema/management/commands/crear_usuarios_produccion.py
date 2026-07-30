"""
Comando de gestión: crear_usuarios_produccion
=============================================
Crea o actualiza los usuarios de prueba del sistema.
Las contraseñas se leen exclusivamente desde variables de entorno;
si una variable no está definida el usuario se omite con una advertencia.

Variables de entorno requeridas:
    ADMIN_PASSWORD           → contraseña del administrador (cesar)
    AGENTE_PAREDES_PASSWORD  → contraseña de agente_paredes
    AGENTE_TOAPANTA_PASSWORD → contraseña de agente_toapanta
    PONCHITO_PASSWORD        → contraseña del comprador Ponchito

Uso:
    python manage.py crear_usuarios_produccion
"""

import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from sistema.models import AgenteInmobiliario, Comprador


class Command(BaseCommand):
    help = "Crea o actualiza los usuarios de prueba para el entorno de producción."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_or_create_group(self, nombre: str) -> Group:
        group, _ = Group.objects.get_or_create(name=nombre)
        return group

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
        user.set_password(password)
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

    # ------------------------------------------------------------------
    # Handler principal
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n==> Creando / actualizando usuarios de producción...\n"
        ))

        errores = []

        # ── Grupos ──────────────────────────────────────────────────────
        grupo_agente    = self._get_or_create_group("Agente")
        grupo_comprador = self._get_or_create_group("Comprador")

        # ── 1. ADMINISTRADOR ────────────────────────────────────────────
        pwd_admin = os.environ.get("ADMIN_PASSWORD")
        if not pwd_admin:
            errores.append("ADMIN_PASSWORD no definida → usuario 'cesar' omitido.")
        else:
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
        pwd_paredes = os.environ.get("AGENTE_PAREDES_PASSWORD")
        if not pwd_paredes:
            errores.append("AGENTE_PAREDES_PASSWORD no definida → usuario 'agente_paredes' omitido.")
        else:
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
        pwd_toapanta = os.environ.get("AGENTE_TOAPANTA_PASSWORD")
        if not pwd_toapanta:
            errores.append("AGENTE_TOAPANTA_PASSWORD no definida → usuario 'agente_toapanta' omitido.")
        else:
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
        pwd_ponchito = os.environ.get("PONCHITO_PASSWORD")
        if not pwd_ponchito:
            errores.append("PONCHITO_PASSWORD no definida → usuario 'Ponchito' omitido.")
        else:
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

        # ── Resumen ──────────────────────────────────────────────────────
        self.stdout.write("")
        if errores:
            for msg in errores:
                self.stdout.write(self.style.WARNING(f"  [ADVERTENCIA] {msg}"))
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS("==> Usuarios de producción procesados.\n"))
