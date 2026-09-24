from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("forms", "0005_formversion_description_formversion_title_and_more")]

    operations = [
        migrations.AddField(
            model_name="form",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True, verbose_name="eliminado el"
            ),
        ),
    ]
