from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("registrations", "0002_periods_cancel_progress")]
    operations = [
        migrations.RemoveField(model_name="registration", name="period"),
        migrations.DeleteModel(name="RegistrationPeriod"),
    ]
