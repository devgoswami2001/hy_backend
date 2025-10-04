from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils.translation import gettext_lazy as _
import uuid
from jobseaker.services.pdf_maker import create_resume_pdf_via_openai
from django.core.exceptions import ValidationError
from employer.models import JobPost, JobApplication
from django.utils import timezone
from datetime import timedelta
User = get_user_model()

class JobSeekerProfile(models.Model):
    """Core Job Seeker Profile - Basic Information Only"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='jobseeker_profile')
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    
    class Gender(models.TextChoices):
        MALE = 'male', _('Male')
        FEMALE = 'female', _('Female')
        OTHER = 'other', _('Other')
        PREFER_NOT_TO_SAY = 'prefer_not_to_say', _('Prefer not to say')
    
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    
    # Contact Information
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    
    # Address
    address_line_1 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Professional Summary
    headline = models.CharField(max_length=200, blank=True)
    summary = models.TextField(max_length=1000, blank=True)
    
    # Current Status
    class JobStatus(models.TextChoices):
        ACTIVELY_LOOKING = 'actively_looking', _('Actively looking')
        OPEN_TO_OPPORTUNITIES = 'open_to_opportunities', _('Open to opportunities')
        NOT_LOOKING = 'not_looking', _('Not looking')
        EMPLOYED = 'employed', _('Currently employed')
    
    job_status = models.CharField(max_length=25, choices=JobStatus.choices, default=JobStatus.ACTIVELY_LOOKING)
    
    # Preferences
    preferred_job_types = models.JSONField(default=list, blank=True)
    preferred_locations = models.JSONField(default=list, blank=True)
    expected_salary = models.PositiveIntegerField(null=True, blank=True)
    willing_to_relocate = models.BooleanField(default=False)
    
    # Media
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    
    # Settings
    profile_visibility = models.BooleanField(default=True)
    allow_recruiter_contact = models.BooleanField(default=True)
    preferred_roles = models.JSONField(default=list, blank=True, help_text="Roles the job seeker is interested in")
    dream_companies = models.JSONField(default=list, blank=True, help_text="List of dream companies")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jobseeker_profiles'
        verbose_name = _('Job Seeker Profile')
        verbose_name_plural = _('Job Seeker Profiles')
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.user.email}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class Resume(models.Model):
    """Complete Resume with all detailed information"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE, related_name='resumes')
    
    # Resume Metadata
    title = models.CharField(max_length=200, help_text="Resume title (e.g., 'Software Developer Resume')")
    is_default = models.BooleanField(default=False, help_text="Primary/default resume")
    is_active = models.BooleanField(default=True)
    
    # Professional Information
    class ExperienceLevel(models.TextChoices):
        FRESHER = 'fresher', _('Fresher (0-1 years)')
        JUNIOR = 'junior', _('Junior (1-3 years)')
        MID_LEVEL = 'mid_level', _('Mid-level (3-5 years)')
        SENIOR = 'senior', _('Senior (5-8 years)')
        LEAD = 'lead', _('Lead/Principal (8+ years)')
        EXECUTIVE = 'executive', _('Executive/Director (10+ years)')
    
    experience_level = models.CharField(max_length=20, choices=ExperienceLevel.choices, blank=True)
    total_experience_years = models.PositiveIntegerField(default=0)
    total_experience_months = models.PositiveIntegerField(default=0)
    
    # Current Job Info
    current_company = models.CharField(max_length=200, blank=True)
    current_designation = models.CharField(max_length=200, blank=True)
    current_salary = models.PositiveIntegerField(null=True, blank=True)
    
    class NoticePeriod(models.TextChoices):
        IMMEDIATE = 'immediate', _('Immediate')
        FIFTEEN_DAYS = '15_days', _('15 days')
        ONE_MONTH = '1_month', _('1 month')
        TWO_MONTHS = '2_months', _('2 months')
        THREE_MONTHS = '3_months', _('3 months')
    
    notice_period = models.CharField(max_length=20, choices=NoticePeriod.choices, blank=True)
    
    # Resume Content (Structured JSON Data)
    education_data = models.JSONField(default=list, blank=True)
    work_experience_data = models.JSONField(default=list, blank=True)
    skills_data = models.JSONField(default=list, blank=True)
    certifications_data = models.JSONField(default=list, blank=True)
    projects_data = models.JSONField(default=list, blank=True)
    languages_data = models.JSONField(default=list, blank=True)
    achievements_data = models.JSONField(default=list, blank=True)
    
    # Resume Files
    resume_pdf = models.FileField(upload_to='resumes/pdf/', null=True, blank=True)
    resume_doc = models.FileField(upload_to='resumes/doc/', null=True, blank=True)
    cover_letter = models.FileField(upload_to='cover_letters/', null=True, blank=True)
    
    # Resume Analytics
    view_count = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    completion_percentage = models.PositiveIntegerField(default=0)
    
    # SEO and Search
    keywords = models.JSONField(default=list, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'jobseeker_resumes'
        verbose_name = _('Resume')
        verbose_name_plural = _('Resumes')
        unique_together = ['profile', 'title']
        indexes = [
            models.Index(fields=['profile', 'is_default']),
            models.Index(fields=['is_active']),
            models.Index(fields=['experience_level']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.profile.full_name}"
    
    def save(self, *args, **kwargs):
        # Ensure only one default resume per profile
        if self.is_default:
            Resume.objects.filter(profile=self.profile, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
                # now call OpenAI resume PDF generator
        pdf_url = create_resume_pdf_via_openai(self, model="gpt-4o-mini")

        if pdf_url:  # store PDF path into resume_pdf field
            self.resume_pdf.name = pdf_url
            super().save(update_fields=["resume_pdf"])
    @property
    def total_experience_display(self):
        if self.total_experience_years == 0 and self.total_experience_months == 0:
            return "Fresher"
        
        parts = []
        if self.total_experience_years > 0:
            parts.append(f"{self.total_experience_years}y")
        if self.total_experience_months > 0:
            parts.append(f"{self.total_experience_months}m")
        
        return " ".join(parts)
    
    def calculate_completion(self):
        """Calculate resume completion percentage"""
        required_sections = [
            'education_data', 'work_experience_data', 'skills_data'
        ]
        
        completed = 0
        total = len(required_sections)
        
        for section in required_sections:
            if getattr(self, section):
                completed += 1
        
        # Bonus points for additional sections
        optional_sections = ['certifications_data', 'projects_data', 'achievements_data']
        for section in optional_sections:
            if getattr(self, section):
                completed += 0.5
                total += 0.5
        
        self.completion_percentage = int((completed / total) * 100)
        return self.completion_percentage


class AIRemarks(models.Model):
    """
    AI-generated remarks and scoring for job seeker applications.
    This model stores AI analysis of how well a job seeker fits a specific job post.
    """
    
    class FitLevel(models.TextChoices):
        EXCELLENT = 'excellent', _('Excellent fit')
        GOOD = 'good', _('Good fit')
        MODERATE = 'moderate', _('Moderate fit')
        POOR = 'poor', _('Poor fit')
        UNKNOWN = 'unknown', _('Unknown')
    
    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', _('Pending analysis')
        COMPLETED = 'completed', _('Analysis completed')
        FAILED = 'failed', _('Analysis failed')
        SKIPPED = 'skipped', _('Analysis skipped')
    
    # Primary relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_post = models.ForeignKey(
        JobPost,
        on_delete=models.CASCADE,
        related_name='ai_remarks',
        verbose_name=_('Job Post')
    )
    job_seeker = models.ForeignKey(
        JobSeekerProfile,
        on_delete=models.CASCADE,
        related_name='ai_remarks',
        verbose_name=_('Job Seeker')
    )
    
    # Core AI analysis fields
    is_fit = models.BooleanField(
        null=True, 
        blank=True, 
        verbose_name=_('fit for the job'),
        help_text=_('AI determination if candidate is suitable for the role')
    )
    
    fit_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('fit percentage (0-100%)'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('AI-calculated percentage match between candidate and job requirements')
    )
    
    fit_level = models.CharField(
        max_length=20,
        choices=FitLevel.choices,
        default=FitLevel.UNKNOWN,
        verbose_name=_('fit level'),
        db_index=True
    )
    
    remarks = models.TextField(
        blank=True, 
        verbose_name=_('remarks'),
        help_text=_('AI-generated detailed analysis and recommendations')
    )
    
    # Detailed scoring breakdown
    skills_match_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('skills match score'),
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    experience_match_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('experience match score'),
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    education_match_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('education match score'),
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    location_match_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('location compatibility score'),
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # AI analysis metadata
    analysis_status = models.CharField(
        max_length=20,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        verbose_name=_('analysis status'),
        db_index=True
    )
    
    ai_model_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('AI model version'),
        help_text=_('Version of the AI model used for analysis')
    )
    
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('AI confidence score'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('How confident the AI is in its analysis')
    )
    
    # Structured insights
    strengths = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('candidate strengths'),
        help_text=_('List of identified candidate strengths')
    )
    
    weaknesses = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('areas for improvement'),
        help_text=_('List of areas where candidate may need development')
    )
    
    missing_skills = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('missing skills'),
        help_text=_('Skills required for the job but not found in candidate profile')
    )
    
    matching_skills = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('matching skills'),
        help_text=_('Skills that match between job requirements and candidate')
    )
    
    recommendations = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('AI recommendations'),
        help_text=_('Specific recommendations for the hiring decision')
    )
    
    # Interview readiness
    interview_recommendation = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_('recommend for interview'),
        help_text=_('AI recommendation to proceed with interview')
    )
    
    suggested_interview_questions = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('suggested interview questions'),
        help_text=_('AI-generated relevant interview questions')
    )
    
    # Risk assessment
    potential_concerns = models.JSONField(
        blank=True,
        default=list,
        verbose_name=_('potential concerns'),
        help_text=_('Areas of potential risk or concern identified by AI')
    )
    
    salary_expectation_alignment = models.CharField(
        max_length=20,
        choices=[
            ('aligned', _('Aligned')),
            ('too_high', _('Too high')),
            ('too_low', _('Too low')),
            ('unknown', _('Unknown')),
        ],
        blank=True,
        verbose_name=_('salary expectation alignment')
    )
    
    # Processing metadata
    analysis_duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('analysis duration (seconds)')
    )
    
    error_message = models.TextField(
        blank=True,
        verbose_name=_('error message'),
        help_text=_('Error message if analysis failed')
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    analyzed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('analysis completion time')
    )
    
    # Review tracking
    reviewed_by_human = models.BooleanField(
        default=False,
        verbose_name=_('reviewed by human recruiter')
    )
    
    human_override = models.BooleanField(
        default=False,
        verbose_name=_('human override of AI decision')
    )
    
    human_remarks = models.TextField(
        blank=True,
        verbose_name=_('human recruiter remarks')
    )
    
    class Meta:
        db_table = 'ai_remarks'
        verbose_name = _('AI Remark')
        verbose_name_plural = _('AI Remarks')
        ordering = ['-created_at']
        unique_together = ['job_post', 'job_seeker']  # One AI analysis per job seeker per job
        indexes = [
            models.Index(fields=['job_post', 'fit_score']),
            models.Index(fields=['job_seeker', 'fit_score']),
            models.Index(fields=['fit_level', 'analysis_status']),
            models.Index(fields=['is_fit', 'interview_recommendation']),
            models.Index(fields=['analysis_status', 'created_at']),
            models.Index(fields=['reviewed_by_human', 'fit_score']),
        ]
    
    def __str__(self):
        return f"AI Analysis: {self.job_seeker.full_name} for {self.job_post.title}"
    
    def clean(self):
        """Custom validation"""
        super().clean()
        
        # Validate fit_score and fit_level consistency
        if self.fit_score is not None:
            if self.fit_score >= 80 and self.fit_level not in [self.FitLevel.EXCELLENT, self.FitLevel.GOOD]:
                raise ValidationError({'fit_level': 'High fit score should correspond to Excellent or Good fit level'})
            elif self.fit_score < 40 and self.fit_level == self.FitLevel.EXCELLENT:
                raise ValidationError({'fit_level': 'Low fit score cannot be Excellent fit level'})
        
        # Ensure analyzed_at is set when analysis is completed
        if self.analysis_status == self.AnalysisStatus.COMPLETED and not self.analyzed_at:
            self.analyzed_at = timezone.now()
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def overall_recommendation(self):
        """Return a human-readable overall recommendation"""
        if self.is_fit is True and self.interview_recommendation is True:
            return "Highly Recommended"
        elif self.is_fit is True:
            return "Recommended"
        elif self.is_fit is False:
            return "Not Recommended"
        else:
            return "Pending Analysis"
    
    @property
    def score_breakdown(self):
        """Return a dictionary of all scoring metrics"""
        return {
            'overall_fit': float(self.fit_score) if self.fit_score else None,
            'skills_match': float(self.skills_match_score) if self.skills_match_score else None,
            'experience_match': float(self.experience_match_score) if self.experience_match_score else None,
            'education_match': float(self.education_match_score) if self.education_match_score else None,
            'location_match': float(self.location_match_score) if self.location_match_score else None,
            'confidence': float(self.confidence_score) if self.confidence_score else None,
        }


