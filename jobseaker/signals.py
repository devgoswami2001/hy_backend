from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import JobSeekerProfile, SubscriptionPlan, JobSeekerSubscription
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=JobSeekerProfile)
def create_freemium_subscription(sender, instance, created, **kwargs):
    """Auto-create freemium subscription when JobSeeker profile is created"""
    if created:  # Only for new profiles
        try:
            # Get freemium plan
            freemium_plan = SubscriptionPlan.objects.filter(
                plan_type=SubscriptionPlan.PlanType.FREEMIUM,
                is_active=True
            ).first()
            
            if not freemium_plan:
                logger.warning("No active Freemium plan found")
                return
            
            # Check if subscription already exists
            if hasattr(instance, 'subscription'):
                logger.info("Subscription already exists for this profile")
                return
            
            # Create freemium subscription
            now = timezone.now()
            subscription = JobSeekerSubscription.objects.create(
                job_seeker=instance,
                plan=freemium_plan,
                status=JobSeekerSubscription.Status.ACTIVE,
                start_date=now,
                end_date=now + timedelta(days=365)  # 1 year free
            )
            
            logger.info(f"Freemium subscription created for JobSeeker {instance.id}")
            
        except Exception as e:
            logger.error(f"Error creating freemium subscription: {str(e)}")
