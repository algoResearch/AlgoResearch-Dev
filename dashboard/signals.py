from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Experiment, Project, User, Organization
from django.contrib.auth import get_user_model
User = get_user_model()

@receiver(post_save, sender=Experiment)
def experiment_created(sender, instance, created, **kwargs):
    if created:
        print(f"Experiment {instance.name} was created!")




@receiver(post_save, sender=Project)
def assign_fund_manager_on_funded(sender, instance, **kwargs):
    if instance.status == "Funded":
        fund_manager = User.objects.filter(
            organization_id=instance.org_id,
            position_type="fund_manager"
        ).first()
        
        if fund_manager and fund_manager not in instance.users.all():
            instance.users.add(fund_manager)
            print(f"✅ Automatically assigned {fund_manager.username} to funded project: {instance.name}")
        else:
            print("⚠️ Fund manager already assigned or not found.")
