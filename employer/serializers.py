# Standard library imports
from calendar import month_name
from datetime import datetime
from django.core.cache import cache
# Django imports
from django.contrib.auth import get_user_model
from django.db.models import Q, F, Count
from django.db.models.functions import Extract
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

# DRF imports
from rest_framework import serializers, viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.pagination import PageNumberPagination

# Third-party imports
from django_filters.rest_framework import DjangoFilterBackend

# Local app imports
from .models import *
from .serializers import *
from .permissions import *
from .filters import *
from jobseaker.models import *
User = get_user_model()

# ============================================================================
# UTILITY SERIALIZERS
# ============================================================================

class EmployerIdSerializer(serializers.Serializer):
    employer_id = serializers.IntegerField()
    company_name = serializers.CharField()
    company_logo = serializers.CharField(allow_null=True, required=False)
    user_role = serializers.CharField()
    access_type = serializers.CharField()


class EmployerProfileCheckSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            # Employer ya HR dono ko allow karo
            user = User.objects.get(
                email=value, 
                role__in=['employer', 'hr']  # Dono roles allow
            )
            
        
            # Check logic
            if user.role == 'employer':
                has_profile = hasattr(user, 'employer_profile')
            elif user.role == 'hr':
                # HR ke case mein company field se employer_profile access
                has_profile =  True
            
            return {
                'email': value,
                'has_employer_profile': has_profile
            }
        
        except User.DoesNotExist:
            return {
                'email': value,
                'has_employer_profile': False
            }

class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info for nested serialization"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name']
        read_only_fields = ['id', 'email', 'first_name', 'last_name', 'full_name']
    
    def get_full_name(self, obj):
        return obj.get_full_name() if hasattr(obj, 'get_full_name') else f"{obj.first_name} {obj.last_name}".strip()

# ============================================================================
# EMPLOYER PROFILE SERIALIZERS
# ============================================================================

class EmployerProfileCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployerProfile
        fields = ['category','company_name', 'designation', 'description', 'website', 'logo']
    
    def validate(self, attrs):
        user = self.context['request'].user
        if hasattr(user, 'employer_profile'):
            raise serializers.ValidationError('Profile already exists.')
        return attrs

class EmployerProfileUpdateSerializer(serializers.ModelSerializer):
    logo_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployerProfile
        fields = [
            'company_name', 'designation', 'description', 'website', 
            'logo', 'logo_preview'
        ]
        extra_kwargs = {
            'logo': {'validators': [validate_image], 'required': False},
        }

    def get_logo_preview(self, obj):
        """Get current logo URL for preview"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None
    
    def validate_website(self, value):
        """Validate and format website URL"""
        if value and not value.startswith(('http://', 'https://')):
            value = f'https://{value}'
        return value
    
    def validate_company_name(self, value):
        """Validate company name uniqueness (excluding current instance)"""
        if value:
            existing = EmployerProfile.objects.filter(
                company_name__iexact=value
            ).exclude(id=self.instance.id if self.instance else None)
            
            if existing.exists():
                raise serializers.ValidationError(
                    "A company with this name already exists."
                )
        return value
    
    def validate_logo(self, value):
        """Validate logo file"""
        if value:
            # Check file size (5MB limit)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError(
                    "Logo file size cannot exceed 5MB."
                )
            
            # Check file format
            allowed_formats = ['jpg', 'jpeg', 'png', 'gif', 'webp']
            file_extension = value.name.split('.')[-1].lower()
            if file_extension not in allowed_formats:
                raise serializers.ValidationError(
                    f"Only {', '.join(allowed_formats).upper()} files are allowed."
                )
        return value
    
    def validate(self, attrs):
        """Overall validation"""
        # Ensure at least one field is being updated
        if not any(attrs.values()):
            raise serializers.ValidationError(
                "At least one field must be updated."
            )
        
        # Ensure company description is provided for better profile completion
        if 'description' in attrs and len(attrs.get('description', '').strip()) < 50:
            raise serializers.ValidationError({
                'description': 'Company description should be at least 50 characters long.'
            })
        
        return attrs
    
    def update(self, instance, validated_data):
        """Custom update with slug regeneration and logging"""
        # Store old values for comparison
        old_company_name = instance.company_name
        
        # If company name changed, regenerate slug
        if 'company_name' in validated_data:
            company_name = validated_data['company_name']
            base_slug = slugify(company_name)
            slug = base_slug
            
            # Ensure slug uniqueness
            counter = 1
            while EmployerProfile.objects.filter(slug=slug).exclude(id=instance.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            validated_data['slug'] = slug
        
        instance = super().update(instance, validated_data)
        
        # Log significant changes (you can implement logging here)
        if old_company_name != instance.company_name:
            pass  # Add logging here if needed
            
        return instance

class EmployerProfileSerializer(serializers.ModelSerializer):
    """Main employer profile serializer for create/update/retrieve operations"""
    user = UserBasicSerializer(read_only=True)
    logo_url = serializers.SerializerMethodField()
    total_jobs = serializers.SerializerMethodField()
    active_jobs = serializers.SerializerMethodField()
    total_applications = serializers.SerializerMethodField()
    company_url = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployerProfile
        fields = [
            'id', 'user', 'company_name', 'slug', 'designation', 
            'description', 'website', 'logo', 'logo_url', 'created_at', 
            'updated_at', 'active_jobs_count', 'total_applications_count',
            'total_jobs', 'active_jobs', 'total_applications', 'company_url'
        ]
        read_only_fields = [
            'id', 'user', 'slug', 'created_at', 'updated_at', 
            'active_jobs_count', 'total_applications_count'
        ]
        extra_kwargs = {
            'logo': {'validators': [validate_image]},
            'company_name': {'required': True, 'allow_blank': False},
            'designation': {'required': True, 'allow_blank': False},
        }

    def get_logo_url(self, obj):
        """Get full URL for company logo"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_total_jobs(self, obj):
        """Get total number of jobs posted by this employer"""
        if hasattr(obj, '_total_jobs'):
            return obj._total_jobs
        return getattr(obj, 'job_posts', obj.job_posts.all()).count()

    def get_active_jobs(self, obj):
        """Get number of active jobs"""
        if hasattr(obj, '_active_jobs'):
            return obj._active_jobs
        return getattr(obj, 'job_posts', obj.job_posts.all()).filter(
            is_active=True, 
            deadline__gte=timezone.now().date()
        ).count()

    def get_total_applications(self, obj):
        """Get total applications received"""
        if hasattr(obj, '_total_applications'):
            return obj._total_applications
        return obj.total_applications_count

    def get_company_url(self, obj):
        """Get company profile URL"""
        request = self.context.get('request')
        if request and obj.slug:
            from django.urls import reverse
            try:
                return request.build_absolute_uri(
                    reverse('employer-detail', kwargs={'pk': obj.pk})
                )
            except:
                return None
        return None

    def validate_website(self, value):
        """Validate website URL"""
        if value and not value.startswith(('http://', 'https://')):
            value = f'https://{value}'
        return value

    def validate_company_name(self, value):
        """Validate company name uniqueness (excluding current instance)"""
        if value:
            queryset = EmployerProfile.objects.filter(company_name__iexact=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    "A company with this name already exists."
                )
        return value

class EmployerProfileListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing employer profiles"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    active_jobs = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployerProfile
        fields = [
            'id', 'company_name', 'slug', 'designation', 'description',
            'logo_url', 'website', 'user_email', 'user_name', 'created_at',
            'active_jobs_count', 'active_jobs'
        ]

    def get_user_name(self, obj):
        """Get user's full name"""
        if obj.user.first_name or obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.email

    def get_logo_url(self, obj):
        """Get company logo URL"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_active_jobs(self, obj):
        """Get active jobs count with caching"""
        return getattr(obj, '_active_jobs_count', obj.active_jobs_count)

class EmployerLeadershipSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = EmployerLeadership
        fields = ['id', 'position', 'name', 'bio', 'linkedin', 'photo', 'photo_url']  # ✅ add 'photo'

        extra_kwargs = {
            "photo": {"write_only": True}  # optional, if you don’t want to expose raw file path
        }

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and hasattr(obj.photo, "url"):
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None

# ============================================================================
# JOB APPLICATION SERIALIZERS
# ============================================================================

class JobApplicationSerializer(serializers.ModelSerializer):
    """Serializer for job applications in employer dashboard"""
    applicant_name = serializers.SerializerMethodField()
    applicant_email = serializers.CharField(source='applicant.email', read_only=True)
    job_title = serializers.CharField(source='job_post.title', read_only=True)
    job_slug = serializers.CharField(source='job_post.slug', read_only=True)
    resume_url = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_since_applied = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = [
            'id', 'applicant_name', 'applicant_email', 'job_title', 'job_slug',
            'cover_letter', 'resume_url', 'status', 'status_display', 
            'is_fit', 'fit_score', 'remarks', 'applied_at', 'reviewed_at',
            'days_since_applied'
        ]
        read_only_fields = ['id', 'applied_at']

    def get_applicant_name(self, obj):
        """Get applicant's full name"""
        if obj.applicant.first_name or obj.applicant.last_name:
            return f"{obj.applicant.first_name} {obj.applicant.last_name}".strip()
        return obj.applicant.email

    def get_resume_url(self, obj):
        """Get resume download URL"""
        if obj.resume:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.resume.url)
            return obj.resume.url
        return None

    def get_days_since_applied(self, obj):
        """Calculate days since application"""
        return (timezone.now() - obj.applied_at).days

# ============================================================================
# JOB POST SERIALIZERS
# ============================================================================

