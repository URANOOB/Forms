from django.contrib import admin
from django.urls import path

from apps.forms.admin import PlatformAdmin

from .models import EmailNotification
from .views import emails, retry_email


@admin.register(EmailNotification)
class EmailNotificationAdmin(PlatformAdmin):
    actions = None

    def has_module_permission(self, request):
        return request.user.has_perm("submissions.view_submission")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        # No default change/add/delete/history endpoints, even for superusers.
        return [
            path(
                "",
                self.admin_site.admin_view(lambda request: emails(self, request)),
                name="notifications_emailnotification_changelist",
            ),
            path(
                "<uuid:notification_id>/retry/",
                self.admin_site.admin_view(retry_email),
                name="notifications_emailnotification_retry",
            ),
        ]
