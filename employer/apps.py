from django.apps import AppConfig

class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'

    def ready(self):
        import signals  # 👈 import signals here

class EmployerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'employer'
