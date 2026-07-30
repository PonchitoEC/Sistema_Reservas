from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Reemplaza ImageField (requiere Pillow) por FileField en
    AgenteInmobiliario.foto y Propiedad.imagen_principal.
    """

    dependencies = [
        ('sistema', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agenteinmobiliario',
            name='foto',
            field=models.FileField(
                blank=True, null=True, upload_to='agentes/'
            ),
        ),
        migrations.AlterField(
            model_name='propiedad',
            name='imagen_principal',
            field=models.FileField(
                blank=True, null=True, upload_to='propiedades/'
            ),
        ),
    ]
