from django.apps import AppConfig


class JobseakerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobseaker'
    def ready(self):
        import jobseaker.signals  # Import signals