class JobPostSerializer(serializers.ModelSerializer):
    """Complete serializer for creating and updating job posts"""
    # Read-only fields computed from relationships
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_logo = serializers.URLField(source='company.logo.url', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    # Computed fields
    applications_count = serializers.IntegerField(read_only=True)
    views_count = serializers.IntegerField(read_only=True)
    days_until_deadline = serializers.SerializerMethodField(read_only=True)
    is_expired = serializers.SerializerMethodField(read_only=True)
    is_deadline_soon = serializers.SerializerMethodField(read_only=True)
    salary_display = serializers.SerializerMethodField(read_only=True)
    
    # Make slug read-only since it's auto-generated
    slug = serializers.SlugField(read_only=True)
    
    class Meta:
        model = JobPost
        fields = [
            # IDs and metadata (read-only)
            'id', 'slug', 'created_at', 'updated_at',
            
            # Company info (read-only)
            'company_name', 'company_logo', 'created_by_name',
            
            # Editable basic info
            'title', 'description',
            
            # Editable job details
            'employment_type', 'experience_level', 'working_mode', 'location',
            
            # Editable salary
            'salary_min', 'salary_max', 'salary_display',
            
            # Editable requirements
            'required_skills', 'screening_questions',
            
            # Editable dates and status
            'deadline', 'is_active', 'is_featured',
            
            # Computed fields (read-only)
            'applications_count', 'views_count', 'days_until_deadline', 
            'is_expired', 'is_deadline_soon',
        ]
        read_only_fields = [
            'id', 'slug', 'created_at', 'updated_at', 'company_name', 'company_logo', 
            'created_by_name', 'applications_count', 'views_count', 'days_until_deadline', 
            'is_expired', 'is_deadline_soon', 'salary_display'
        ]

    def get_days_until_deadline(self, obj):
        """Calculate days until deadline (can be negative for expired jobs)"""
        if obj.deadline:
            today = timezone.now().date()
            delta = obj.deadline - today
            return delta.days
        return None

    def get_is_expired(self, obj):
        """Check if job posting has expired"""
        if obj.deadline:
            return obj.deadline < timezone.now().date()
        return False

    def get_is_deadline_soon(self, obj):
        """Check if deadline is within 7 days"""
        days_left = self.get_days_until_deadline(obj)
        return days_left is not None and 0 <= days_left <= 7

    def get_salary_display(self, obj):
        """Format salary range for display"""
        if obj.salary_min and obj.salary_max:
            return f"${obj.salary_min:,} - ${obj.salary_max:,}"
        elif obj.salary_min:
            return f"${obj.salary_min:,}+"
        elif obj.salary_max:
            return f"Up to ${obj.salary_max:,}"
        return "Negotiable"

    def validate_deadline(self, value):
        """Validate that deadline is not in the past"""
        if value and value < timezone.now().date():
            raise serializers.ValidationError("Deadline cannot be in the past.")
        return value

    def validate_salary_min(self, value):
        """Validate minimum salary"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Minimum salary cannot be negative.")
        return value

    def validate_salary_max(self, value):
        """Validate maximum salary"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Maximum salary cannot be negative.")
        return value

    def validate_required_skills(self, value):
        """Validate required skills format"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Required skills must be a list.")
        if len(value) > 20:
            raise serializers.ValidationError("Maximum 20 skills allowed.")
        
        for skill in value:
            if not isinstance(skill, str) or len(skill.strip()) == 0:
                raise serializers.ValidationError("Each skill must be a non-empty string.")
            if len(skill) > 50:
                raise serializers.ValidationError("Each skill must be less than 50 characters.")
        
        return [skill.strip() for skill in value if skill.strip()]

    def validate_screening_questions(self, value):
        """Validate screening questions format"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Screening questions must be a list.")
        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 screening questions allowed.")
        
        for question in value:
            if not isinstance(question, dict):
                raise serializers.ValidationError("Each question must be an object.")
            if 'question' not in question or not question['question'].strip():
                raise serializers.ValidationError("Question text is required.")
            if len(question['question']) > 500:
                raise serializers.ValidationError("Question text must be less than 500 characters.")
        
        return value

    def validate(self, data):
        """Cross-field validation"""
        salary_min = data.get('salary_min')
        salary_max = data.get('salary_max')
        
        # If both salary fields are provided, min should not exceed max
        if salary_min is not None and salary_max is not None:
            if salary_min > salary_max:
                raise serializers.ValidationError({
                    'salary_min': 'Minimum salary cannot exceed maximum salary.'
                })
        
        return data

    def create(self, validated_data):
        """Create a new job post"""
        request = self.context.get('request')
        if request and request.user:
            if not hasattr(request.user, 'employer_profile'):
                raise serializers.ValidationError("Only employers can create job posts")
            
            validated_data['created_by'] = request.user
            validated_data['company'] = request.user.employer_profile
            validated_data['company_name'] = request.user.employer_profile.company_name
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update an existing job post"""
        # Prevent updating company-related fields
        validated_data.pop('company', None)
        validated_data.pop('created_by', None)
        validated_data.pop('company_name', None)
        
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        """Customize the output representation"""
        data = super().to_representation(instance)
        
        # Ensure required_skills is always a list
        if not data.get('required_skills'):
            data['required_skills'] = []
            
        # Ensure screening_questions is always a list
        if not data.get('screening_questions'):
            data['screening_questions'] = []
            
        return data

class JobPostListSerializer(serializers.ModelSerializer):
    """Complete serializer for job posts in dashboard listing"""
    applications_count = serializers.IntegerField(read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_logo = serializers.ImageField(source='company.company_logo', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    days_remaining = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    salary_display = serializers.SerializerMethodField()
    
    class Meta:
        model = JobPost
        fields = [
            # Basic info
            'id', 'title', 'slug', 'description',
            
            # Company info
            'company_name', 'company_logo', 'created_by_name',
            
            # Job details
            'employment_type', 'experience_level', 'working_mode', 'location',
            
            # Salary
            'salary_min', 'salary_max', 'salary_display',
            
            # Skills and requirements
            'required_skills', 'screening_questions',
            
            # Dates and deadlines
            'deadline', 'days_remaining', 'days_until_deadline', 'is_expired',
            'created_at',
            
            # Status and features
            'is_active', 'is_featured',
            
            # Metrics
            'applications_count', 'views_count',
        ]

    def get_days_remaining(self, obj):
        """Calculate days remaining until deadline"""
        if obj.deadline:
            remaining = (obj.deadline - timezone.now().date()).days
            return max(0, remaining)
        return None

    def get_days_until_deadline(self, obj):
        """Calculate days until deadline (can be negative for expired jobs)"""
        if obj.deadline:
            return (obj.deadline - timezone.now().date()).days
        return None

    def get_is_expired(self, obj):
        """Check if job posting has expired"""
        if obj.deadline:
            return obj.deadline < timezone.now().date()
        return False

    def get_salary_display(self, obj):
        """Format salary range for display"""
        if obj.salary_min and obj.salary_max:
            return f"${obj.salary_min:,} - ${obj.salary_max:,}"
        elif obj.salary_min:
            return f"${obj.salary_min:,}+"
        elif obj.salary_max:
            return f"Up to ${obj.salary_max:,}"
        return "Not specified"

# ============================================================================
# DASHBOARD AND STATISTICS SERIALIZERS
# ============================================================================

class EmployerDashboardSerializer(serializers.Serializer):
    """Serializer for employer dashboard data"""
    total_jobs = serializers.IntegerField()
    active_jobs = serializers.IntegerField()
    total_applications = serializers.IntegerField()
    pending_applications = serializers.IntegerField()
    shortlisted_applications = serializers.IntegerField()
    hired_candidates = serializers.IntegerField()
    recent_applications = JobApplicationSerializer(many=True, read_only=True)
    top_performing_jobs = JobPostListSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        """Add computed fields to dashboard data"""
        if isinstance(instance, dict):
            data = instance
        else:
            data = super().to_representation(instance)
        
        # Add percentage calculations
        total_apps = data.get('total_applications', 0)
        if total_apps > 0:
            data['conversion_metrics'] = {
                'shortlisting_rate': round((data.get('shortlisted_applications', 0) / total_apps) * 100, 2),
                'hiring_rate': round((data.get('hired_candidates', 0) / total_apps) * 100, 2),
                'pending_rate': round((data.get('pending_applications', 0) / total_apps) * 100, 2),
            }
        else:
            data['conversion_metrics'] = {
                'shortlisting_rate': 0,
                'hiring_rate': 0,
                'pending_rate': 0,
            }
        
        return data

class EmployerProfileStatsSerializer(serializers.Serializer):
    """Serializer for employer statistics endpoint"""
    total_jobs = serializers.IntegerField()
    active_jobs = serializers.IntegerField()
    total_applications = serializers.IntegerField()
    pending_applications = serializers.IntegerField()
    hired_count = serializers.IntegerField()

    def to_representation(self, instance):
        """Add additional computed statistics"""
        data = super().to_representation(instance)
        
        # Add averages and rates
        total_jobs = data.get('total_jobs', 0)
        total_apps = data.get('total_applications', 0)
        
        if total_jobs > 0:
            data['avg_applications_per_job'] = round(total_apps / total_jobs, 2)
        else:
            data['avg_applications_per_job'] = 0
            
        if total_apps > 0:
            data['hiring_success_rate'] = round((data.get('hired_count', 0) / total_apps) * 100, 2)
        else:
            data['hiring_success_rate'] = 0
            
        return data

class MonthlyApplicationsSerializer(serializers.Serializer):
    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user type"""
        try:
            print(f"Debug - User: {user.email}, Role: {user.role}")
            
            if user.role == 'employer':
                profile = getattr(user, 'employer_profile', None)
                print(f"Debug - Employer profile found: {profile}")
                return profile
                
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                if hr_record:
                    profile = hr_record.company
                    print(f"Debug - HR company profile found: {profile}")
                    return profile
                else:
                    print(f"Debug - No hr_user record found for {user.email}")
                    
            else:
                print(f"Debug - User role '{user.role}' not handled")
                
            return None
            
        except Exception as e:
            print(f"Error getting employer profile: {e}")
            return None

    def to_representation(self, instance):
        year = self.context.get('year', datetime.now().year)
        user = instance  # User instance
        
        # Debug information
        print(f"Processing user: {user.email}, Role: {user.role}")
        
        employer_profile = self.get_employer_profile(user)
        
        if not employer_profile:
            error_msg = f'No employer profile found for user {user.email} with role {user.role}'
            print(f"Error: {error_msg}")
            return {
                'error': error_msg,
                'monthly_data': [],
                'user_info': {
                    'email': user.email,
                    'role': user.role,
                    'has_employer_profile': hasattr(user, 'employer_profile'),
                    'has_hr_user': hasattr(user, 'hr_user')
                }
            }
        
        print(f"Found employer profile: {employer_profile.company_name}")
        
        try:
            # Get all JobPosts posted by this employer's company
            job_posts = employer_profile.job_posts.all()
            print(f"Found {job_posts.count()} job posts for company")
            
            # Get all JobApplications in that year, for those jobs
            monthly_data = JobApplication.objects.filter(
                applied_at__year=year,
                job_post__in=job_posts,
                is_deleted=False
            ).annotate(
                month=Extract('applied_at', 'month')
            ).values('month').annotate(
                applications=Count('id')
            ).order_by('month')
            
            print(f"Found applications data: {list(monthly_data)}")
            
            # Convert DB result to dict {1: 20, 2: 14, ...}
            month_counts = {item['month']: item['applications'] for item in monthly_data}
            
            # Prepare final result with all 12 months
            result = []
            for month_num in range(1, 13):
                result.append({
                    "month": month_name[month_num],
                    "applications": month_counts.get(month_num, 0)
                })
            
            return {
                'year': year,
                'company': employer_profile.company_name,
                'total_applications': sum(month_counts.values()),
                'monthly_data': result
            }
            
        except Exception as e:
            error_msg = f"Error processing monthly data: {str(e)}"
            print(error_msg)
            return {
                'error': error_msg,
                'monthly_data': []
            }
