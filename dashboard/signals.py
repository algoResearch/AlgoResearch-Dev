from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Experiment, Project, User, Organization
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models.signals import m2m_changed
from .models import Conversation
from myapp.utils.image_tools import generate_group_photo
User = get_user_model()

@receiver(post_save, sender=Experiment)
def experiment_created(sender, instance, created, **kwargs):
    if created:
        print(f"Experiment {instance.name} was created!")

@receiver(post_save, sender=Conversation)
def create_group_photo(sender, instance, created, **kwargs):
    if created and instance.type == 'group' and not instance.profile_picture:
        # Avoid empty set during initial save — defer to m2m handler if needed
        member_images = [
            member.profile_picture for member in instance.group_members.all()
            if member.profile_picture and hasattr(member.profile_picture, 'file')
        ][:4]

        if member_images:
            image_file = generate_group_photo(member_images)
            if image_file:
                instance.profile_picture.save(image_file.name, image_file, save=True)


@receiver(m2m_changed, sender=Conversation.members_new.through)
def generate_group_photo_on_members_update(sender, instance, action, **kwargs):
    if action == "post_add" and instance.type == 'group' and not instance.profile_picture:
        member_images = [
            member.profile_picture for member in instance.group_members.all()
            if member.profile_picture and hasattr(member.profile_picture, 'file')
        ][:4]

        if member_images:
            image_file = generate_group_photo(member_images)
            if image_file:
                instance.profile_picture.save(image_file.name, image_file, save=True)

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
