from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("submissions", "0005_submissionfile_uploaded_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="assigned_to",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_submissions", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="submission",
            name="review_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="submission",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SubmissionActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=40)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity", to="submissions.submission")),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="SubmissionNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notes", to="submissions.submission")),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
    ]
