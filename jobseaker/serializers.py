# jobseeker/serializers.py
from rest_framework import serializers
from .models import JobSeekerProfile, Resume
from hyresensemain.models import User
from .utils.resume_parser import ResumeParser
from django.db import transaction
from django.utils import timezone

from employer.models import *

import os
import tempfile
from employer.models import JobPost, JobApplication
from .models import  JobSeekerProfile, Resume
import logging

logger = logging.getLogger(__name__)


class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email']  # no username now

class JobSeekerProfileCreateSerializer(serializers.ModelSerializer):
    user = UserCreateSerializer()

    class Meta:
        model = JobSeekerProfile
        exclude = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user = UserCreateSerializer().create(user_data)
        jobseeker_profile = JobSeekerProfile.objects.create(user=user, **validated_data)
        return jobseeker_profile




class ResumeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        exclude = [ 'profile','completion_percentage', 'created_at', 'updated_at']



# serializers.py



class ResumeUploadSerializer(serializers.Serializer):
    resume_file = serializers.FileField()

    def validate_resume_file(self, value):
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ['.pdf', '.docx', '.txt']:
            raise serializers.ValidationError("File must be PDF, DOCX, or TXT only")
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Max file size is 10MB")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        resume_file = validated_data['resume_file']
        ext = os.path.splitext(resume_file.name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            for chunk in resume_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        try:
            parser = ResumeParser()
            profile, resume, parsed_data = parser.parse_resume_file(temp_path, user)
            return {'profile': profile, 'resume': resume, 'parsed': parsed_data}
        finally:
            os.unlink(temp_path)





class JobMatchingSerializer(serializers.ModelSerializer):
    match_score = serializers.SerializerMethodField()
    matching_skills = serializers.SerializerMethodField()
    salary_match = serializers.SerializerMethodField()
    location_match = serializers.SerializerMethodField()
    
    class Meta:
        model = JobPost
        fields = [
            'id', 'title', 'company_name', 'location', 'employment_type',
            'salary_min', 'salary_max', 'required_skills', 'experience_level',
            'match_score', 'matching_skills', 'salary_match', 'location_match'
        ]
    
    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None)
        self.user_resume = kwargs.pop('user_resume', None)
        super().__init__(*args, **kwargs)
    
    def get_match_score(self, obj):
        if not self.user_profile or not self.user_resume:
            return 0
        
        score = 0
        
        # Location match (25%)
        if self.user_profile.preferred_locations:
            for loc in self.user_profile.preferred_locations:
                if loc.lower() in obj.location.lower():
                    score += 25
                    break
        
        # Job type match (20%)
        if obj.employment_type in (self.user_profile.preferred_job_types or []):
            score += 20
        
        # Skills match (35%)
        user_skills = self._get_user_skills()
        job_skills = obj.required_skills or []
        if user_skills and job_skills:
            matching = set(s.lower() for s in user_skills) & set(s.lower() for s in job_skills)
            if job_skills:
                score += (len(matching) / len(job_skills)) * 35
        
        # Salary match (20%)
        if self.user_profile.expected_salary and obj.salary_max:
            if obj.salary_max >= self.user_profile.expected_salary:
                score += 20
            elif obj.salary_max >= self.user_profile.expected_salary * 0.8:
                score += 10
        
        return round(score, 1)
    
    def get_matching_skills(self, obj):
        user_skills = self._get_user_skills()
        job_skills = obj.required_skills or []
        if user_skills and job_skills:
            return list(set(s.lower() for s in user_skills) & set(s.lower() for s in job_skills))
        return []
    
    def get_salary_match(self, obj):
        if not self.user_profile.expected_salary or not obj.salary_max:
            return None
        return obj.salary_max >= self.user_profile.expected_salary
    
    def get_location_match(self, obj):
        if not self.user_profile.preferred_locations:
            return None
        return any(loc.lower() in obj.location.lower() for loc in self.user_profile.preferred_locations)
    
    def _get_user_skills(self):
        if not self.user_resume or not self.user_resume.skills_data:
            return []
        
        skills = []
        for skill_data in self.user_resume.skills_data:
            if isinstance(skill_data, dict):
                for category, skill_list in skill_data.items():
                    skills.extend(skill_list)
            elif isinstance(skill_data, list):
                skills.extend(skill_data)
        return skills




