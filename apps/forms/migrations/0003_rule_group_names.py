from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("forms", "0002_spanish_admin_labels")]

    operations = [
        migrations.RenameField("conditionalrule", "group", "group_key"),
        migrations.RenameField("conditionalrule", "combinator", "group_operator"),
        migrations.AlterField(
            "conditionalrule",
            "group_key",
            models.CharField("grupo", max_length=100, null=True, blank=True),
        ),
        migrations.AlterField(
            "conditionalrule",
            "group_operator",
            models.CharField(
                "operador de grupo",
                max_length=3,
                default="AND",
                choices=[("AND", "Todas"), ("OR", "Alguna")],
            ),
        ),
        migrations.AlterModelOptions(
            "conditionalrule",
            {
                "ordering": ["order", "id"],
                "verbose_name": "regla condicional",
                "verbose_name_plural": "reglas condicionales",
            },
        ),
    ]
