from django.contrib import admin
from .models import (
    EmployerProfile, HRUser, JobPost, JobApplication,
    ActivityLog, CompanyPost, PostComment, PostLike, CommentLike
)


@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user', 'designation', 'created_at')
    search_fields = ('company_name', 'user__email')
    list_filter = ('created_at',)
    readonly_fields = ('slug',)


@admin.register(HRUser)
class HRUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'can_post_jobs', 'can_manage_team')
    list_filter = ('role', 'company')
    search_fields = ('user__email',)


@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'employment_type', 'is_active', 'deadline')
    search_fields = ('title', 'company__company_name')
    list_filter = ('employment_type', 'experience_level', 'working_mode', 'is_active', 'deadline')


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('applicant', 'job_post', 'status', 'applied_at', 'is_fit', 'fit_score')
    list_filter = ('status', 'applied_at', 'is_fit')
    search_fields = ('applicant__email', 'job_post__title')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'role', 'timestamp')
    list_filter = ('role', 'action', 'timestamp')
    search_fields = ('user__email', 'message')


@admin.register(CompanyPost)
class CompanyPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'visibility', 'is_pinned', 'created_at')
    list_filter = ('visibility', 'is_pinned', 'is_active')
    search_fields = ('title', 'company__company_name')


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'comment', 'created_at')
    search_fields = ('user__email', 'post__title')
    list_filter = ('created_at',)


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'liked_at')
    search_fields = ('user__email', 'post__title')
    list_filter = ('liked_at',)


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'liked_at')
    list_filter = ('liked_at',)
    search_fields = ('user__email',)
