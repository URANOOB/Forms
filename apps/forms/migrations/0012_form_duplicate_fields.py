from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("forms", "0011_form_response_summary")]
    operations = [
        migrations.AddField(
            model_name="form",
            name="duplicate_fields",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
