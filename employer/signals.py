from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import JobPost, EmployerProfile, JobApplication,JobApplication, JobPost
from django.db.models import F

@receiver([post_save, post_delete], sender=JobPost)
def update_employer_active_jobs(sender, instance, **kwargs):
    employer = instance.company
    active_count = JobPost.objects.filter(company=employer, is_active=True).count()
    employer.active_jobs_count = active_count
    employer.save(update_fields=['active_jobs_count'])


@receiver([post_save, post_delete], sender=JobApplication)
def update_employer_total_applications(sender, instance, **kwargs):
    employer = instance.job_post.company
    active_job_ids = JobPost.objects.filter(company=employer, is_active=True).values_list('id', flat=True)
    valid_statuses = ['applied', 'under_review', 'shortlisted', 'interview_scheduled', 'offer_made', 'hired']
    count = JobApplication.objects.filter(
        job_post_id__in=active_job_ids,
        status__in=valid_statuses
    ).count()
    employer.total_applications_count = count
    employer.save(update_fields=['total_applications_count'])



@receiver(post_save, sender=JobApplication)
def update_job_post_applications_count_on_save(sender, instance, created, **kwargs):
    if created:
        JobPost.objects.filter(id=instance.job_post_id).update(
            applications_count=F('applications_count') + 1
        )

@receiver(post_delete, sender=JobApplication)
def update_job_post_applications_count_on_delete(sender, instance, **kwargs):
    JobPost.objects.filter(id=instance.job_post_id).update(
        applications_count=F('applications_count') - 1
    )