class JobApplicationSerializer(serializers.ModelSerializer):
    job_post_id = serializers.IntegerField(write_only=True)
    applicant_name = serializers.CharField(source='applicant.get_full_name', read_only=True)
    job_title = serializers.CharField(source='job_post.title', read_only=True)
    
    class Meta:
        model = JobApplication
        fields = [
            'id', 'job_post_id', 'cover_letter', 'resume', 
            'description', 'status', 'applied_at', 
            'applicant_name', 'job_title'
        ]
        read_only_fields = ['id', 'status', 'applied_at', 'applicant_name', 'job_title']
        
    def validate_job_post_id(self, value):
        """Validate job post exists and is active"""
        try:
            job_post = JobPost.objects.get(id=value, is_active=True)
            if hasattr(job_post, 'deadline') and job_post.deadline and job_post.deadline < timezone.now():
                raise serializers.ValidationError("Job application deadline has passed.")
            return value
        except JobPost.DoesNotExist:
            raise serializers.ValidationError("Invalid job post or job post is no longer active.")
    
    def validate(self, attrs):
        """Custom validation for the entire object"""
        request = self.context.get('request')
        job_post_id = attrs.get('job_post_id')
        
        # Check if user already applied to this job
        if JobApplication.objects.filter(
            job_post_id=job_post_id, 
            applicant=request.user,
            is_deleted=False
        ).exists():
            raise serializers.ValidationError("You have already applied to this job.")
            
        # Validate user role
        if request.user.role != 'jobseeker':
            raise serializers.ValidationError("Only jobseekers can apply to jobs.")
            
        return attrs
    
    def create(self, validated_data):
        """Create job application with proper error handling"""
        request = self.context.get('request')
        job_post_id = validated_data.pop('job_post_id')
        
        try:
            with transaction.atomic():
                job_post = JobPost.objects.get(id=job_post_id)
                application = JobApplication.objects.create(
                    job_post=job_post,
                    applicant=request.user,
                    status='applied',
                    **validated_data
                )
                
                logger.info(f"Job application created: {application.id} by user {request.user.id}")
                return application
                
        except Exception as e:
            logger.error(f"Error creating job application: {str(e)}")
            raise serializers.ValidationError("Failed to submit application. Please try again.")


class JobApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobApplication
        fields = [
            'id', 'job_post', 'applicant', 'cover_letter', 
            'resume', 'status', 'description', 'reviewed_by', 
            'reviewed_at', 'applied_at'
        ]
        read_only_fields = ['id', 'applied_at', 'reviewed_by', 'reviewed_at', 'applicant', 'resume']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make description optional
        self.fields['description'].required = False
        self.fields['description'].allow_blank = True

class JobPostSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = JobPost
        fields = [
            'id',
            'title',
            'slug',
            'company_name',
            'created_by_name',
            'employment_type',
            'experience_level',
            'working_mode',
            'location',
            'salary_min',
            'salary_max',
            'deadline',
            'required_skills',
            'screening_questions',
            'description',
            'applications_count',
            'views_count',
            'is_active',
            'is_featured',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['slug', 'applications_count', 'views_count', 'created_at', 'updated_at']
    
    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None
    

class JobApplicationComprehensiveSerializer(serializers.ModelSerializer):
    # Complete Job Post data
    job_title = serializers.CharField(source='job_post.title')
    job_slug = serializers.CharField(source='job_post.slug')
    company_name = serializers.CharField(source='job_post.company_name')
    employment_type = serializers.CharField(source='job_post.employment_type')
    employment_type_display = serializers.CharField(source='job_post.get_employment_type_display')
    experience_level = serializers.CharField(source='job_post.experience_level')
    experience_level_display = serializers.CharField(source='job_post.get_experience_level_display')
    working_mode = serializers.CharField(source='job_post.working_mode')
    working_mode_display = serializers.CharField(source='job_post.get_working_mode_display')
    location = serializers.CharField(source='job_post.location')
    salary_min = serializers.IntegerField(source='job_post.salary_min')
    salary_max = serializers.IntegerField(source='job_post.salary_max')
    deadline = serializers.DateField(source='job_post.deadline')
    required_skills = serializers.JSONField(source='job_post.required_skills')
    screening_questions = serializers.JSONField(source='job_post.screening_questions')
    job_description = serializers.CharField(source='job_post.description')
    applications_count = serializers.IntegerField(source='job_post.applications_count')
    views_count = serializers.IntegerField(source='job_post.views_count')
    is_active = serializers.BooleanField(source='job_post.is_active')
    is_featured = serializers.BooleanField(source='job_post.is_featured')
    job_created_at = serializers.DateTimeField(source='job_post.created_at')
    
    # Complete Company data
    company_logo = serializers.SerializerMethodField()
    company_website = serializers.SerializerMethodField()
    company_location = serializers.SerializerMethodField()
    company_address = serializers.SerializerMethodField()
    company_city = serializers.SerializerMethodField()
    company_state = serializers.SerializerMethodField()
    company_country = serializers.SerializerMethodField()
    company_phone = serializers.SerializerMethodField()
    company_email = serializers.SerializerMethodField()
    company_industry = serializers.SerializerMethodField()
    company_size = serializers.SerializerMethodField()
    company_description = serializers.SerializerMethodField()
    company_founded_year = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    
    # Application status details
    status_display = serializers.CharField(source='get_status_display')
    reviewed_by_name = serializers.SerializerMethodField()
    reviewed_by_email = serializers.SerializerMethodField()
    
    # Resume info
    resume_name = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()
    
    # Timeline calculations
    days_since_applied = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    is_deadline_passed = serializers.SerializerMethodField()
    salary_range = serializers.SerializerMethodField()
    
    # Complete AI Analysis
    ai_analysis = serializers.SerializerMethodField()
    
    # Company methods - Return URLs for files
    def get_company_logo(self, obj):
        try:
            if obj.job_post.company and obj.job_post.company.logo:
                request = self.context.get('request')
                return request.build_absolute_uri(obj.job_post.company.logo.url) if request else obj.job_post.company.logo.url
        except:
            pass
        return None
    
    def get_company_website(self, obj):
        try:
            return str(obj.job_post.company.website) if obj.job_post.company and obj.job_post.company.website else None
        except:
            return None
    
    def get_company_location(self, obj):
        try:
            return str(obj.job_post.company.location) if obj.job_post.company and obj.job_post.company.location else None
        except:
            return None
    
    def get_company_address(self, obj):
        try:
            return str(obj.job_post.company.address) if obj.job_post.company and obj.job_post.company.address else None
        except:
            return None
    
    def get_company_city(self, obj):
        try:
            return str(obj.job_post.company.city) if obj.job_post.company and obj.job_post.company.city else None
        except:
            return None
    
    def get_company_state(self, obj):
        try:
            return str(obj.job_post.company.state) if obj.job_post.company and obj.job_post.company.state else None
        except:
            return None
    
    def get_company_country(self, obj):
        try:
            return str(obj.job_post.company.country) if obj.job_post.company and obj.job_post.company.country else None
        except:
            return None
    
    def get_company_phone(self, obj):
        try:
            return str(obj.job_post.company.phone) if obj.job_post.company and obj.job_post.company.phone else None
        except:
            return None
    
    def get_company_email(self, obj):
        try:
            return str(obj.job_post.company.email) if obj.job_post.company and obj.job_post.company.email else None
        except:
            return None
    
    def get_company_industry(self, obj):
        try:
            return str(obj.job_post.company.industry) if obj.job_post.company and obj.job_post.company.industry else None
        except:
            return None
    
    def get_company_size(self, obj):
        try:
            return str(obj.job_post.company.size) if obj.job_post.company and obj.job_post.company.size else None
        except:
            return None
    
    def get_company_description(self, obj):
        try:
            return str(obj.job_post.company.description) if obj.job_post.company and obj.job_post.company.description else None
        except:
            return None
    
    def get_company_founded_year(self, obj):
        try:
            return int(obj.job_post.company.founded_year) if obj.job_post.company and obj.job_post.company.founded_year else None
        except:
            return None
    
    def get_is_verified(self, obj):
        try:
            return bool(obj.job_post.company.is_verified) if obj.job_post.company else False
        except:
            return False
    
    # Application methods
    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else None
    
    def get_reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else None
    
    def get_resume_name(self, obj):
        try:
            if obj.resume and obj.resume.name:
                return obj.resume.name.split('/')[-1]
        except:
            pass
        return None
    
    def get_resume_url(self, obj):
        try:
            if obj.resume:
                request = self.context.get('request')
                return request.build_absolute_uri(obj.resume.url) if request else obj.resume.url
        except:
            pass
        return None
    
    def get_days_since_applied(self, obj):
        return (timezone.now() - obj.applied_at).days
    
    def get_days_until_deadline(self, obj):
        if obj.job_post.deadline:
            return (obj.job_post.deadline - timezone.now().date()).days
        return None
    
    def get_is_deadline_passed(self, obj):
        return obj.job_post.deadline < timezone.now().date() if obj.job_post.deadline else False
    
    def get_salary_range(self, obj):
        min_sal = obj.job_post.salary_min
        max_sal = obj.job_post.salary_max
        if min_sal and max_sal:
            return f"₹{min_sal:,} - ₹{max_sal:,}"
        elif min_sal:
            return f"₹{min_sal:,}+"
        elif max_sal:
            return f"Up to ₹{max_sal:,}"
        return "Not specified"
    
    def get_ai_analysis(self, obj):
        try:
            ai_remark = obj.job_post.ai_remarks.filter(job_seeker__user=obj.applicant).first()
            if ai_remark:
                return {
                    'id': str(ai_remark.id),
                    'is_fit': ai_remark.is_fit,
                    'fit_score': float(ai_remark.fit_score) if ai_remark.fit_score else None,
                    'fit_level': ai_remark.fit_level,
                    'fit_level_display': getattr(ai_remark, 'get_fit_level_display', lambda: ai_remark.fit_level)(),
                    'remarks': ai_remark.remarks,
                    'skills_match_score': float(ai_remark.skills_match_score) if ai_remark.skills_match_score else None,
                    'experience_match_score': float(ai_remark.experience_match_score) if ai_remark.experience_match_score else None,
                    'education_match_score': float(ai_remark.education_match_score) if ai_remark.education_match_score else None,
                    'location_match_score': float(ai_remark.location_match_score) if ai_remark.location_match_score else None,
                    'analysis_status': ai_remark.analysis_status,
                    'analysis_status_display': getattr(ai_remark, 'get_analysis_status_display', lambda: ai_remark.analysis_status)(),
                    'ai_model_version': ai_remark.ai_model_version,
                    'confidence_score': float(ai_remark.confidence_score) if ai_remark.confidence_score else None,
                    'strengths': ai_remark.strengths,
                    'weaknesses': ai_remark.weaknesses,
                    'missing_skills': ai_remark.missing_skills,
                    'matching_skills': ai_remark.matching_skills,
                    'recommendations': ai_remark.recommendations,
                    'interview_recommendation': ai_remark.interview_recommendation,
                    'suggested_interview_questions': ai_remark.suggested_interview_questions,
                    'potential_concerns': ai_remark.potential_concerns,
                    'salary_expectation_alignment': ai_remark.salary_expectation_alignment,
                    'analysis_duration_seconds': ai_remark.analysis_duration_seconds,
                    'error_message': ai_remark.error_message,
                    'analyzed_at': ai_remark.analyzed_at,
                    'reviewed_by_human': ai_remark.reviewed_by_human,
                    'human_override': ai_remark.human_override,
                    'human_remarks': ai_remark.human_remarks,
                    'overall_recommendation': ai_remark.overall_recommendation,
                    'score_breakdown': ai_remark.score_breakdown,
                }
            return None
        except Exception as e:
            return {'error': str(e)}
    
    class Meta:
        model = JobApplication
        fields = [
            # Application basic info
            'id', 'cover_letter', 'resume_name', 'resume_url', 
            'status', 'status_display', 'description', 'applied_at', 
            'reviewed_at', 'reviewed_by_name', 'reviewed_by_email',
            'created_at', 'updated_at',
            
            # Job Post complete info
            'job_title', 'job_slug', 'company_name', 'employment_type', 
            'employment_type_display', 'experience_level', 'experience_level_display',
            'working_mode', 'working_mode_display', 'location', 'salary_min', 
            'salary_max', 'salary_range', 'deadline', 'required_skills', 
            'screening_questions', 'job_description', 'applications_count', 
            'views_count', 'is_active', 'is_featured', 'job_created_at',
            
            # Company complete info
            'company_logo', 'company_website', 'company_location', 
            'company_address', 'company_city', 'company_state', 'company_country',
            'company_phone', 'company_email', 'company_industry', 'company_size',
            'company_description', 'company_founded_year', 'is_verified',
            
            # Calculated fields
            'days_since_applied', 'days_until_deadline', 'is_deadline_passed',
            
            # AI Analysis complete
            'ai_analysis'
        ]

class JobApplicationStatusUpdateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=['withdrawn', 'applied', 'user_rejected']
    )
    
    class Meta:
        model = JobApplication
        fields = ['status']
        
    def validate_status(self, value):
        if value not in ['withdrawn', 'applied', 'user_rejected']:
            raise serializers.ValidationError("Invalid status choice")
        return value




