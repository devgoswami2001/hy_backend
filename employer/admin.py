from django.contrib import admin
from django.http import HttpResponse
import csv
from datetime import datetime
from .models import *

# ------------------- CSV Export Helper Function -------------------
def export_to_csv(modeladmin, request, queryset):
    """
    Generic CSV export function for any model
    """
    # Get all field names from the model
    model = queryset.model
    field_names = [field.name for field in model._meta.fields]
    
    # Create response with CSV header
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename={model.__name__}_{timestamp}.csv'
    
    writer = csv.writer(response)
    writer.writerow(field_names)
    
    # Write data rows
    for obj in queryset:
        row = []
        for field in field_names:
            value = getattr(obj, field)
            # Handle special field types
            if hasattr(value, 'strftime'):  # DateTime fields
                value = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, bool):   # Boolean fields
                value = 'Yes' if value else 'No'
            elif value is None:             # Null fields
                value = ''
            row.append(str(value))
        writer.writerow(row)
    
    return response

export_to_csv.short_description = "📊 Export selected items to CSV"

# ------------------- Employer Profile -------------------
class EmployerLeadershipInline(admin.TabularInline):
    model = EmployerLeadership
    extra = 1
    fields = ('position', 'name', 'bio', 'linkedin', 'photo')
    show_change_link = True

@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user', 'designation', 'created_at')
    search_fields = ('company_name', 'user__email')
    list_filter = ('created_at',)
    readonly_fields = ('slug',)
    inlines = [EmployerLeadershipInline]
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- HR User -------------------
@admin.register(HRUser)
class HRUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'can_post_jobs', 'can_manage_team')
    list_filter = ('role', 'company')
    search_fields = ('user__email',)
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Jobs -------------------
@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'employment_type', 'is_active', 'deadline')
    search_fields = ('title', 'company__company_name')
    list_filter = ('employment_type', 'experience_level', 'working_mode', 'is_active', 'deadline')
    actions = [export_to_csv]  # ✅ Export action added

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'applicant', 'job_post', 'status', 'applied_at')
    list_filter = ('status', 'job_post')
    search_fields = ('applicant__email', 'job_post__title')
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Activity Logs -------------------
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'role', 'timestamp')
    list_filter = ('role', 'action', 'timestamp')
    search_fields = ('user__email', 'message')
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Company Posts -------------------
@admin.register(CompanyPost)
class CompanyPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'visibility', 'is_pinned', 'created_at')
    list_filter = ('visibility', 'is_pinned', 'is_active')
    search_fields = ('title', 'company__company_name')
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Post Comments & Likes -------------------
@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'comment', 'created_at')
    search_fields = ('user__email', 'post__title')
    list_filter = ('created_at',)
    actions = [export_to_csv]  # ✅ Export action added

@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'liked_at')
    search_fields = ('user__email', 'post__title')
    list_filter = ('liked_at',)
    actions = [export_to_csv]  # ✅ Export action added

@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'liked_at')
    list_filter = ('liked_at',)
    search_fields = ('user__email',)
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Employer Leadership -------------------
@admin.register(EmployerLeadership)
class EmployerLeadershipAdmin(admin.ModelAdmin):
    list_display = ('name', 'position', 'employer')
    search_fields = ('name', 'position', 'employer__company_name')
    list_filter = ('position',)
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Job Application Chat -------------------
@admin.register(JobApplicationChat)
class JobApplicationChatAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job_application",
        "jobseeker",
        "employer",
        "last_message_at",
        "created_at",
    )
    search_fields = (
        "job_application__id",
        "jobseeker__email",
        "employer__email",
    )
    list_filter = ("last_message_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Job Application Messages -------------------
@admin.register(JobApplicationMessage)
class JobApplicationMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "chat",
        "sender",
        "message_type",
        "is_read",
        "sent_at",
    )
    search_fields = (
        "sender__email",
        "chat__id",
        "message",
    )
    list_filter = (
        "message_type",
        "is_read",
        "sent_at",
    )
    readonly_fields = (
        "id",
        "sent_at",
    )
    actions = [export_to_csv]  # ✅ Export action added

# ------------------- Subscription Models -------------------
@admin.register(EmployerSubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "plan_type",
        "price",
        "duration_days",
        "free_hr_logins",
        "extra_hr_login_price",
        "is_active",
    )
    list_filter = ("plan_type", "is_active")
    search_fields = ("name",)
    actions = [export_to_csv]  # ✅ Export action added

@admin.register(EmployerSubscription)
class EmployerSubscriptionPanel(admin.ModelAdmin):
    list_display = (
        "employer",
        "plan",
        "subscription_start",
        "subscription_end",
        "allowed_hr_seats",
        "extra_seats_purchased",
        "active_status",
    )
    readonly_fields = (
        "allowed_hr_seats",
        "extra_seats_purchased",
    )
    actions = [export_to_csv]  # ✅ Export action added

    def subscription_start(self, obj):
        return obj.start_date

    def subscription_end(self, obj):
        return obj.end_date

    def allowed_hr_seats(self, obj):
        return obj.plan.free_hr_logins + obj.purchased_hr_seats

    def extra_seats_purchased(self, obj):
        return obj.purchased_hr_seats

    def active_status(self, obj):
        return obj.is_active

    subscription_start.short_description = "Start Date"
    subscription_end.short_description = "End Date"
    allowed_hr_seats.short_description = "Total HR Seats"
    extra_seats_purchased.short_description = "Extra HR Seats"
    active_status.short_description = "Active"

@admin.register(EmployerPayUPayment)
class EmployerPaymentConsole(admin.ModelAdmin):
    list_display = (
        "txnid",
        "employer",
        "payment_type",
        "plan",
        "seats",
        "amount",
        "status",
        "created_at",
    )
    readonly_fields = (
        "txnid",
        "amount",
        "status",
        "payu_payment_id",
        "bank_ref_num",
        "created_at",
        "raw_response",
    )
    search_fields = (
        "txnid",
        "employer__company_name",
        "payu_payment_id",
    )
    list_filter = (
        "status",
        "payment_type",
        "created_at",
    )
    ordering = ("-created_at",)
    actions = [export_to_csv]  # ✅ Export action added