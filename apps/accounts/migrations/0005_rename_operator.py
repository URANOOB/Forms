from django.db import migrations


def rename_operator(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias
    old = Group.objects.using(database).filter(name="Visor").first()
    if old is None:
        return
    target = Group.objects.using(database).filter(name="Operador").first()
    if target is None:
        old.name = "Operador"
        old.save(using=database, update_fields=["name"])
        return
    membership = User.groups.through
    membership.objects.using(database).bulk_create(
        [
            membership(user_id=user_id, group_id=target.pk)
            for user_id in membership.objects.using(database)
            .filter(group_id=old.pk)
            .values_list("user_id", flat=True)
        ],
        ignore_conflicts=True,
    )
    grants = Group.permissions.through
    grants.objects.using(database).bulk_create(
        [
            grants(group_id=target.pk, permission_id=permission_id)
            for permission_id in grants.objects.using(database)
            .filter(group_id=old.pk)
            .values_list("permission_id", flat=True)
        ],
        ignore_conflicts=True,
    )
    old.delete(using=database)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_ratelimitbucket")]
    operations = [migrations.RunPython(rename_operator, migrations.RunPython.noop)]