class SubscriptionPlan(models.Model):
    """Simple subscription plans"""
    
    class PlanType(models.TextChoices):
        FREEMIUM = 'freemium', _('Freemium')
        PREMIUM = 'premium', _('Premium')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PlanType.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Core Features
    daily_swipe_limit = models.PositiveIntegerField(default=20)
    has_advanced_cards = models.BooleanField(default=False)
    has_verified_jobs = models.BooleanField(default=False)
    mock_interviews_monthly = models.PositiveIntegerField(default=0)
    has_profile_review = models.BooleanField(default=False)
    has_skill_training = models.BooleanField(default=False)
    has_hyresense = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'subscription_plans'
    
    def __str__(self):
        return f"{self.name} - ₹{self.price}"


class JobSeekerSubscription(models.Model):
    """User subscriptions"""
    
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        EXPIRED = 'expired', _('Expired')
        CANCELLED = 'cancelled', _('Cancelled')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_seeker = models.OneToOneField(JobSeekerProfile, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    # Usage Tracking
    daily_swipes_used = models.PositiveIntegerField(default=0)
    swipe_reset_date = models.DateField(default=timezone.now)
    monthly_interviews_used = models.PositiveIntegerField(default=0)
    monthly_reset_date = models.DateTimeField(default=timezone.now)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'jobseeker_subscriptions'
    
    def __str__(self):
        return f"{self.job_seeker.full_name} - {self.plan.name}"
    
    @property
    def is_active(self):
        now = timezone.now()
        return self.status == self.Status.ACTIVE and self.start_date <= now <= self.end_date
    
    def can_swipe_job(self):
        """Check daily swipe limit"""
        self._reset_daily_swipes()
        return self.daily_swipes_used < self.plan.daily_swipe_limit
    
    def increment_swipe(self):
        """Use one swipe"""
        self._reset_daily_swipes()
        self.daily_swipes_used += 1
        self.save(update_fields=['daily_swipes_used'])
    
    def can_book_interview(self):
        """Check monthly interview limit"""
        self._reset_monthly_usage()
        return self.monthly_interviews_used < self.plan.mock_interviews_monthly
    
    def increment_interview(self):
        """Use one interview"""
        self._reset_monthly_usage()
        self.monthly_interviews_used += 1
        self.save(update_fields=['monthly_interviews_used'])
    
    def _reset_daily_swipes(self):
        """Reset swipes if new day"""
        today = timezone.now().date()
        if self.swipe_reset_date < today:
            self.daily_swipes_used = 0
            self.swipe_reset_date = today
            self.save(update_fields=['daily_swipes_used', 'swipe_reset_date'])
    
    def _reset_monthly_usage(self):
        """Reset monthly counters"""
        now = timezone.now()
        if now >= self.monthly_reset_date + timedelta(days=30):
            self.monthly_interviews_used = 0
            self.monthly_reset_date = now
            self.save(update_fields=['monthly_interviews_used', 'monthly_reset_date'])


class RazorpayPayment(models.Model):
    """Simple payment tracking"""
    
    class Status(models.TextChoices):
        CREATED = 'created', _('Created')
        PAID = 'paid', _('Paid')
        FAILED = 'failed', _('Failed')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_seeker = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE)
    subscription = models.ForeignKey(JobSeekerSubscription, on_delete=models.SET_NULL, null=True, blank=True)
    
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'razorpay_payments'
    
    def __str__(self):
        return f"{self.razorpay_order_id} - ₹{self.amount} - {self.status}"
