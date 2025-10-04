from django.apps import AppConfig

class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'

    def ready(self):
        import signals

class EmployerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'employer'   # ✅ must match the folder name
    label = 'employer'  # optional, but ensures uniqueness

    def ready(self):
        import employer.signals  # ✅ correct import