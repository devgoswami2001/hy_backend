from django.contrib import admin
from .models import (
    EmployerProfile, HRUser, JobPost, JobApplication,
    ActivityLog, CompanyPost, PostComment, PostLike, CommentLike,
    EmployerLeadership   # ✅ add here
)


# ---------------- Employer Profile ----------------
class EmployerLeadershipInline(admin.TabularInline):  
    model = EmployerLeadership
    extra = 1  # empty inline form count
    fields = ('position', 'name', 'bio', 'linkedin', 'photo')  
    show_change_link = True


@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user', 'designation', 'created_at')
    search_fields = ('company_name', 'user__email')
    list_filter = ('created_at',)
    readonly_fields = ('slug',)
    inlines = [EmployerLeadershipInline]   # ✅ leadership inline


# ---------------- HR User ----------------
@admin.register(HRUser)
class HRUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'can_post_jobs', 'can_manage_team')
    list_filter = ('role', 'company')
    search_fields = ('user__email',)


# ---------------- Jobs ----------------
@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'employment_type', 'is_active', 'deadline')
    search_fields = ('title', 'company__company_name')
    list_filter = ('employment_type', 'experience_level', 'working_mode', 'is_active', 'deadline')


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'applicant', 'job_post', 'status', 'applied_at')
    list_filter = ('status', 'job_post')


# ---------------- Activity Logs ----------------
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'role', 'timestamp')
    list_filter = ('role', 'action', 'timestamp')
    search_fields = ('user__email', 'message')


# ---------------- Company Posts ----------------
@admin.register(CompanyPost)
class CompanyPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'visibility', 'is_pinned', 'created_at')
    list_filter = ('visibility', 'is_pinned', 'is_active')
    search_fields = ('title', 'company__company_name')


# ---------------- Post Comments & Likes ----------------
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


# ---------------- Employer Leadership ----------------
@admin.register(EmployerLeadership)
class EmployerLeadershipAdmin(admin.ModelAdmin):
    list_display = ('name', 'position', 'employer')
    search_fields = ('name', 'position', 'employer__company_name')
    list_filter = ('position',)
