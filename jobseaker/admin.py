from django.contrib import admin
from .models import *


@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'phone_number', 'job_status', 'created_at')
    list_filter = ('job_status', 'gender', 'country', 'created_at')
    search_fields = ('first_name', 'last_name', 'user__email', 'phone_number')
    ordering = ('-created_at',)


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = [
        'profile',
        'created_at', 
        'updated_at',
        # Remove 'total_experience_display' - doesn't exist
        # Add actual fields from your Resume model instead
    ]
    
    list_filter = [
        'created_at',
        'updated_at',
        # Remove 'notice_period' - field doesn't exist in Resume model
        # Add actual fields that exist in your Resume model
    ]
    
    # If you need total_experience_display, add this method:
    def total_experience_display(self, obj):
        # Calculate from work_experience_data if needed
        return "N/A"  # Replace with actual calculation
    total_experience_display.short_description = "Total Experience"







@admin.register(AIRemarks)
class AIRemarksAdmin(admin.ModelAdmin):
    list_display = (
        "job_post",
        "job_seeker",
        "fit_score",
        "fit_level",
        "analysis_status",
        "interview_recommendation",
        "confidence_score",
        "created_at",
    )
    list_filter = (
        "fit_level",
        "analysis_status",
        "interview_recommendation",
        "reviewed_by_human",
        "human_override",
        "created_at",
    )
    search_fields = (
        "job_post__title",
        "job_seeker__full_name",
        "remarks",
        "human_remarks",
    )
    ordering = ("-created_at",)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_type', 'price', 'daily_swipe_limit', 'is_active']
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name']

@admin.register(JobSeekerSubscription)
class JobSeekerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['job_seeker', 'plan', 'status', 'start_date', 'end_date']
    list_filter = ['status', 'plan__plan_type']
    search_fields = ['job_seeker__first_name', 'job_seeker__last_name']
    raw_id_fields = ['job_seeker', 'plan']

@admin.register(RazorpayPayment)
class RazorpayPaymentAdmin(admin.ModelAdmin):
    list_display = ['razorpay_order_id', 'job_seeker', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['razorpay_order_id', 'razorpay_payment_id']
    raw_id_fields = ['job_seeker', 'subscription']

