from django.apps import AppConfig


class AuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authapi"

    def ready(self):
        import authapi.signals
        return super().ready()