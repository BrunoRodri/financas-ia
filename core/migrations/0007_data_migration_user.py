from django.db import migrations


def assign_to_first_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    if not User.objects.filter(pk=1).exists():
        User.objects.create_superuser(
            pk=1, username='admin', password='admin123', email=''
        )

    for model_name in ['Tag', 'CreditCard', 'RecurringRule', 'Transaction', 'Goal']:
        Model = apps.get_model('core', model_name)
        Model.objects.filter(user__isnull=True).update(user_id=1)

    UserSettings = apps.get_model('core', 'UserSettings')
    UserSettings.objects.filter(user__isnull=True).update(user_id=1)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_add_user_fk'),
    ]

    operations = [
        migrations.RunPython(assign_to_first_user, migrations.RunPython.noop),
    ]
