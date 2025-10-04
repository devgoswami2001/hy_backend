from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import ArrayField
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import uuid
import os


def validate_file_size(value, max_size_mb=5):
    """Validate file size"""
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f'File size cannot exceed {max_size_mb}MB.')


def validate_resume(value):
    """Validate resume file"""
    validate_file_size(value, 5)  # 5MB limit
    if not value.name.lower().endswith(('.pdf', '.doc', '.docx')):
        raise ValidationError('Only PDF, DOC, and DOCX files are allowed.')


def validate_image(value):
    """Validate image file"""
    validate_file_size(value, 10)  # 10MB limit
    if not value.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
        raise ValidationError('Only JPG, JPEG, PNG, GIF, and WEBP files are allowed.')


def validate_video(value):
    """Validate video file"""
    validate_file_size(value, 50)  # 50MB limit
    if not value.name.lower().endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv')):
        raise ValidationError('Only MP4, AVI, MOV, WMV, and FLV files are allowed.')


def upload_to_resume(instance, filename):
    """Upload resume with UUID"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('resumes', str(instance.applicant.id), filename)


def upload_to_post_media(instance, filename, folder):
    """Upload post media with UUID"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join(f'posts/{folder}', str(instance.company.id), filename)

def upload_to_post_image(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('posts/images', str(instance.company.id), filename)

def upload_to_post_video(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('posts/videos', str(instance.company.id), filename)

def upload_to_post_document(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('posts/documents', str(instance.company.id), filename)

class BaseModel(models.Model):
    """Abstract base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        """Soft delete the object"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()


class ActiveManager(models.Manager):
    """Manager to exclude soft-deleted objects"""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class EmployerProfile(BaseModel):
    """
    Main employer profile linked to a user with role='employer'.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'employer'},
        related_name='employer_profile',
        verbose_name=_('user')
    )
    company_name = models.CharField(
        max_length=255,
        verbose_name=_('company name'),
        db_index=True
    )
    is_active = models.BooleanField(default=True)
    slug = models.SlugField(unique=True, blank=True, max_length=255)
    designation = models.CharField(max_length=100, verbose_name=_('designation'))
    description = models.TextField(blank=True, verbose_name=_('company description'))
    website = models.URLField(blank=True, verbose_name=_('website'))
    logo = models.ImageField(
        upload_to='company_logos/',
        blank=True,
        null=True,
        validators=[validate_image],
        verbose_name=_('company logo')
    )
    banner = models.ImageField(
        upload_to='company_banners/',
        blank=True,
        null=True,
        validators=[validate_image],
        verbose_name=_('company banner'),
        help_text=_('Recommended size: 1200x400 pixels')
    )

    # ✅ Company Categories
    CATEGORY_CHOICES = [
        # Technology
        ('it', _('Information Technology & Services')),
        ('software', _('Software Development')),
        ('internet', _('Internet & Web Services')),
        ('telecom', _('Telecommunications')),
        ('electronics', _('Electronics & Semiconductors')),
        ('ai', _('Artificial Intelligence / Machine Learning')),

        # Finance & Business
        ('finance', _('Banking, Finance & Insurance')),
        ('investment', _('Investment Management')),
        ('accounting', _('Accounting')),
        ('consulting', _('Management Consulting')),
        ('real_estate', _('Real Estate & Property Management')),

        # Healthcare
        ('healthcare', _('Healthcare & Hospitals')),
        ('pharma', _('Pharmaceuticals')),
        ('biotech', _('Biotechnology')),
        ('medical_devices', _('Medical Devices')),
        ('wellness', _('Health, Wellness & Fitness')),

        # Education
        ('education', _('Education & Training')),
        ('edtech', _('EdTech')),
        ('research', _('Research & Development')),

        # Manufacturing & Industry
        ('manufacturing', _('Manufacturing')),
        ('automotive', _('Automotive')),
        ('aerospace', _('Aerospace & Defense')),
        ('construction', _('Construction & Engineering')),
        ('energy', _('Energy & Utilities')),
        ('oil_gas', _('Oil & Gas')),
        ('mining', _('Mining & Metals')),
        ('chemical', _('Chemicals')),

        # Retail, FMCG & Consumer
        ('retail', _('Retail & Wholesale')),
        ('fmcg', _('FMCG / Consumer Goods')),
        ('food', _('Food & Beverages')),
        ('fashion', _('Apparel & Fashion')),
        ('luxury', _('Luxury Goods & Jewelry')),
        ('hospitality', _('Hospitality')),
        ('travel', _('Travel & Tourism')),

        # Media & Entertainment
        ('media', _('Media & Publishing')),
        ('entertainment', _('Entertainment & Film')),
        ('sports', _('Sports & Recreation')),
        ('gaming', _('Gaming')),
        ('marketing', _('Marketing & Advertising')),
        ('design', _('Design & Creative Services')),

        # Logistics & Transport
        ('logistics', _('Logistics & Supply Chain')),
        ('transport', _('Transportation')),
        ('shipping', _('Shipping & Marine')),
        ('aviation', _('Aviation')),

        # Agriculture & Environment
        ('agriculture', _('Agriculture & Farming')),
        ('forestry', _('Forestry & Paper')),
        ('fisheries', _('Fisheries & Aquaculture')),
        ('environment', _('Environmental Services')),
        ('renewables', _('Renewable Energy')),

        # Government & Nonprofit
        ('government', _('Government Administration')),
        ('ngo', _('Nonprofit / NGO')),
        ('defense', _('Defense & Security')),
        ('public_safety', _('Public Safety & Law Enforcement')),

        # Legal & HR
        ('legal', _('Legal Services')),
        ('hr', _('Human Resources & Staffing')),

        # Miscellaneous
        ('ecommerce', _('E-commerce')),
        ('startup', _('Startups')),
        ('other', _('Other')),
    ]

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
        verbose_name=_('company category'),
        db_index=True
    )

    # Cached counts
    active_jobs_count = models.PositiveIntegerField(default=0)
    total_applications_count = models.PositiveIntegerField(default=0)
    followers_count = models.PositiveIntegerField(default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.company_name)
            # Ensure uniqueness
            counter = 1
            original_slug = self.slug
            while EmployerProfile.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def update_followers_count(self):
        """Update cached followers count"""
        self.followers_count = self.followers.filter(is_active=True).count()
        self.save(update_fields=['followers_count'])

    def __str__(self):
        return f"{self.company_name} ({self.user.email})"

    class Meta:
        verbose_name = _('Employer Profile')
        verbose_name_plural = _('Employer Profiles')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['slug']),
            models.Index(fields=['created_at']),
            models.Index(fields=['followers_count']),
            models.Index(fields=['category']),  # ✅ fast category filtering
        ]


class EmployerLeadership(models.Model):
    employer = models.ForeignKey(
        'EmployerProfile',
        related_name='leadership_team',
        on_delete=models.CASCADE
    )
    position = models.CharField(max_length=100)  # Free text, e.g., CEO / CTO / Founder
    name = models.CharField(max_length=255)
    bio = models.TextField(blank=True, null=True)
    linkedin = models.URLField(blank=True, null=True)
    photo = models.ImageField(upload_to='leadership_photos/', blank=True, null=True)

    class Meta:
        verbose_name = "Leadership Member"
        verbose_name_plural = "Leadership Team"



class CompanyFollower(BaseModel):
    """
    Model to track job seekers following companies
    """
    company = models.ForeignKey(
        EmployerProfile,
        on_delete=models.CASCADE,
        related_name='followers',
        verbose_name=_('company')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'jobseeker'},
        related_name='following_companies',
        verbose_name=_('job seeker')
    )
    followed_at = models.DateTimeField(auto_now_add=True, verbose_name=_('followed at'))
    is_active = models.BooleanField(default=True, verbose_name=_('is active'))
    
    # Notification preferences
    notify_new_jobs = models.BooleanField(default=True, verbose_name=_('notify new jobs'))
    notify_company_updates = models.BooleanField(default=True, verbose_name=_('notify company updates'))

    objects = ActiveManager()
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update company followers count when a new follower is added
        if self.is_active:
            self.company.update_followers_count()

    def delete(self, *args, **kwargs):
        company = self.company
        super().delete(*args, **kwargs)
        # Update company followers count when follower is removed
        company.update_followers_count()

    def __str__(self):
        return f"{self.user.email} follows {self.company.company_name}"

    class Meta:
        verbose_name = _('Company Follower')
        verbose_name_plural = _('Company Followers')
        ordering = ['-followed_at']
        unique_together = ['company', 'user']  # Prevent duplicate follows
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['followed_at']),
        ]


class HRUser(BaseModel):
    """
    Team members under an employer profile with specific HR roles and permissions.
    """
    class HRRoles(models.TextChoices):
        HR_MANAGER = 'HR Manager', _('HR Manager')
        RECRUITER = 'Recruiter', _('Recruiter')
        INTERVIEWER = 'Interviewer', _('Interviewer')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'employer'},
        related_name='hr_user',
        verbose_name=_('user')
    )
    company = models.ForeignKey(
        EmployerProfile,
        on_delete=models.CASCADE,
        related_name='hr_team',
        verbose_name=_('employer profile')
    )
    role = models.CharField(
        max_length=50, 
        choices=HRRoles.choices, 
        verbose_name=_('HR role'),
        db_index=True
    )

    # Permission flags
    can_post_jobs = models.BooleanField(default=False, verbose_name=_('can post jobs'))
    can_view_applicants = models.BooleanField(default=True, verbose_name=_('can view applicants'))
    can_edit_profile = models.BooleanField(default=False, verbose_name=_('can edit profile'))
    can_post_feed = models.BooleanField(default=False, verbose_name=_('can post feed'))
    can_manage_team = models.BooleanField(default=False, verbose_name=_('can manage team'))

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.user.email} - {self.role} at {self.company.company_name}"

    class Meta:
        verbose_name = _('HR User')
        verbose_name_plural = _('HR Users')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['company']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user'], 
                name='unique_hr_user_per_account',
                condition=models.Q(is_deleted=False)
            ),
        ]


class ActiveJobManager(models.Manager):
    """Manager for active jobs only"""
    def get_queryset(self):
        return super().get_queryset().filter(
            is_active=True,
            is_deleted=False,
            deadline__gte=timezone.now().date()
        )


class JobPost(BaseModel):
    """
    Job post created by HR user or employer.
    """
    class EmploymentTypeChoices(models.TextChoices):
        FULL_TIME = 'Full-time', _('Full-time')
        PART_TIME = 'Part-time', _('Part-time')
        INTERNSHIP = 'Internship', _('Internship')
        CONTRACT = 'Contract', _('Contract')

    class ExperienceLevelChoices(models.TextChoices):
        ENTRY = 'Entry-level', _('Entry-level')
        MID = 'Mid-level', _('Mid-level')
        SENIOR = 'Senior-level', _('Senior-level')

    class WorkingModeChoices(models.TextChoices):
        ON_SITE = 'On-site', _('On-site')
        HYBRID = 'Hybrid', _('Hybrid')
        REMOTE = 'Remote', _('Remote')

    company = models.ForeignKey(
        EmployerProfile,
        on_delete=models.CASCADE,
        related_name='job_posts',
        verbose_name=_('Company Admin')
    )
    
    # ✅ Add the company_name field
    company_name = models.CharField(
        max_length=255,
        verbose_name=_('Company Name'),
        db_index=True,
        help_text=_('Name of the company posting this job')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('created by'),
        limit_choices_to={'role': 'employer'}
    )

    title = models.CharField(max_length=255, verbose_name=_('job title'), db_index=True)
    slug = models.SlugField(unique=True, blank=True, max_length=255)
    employment_type = models.CharField(
        max_length=50,
        choices=EmploymentTypeChoices.choices,
        default=EmploymentTypeChoices.FULL_TIME,
        verbose_name=_('employment type'),
        db_index=True
    )
    experience_level = models.CharField(
        max_length=50,
        choices=ExperienceLevelChoices.choices,
        default=ExperienceLevelChoices.MID,
        verbose_name=_('experience level'),
        db_index=True
    )
    working_mode = models.CharField(
        max_length=50,
        choices=WorkingModeChoices.choices,
        default=WorkingModeChoices.ON_SITE,
        verbose_name=_('working mode'),
        db_index=True
    )
    location = models.CharField(max_length=255, verbose_name=_('location'), db_index=True)
    
    salary_min = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name=_('min salary'),
        validators=[MinValueValidator(0)]
    )
    salary_max = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name=_('max salary'),
        validators=[MinValueValidator(0)]
    )

    deadline = models.DateField(verbose_name=_('application deadline'), db_index=True)

    required_skills = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('required skills')
    )

    screening_questions = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('screening questions')
    )
    description = models.TextField(
        verbose_name=_('job description'),
        help_text=_('Detailed description of the job role and responsibilities'), default=""
    )
    # Cached counts
    applications_count = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True, verbose_name=_('is active'), db_index=True)
    is_featured = models.BooleanField(default=False, verbose_name=_('is featured'))

    objects = ActiveManager()
    all_objects = models.Manager()
    active_jobs = ActiveJobManager()

    def clean(self):
        """Custom validation"""
        super().clean()
        if self.deadline and self.deadline < timezone.now().date():
            raise ValidationError({'deadline': 'Deadline cannot be in the past.'})
        
        if self.salary_min and self.salary_max:
            if self.salary_min > self.salary_max:
                raise ValidationError({
                    'salary_min': 'Minimum salary cannot exceed maximum salary.'
                })

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.title}-{self.company.company_name}")
            self.slug = base_slug
            counter = 1
            while JobPost.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} at {self.company.company_name}"

    class Meta:
        verbose_name = _('Job Post')
        verbose_name_plural = _('Job Posts')
        ordering = ['-is_featured', '-created_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['location']),
            models.Index(fields=['employment_type']),
            models.Index(fields=['experience_level']),
            models.Index(fields=['working_mode']),
            models.Index(fields=['deadline']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['company', 'is_active']),
        ]


class JobApplication(BaseModel):
    """
    Application made by a jobseeker to a job post, with employer/AI evaluation.
    """
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('under_review', 'Under Review'),
        ('shortlisted', 'Shortlisted'),
        ('interview_scheduled', 'Interview Scheduled'),
        ('offer_made', 'Offer Made'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
        ('user_rejected', 'User Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    is_fit = models.BooleanField(default=False)  # add this if required
    fit_score = models.IntegerField(default=0)
    remarks = models.TextField(blank=True, null=True)
    job_post = models.ForeignKey(
        'JobPost',
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('job post')
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_applications',
        limit_choices_to={'role': 'jobseeker'},
        verbose_name=_('applicant')
    )
    cover_letter = models.TextField(blank=True, verbose_name=_('cover letter'))
    resume = models.FileField(
        upload_to=upload_to_resume,
        verbose_name=_('resume'),
        validators=[validate_resume]
    )
    status = models.CharField(
        max_length=30, 
        choices=STATUS_CHOICES, 
        default='applied', 
        verbose_name=_('status'),
        db_index=True
    )
    description = models.TextField()
    # AI/HR Evaluation
    
    
    # Tracking fields
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        verbose_name=_('reviewed by')
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    applied_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.applicant.email} - {self.job_post.title}"

    class Meta:
        verbose_name = _('Job Application')
        verbose_name_plural = _('Job Applications')
        ordering = ['-applied_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['applied_at']),
            models.Index(fields=['job_post', 'status']),
            models.Index(fields=['applicant', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['job_post', 'applicant'], 
                name='unique_application_per_jobseeker',
                condition=models.Q(is_deleted=False)
            ),
        ]


class ActivityLog(models.Model):
    """
    Tracks actions taken by employer or HR users (audit log).
    """
    class ActorRole(models.TextChoices):
        EMPLOYER = 'employer', _('Employer')
        HR = 'hr', _('HR User')

    class ActionType(models.TextChoices):
        JOB_CREATED = 'job_created', _('Job Created')
        JOB_UPDATED = 'job_updated', _('Job Updated')
        JOB_DELETED = 'job_deleted', _('Job Deleted')
        APPLICATION_VIEWED = 'application_viewed', _('Application Viewed')
        STATUS_CHANGED = 'status_changed', _('Application Status Changed')
        INTERVIEW_SCHEDULED = 'interview_scheduled', _('Interview Scheduled')
        PROFILE_UPDATED = 'profile_updated', _('Profile Updated')
        FEED_POSTED = 'feed_posted', _('Feed Posted')
        COMMENT_ADDED = 'comment_added', _('Comment Added')
        USER_LOGIN = 'user_login', _('User Login')
        USER_LOGOUT = 'user_logout', _('User Logout')
        OTHER = 'other', _('Other')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('actor')
    )
    role = models.CharField(
        max_length=20,
        choices=ActorRole.choices,
        verbose_name=_('actor role'),
        db_index=True
    )
    action = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        verbose_name=_('action type'),
        db_index=True
    )
    
    # Generic foreign key for better flexibility
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Legacy fields for backward compatibility
    target_model = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('target model')
    )
    target_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('target object ID')
    )
    
    message = models.TextField(blank=True, verbose_name=_('description/message'))
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_('timestamp'), db_index=True)

    class Meta:
        verbose_name = _('Activity Log')
        verbose_name_plural = _('Activity Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user} | {self.action} | {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class CompanyPost(BaseModel):
    """
    Company post/announcement by employer or HR.
    Supports media, visibility, pinning, comments, and analytics.
    """
    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('jobseekers_only', 'Only Jobseekers'),
        ('internal', 'Only HR/Employer'),
    ]

    company = models.ForeignKey(
        'EmployerProfile',
        on_delete=models.CASCADE,
        related_name='company_posts',
        verbose_name=_('employer profile')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('posted by'),
        limit_choices_to={'role': 'employer'}
    )

    title = models.CharField(max_length=255, verbose_name=_('title'), db_index=True)
    slug = models.SlugField(unique=True, blank=True, max_length=255)
    content = models.TextField(verbose_name=_('content'))
    
    image = models.ImageField(
        upload_to=upload_to_post_image,  # Changed from lambda
        blank=True,
        null=True,
        validators=[validate_image],
        verbose_name=_('image')
    )
    video = models.FileField(
        upload_to=upload_to_post_video,  # Changed from lambda
        blank=True,
        null=True,
        validators=[validate_video],
        verbose_name=_('video')
    )
    document = models.FileField(
        upload_to=upload_to_post_document,  # Changed from lambda
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'txt'])],
        verbose_name=_('attachment/document')
    )

    visibility = models.CharField(
        max_length=50,
        choices=VISIBILITY_CHOICES,
        default='public',
        verbose_name=_('visibility'),
        db_index=True
    )
    video_url = models.URLField(blank=True, null=True, verbose_name=_('video URL'))
    external_link = models.URLField(blank=True, null=True, verbose_name=_('external link'))
    category = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('category'))
    
    allow_comments = models.BooleanField(default=True, verbose_name=_('allow comments'))
    is_pinned = models.BooleanField(default=False, verbose_name=_('pin this post'), db_index=True)
    is_active = models.BooleanField(default=True, verbose_name=_('is active'), db_index=True)

    # Cached counts
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.title}-{self.company.company_name}")
            self.slug = base_slug
            counter = 1
            while CompanyPost.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - {self.company.company_name}"

    class Meta:
        verbose_name = _('Company Post')
        verbose_name_plural = _('Company Posts')
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['visibility']),
            models.Index(fields=['is_pinned']),
            models.Index(fields=['is_active']),
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['created_at']),
        ]


class PostComment(BaseModel):
    """
    Comments made by users on a company post.
    """
    post = models.ForeignKey(
        CompanyPost,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_('post')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('commented by')
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name=_('parent comment')
    )
    comment = models.TextField(verbose_name=_('comment'))
    
    # Cached counts
    likes_count = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"Comment by {self.user.email} on {self.post.title}"

    class Meta:
        verbose_name = _('Post Comment')
        verbose_name_plural = _('Post Comments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
            models.Index(fields=['user']),
            models.Index(fields=['parent']),
        ]


class PostLike(models.Model):
    """
    Likes on company posts.
    """
    post = models.ForeignKey(
        CompanyPost,
        on_delete=models.CASCADE,
        related_name='likes_details',
        verbose_name=_('post')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_likes',
        verbose_name=_('liked by')
    )
    liked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('post', 'user')
        verbose_name = _('Post Like')
        verbose_name_plural = _('Post Likes')
        ordering = ['-liked_at']
        indexes = [
            models.Index(fields=['post', 'liked_at']),
            models.Index(fields=['user', 'liked_at']),
        ]

    def __str__(self):
        return f"{self.user.email} liked {self.post.title}"


class CommentLike(models.Model):
    """
    Likes on comments.
    """
    comment = models.ForeignKey(
        PostComment,
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name=_('comment')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_likes',
        verbose_name=_('liked by')
    )
    liked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('comment', 'user')
        verbose_name = _('Comment Like')
        verbose_name_plural = _('Comment Likes')
        ordering = ['-liked_at']

    def __str__(self):
        return f"{self.user.email} liked comment"




class ApplicationRemark(BaseModel):
    """
    Remarks/feedback given by HR or Interviewers on a Job Application.
    Each application can have multiple remarks.
    """
    application = models.ForeignKey(
        'JobApplication',
        on_delete=models.CASCADE,
        related_name='remarks_history',
        verbose_name=_('job application')
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='application_remarks',
        limit_choices_to=models.Q(role__in=['hr', 'employer', 'interviewer']),
        verbose_name=_('reviewer')
    )
    remark = models.TextField(verbose_name=_('remark'))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Remark by {self.reviewer.email} on {self.application}"

    class Meta:
        verbose_name = _('Application Remark')
        verbose_name_plural = _('Application Remarks')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application', 'created_at']),
            models.Index(fields=['reviewer']),
        ]