# ============================================================================
# HR USER SERIALIZERS
# ============================================================================

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'full_name', 'role', 'is_active']
        read_only_fields = ['id', 'email', 'role', 'is_active', 'full_name']
    
    def get_full_name(self, obj):
        """Return formatted full name"""
        return f"{obj.first_name} {obj.last_name}".strip()

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=True, max_length=150, allow_blank=False)
    last_name = serializers.CharField(required=True, max_length=150, allow_blank=False)

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'username', 'first_name', 'last_name']
        read_only_fields = ['id']
        extra_kwargs = {
            'first_name': {'required': True, 'allow_blank': False},
            'last_name': {'required': True, 'allow_blank': False},
            'email': {'required': True},
            'username': {'required': True},
        }

    def validate_first_name(self, value):
        """Validate first name"""
        if not value or not value.strip():
            raise serializers.ValidationError("First name is required and cannot be empty.")
        if len(value.strip()) < 2:
            raise serializers.ValidationError("First name must be at least 2 characters long.")
        return value.strip().title()

    def validate_last_name(self, value):
        """Validate last name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Last name is required and cannot be empty.")
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Last name must be at least 2 characters long.")
        return value.strip().title()

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data['role'] = User.Roles.HR  # Automatically set role to 'hr'
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)
    first_name = serializers.CharField(required=False, max_length=150)
    last_name = serializers.CharField(required=False, max_length=150)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'first_name', 'last_name']
        extra_kwargs = {
            'email': {'required': False, 'validators': []},  # Remove all validators
            'username': {'required': False, 'validators': []}  # Remove all validators
        }

    def validate_email(self, value):
        """Custom email validation that excludes current user"""
        if value and self.instance:
            # Check if another user (not current one) has this email
            if User.objects.filter(email=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_username(self, value):
        """Custom username validation that excludes current user"""
        if value and self.instance:
            # Check if another user (not current one) has this username
            if User.objects.filter(username=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("A user with this username already exists.")
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

class HRUserSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    permissions = serializers.SerializerMethodField()
    hr_full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = HRUser
        fields = [
            'id', 'user', 'company', 'company_name', 'role', 'hr_full_name',
            'can_post_jobs', 'can_view_applicants', 'can_edit_profile',
            'can_post_feed', 'can_manage_team', 'permissions',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'company_name', 'permissions', 'hr_full_name',
            'created_at', 'updated_at'
        ]
    
    def get_permissions(self, obj):
        return {
            'can_post_jobs': obj.can_post_jobs,
            'can_view_applicants': obj.can_view_applicants,
            'can_edit_profile': obj.can_edit_profile,
            'can_post_feed': obj.can_post_feed,
            'can_manage_team': obj.can_manage_team,
        }
    
    def get_hr_full_name(self, obj):
        """Get HR user's full name"""
        if obj.user and (obj.user.first_name or obj.user.last_name):
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.email if obj.user else "N/A"

