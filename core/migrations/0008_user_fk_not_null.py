from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_data_migration_user'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='tag',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='tags',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
        migrations.AlterField(
            model_name='creditcard',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='credit_cards',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
        migrations.AlterField(
            model_name='recurringrule',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='recurring_rules',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transactions',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
        migrations.AlterField(
            model_name='goal',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='goals',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
        migrations.AlterField(
            model_name='usersettings',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='settings',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuário',
            ),
        ),
    ]
