from django.apps import AppConfig
print("Write you secret message here")
class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

def ready(self):
    import dashboard.signals  # Replace with the actual path

class MyAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myapp'

    def ready(self):
        import myapp.signals  # Ensure signals are imported and registered


