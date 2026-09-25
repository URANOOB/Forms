from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("submissions", "0004_submission_attention_submission_attention_note")]

    operations = [
        # Historical files have no reliable upload timestamp. Keep them unknown.
        migrations.AddField(
            model_name="submissionfile",
            name="uploaded_at",
            field=models.DateTimeField(null=True, editable=False),
        ),
        migrations.AlterField(
            model_name="submissionfile",
            name="uploaded_at",
            field=models.DateTimeField(default=timezone.now, null=True, editable=False),
        ),
    ]