class HRUserCreateSerializer(serializers.ModelSerializer):
    user = UserCreateSerializer()

    class Meta:
        model = HRUser
        fields = [
            'id', 'user', 'role', 'can_post_jobs', 'can_view_applicants',
            'can_edit_profile', 'can_post_feed', 'can_manage_team',
        ]
        read_only_fields = ['id']

    def validate(self, data):
        """Validate HR user creation data"""
        user_data = data.get('user', {})
        
        # Ensure first_name and last_name are provided
        if not user_data.get('first_name'):
            raise serializers.ValidationError({
                'user': {'first_name': 'First name is required for HR user registration.'}
            })
        
        if not user_data.get('last_name'):
            raise serializers.ValidationError({
                'user': {'last_name': 'Last name is required for HR user registration.'}
            })
        
        return data

    def create(self, validated_data):
        user_data = validated_data.pop('user')

        user_serializer = UserCreateSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        # Remove company if it exists in validated_data to avoid conflict
        validated_data.pop('company', None)

        request = self.context.get('request')
        if not request or not hasattr(request.user, 'employer_profile'):
            raise serializers.ValidationError("Authenticated employer user with company profile is required.")

        company = request.user.employer_profile
        hr_user = HRUser.objects.create(user=user, company=company, **validated_data)
        return hr_user

class HRUserUpdateSerializer(serializers.ModelSerializer):
    user = UserUpdateSerializer()

    class Meta:
        model = HRUser
        fields = [
            'id', 'user', 'role', 'can_post_jobs', 'can_view_applicants',
            'can_edit_profile', 'can_post_feed', 'can_manage_team',
        ]
        read_only_fields = ['id', 'company']

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', None)
        if user_data:
            user_serializer = UserUpdateSerializer(
                instance=instance.user,
                data=user_data,
                partial=True
            )
            user_serializer.is_valid(raise_exception=True)
            user_serializer.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