class EmployerProfileSerializer(serializers.ModelSerializer):
    """Serializer for EmployerProfile with all details"""
    followers_count = serializers.IntegerField(read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = EmployerProfile
        fields = [
            'id', 'user', 'user_email', 'company_name', 'slug', 'designation', 
            'description', 'website', 'logo', 'banner', 'active_jobs_count', 
            'total_applications_count', 'followers_count', 'created_at'
        ]

class CompanyPostSerializer(serializers.ModelSerializer):
    """Serializer for CompanyPost with essential fields"""
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)
    
    class Meta:
        model = CompanyPost
        fields = [
            'id', 'title', 'slug', 'content', 'image', 'video', 'document', 
            'visibility', 'video_url', 'external_link', 'category', 'allow_comments', 
            'is_pinned', 'is_active', 'likes_count', 'comments_count', 
            'views_count', 'shares_count', 'created_at', 'created_by_email'
        ]

class JobPostSerializer(serializers.ModelSerializer):
    """Serializer for JobPost with essential fields"""
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)
    
    class Meta:
        model = JobPost
        fields = [
            'id', 'title', 'slug', 'company_name', 'employment_type', 
            'experience_level', 'working_mode', 'location', 'salary_min', 
            'salary_max', 'deadline', 'required_skills', 'screening_questions', 
            'description', 'applications_count', 'views_count', 'is_active', 
            'is_featured', 'created_at', 'created_by_email'
        ]


