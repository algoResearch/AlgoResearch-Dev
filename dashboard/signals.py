from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Experiment

@receiver(post_save, sender=Experiment)
def experiment_created(sender, instance, created, **kwargs):
    if created:
        print(f"Experiment {instance.name} was created!")