# Alternative simplified serializer for HR user listing
class HRUserListSerializer(serializers.ModelSerializer):
    """Simplified serializer for HR user listing"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_first_name = serializers.CharField(source='user.first_name', read_only=True)
    user_last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    class Meta:
        model = HRUser
        fields = [
            'id', 'user_email', 'user_first_name', 'user_last_name', 'full_name',
            'company_name', 'role', 'can_post_jobs', 'can_view_applicants',
            'can_edit_profile', 'can_post_feed', 'can_manage_team',
            'created_at', 'updated_at'
        ]
    
    def get_full_name(self, obj):
        """Get formatted full name"""
        if obj.user and (obj.user.first_name or obj.user.last_name):
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.email if obj.user else "N/A"
# ============================================================================
# COMPANY POST SERIALIZERS
# ============================================================================

class CommentLikeSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = CommentLike
        fields = ['id', 'comment', 'user', 'user_email', 'liked_at']
        read_only_fields = ['user_email']


class PostCommentSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    replies = serializers.SerializerMethodField()
    likes = CommentLikeSerializer(many=True, read_only=True)  # all likes on this comment

    class Meta:
        model = PostComment
        fields = [
            'id', 'post', 'user', 'user_email', 'parent', 'comment',
            'likes_count', 'replies_count', 'created_at',
            'replies', 'likes'
        ]
        read_only_fields = [
            'likes_count', 'replies_count', 'created_at',
            'replies', 'user_email', 'likes'
        ]

    def get_replies(self, obj):
        """Recursively fetch replies for a comment"""
        if obj.replies_count and obj.replies.exists():
            return PostCommentSerializer(obj.replies.all(), many=True).data
        return []


class PostLikeSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = PostLike
        fields = ['id', 'post', 'user', 'user_email', 'liked_at']
        read_only_fields = ['user_email']


class CompanyPostSerializer(serializers.ModelSerializer):
    """For creating/updating posts"""
    company_name = serializers.CharField(source='company.company_name', read_only=True)

    class Meta:
        model = CompanyPost
        fields = [
            'id', 'company', 'company_name', 'created_by', 'title', 'content',
            'image', 'video', 'video_url', 'external_link', 'category',
            'visibility', 'allow_comments', 'is_pinned', 'is_active',
            'likes_count', 'comments_count', 'views_count', 'shares_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'company', 'company_name', 'created_by',
            'likes_count', 'comments_count', 'views_count', 'shares_count',
            'created_at', 'updated_at'
        ]


class CompanyPostViewSerializer(serializers.ModelSerializer):
    """Detailed view serializer including comments and likes"""
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    liked_users_preview = serializers.SerializerMethodField()  # first few liked users
    comments = PostCommentSerializer(many=True, read_only=True)  # all comments

    class Meta:
        model = CompanyPost
        fields = [
            'id', 'company', 'company_name', 'created_by', 'title', 'slug',
            'content', 'image', 'video', 'document', 'video_url', 'external_link',
            'category', 'visibility', 'allow_comments', 'is_pinned', 'is_active',
            'likes_count', 'comments_count', 'views_count', 'shares_count',
            'liked_users_preview',   # 👈 added preview
            'comments',              # 👈 nested comments with likes
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'slug', 'likes_count', 'comments_count', 'views_count', 'shares_count',
            'created_at', 'updated_at', 'company_name',
            'liked_users_preview', 'comments'
        ]

    def get_liked_users_preview(self, obj):
        """Return first 3 liked users (email)"""
        likes = obj.likes_details.select_related("user").all()[:3]
        return [like.user.email for like in likes]

# class CompanyProfileViewSerializer(serializers.ModelSerializer):
#     user_email = serializers.CharField(source='user.email', read_only=True)
#     logo_url = serializers.SerializerMethodField()
#     banner_url = serializers.SerializerMethodField()
    
#     class Meta:
#         model = EmployerProfile
#         fields = [
#             'id', 'user_email', 'company_name', 'slug', 'designation', 
#             'description', 'website', 'logo_url', 'banner_url',
#             'active_jobs_count', 'total_applications_count', 'followers_count',
#             'created_at', 'updated_at'
#         ]

#     def get_logo_url(self, obj):
#         if obj.logo:
#             return self.context['request'].build_absolute_uri(obj.logo.url)
#         return None

#     def get_banner_url(self, obj):
#         if obj.banner:
#             return self.context['request'].build_absolute_uri(obj.banner.url)
#         return None

# class CompanyProfileEditSerializer(serializers.ModelSerializer):
#     logo_url = serializers.SerializerMethodField()
#     banner_url = serializers.SerializerMethodField()
    
#     class Meta:
#         model = EmployerProfile
#         fields = ['description', 'logo', 'banner', 'logo_url', 'banner_url']
#         extra_kwargs = {
#             'logo': {'validators': [validate_image], 'required': False},
#             'banner': {'validators': [validate_image], 'required': False},
#         }

#     def get_logo_url(self, obj):
#         if obj.logo:
#             return self.context['request'].build_absolute_uri(obj.logo.url)
#         return None

#     def get_banner_url(self, obj):
#         if obj.banner:
#             return self.context['request'].build_absolute_uri(obj.banner.url)
#         return None


class CompanyProfileViewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    user_permissions = serializers.SerializerMethodField()
    company_stats = serializers.SerializerMethodField()
    leadership_team = EmployerLeadershipSerializer(many=True, read_only=True)  # ✅ NESTED serializer

    class Meta:
        model = EmployerProfile
        fields = [
            'id', 'user_email', 'company_name', 'slug', 'designation',
            'description', 'website', 'logo_url', 'banner_url',
            'active_jobs_count', 'total_applications_count', 'followers_count',
            'created_at', 'updated_at',
            'user_permissions', 'company_stats',
            'leadership_team'   # ✅ will now return full nested data
        ]

    def get_logo_url(self, obj):
        if obj.logo:
            return self.context['request'].build_absolute_uri(obj.logo.url)
        return None

    def get_banner_url(self, obj):
        if obj.banner:
            return self.context['request'].build_absolute_uri(obj.banner.url)
        return None

    def get_user_permissions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return {
                'can_edit_profile': False,
                'can_manage_team': False,
                'can_post_jobs': False,
                'user_role': None
            }

        user = request.user

        if user.role == 'employer' and hasattr(user, 'employer_profile') and user.employer_profile == obj:
            return {
                'can_edit_profile': True,
                'can_manage_team': True,
                'can_post_jobs': True,
                'can_view_applicants': True,
                'can_post_feed': True,
                'user_role': 'employer',
                'is_owner': True
            }
        elif user.role == 'hr' and hasattr(user, 'hr_user') and user.hr_user.company == obj:
            hr_record = user.hr_user
            return {
                'can_edit_profile': hr_record.can_edit_profile,
                'can_manage_team': hr_record.can_manage_team,
                'can_post_jobs': hr_record.can_post_jobs,
                'can_view_applicants': hr_record.can_view_applicants,
                'can_post_feed': hr_record.can_post_feed,
                'user_role': 'hr',
                'hr_role': hr_record.role,
                'is_owner': False
            }

        return {
            'can_edit_profile': False,
            'can_manage_team': False,
            'can_post_jobs': False,
            'can_view_applicants': False,
            'can_post_feed': False,
            'user_role': user.role,
            'is_owner': False
        }

    def get_company_stats(self, obj):
        from django.utils import timezone
        cache_key = f"company_basic_stats_{obj.id}"
        stats = cache.get(cache_key)

        if not stats:
            now = timezone.now().date()
            stats = {
                'total_jobs': obj.job_posts.count(),
                'active_jobs': obj.job_posts.filter(
                    is_active=True,
                    deadline__gte=now
                ).count(),
                'total_hr_members': obj.hr_team.filter(is_deleted=False).count(),
                'last_job_posted': None
            }

            last_job = obj.job_posts.order_by('-created_at').first()
            if last_job:
                stats['last_job_posted'] = last_job.created_at.isoformat()

            cache.set(cache_key, stats, 600)

        return stats
    
class CompanyProfileEditSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    current_permissions = serializers.SerializerMethodField()

    class Meta:
        model = EmployerProfile
        fields = [
            'company_name', 'designation', 'description', 'website',
            'logo', 'banner', 'logo_url', 'banner_url', 'current_permissions'
        ]
        extra_kwargs = {
            'logo': {'required': False, 'allow_null': True, 'use_url': True},
            'banner': {'required': False, 'allow_null': True, 'use_url': True},
            'company_name': {'required': False, 'allow_blank': True},
            'designation': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True},
            'website': {'required': False, 'allow_blank': True},
        }

    def validate_logo(self, value):
        if value:
            validate_image(value)
        return value

    def validate_banner(self, value):
        if value:
            validate_image(value)
        return value

    def get_logo_url(self, obj):
        return self.context['request'].build_absolute_uri(obj.logo.url) if obj.logo else None

    def get_banner_url(self, obj):
        return self.context['request'].build_absolute_uri(obj.banner.url) if obj.banner else None

    def get_current_permissions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return {'can_edit': False}

        user = request.user
        if user.role == 'employer' and hasattr(user, 'employer_profile') and user.employer_profile == obj:
            return {
                'can_edit': True,
                'user_role': 'employer',
                'user_email': user.email
            }
        elif user.role == 'hr' and hasattr(user, 'hr_user') and user.hr_user.company == obj:
            hr_record = user.hr_user
            return {
                'can_edit': hr_record.can_edit_profile,
                'user_role': 'hr',
                'hr_role': hr_record.role,
                'user_email': user.email
            }
        return {'can_edit': False}

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        user = request.user
        if user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            if not hr_record or not hr_record.can_edit_profile:
                raise serializers.ValidationError("You don't have permission to edit the company profile")

        return attrs

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request and request.user:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Company profile updated: {instance.company_name} "
                f"by {request.user.email} ({request.user.role})"
            )
        return super().update(instance, validated_data)


class ApplicantSkillsSerializer(serializers.Serializer):
    """Serializer for applicant's skills from their resume"""
    skills = serializers.ListField(child=serializers.CharField(), read_only=True)
    