class CompanyPostSerializer(serializers.ModelSerializer):
    """
    Serializer for company posts
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_logo = serializers.ImageField(source='company.logo', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    is_liked = serializers.SerializerMethodField()
    
    class Meta:
        model = CompanyPost
        fields = [
            'id', 'title', 'slug', 'content', 'image', 'video', 'document',
            'video_url', 'external_link', 'category', 'visibility', 'is_pinned',
            'likes_count', 'comments_count', 'views_count', 'shares_count',
            'created_at', 'updated_at', 'company_name', 'company_logo',
            'created_by_name', 'is_liked'
        ]
        read_only_fields = [
            'id', 'slug', 'likes_count', 'comments_count', 'views_count',
            'shares_count', 'created_at', 'updated_at'
        ]
    
    def get_is_liked(self, obj):
        """Check if current user has liked this post"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False


class PostCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    is_liked = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()  # New field
    
    class Meta:
        model = PostComment
        fields = [
            'id', 'comment', 'parent', 'likes_count', 'replies_count',
            'created_at', 'user_name', 'is_liked', 'can_delete'
        ]
        read_only_fields = ['id', 'likes_count', 'replies_count', 'created_at']
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return CommentLike.objects.filter(comment=obj, user=request.user).exists()
        return False
    
    def get_can_delete(self, obj):
        """Check if current user can delete this comment"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False