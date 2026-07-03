# payments/services.py
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from .models import SubscriptionActivation, PayUPayment, JobSeekerSubscription


@transaction.atomic
def activate_subscription(payment: PayUPayment):
    """
    Safely activates subscription for a successful PayU payment.
    This function is idempotent.
    """

    # 🔒 Prevent double activation
    if hasattr(payment, "activation"):
        return payment.activation.subscription

    # ⏱️ Subscription duration (example: 30 days)
    start_date = timezone.now()
    end_date = start_date + timedelta(days=30)

    # 🧾 Create subscription
    subscription = JobSeekerSubscription.objects.create(
        job_seeker=payment.job_seeker,
        plan=payment.plan,
        status=JobSeekerSubscription.Status.ACTIVE,
        start_date=start_date,
        end_date=end_date,
    )

    # 🔗 Link payment → subscription
    SubscriptionActivation.objects.create(
        payment=payment,
        subscription=subscription,
    )

    return subscription