class AIRemarksSerializer(serializers.ModelSerializer):
    """Serializer for AI evaluation of the applicant"""
    fit_percentage = serializers.DecimalField(source='fit_score', max_digits=5, decimal_places=2, read_only=True)
    overall_recommendation = serializers.CharField(read_only=True)
    matching_skills = serializers.ListField(child=serializers.CharField(), read_only=True)
    missing_skills = serializers.ListField(child=serializers.CharField(), read_only=True)
    
    class Meta:
        model = AIRemarks
        fields = [
            'fit_level', 'fit_percentage', 'remarks', 'skills_match_score', 
            'experience_match_score', 'education_match_score', 'location_match_score',
            'interview_recommendation', 'overall_recommendation', 'matching_skills',
            'missing_skills', 'strengths', 'weaknesses', 'recommendations'
        ]

class JobApplicantSerializer(serializers.ModelSerializer):
    """Main serializer for viewing job applicants with all required fields"""
    
    # Candidate Information
    candidate_id = serializers.UUIDField(source='applicant.id', read_only=True)
    candidate_name = serializers.SerializerMethodField()
    candidate_email = serializers.EmailField(source='applicant.email', read_only=True)
    candidate_phone = serializers.CharField(source='applicant.jobseeker_profile.phone_number', read_only=True)
    
    # Application Details
    candidate_applied_for = serializers.CharField(source='job_post.title', read_only=True)
    applied_on = serializers.DateTimeField(source='applied_at', format='%B %d, %Y', read_only=True)
    status = serializers.CharField(read_only=True)
    
    # Skills Match Information
    candidate_skills = serializers.SerializerMethodField()
    skills_match = serializers.SerializerMethodField()
    
    # AI Remarks
    ai_remarks = serializers.SerializerMethodField()
    
    # Actions (can be customized based on status)
    available_actions = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = [
            'candidate_id', 'candidate_name', 'candidate_email', 'candidate_phone',
            'candidate_applied_for', 'applied_on', 'status', 'candidate_skills',
            'skills_match', 'ai_remarks', 'available_actions', 'resume', 'cover_letter'
        ]
    
    def get_candidate_name(self, obj):
        """Get full name of the candidate"""
        profile = getattr(obj.applicant, 'jobseeker_profile', None)
        if profile:
            return profile.full_name
        return f"{obj.applicant.first_name} {obj.applicant.last_name}".strip() or obj.applicant.email
    
    def get_candidate_skills(self, obj):
        """Extract skills from candidate's default resume"""
        try:
            profile = obj.applicant.jobseeker_profile
            default_resume = profile.resumes.filter(is_default=True, is_active=True).first()
            if default_resume and default_resume.skills_data:
                return default_resume.skills_data
            return []
        except:
            return []
    
    def get_skills_match(self, obj):
        """Get skills match percentage from AI remarks"""
        try:
            ai_remark = obj.job_post.ai_remarks.filter(job_seeker=obj.applicant.jobseeker_profile).first()
            if ai_remark and ai_remark.skills_match_score:
                return f"{ai_remark.skills_match_score}%"
            return "Not analyzed"
        except:
            return "Not available"
    
    def get_ai_remarks(self, obj):
        """Get AI evaluation for this candidate"""
        try:
            ai_remark = obj.job_post.ai_remarks.filter(job_seeker=obj.applicant.jobseeker_profile).first()
            if ai_remark:
                return AIRemarksSerializer(ai_remark).data
            return None
        except:
            return None
    
    def get_available_actions(self, obj):
        """Return available actions based on current status"""
        actions = []
        
        if obj.status == 'applied':
            actions.extend(['review', 'shortlist', 'reject'])
        elif obj.status == 'under_review':
            actions.extend(['shortlist', 'schedule_interview', 'reject'])
        elif obj.status == 'shortlisted':
            actions.extend(['schedule_interview', 'reject'])
        elif obj.status == 'interview_scheduled':
            actions.extend(['make_offer', 'reject'])
        elif obj.status == 'offer_made':
            actions.extend(['hire', 'withdraw_offer'])
        
        actions.append('view_profile')  # Always available
        actions.append('download_resume')  # Always available
        
        return actions

class JobApplicationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing multiple applications"""
    
    candidate_name = serializers.SerializerMethodField()
    candidate_email = serializers.EmailField(source='applicant.email', read_only=True)
    position = serializers.CharField(source='job_post.title', read_only=True)
    applied_date = serializers.DateTimeField(source='applied_at', format='%b %d, %Y', read_only=True)
    fit_score = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = [
            'id', 'candidate_name', 'candidate_email', 'position',
            'applied_date', 'status', 'fit_score'
        ]
    
    def get_candidate_name(self, obj):
        profile = getattr(obj.applicant, 'jobseeker_profile', None)
        if profile:
            return profile.full_name
        return obj.applicant.email
    
    def get_fit_score(self, obj):
        try:
            ai_remark = obj.job_post.ai_remarks.filter(job_seeker=obj.applicant.jobseeker_profile).first()
            if ai_remark and ai_remark.fit_score:
                return f"{ai_remark.fit_score}%"
            return "Pending"
        except:
            return "N/A"
        
class JobPostListSerializer(serializers.ModelSerializer):
    """Simple serializer for listing job posts with ID and title only"""
    
    job_id = serializers.UUIDField(source='id', read_only=True)
    job_title = serializers.CharField(source='title', read_only=True)
    company_name = serializers.CharField(read_only=True)
    created_date = serializers.DateTimeField(source='created_at', format='%B %d, %Y', read_only=True)
    applications_count = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = JobPost
        fields = [
            'job_id', 'job_title', 'company_name', 'created_date', 
            'applications_count', 'is_active'
        ]

class JobPostDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual job post view"""
    
    job_id = serializers.UUIDField(source='id', read_only=True)
    job_title = serializers.CharField(source='title', read_only=True)
    created_by_user = serializers.CharField(source='created_by.email', read_only=True)
    total_applications = serializers.IntegerField(source='applications_count', read_only=True)
    
    class Meta:
        model = JobPost
        fields = [
            'job_id', 'job_title', 'company_name', 'employment_type',
            'experience_level', 'working_mode', 'location', 'salary_min',
            'salary_max', 'deadline', 'required_skills', 'description',
            'created_by_user', 'total_applications', 'is_active', 'is_featured'
        ]


class JobSeekerProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)  # ✅ fix here
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = JobSeekerProfile
        fields = [
            "id", "full_name", "first_name", "last_name", "email",
            "phone_number", "city", "state", "country", "headline", "summary",
            "preferred_job_types", "preferred_locations", "expected_salary",
            "linkedin_url", "portfolio_url"
        ]


class AIRemarksSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIRemarks
        fields = [
            "fit_score", "fit_level", "remarks", "overall_recommendation",
            "skills_match_score", "experience_match_score",
            "education_match_score", "location_match_score",
            "confidence_score", "strengths", "weaknesses",
            "missing_skills", "matching_skills", "recommendations"
        ]


class JobApplicationSerializer(serializers.ModelSerializer):
    applicant_profile = JobSeekerProfileSerializer(source="applicant.jobseeker_profile", read_only=True)
    ai_remarks = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id", "status", "applied_at", "cover_letter", "resume",
            "applicant_profile", "ai_remarks"
        ]

    def get_ai_remarks(self, obj):
        """Return AI remarks if available"""
        try:
            remark = obj.job_post.ai_remarks.get(job_seeker=obj.applicant.jobseeker_profile)
            return AIRemarksSerializer(remark).data
        except AIRemarks.DoesNotExist:
            return None

class ApplicationRemarkSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.get_full_name", read_only=True)
    reviewer_email = serializers.EmailField(source="reviewer.email", read_only=True)

    class Meta:
        model = ApplicationRemark
        fields = [
            'id',
            'application',
            'reviewer',
            'reviewer_name',
            'reviewer_email',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reviewer', 'created_at', 'updated_at']
        
class ResumeSerializer(serializers.ModelSerializer):
    total_experience_display = serializers.ReadOnlyField()

    class Meta:
        model = Resume
        exclude = ['profile']   # avoid circular nesting


class JobApplicationDetailCompositeSerializer(serializers.ModelSerializer):
    """Composite serializer to return full application detail"""
    ai_section = serializers.SerializerMethodField()
    resume_section = serializers.SerializerMethodField()
    profile_section = serializers.SerializerMethodField()
    remarks_section = ApplicationRemarkSerializer(many=True, read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id',
            'status',
            'applied_at',
            'cover_letter',
            'ai_section',
            'resume_section',
            'profile_section',
            'remarks_section',
        ]

    def get_ai_section(self, obj):
        ai_remark = AIRemarks.objects.filter(
            job_post=obj.job_post, job_seeker=obj.applicant.jobseeker_profile
        ).first()
        return AIRemarksSerializer(ai_remark).data if ai_remark else None

    def get_resume_section(self, obj):
        resume = Resume.objects.filter(
            profile=obj.applicant.jobseeker_profile,
            is_default=True
        ).first()
        return ResumeSerializer(resume).data if resume else None

    def get_profile_section(self, obj):
        return JobSeekerProfileSerializer(obj.applicant.jobseeker_profile).data









class AIRemarksSerializers(serializers.ModelSerializer):
    overall_recommendation = serializers.ReadOnlyField()
    score_breakdown = serializers.ReadOnlyField()

    class Meta:
        model = AIRemarks
        fields = [
            "id",
            "is_fit",
            "fit_score",
            "fit_level",
            "remarks",
            "skills_match_score",
            "experience_match_score",
            "education_match_score",
            "location_match_score",
            "analysis_status",
            "ai_model_version",
            "confidence_score",
            "strengths",
            "weaknesses",
            "missing_skills",
            "matching_skills",
            "recommendations",
            "interview_recommendation",
            "suggested_interview_questions",
            "potential_concerns",
            "salary_expectation_alignment",
            "analysis_duration_seconds",
            "error_message",
            "created_at",
            "updated_at",
            "analyzed_at",
            "reviewed_by_human",
            "human_override",
            "human_remarks",
            "overall_recommendation",
            "score_breakdown",
        ]


class ResumeSerializers(serializers.ModelSerializer):
    total_experience_display = serializers.ReadOnlyField()

    class Meta:
        model = Resume
        fields = [
            "id",
            "title",
            "is_default",
            "is_active",
            "experience_level",
            "total_experience_years",
            "total_experience_months",
            "total_experience_display",
            "current_company",
            "current_designation",
            "current_salary",
            "notice_period",
            "education_data",
            "work_experience_data",
            "skills_data",
            "certifications_data",
            "projects_data",
            "languages_data",
            "achievements_data",
            "resume_pdf",
            "resume_doc",
            "cover_letter",
            "view_count",
            "download_count",
            "completion_percentage",
            "keywords",
            "created_at",
            "updated_at",
            "last_accessed",
        ]


class JobSeekerProfileSerializers(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = JobSeekerProfile
        fields = [
            "id",
            "full_name",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "phone_number",
            "profile_picture",
            "address_line_1",
            "city",
            "state",
            "country",
            "postal_code",
            "headline",
            "summary",
            "job_status",
            "preferred_job_types",
            "preferred_locations",
            "expected_salary",
            "willing_to_relocate",
            "profile_picture",
            "linkedin_url",
            "portfolio_url",
            "profile_visibility",
            "allow_recruiter_contact",
            "preferred_roles",
            "dream_companies",
            "created_at",
            "updated_at",
        ]


class SimpleApplicationSerializers(serializers.ModelSerializer):
    applicant_email = serializers.SerializerMethodField()
    reviewed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "status",
            "is_fit",
            "fit_score",
            "remarks",
            "cover_letter",
            "description",
            "applied_at",
            "reviewed_at",
            "applicant_email",
            "reviewed_by_email",
        ]

    def get_applicant_email(self, obj):
        return getattr(obj.applicant, "email", None)

    def get_reviewed_by_email(self, obj):
        return getattr(obj.reviewed_by, "email", None)


class ApplicationRemarkSerializers(serializers.ModelSerializer):
    reviewer_email = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationRemark
        fields = ["id", "remark", "reviewer_email", "created_at", "updated_at"]

    def get_reviewer_email(self, obj):
        return getattr(obj.reviewer, "email", None)


class ApplicationProfileViewSerializer(serializers.Serializer):
    # Composite serializer for the endpoint response
    ai_analysis = AIRemarksSerializers(allow_null=True)
    resume = ResumeSerializers(allow_null=True)
    profile = JobSeekerProfileSerializers()
    application = SimpleApplicationSerializers()
    remarks = ApplicationRemarkSerializers(many=True)