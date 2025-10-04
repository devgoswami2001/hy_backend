from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, Avg, F, Prefetch
from rest_framework.views import APIView
from django.utils import timezone
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from datetime import timedelta
from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
import logging
from django.db import models
from rest_framework.exceptions import PermissionDenied


logger = logging.getLogger(__name__)

from .permissions import *
from .models import *
from .serializers import *

# ============================================================================
# UTILITY VIEWS
# ============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def check_employer_profile(request):
    """Check if an email has an associated employer profile"""
    serializer = EmployerProfileCheckSerializer(data=request.data)
    if serializer.is_valid():
        result = serializer.validated_data['email']
        return Response(result, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmployerIdView(generics.GenericAPIView):
    """Get employer ID for authenticated user (Employer or HR)"""
    permission_classes = [IsAuthenticated]
    
    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user type"""
        try:
            if user.role == 'employer':
                # Direct access for employer
                return getattr(user, 'employer_profile', None)
            elif user.role == 'hr':
                # Access through company ForeignKey for HR
                hr_record = getattr(user, 'hr_user', None)
                if hr_record:
                    return hr_record.company  # company is ForeignKey to EmployerProfile
                return None
            else:
                return None
        except AttributeError:
            return None

    def get(self, request):
        try:
            # Get employer profile based on user role
            employer_profile = self.get_employer_profile(request.user)
            
            if not employer_profile:
                return Response(
                    {
                        "error": "Employer profile not found.",
                        "detail": f"No employer profile access for user {request.user.email} with role {request.user.role}"
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Build logo URL if present
            logo_url = (
                request.build_absolute_uri(employer_profile.logo.url)
                if employer_profile.logo else None
            )
            
            # Create response data
            response_data = {
                'employer_id': employer_profile.id,
                'company_name': employer_profile.company_name,
                'company_logo': logo_url,   # ✅ Always included
                'user_role': request.user.role,
                'access_type': 'direct' if request.user.role == 'employer' else 'through_company'
            }
            
            serializer = EmployerIdSerializer(response_data)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {
                    "error": "Failed to fetch employer profile.",
                    "detail": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class EmployerLeadershipCreateView(generics.CreateAPIView):
    serializer_class = EmployerLeadershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]
    parser_classes = [MultiPartParser, FormParser]  # ✅ add this

    def perform_create(self, serializer):
        employer_profile = getattr(self.request.user, "employer_profile", None)
        serializer.save(employer=employer_profile)


class EmployerLeadershipUpdateView(generics.UpdateAPIView):
    serializer_class = EmployerLeadershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]
    parser_classes = [MultiPartParser, FormParser]  # ✅ add this

    def get_queryset(self):
        return EmployerLeadership.objects.filter(employer=self.request.user.employer_profile)

class EmployerLeadershipDeleteView(generics.DestroyAPIView):
    queryset = EmployerLeadership.objects.all()
    serializer_class = EmployerLeadershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get_queryset(self):
        # Employer can only delete their own leadership team
        return EmployerLeadership.objects.filter(employer=self.request.user.employer_profile)


class EmployerLeadershipListView(generics.ListAPIView):
    serializer_class = EmployerLeadershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get_queryset(self):
        return EmployerLeadership.objects.filter(employer=self.request.user.employer_profile)

# ============================================================================
# PAGINATION CLASSES
# ============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for most views"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class JobPostPagination(PageNumberPagination):
    """Custom pagination for job posts"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

# ============================================================================
# FILTER CLASSES
# ============================================================================

class JobPostFilter(django_filters.FilterSet):
    """Filter class for job posts"""
    title = django_filters.CharFilter(lookup_expr='icontains')
    location = django_filters.CharFilter(lookup_expr='icontains')
    employment_type = django_filters.MultipleChoiceFilter(choices=JobPost.EmploymentTypeChoices.choices)
    experience_level = django_filters.MultipleChoiceFilter(choices=JobPost.ExperienceLevelChoices.choices)
    working_mode = django_filters.MultipleChoiceFilter(choices=JobPost.WorkingModeChoices.choices)
    salary_min = django_filters.NumberFilter(field_name='salary_min', lookup_expr='gte')
    salary_max = django_filters.NumberFilter(field_name='salary_max', lookup_expr='lte')
    skills = django_filters.CharFilter(method='filter_skills')
    company = django_filters.CharFilter(field_name='company__company_name', lookup_expr='icontains')
    is_featured = django_filters.BooleanFilter()
    
    class Meta:
        model = JobPost
        fields = ['employment_type', 'experience_level', 'working_mode', 'is_featured']
    
    def filter_skills(self, queryset, name, value):
        skills = [skill.strip() for skill in value.split(',')]
        return queryset.filter(required_skills__overlap=skills)

# ============================================================================
# EMPLOYER PROFILE VIEWS
# ============================================================================

class EmployerProfileCreateView(generics.CreateAPIView):
    """Create employer profile"""
    serializer_class = EmployerProfileCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EmployerProfileUpdateView(generics.UpdateAPIView):
    """Update employer profile"""
    serializer_class = EmployerProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_object(self):
        """Get current user's employer profile"""
        try:
            return self.request.user.employer_profile
        except EmployerProfile.DoesNotExist:
            raise NotFound("Employer profile not found.")
    
    def update(self, request, *args, **kwargs):
        """Custom update response with full profile data"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Save updated instance
        updated_instance = serializer.save()
        
        # Return full profile data using detailed serializer
        response_serializer = EmployerProfileSerializer(
            updated_instance, 
            context={'request': request}
        )
        
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class EmployerProfileViewSet(viewsets.ModelViewSet):
    """Main employer profile viewset"""
    serializer_class = EmployerProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrHR]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['company_name', 'description']
    ordering_fields = ['company_name', 'created_at']
    ordering = ['-created_at']

    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user role"""
        try:
            if user.role == 'employer':
                return getattr(user, 'employer_profile', None)
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                return hr_record.company if hr_record else None
            return None
        except AttributeError:
            return None

    def get_queryset(self):
        user = self.request.user
        
        if self.action == 'list':
            # Admin users see all, others see filtered
            if user.is_staff or user.role == 'admin':
                return EmployerProfile.objects.select_related('user').prefetch_related('job_posts')
            else:
                # Regular users see only their accessible profiles
                profile = self.get_employer_profile(user)
                if profile:
                    return EmployerProfile.objects.filter(id=profile.id).select_related('user').prefetch_related('job_posts')
                return EmployerProfile.objects.none()
        
        # For detail view, retrieve, update, delete
        profile = self.get_employer_profile(user)
        if profile:
            return EmployerProfile.objects.filter(id=profile.id).select_related('user')
        return EmployerProfile.objects.none()

    def get_object(self):
        """Ensure users can only access profiles they have permission for"""
        obj = super().get_object()
        user = self.request.user
        
        # Admin users can access all
        if user.is_staff or user.role == 'admin':
            return obj
        
        # Check if user has access to this profile
        user_profile = self.get_employer_profile(user)
        if not user_profile or obj.id != user_profile.id:
            raise PermissionDenied("You don't have permission to access this employer profile")
        
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return EmployerProfileListSerializer
        return EmployerProfileSerializer

    def perform_create(self, serializer):
        # Only employers can create profiles
        if self.request.user.role != 'employer':
            raise PermissionDenied("Only employers can create employer profiles")
            
        serializer.save(user=self.request.user)
        
        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            role=self.request.user.role,
            action='profile_created',
            content_object=serializer.instance,
            message=f"Created employer profile for {serializer.instance.company_name}",
            ip_address=self.get_client_ip()
        )

    def perform_update(self, serializer):
        user = self.request.user
        
        # Check HR permissions for editing
        if user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            if not hr_record or not hr_record.can_edit_profile:
                raise PermissionDenied("You don't have permission to edit the company profile")
        
        serializer.save()
        
        ActivityLog.objects.create(
            user=self.request.user,
            role=self.request.user.role,
            action='profile_updated',
            content_object=serializer.instance,
            message=f"Updated employer profile for {serializer.instance.company_name}",
            ip_address=self.get_client_ip()
        )

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get company statistics"""
        profile = self.get_object()  # This already checks permissions
        
        # Cache key for stats
        cache_key = f"employer_stats_{profile.id}"
        stats = cache.get(cache_key)
        
        if not stats:
            stats = {
                'total_jobs': profile.job_posts.count(),
                'active_jobs': profile.job_posts.filter(
                    is_active=True, 
                    deadline__gte=timezone.now().date()
                ).count(),
                'total_applications': JobApplication.objects.filter(
                    job_post__company=profile,
                    is_deleted=False
                ).count(),
                'pending_applications': JobApplication.objects.filter(
                    job_post__company=profile, 
                    status='applied',
                    is_deleted=False
                ).count(),
                'hired_count': JobApplication.objects.filter(
                    job_post__company=profile, 
                    status='hired',
                    is_deleted=False
                ).count(),
                'company_name': profile.company_name,
                'user_role': request.user.role
            }
            # Cache for 15 minutes
            cache.set(cache_key, stats, 900)
        
        serializer = EmployerProfileStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def dashboard(self, request, pk=None):
        """Get employer dashboard data"""
        profile = self.get_object()  # This already checks permissions
        
        # Recent applications (last 30 days)
        recent_applications = JobApplication.objects.filter(
            job_post__company=profile,
            applied_at__gte=timezone.now() - timedelta(days=30),
            is_deleted=False
        ).select_related('applicant', 'job_post').order_by('-applied_at')[:10]
        
        # Top performing jobs
        top_jobs = profile.job_posts.filter(
            is_active=True
        ).annotate(
            app_count=Count('applications', filter=Q(applications__is_deleted=False))
        ).order_by('-app_count')[:5]
        
        dashboard_data = {
            'profile_info': {
                'company_name': profile.company_name,
                'user_role': request.user.role,
                'user_email': request.user.email
            },
            'stats': {
                'total_jobs': profile.active_jobs_count,
                'active_jobs': profile.job_posts.filter(
                    is_active=True, 
                    deadline__gte=timezone.now().date()
                ).count(),
                'total_applications': profile.total_applications_count,
                'pending_applications': JobApplication.objects.filter(
                    job_post__company=profile, 
                    status='applied',
                    is_deleted=False
                ).count(),
                'shortlisted_applications': JobApplication.objects.filter(
                    job_post__company=profile, 
                    status='shortlisted',
                    is_deleted=False
                ).count(),
                'hired_candidates': JobApplication.objects.filter(
                    job_post__company=profile, 
                    status='hired',
                    is_deleted=False
                ).count(),
            },
            'recent_activities': {
                'recent_applications': JobApplicationSerializer(
                    recent_applications, 
                    many=True, 
                    context={'request': request}
                ).data,
                'top_performing_jobs': JobPostListSerializer(
                    top_jobs, 
                    many=True, 
                    context={'request': request}
                ).data
            }
        }
        
        serializer = EmployerDashboardSerializer(dashboard_data)
        return Response(serializer.data)

    def get_client_ip(self):
        """Get client IP address"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


# ============================================================================
# MONTHLY STATISTICS VIEWS
# ============================================================================

class MonthlyApplicationsViewSet(viewsets.ViewSet):
    """Monthly application statistics for employers"""
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def monthly_stats(self, request):
        """Get monthly application statistics for the authenticated employer."""
        try:
            from datetime import datetime
            year = request.GET.get('year', datetime.now().year)
            
            try:
                year = int(year)
                if year < 2020 or year > datetime.now().year + 1:
                    return Response(
                        {"error": "Invalid year. Please provide a valid year."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {"error": "Year must be a valid integer."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if employer has profile
            if not hasattr(request.user, 'employer_profile'):
                return Response(
                    {"error": "Employer profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = MonthlyApplicationsSerializer(context={'year': year})
            data = serializer.to_representation(request.user)
            
            response_data = {
                "year": year,
                "total_applications": sum(item['applications'] for item in data),
                "monthly_data": data,
                "message": "Monthly application statistics retrieved successfully."
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            print("Monthly stats error:\n", traceback.format_exc())
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monthly_applications_view(request):
    year = request.GET.get('year', datetime.now().year)
    
    # Now request.user is guaranteed to be authenticated
    serializer = MonthlyApplicationsSerializer(
        request.user,
        context={'year': int(year)}
    )
    
    data = serializer.to_representation(request.user)
    return Response(data)
# ============================================================================
# JOB POST VIEWS
# ============================================================================

class JobPostListCreateAPIView(generics.ListCreateAPIView):
    """List and create view for job posts"""
    queryset = JobPost.active_jobs.select_related('company', 'created_by').all()
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrReadOnly]
    pagination_class = JobPostPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobPostFilter
    search_fields = ['title', 'location', 'required_skills', 'company__company_name']
    ordering_fields = ['created_at', 'deadline', 'applications_count', 'views_count']
    ordering = ['-is_featured', '-created_at']
    
    def get_serializer_class(self):
        """Use different serializers for list and create views"""
        if self.request.method == 'GET':
            return JobPostListSerializer
        return JobPostSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset()
        
        # If user is employer, show their jobs (including inactive)
        if self.request.user.is_authenticated and hasattr(self.request.user, 'employer_profile'):
            if self.request.query_params.get('my_jobs') == 'true':
                return JobPost.objects.filter(
                    company=self.request.user.employer_profile
                ).select_related('company', 'created_by')
        
        # For public, only show active jobs with future deadlines
        return queryset.filter(
            deadline__gte=timezone.now().date()
        )
    
    def perform_create(self, serializer):
        """Set company from user's employer profile"""
        if hasattr(self.request.user, 'employer_profile'):
            serializer.save(
                company=self.request.user.employer_profile,
                created_by=self.request.user
            )
        else:
            return Response(
                {'error': 'Only employers can create job posts'},
                status=status.HTTP_403_FORBIDDEN
            )


class JobPostRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete view for job posts"""
    queryset = JobPost.objects.select_related('company', 'created_by').all()
    serializer_class = JobPostSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrReadOnly]
    lookup_field = 'slug'
    
    def get_object(self):
        """Override to increment view count"""
        obj = super().get_object()
        
        # Increment view count (use F() to avoid race conditions)
        if self.request.method == 'GET':
            JobPost.objects.filter(pk=obj.pk).update(
                views_count=F('views_count') + 1
            )
            # Refresh from DB to get updated count
            obj.refresh_from_db(fields=['views_count'])
        
        return obj
    
    def perform_update(self, serializer):
        """Custom update logic"""
        # Only allow owner or company admin to update
        job_post = self.get_object()
        if (self.request.user != job_post.created_by and 
            self.request.user.employer_profile != job_post.company):
            return Response(
                {'error': 'You can only update your own job posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer.save()
    
    def perform_destroy(self, instance):
        """Soft delete instead of hard delete"""
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class FeaturedJobPostListAPIView(generics.ListAPIView):
    """List featured job posts"""
    queryset = JobPost.active_jobs.filter(
        is_featured=True,
        deadline__gte=timezone.now().date()
    ).select_related('company', 'created_by')[:10]
    
    serializer_class = JobPostListSerializer
    permission_classes = []  # Public endpoint


class JobPostStatsAPIView(generics.GenericAPIView):
    """Get job post statistics for employers"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        """Return job post statistics"""
        if not hasattr(request.user, 'employer_profile'):
            return Response(
                {'error': 'Only employers can view stats'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        company = request.user.employer_profile
        stats = {
            'total_jobs': JobPost.objects.filter(company=company).count(),
            'active_jobs': JobPost.active_jobs.filter(company=company).count(),
            'total_applications': JobPost.objects.filter(company=company).aggregate(
                total=models.Sum('applications_count')
            )['total'] or 0,
            'total_views': JobPost.objects.filter(company=company).aggregate(
                total=models.Sum('views_count')
            )['total'] or 0,
            'featured_jobs': JobPost.objects.filter(
                company=company, is_featured=True
            ).count(),
        }
        
        return Response(stats)


# class JobPostViewSet(viewsets.ModelViewSet):
#     """
#     Complete ViewSet for job posts with all CRUD operations
#     """
#     queryset = JobPost.objects.select_related(
#         'company', 
#         'created_by', 
#         'created_by__employer_profile'
#     ).all()
    
#     permission_classes = [IsAuthenticatedOrReadOnly, IsEmployerOrHR]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_class = JobPostFilter
#     search_fields = ['title', 'location', 'company_name', 'required_skills']
#     ordering_fields = ['created_at', 'deadline', 'applications_count', 'views_count']
#     ordering = ['-is_featured', '-created_at']
#     lookup_field = 'id'  # Using ID for lookup
    
#     def get_permissions(self):
#         """Dynamic permissions based on action"""
#         if self.action == 'retrieve':
#             # Allow anyone to retrieve active job posts
#             permission_classes = []
#         elif self.action in ['list', 'featured']:
#             # Public endpoints
#             permission_classes = []
#         else:
#             # Authenticated users only for other actions
#             permission_classes = [IsAuthenticated,]
        
#         return [permission() for permission in permission_classes]
    
#     def get_serializer_class(self):
#         """Use different serializers for different actions"""
#         if self.action in ['list', 'my_jobs', 'featured']:
#             return JobPostListSerializer
#         return JobPostSerializer
    
#     def get_queryset(self):
#         """Filter queryset based on user permissions and requirements"""
#         queryset = super().get_queryset()
        
#         # For retrieve action, allow public access to active jobs
#         if self.action == 'retrieve':
#             return queryset.filter(is_active=True)
        
#         # For actions that need access to inactive jobs (update, delete)
#         if self.action in ['update', 'partial_update', 'destroy', 'deactivate', 'activate', 'toggle_featured']:
#             # For employers viewing their own jobs, show all (active + inactive)
#             if (self.request.user.is_authenticated and 
#                 hasattr(self.request.user, 'employer_profile')):
#                 return queryset.filter(company=self.request.user.employer_profile)
#             # For public access, deny access
#             return queryset.none()  # Return empty queryset for unauthorized users
        
#         # If user is employer and wants to see their own jobs (my_jobs endpoint)
#         if self.request.user.is_authenticated and hasattr(self.request.user, 'employer_profile'):
#             if self.request.query_params.get('my_jobs') == 'true':
#                 # Show all jobs (active + inactive) for my_jobs
#                 return queryset.filter(
#                     company=self.request.user.employer_profile
#                 )
        
#         # For public listing (list action), only show active jobs with future deadlines
#         if self.action == 'list':
#             return queryset.filter(
#                 is_active=True,
#                 deadline__gte=timezone.now().date()
#             )
        
#         # Default queryset
#         return queryset
    
#     def retrieve(self, request, *args, **kwargs):
#         """Override retrieve to allow public access and increment view count"""
#         try:
#             if (request.user.is_authenticated and 
#                 hasattr(request.user, 'employer_profile')):
#                 # Employers can view their own jobs (active or inactive)
#                 instance = JobPost.objects.select_related(
#                     'company', 'created_by', 'created_by__employer_profile'
#                 ).get(
#                     id=self.kwargs[self.lookup_field],
#                     company=request.user.employer_profile
#                 )
#             else:
#                 # Public users can only view active jobs
#                 instance = JobPost.objects.select_related(
#                     'company', 'created_by', 'created_by__employer_profile'
#                 ).get(
#                     id=self.kwargs[self.lookup_field],
#                     is_active=True
#                 )
#         except JobPost.DoesNotExist:
#             return Response(
#                 {'error': 'Job post not found or not accessible'},
#                 status=status.HTTP_404_NOT_FOUND
#             )
        
#         # Check object permissions
#         self.check_object_permissions(request, instance)
        
#         # Increment view count (use F() to avoid race conditions)
#         JobPost.objects.filter(pk=instance.pk).update(
#             views_count=F('views_count') + 1
#         )
        
#         # Refresh from DB to get updated count
#         instance.refresh_from_db(fields=['views_count'])
        
#         serializer = self.get_serializer(instance)
#         return Response(serializer.data)
    
#     def create(self, request, *args, **kwargs):
#         """Override create to handle employer-only creation"""
#         if not hasattr(request.user, 'employer_profile'):
#             return Response(
#                 {'error': 'Only employers can create job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         serializer = self.get_serializer(data=request.data)
#         if serializer.is_valid():
#             self.perform_create(serializer)
#             headers = self.get_success_headers(serializer.data)
#             return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     def perform_create(self, serializer):
#         """Set company from user's employer profile"""
#         serializer.save(
#             company=self.request.user.employer_profile,
#             created_by=self.request.user,
#             company_name=self.request.user.employer_profile.company_name
#         )
    
#     def update(self, request, *args, **kwargs):
#         """Override update to handle permissions"""
#         instance = self.get_object()
        
#         # Only allow owner or company admin to update
#         if (request.user != instance.created_by and 
#             hasattr(request.user, 'employer_profile') and
#             request.user.employer_profile != instance.company):
#             return Response(
#                 {'error': 'You can only update your own job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         partial = kwargs.pop('partial', False)
#         serializer = self.get_serializer(instance, data=request.data, partial=partial)
#         if serializer.is_valid():
#             self.perform_update(serializer)
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     def perform_update(self, serializer):
#         """Custom update logic"""
#         serializer.save()
    
#     def destroy(self, request, *args, **kwargs):
#         """Override destroy to handle permissions and deletion"""
#         instance = self.get_object()
        
#         # Check permission
#         if (request.user != instance.created_by and 
#             hasattr(request.user, 'employer_profile') and
#             request.user.employer_profile != instance.company):
#             return Response(
#                 {'error': 'You can only delete your own job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         self.perform_destroy(instance)
#         return Response(status=status.HTTP_204_NO_CONTENT)
    
#     def perform_destroy(self, instance):
#         """Hard delete the job post"""
#         instance.delete()  # This actually removes the record from database
    
#     @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
#     def deactivate(self, request, id=None):
#         """Deactivate a job post (soft delete)"""
#         job = self.get_object()
        
#         # Check permission
#         if (request.user != job.created_by and 
#             hasattr(request.user, 'employer_profile') and
#             request.user.employer_profile != job.company):
#             return Response(
#                 {'error': 'You can only modify your own job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         job.is_active = False
#         job.save(update_fields=['is_active'])

#         return Response({
#             'success': True,
#             'message': f'Job "{job.title}" has been deactivated'
#         })
    
#     @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
#     def activate(self, request, id=None):
#         """Activate a job post"""
#         job = self.get_object()

#         # Check permission
#         if (request.user != job.created_by and 
#             hasattr(request.user, 'employer_profile') and
#             request.user.employer_profile != job.company):
#             return Response(
#                 {'error': 'You can only modify your own job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         job.is_active = True
#         job.save(update_fields=['is_active'])

#         return Response({
#             'success': True,
#             'message': f'Job "{job.title}" has been activated'
#         })
    
#     @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
#     def toggle_featured(self, request, id=None):
#         """Toggle featured status of a job post"""
#         job = self.get_object()
        
#         # Check permission
#         if (request.user != job.created_by and 
#             hasattr(request.user, 'employer_profile') and
#             request.user.employer_profile != job.company):
#             return Response(
#                 {'error': 'You can only modify your own job posts'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         job.is_featured = not job.is_featured
#         job.save(update_fields=['is_featured'])
        
#         return Response({
#             'success': True,
#             'is_featured': job.is_featured,
#             'message': f"Job {'featured' if job.is_featured else 'unfeatured'} successfully"
#         })
    
#     @action(detail=False, methods=['get'], permission_classes=[])
#     def featured(self, request):
#         """Get featured job posts - Public endpoint"""
#         featured_jobs = self.get_queryset().filter(
#             is_featured=True,
#             is_active=True,
#             deadline__gte=timezone.now().date()
#         )[:10]
        
#         page = self.paginate_queryset(featured_jobs)
#         if page is not None:
#             serializer = JobPostListSerializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
        
#         serializer = JobPostListSerializer(featured_jobs, many=True)
#         return Response(serializer.data)
    
#     @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
#     def my_jobs(self, request):
#         """Get current employer's job posts with complete information"""
#         if not hasattr(request.user, 'employer_profile'):
#             return Response(
#                 {'error': 'Only employers can view their jobs'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
    
#         jobs = JobPost.objects.filter(
#             company=request.user.employer_profile
#         ).select_related(
#             'company', 
#             'created_by'
#         ).order_by('-is_featured', '-created_at')
    
#         page = self.paginate_queryset(jobs)
#         if page is not None:
#             serializer = JobPostListSerializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
    
#         serializer = JobPostListSerializer(jobs, many=True)
#         return Response(serializer.data)
    
#     @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
#     def stats(self, request):
#         """Get job post statistics for current employer"""
#         if not hasattr(request.user, 'employer_profile'):
#             return Response(
#                 {'error': 'Only employers can view their jobs'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         company = request.user.employer_profile
#         now = timezone.now().date()
        
#         stats = {
#             'total_jobs': JobPost.objects.filter(company=company).count(),
#             'active_jobs': JobPost.objects.filter(
#                 company=company, 
#                 is_active=True,
#                 deadline__gte=now
#             ).count(),
#             'inactive_jobs': JobPost.objects.filter(
#                 company=company, 
#                 is_active=False
#             ).count(),
#             'expired_jobs': JobPost.objects.filter(
#                 company=company,
#                 deadline__lt=now
#             ).count(),
#             'featured_jobs': JobPost.objects.filter(
#                 company=company, 
#                 is_featured=True,
#                 is_active=True
#             ).count(),
#             'total_applications': JobPost.objects.filter(company=company).aggregate(
#                 total=models.Sum('applications_count')
#             )['total'] or 0,
#             'total_views': JobPost.objects.filter(company=company).aggregate(
#                 total=models.Sum('views_count')
#             )['total'] or 0,
#             'avg_applications_per_job': JobPost.objects.filter(company=company).aggregate(
#                 avg=models.Avg('applications_count')
#             )['avg'] or 0,
#         }
        
#         return Response(stats)
class JobPostViewSet(viewsets.ModelViewSet):
    """
    Complete ViewSet for job posts with all CRUD operations
    Support for both Employer and HR users
    """
    queryset = JobPost.objects.select_related(
        'company', 
        'created_by', 
        'created_by__employer_profile'
    ).all()
    
    permission_classes = [IsAuthenticatedOrReadOnly, IsEmployerOrHR]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobPostFilter
    search_fields = ['title', 'location', 'company_name', 'required_skills']
    ordering_fields = ['created_at', 'deadline', 'applications_count', 'views_count']
    ordering = ['-is_featured', '-created_at']
    lookup_field = 'id'
    
    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user role"""
        try:
            if user.role == 'employer':
                return getattr(user, 'employer_profile', None)
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                return hr_record.company if hr_record else None
            return None
        except AttributeError:
            return None
    
    def check_job_permissions(self, user, job_instance, action='view'):
        """Check if user has permission to perform action on job"""
        if not user.is_authenticated:
            return False
            
        employer_profile = self.get_employer_profile(user)
        if not employer_profile:
            return False
        
        # Check if job belongs to user's company
        if job_instance.company != employer_profile:
            return False
        
        # Additional HR permission checks
        if user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            if not hr_record:
                return False
                
            # Check HR permissions based on action
            if action == 'create' and not hr_record.can_post_jobs:
                return False
            elif action in ['update', 'delete'] and not hr_record.can_post_jobs:
                return False
                
        return True
    
    def get_permissions(self):
        """Dynamic permissions based on action"""
        if self.action == 'retrieve':
            permission_classes = []
        elif self.action in ['list', 'featured']:
            permission_classes = []
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['list', 'my_jobs', 'featured']:
            return JobPostListSerializer
        return JobPostSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions and requirements"""
        queryset = super().get_queryset()
        
        # For retrieve action, allow public access to active jobs
        if self.action == 'retrieve':
            return queryset.filter(is_active=True)
        
        # For actions that need access to inactive jobs
        if self.action in ['update', 'partial_update', 'destroy', 'deactivate', 'activate', 'toggle_featured']:
            if self.request.user.is_authenticated:
                employer_profile = self.get_employer_profile(self.request.user)
                if employer_profile:
                    return queryset.filter(company=employer_profile)
            return queryset.none()
        
        # For my_jobs endpoint or employer/HR viewing their jobs
        if (self.request.user.is_authenticated and 
            self.request.query_params.get('my_jobs') == 'true'):
            employer_profile = self.get_employer_profile(self.request.user)
            if employer_profile:
                return queryset.filter(company=employer_profile)
        
        # For public listing, only show active jobs
        if self.action == 'list':
            return queryset.filter(
                is_active=True,
                deadline__gte=timezone.now().date()
            )
        
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to allow public access and increment view count"""
        try:
            if request.user.is_authenticated:
                employer_profile = self.get_employer_profile(request.user)
                if employer_profile:
                    # Employer/HR can view their own jobs (active or inactive)
                    instance = JobPost.objects.select_related(
                        'company', 'created_by', 'created_by__employer_profile'
                    ).get(
                        id=self.kwargs[self.lookup_field],
                        company=employer_profile
                    )
                else:
                    # Other authenticated users can only view active jobs
                    instance = JobPost.objects.select_related(
                        'company', 'created_by', 'created_by__employer_profile'
                    ).get(
                        id=self.kwargs[self.lookup_field],
                        is_active=True
                    )
            else:
                # Public users can only view active jobs
                instance = JobPost.objects.select_related(
                    'company', 'created_by', 'created_by__employer_profile'
                ).get(
                    id=self.kwargs[self.lookup_field],
                    is_active=True
                )
        except JobPost.DoesNotExist:
            return Response(
                {'error': 'Job post not found or not accessible'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check object permissions
        self.check_object_permissions(request, instance)
        
        # Increment view count
        JobPost.objects.filter(pk=instance.pk).update(
            views_count=F('views_count') + 1
        )
        
        instance.refresh_from_db(fields=['views_count'])
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """Override create to handle employer and HR creation"""
        employer_profile = self.get_employer_profile(request.user)
        
        if not employer_profile:
            return Response(
                {'error': 'Only employers and HR users can create job posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check HR permissions
        if request.user.role == 'hr':
            hr_record = getattr(request.user, 'hr_user', None)
            if not hr_record or not hr_record.can_post_jobs:
                return Response(
                    {'error': 'You do not have permission to create job posts'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def perform_create(self, serializer):
        """Set company from user's employer profile"""
        employer_profile = self.get_employer_profile(self.request.user)
        serializer.save(
            company=employer_profile,
            created_by=self.request.user,
            company_name=employer_profile.company_name
        )
    
    def update(self, request, *args, **kwargs):
        """Override update to handle permissions"""
        instance = self.get_object()
        
        if not self.check_job_permissions(request.user, instance, 'update'):
            return Response(
                {'error': 'You do not have permission to update this job post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            self.perform_update(serializer)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to handle permissions and deletion"""
        instance = self.get_object()
        
        if not self.check_job_permissions(request.user, instance, 'delete'):
            return Response(
                {'error': 'You do not have permission to delete this job post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def deactivate(self, request, id=None):
        """Deactivate a job post (soft delete)"""
        job = self.get_object()
        
        if not self.check_job_permissions(request.user, job, 'update'):
            return Response(
                {'error': 'You do not have permission to modify this job post'},
                status=status.HTTP_403_FORBIDDEN
            )

        job.is_active = False
        job.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f'Job "{job.title}" has been deactivated'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def activate(self, request, id=None):
        """Activate a job post"""
        job = self.get_object()

        if not self.check_job_permissions(request.user, job, 'update'):
            return Response(
                {'error': 'You do not have permission to modify this job post'},
                status=status.HTTP_403_FORBIDDEN
            )

        job.is_active = True
        job.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f'Job "{job.title}" has been activated'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle_featured(self, request, id=None):
        """Toggle featured status of a job post"""
        job = self.get_object()
        
        if not self.check_job_permissions(request.user, job, 'update'):
            return Response(
                {'error': 'You do not have permission to modify this job post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        job.is_featured = not job.is_featured
        job.save(update_fields=['is_featured'])
        
        return Response({
            'success': True,
            'is_featured': job.is_featured,
            'message': f"Job {'featured' if job.is_featured else 'unfeatured'} successfully"
        })
    
    @action(detail=False, methods=['get'], permission_classes=[])
    def featured(self, request):
        """Get featured job posts - Public endpoint"""
        featured_jobs = self.get_queryset().filter(
            is_featured=True,
            is_active=True,
            deadline__gte=timezone.now().date()
        )[:10]
        
        page = self.paginate_queryset(featured_jobs)
        if page is not None:
            serializer = JobPostListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = JobPostListSerializer(featured_jobs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_jobs(self, request):
        """Get current employer/HR's job posts with complete information"""
        employer_profile = self.get_employer_profile(request.user)
        
        if not employer_profile:
            return Response(
                {'error': 'Only employers and HR users can view jobs'},
                status=status.HTTP_403_FORBIDDEN
            )
    
        jobs = JobPost.objects.filter(
            company=employer_profile
        ).select_related(
            'company', 
            'created_by'
        ).order_by('-is_featured', '-created_at')
    
        page = self.paginate_queryset(jobs)
        if page is not None:
            serializer = JobPostListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
    
        serializer = JobPostListSerializer(jobs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def stats(self, request):
        """Get job post statistics for current employer/HR"""
        employer_profile = self.get_employer_profile(request.user)
        
        if not employer_profile:
            return Response(
                {'error': 'Only employers and HR users can view job statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        now = timezone.now().date()
        
        stats = {
            'user_info': {
                'email': request.user.email,
                'role': request.user.role,
                'company_name': employer_profile.company_name
            },
            'job_stats': {
                'total_jobs': JobPost.objects.filter(company=employer_profile).count(),
                'active_jobs': JobPost.objects.filter(
                    company=employer_profile, 
                    is_active=True,
                    deadline__gte=now
                ).count(),
                'inactive_jobs': JobPost.objects.filter(
                    company=employer_profile, 
                    is_active=False
                ).count(),
                'expired_jobs': JobPost.objects.filter(
                    company=employer_profile,
                    deadline__lt=now
                ).count(),
                'featured_jobs': JobPost.objects.filter(
                    company=employer_profile, 
                    is_featured=True,
                    is_active=True
                ).count(),
            },
            'engagement_stats': {
                'total_applications': JobPost.objects.filter(company=employer_profile).aggregate(
                    total=models.Sum('applications_count')
                )['total'] or 0,
                'total_views': JobPost.objects.filter(company=employer_profile).aggregate(
                    total=models.Sum('views_count')
                )['total'] or 0,
                'avg_applications_per_job': JobPost.objects.filter(company=employer_profile).aggregate(
                    avg=models.Avg('applications_count')
                )['avg'] or 0,
            }
        }
        
        return Response(stats)

# ============================================================================
# COMPANY POST VIEWS
# ============================================================================

class CompanyPostListCreateView(generics.ListCreateAPIView):
    """List and create company posts"""
    queryset = CompanyPost.objects.all()
    serializer_class = CompanyPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        user = self.request.user
        
        # Get company based on user role
        if user.role == 'employer':
            try:
                company = user.employer_profile
            except AttributeError:
                raise serializers.ValidationError("Could not retrieve company ID. Please make sure your user profile is linked to a company.")
        elif user.role == 'hr':
            try:
                company = user.hr_user.company
            except AttributeError:
                raise serializers.ValidationError("Could not retrieve company ID. Please make sure your HR profile is linked to a company.")
        else:
            raise serializers.ValidationError("Only employers and HR users can create company posts.")

        serializer.save(created_by=user, company=company)



class CompanyPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete company posts"""
    queryset = CompanyPost.objects.all()
    serializer_class = CompanyPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


# class CompanyPostsByUserCompanyView(generics.ListAPIView):
#     """Get company posts by user's company"""
#     serializer_class = CompanyPostViewSerializer
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user
#         try:
#             company = user.employer_profile
#             return CompanyPost.objects.filter(company=company, is_active=True)
#         except AttributeError:
#             # User does not have an associated employer_profile
#             return CompanyPost.objects.none()
class CompanyPostsByUserCompanyView(generics.ListAPIView):
    """Get company posts by user's company - supports both Employer and HR users"""
    serializer_class = CompanyPostViewSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrHR]

    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user role"""
        try:
            if user.role == 'employer':
                employer_profile = getattr(user, 'employer_profile', None)
                print(f"[DEBUG] Employer user -> employer_profile: {employer_profile}")
                return employer_profile
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                print(f"[DEBUG] HR user -> hr_record: {hr_record}")
                return hr_record.company if hr_record else None
            return None
        except AttributeError as e:
            print(f"[DEBUG][get_employer_profile] AttributeError: {e}")
            return None

    def get_queryset(self):
        """Get company posts based on user's role and company access"""
        user = self.request.user
        employer_profile = self.get_employer_profile(user)
        print(f"[DEBUG] get_queryset -> user: {user.email}, role: {user.role}, employer_profile: {employer_profile}")

        if not employer_profile:
            print("[DEBUG] No employer profile found, returning empty queryset")
            return CompanyPost.objects.none()

        queryset = CompanyPost.objects.filter(
            company=employer_profile
        ).select_related(
            'company', 'created_by'
        ).prefetch_related(
            'likes_details'
        )
        print(f"[DEBUG] Base queryset count: {queryset.count()} (company_id={employer_profile.id})")

        # filter param
        show_inactive = self.request.query_params.get('show_inactive', 'false').lower() == 'true'
        print(f"[DEBUG] show_inactive param: {show_inactive}")

        # Employers -> see everything (active + inactive by default)
        # HR -> only active, unless show_inactive=true
        if user.role == 'hr' and not show_inactive:
            queryset = queryset.filter(is_active=True)
            print(f"[DEBUG] HR filtered active only: {queryset.count()}")

        final_queryset = queryset.order_by('-is_pinned', '-created_at')
        print(f"[DEBUG] Final queryset count: {final_queryset.count()}")
        return final_queryset

    def list(self, request, *args, **kwargs):
        user = request.user
        employer_profile = self.get_employer_profile(user)
        print(f"[DEBUG] list -> user: {user.email}, employer_profile: {employer_profile}")

        if not employer_profile:
            print("[DEBUG] No employer profile found in list()")
            return Response({
                'success': False,
                'message': 'No company profile found. You must be an employer or HR user.',
                'error': 'Access denied',
                'results': []
            }, status=status.HTTP_403_FORBIDDEN)

        queryset = self.filter_queryset(self.get_queryset())
        print(f"[DEBUG] list -> queryset count after filters: {queryset.count()}")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            print(f"[DEBUG] list -> paginated results count: {len(serializer.data)}")
            paginated_response = self.get_paginated_response(serializer.data)

            paginated_response.data.update({
                'success': True,
                'company_info': {
                    'id': employer_profile.id,
                    'name': employer_profile.company_name,
                    'slug': employer_profile.slug,
                    'logo_url': request.build_absolute_uri(employer_profile.logo.url) if employer_profile.logo else None
                },
                'user_info': {
                    'email': user.email,
                    'role': user.role,
                    'permissions': self.get_user_permissions(user)
                },
                'filters_applied': {
                    'show_inactive': request.query_params.get('show_inactive', 'false').lower() == 'true',
                    'company_id': employer_profile.id
                }
            })
            return paginated_response

        serializer = self.get_serializer(queryset, many=True)
        print(f"[DEBUG] list -> non-paginated results count: {len(serializer.data)}")

        return Response({
            'success': True,
            'company_info': {
                'id': employer_profile.id,
                'name': employer_profile.company_name,
                'slug': employer_profile.slug,
                'logo_url': request.build_absolute_uri(employer_profile.logo.url) if employer_profile.logo else None
            },
            'user_info': {
                'email': user.email,
                'role': user.role,
                'permissions': self.get_user_permissions(user)
            },
            'filters_applied': {
                'show_inactive': request.query_params.get('show_inactive', 'false').lower() == 'true',
                'company_id': employer_profile.id
            },
            'count': len(serializer.data),
            'results': serializer.data
        })

    def get_user_permissions(self, user):
        """Get user permissions for company posts"""
        if user.role == 'employer':
            return {
                'can_create_post': True,
                'can_edit_posts': True,
                'can_delete_posts': True,
                'can_pin_posts': True,
                'can_moderate': True,
                'can_view_inactive': True
            }
        elif user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            if hr_record:
                return {
                    'can_create_post': hr_record.can_post_feed,
                    'can_edit_posts': hr_record.can_post_feed,
                    'can_delete_posts': hr_record.can_post_feed,
                    'can_pin_posts': hr_record.can_post_feed,
                    'can_moderate': hr_record.can_post_feed,
                    'can_view_inactive': True,
                    'hr_role': hr_record.role
                }
        return {
            'can_create_post': False,
            'can_edit_posts': False,
            'can_delete_posts': False,
            'can_pin_posts': False,
            'can_moderate': False,
            'can_view_inactive': False
        }


class CompanyPostLikeView(APIView):
    """Like a company post"""
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrJobseeker]
    
    def post(self, request, pk):
        post = get_object_or_404(CompanyPost, pk=pk)
        like, created = post.likes_details.get_or_create(user=request.user)
        if not created:
            return Response({'detail': 'Already liked'}, status=status.HTTP_400_BAD_REQUEST)
        post.likes_count = post.likes_details.count()
        post.save(update_fields=['likes_count'])
        return Response(PostLikeSerializer(like).data)


class CompanyPostUnlikeView(APIView):
    """Unlike a company post"""
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrJobseeker]
    
    def post(self, request, pk):
        post = get_object_or_404(CompanyPost, pk=pk)
        deleted, _ = post.likes_details.filter(user=request.user).delete()
        if deleted:
            post.likes_count = post.likes_details.count()
            post.save(update_fields=['likes_count'])
        return Response({'detail': 'Unliked'}, status=status.HTTP_204_NO_CONTENT)


class CompanyPostCommentListCreateView(generics.ListCreateAPIView):
    """List and create comments on company posts"""
    serializer_class = PostCommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # Only top-level comments for the post
        return PostComment.objects.filter(
            post_id=self.kwargs['pk'], parent__isnull=True
        ).order_by('-created_at')

    def perform_create(self, serializer):
        post = get_object_or_404(CompanyPost, pk=self.kwargs['pk'])
        serializer.save(user=self.request.user, post=post)


class PostCommentLikeView(APIView):
    """Like a comment"""
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrJobseeker]

    def post(self, request, pk):
        comment = get_object_or_404(PostComment, pk=pk)
        like, created = comment.likes.get_or_create(user=request.user)
        if not created:
            return Response({'detail': 'Already liked'}, status=status.HTTP_400_BAD_REQUEST)
        comment.likes_count = comment.likes.count()
        comment.save(update_fields=['likes_count'])
        return Response(CommentLikeSerializer(like).data)


class PostCommentUnlikeView(APIView):
    """Unlike a comment"""
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrJobseeker]

    def post(self, request, pk):
        comment = get_object_or_404(PostComment, pk=pk)
        deleted, _ = comment.likes.filter(user=request.user).delete()
        if deleted:
            comment.likes_count = comment.likes.count()
            comment.save(update_fields=['likes_count'])
        return Response({'detail': 'Unliked'}, status=status.HTTP_204_NO_CONTENT)


class PostCommentReplyCreateView(generics.CreateAPIView):
    """Create replies to comments"""
    serializer_class = PostCommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrJobseeker]

    def perform_create(self, serializer):
        parent = get_object_or_404(PostComment, pk=self.kwargs['pk'])
        serializer.save(user=self.request.user, post=parent.post, parent=parent)

# ============================================================================
# HR USER MANAGEMENT VIEWS
# ============================================================================

# class HRUserViewSet(viewsets.ModelViewSet):
#     """ViewSet for HR user management"""
#     permission_classes = [permissions.IsAuthenticated, IsEmployerOrHRTeam]

#     def get_serializer_class(self):
#         """Use different serializers for different actions"""
#         if self.action == 'create':
#             return HRUserCreateSerializer
#         elif self.action in ['update', 'partial_update']:
#             return HRUserUpdateSerializer
#         elif self.action == 'list':
#             return HRUserListSerializer  # Use the new list serializer for better performance
#         return HRUserSerializer

#     # def get_queryset(self):
#     #     """Get queryset based on user permissions"""
#     #     user = self.request.user
        
#     #     # Select related user for better performance
#     #     queryset = HRUser.objects.select_related('user', 'company').filter(is_deleted=False)
        
#     #     if user.role == User.Roles.EMPLOYER:
#     #         profile = getattr(user, 'employer_profile', None)
#     #         if profile:
#     #             return queryset.filter(company=profile)
#     #     elif hasattr(user, 'hr_user'):
#     #         return queryset.filter(company=user.hr_user.company)
#     def get_queryset(self):
#         """Get queryset based on user permissions"""
#         user = self.request.user
    
#         if user.role == User.Roles.EMPLOYER:
#             profile = getattr(user, 'employer_profile', None)
#             if profile:
#                 return HRUser.objects.select_related('user', 'company').filter(
#                     company=profile
#                 )  # Remove is_deleted=False filter to allow deletion of any HR user
#         elif hasattr(user, 'hr_user'):
#             return HRUser.objects.select_related('user', 'company').filter(
#                 company=user.hr_user.company
#             )
    
#         return HRUser.objects.none()
        
#         #return queryset.none()

#     def perform_create(self, serializer):
#         """Handle HR user creation with validation"""
#         company = getattr(self.request.user, 'employer_profile', None)
#         if not company:
#             raise permissions.PermissionDenied(
#                 "Authenticated user must have an employer profile to create HR users."
#             )
        
#         # The serializer will handle user creation and linking
#         hr_user = serializer.save()
        
#         # Optional: Log the creation
#         logger.info(f"HR user created: {hr_user.user.email} for company {company.company_name}")

#     def perform_update(self, serializer):
#         """Handle HR user updates"""
#         hr_user = serializer.save()
        
#         # Optional: Log the update
#         logger.info(f"HR user updated: {hr_user.user.email}")

#     def perform_destroy(self, instance):
#        """Delete both HR user and associated user account"""
#        user_to_delete = instance.user  # Get the user before deleting HR instance
    
#        # Delete the HRUser record first
#        instance.delete()
    
#        # Then delete the associated User record
#        user_to_delete.delete()
    
#        logger.info(f"HR user and associated user account deleted: {user_to_delete.email}")

#     def create(self, request, *args, **kwargs):
#         """Override create to provide better error handling"""
#         try:
#             serializer = self.get_serializer(data=request.data)
#             serializer.is_valid(raise_exception=True)
#             self.perform_create(serializer)
#             headers = self.get_success_headers(serializer.data)
            
#             return Response({
#                 'success': True,
#                 'message': 'HR user created successfully',
#                 'data': serializer.data
#             }, status=status.HTTP_201_CREATED, headers=headers)
            
#         except Exception as e:
#             logger.error(f"HR user creation failed: {str(e)}")
#             return Response({
#                 'success': False,
#                 'message': 'Failed to create HR user',
#                 'error': str(e)
#             }, status=status.HTTP_400_BAD_REQUEST)

#     def update(self, request, *args, **kwargs):
#         """Override update to provide better error handling"""
#         try:
#             partial = kwargs.pop('partial', False)
#             instance = self.get_object()
#             serializer = self.get_serializer(instance, data=request.data, partial=partial)
#             serializer.is_valid(raise_exception=True)
#             self.perform_update(serializer)

#             return Response({
#                 'success': True,
#                 'message': 'HR user updated successfully',
#                 'data': serializer.data
#             })
            
#         except Exception as e:
#             logger.error(f"HR user update failed: {str(e)}")
#             return Response({
#                 'success': False,
#                 'message': 'Failed to update HR user',
#                 'error': str(e)
#             }, status=status.HTTP_400_BAD_REQUEST)

#     def destroy(self, request, *args, **kwargs):
#         """Override destroy to provide proper success response"""
#         instance = self.get_object()
#         user_email = instance.user.email
#         self.perform_destroy(instance)
    
#         return Response({
#             'success': True,
#             'message': f'HR user {user_email} has been deleted successfully'
#         }, status=status.HTTP_200_OK)

#     @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
#     def reactivate(self, request, pk=None):
#         """Reactivate a soft-deleted HR user"""
#         try:
#             # Get HR user including soft-deleted ones
#             hr_user = get_object_or_404(
#                 HRUser.objects.select_related('user', 'company'),
#                 pk=pk,
#                 company=request.user.employer_profile
#             )
            
#             # Reactivate both HR user and associated user account
#             hr_user.is_deleted = False
#             hr_user.user.is_active = True
            
#             hr_user.save(update_fields=['is_deleted'])
#             hr_user.user.save(update_fields=['is_active'])
            
#             return Response({
#                 'success': True,
#                 'message': f'HR user {hr_user.user.email} has been reactivated'
#             })
            
#         except Exception as e:
#             return Response({
#                 'success': False,
#                 'message': 'Failed to reactivate HR user',
#                 'error': str(e)
#             }, status=status.HTTP_400_BAD_REQUEST)

#     @action(detail=False, methods=['get'])
#     def permissions_list(self, request):
#         """Get available permissions for HR users"""
#         permissions_data = {
#             'available_permissions': [
#                 {'key': 'can_post_jobs', 'label': 'Can Post Jobs', 'description': 'Allow posting and managing job posts'},
#                 {'key': 'can_view_applicants', 'label': 'Can View Applicants', 'description': 'Allow viewing job applications'},
#                 {'key': 'can_edit_profile', 'label': 'Can Edit Profile', 'description': 'Allow editing company profile'},
#                 {'key': 'can_post_feed', 'label': 'Can Post Feed', 'description': 'Allow posting company updates'},
#                 {'key': 'can_manage_team', 'label': 'Can Manage Team', 'description': 'Allow managing HR team members'},
#             ],
#             'role_choices': [
#                 {'value': 'hr_admin', 'label': 'HR Admin'},
#                 {'value': 'hr_recruiter', 'label': 'HR Recruiter'},
#                 {'value': 'hr_coordinator', 'label': 'HR Coordinator'},
#             ]
#         }
#         return Response(permissions_data)


# class CompanyProfileViewSet(viewsets.ModelViewSet):
#     permission_classes = [IsAuthenticated, IsEmployer]
#     parser_classes = [MultiPartParser, FormParser]
#     http_method_names = ['get', 'put', 'patch']
    
#     def get_serializer_class(self):
#         if self.action in ['update', 'partial_update']:
#             return CompanyProfileEditSerializer
#         return CompanyProfileViewSerializer
    
#     def get_object(self):
#         return self.request.user.employer_profile
    
#     def list(self, request):
#         serializer = self.get_serializer(self.get_object())
#         return Response(serializer.data)

class HRUserViewSet(viewsets.ModelViewSet):
    """ViewSet for HR user management - supports both Employer and HR users"""
    permission_classes = [permissions.IsAuthenticated, IsEmployerOrHRTeam]

    def get_employer_profile(self, user):
        """Helper method to get employer profile based on user role"""
        try:
            if user.role == 'employer':
                return getattr(user, 'employer_profile', None)
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                return hr_record.company if hr_record else None
            return None
        except AttributeError:
            return None

    def check_hr_management_permission(self, user):
        """Check if user can manage HR team"""
        if user.role == 'employer':
            return True  # Employers can always manage HR team
        elif user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            return hr_record and hr_record.can_manage_team
        return False

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'create':
            return HRUserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return HRUserUpdateSerializer
        elif self.action == 'list':
            return HRUserListSerializer
        return HRUserSerializer

    def get_queryset(self):
        """Get queryset based on user permissions"""
        user = self.request.user
        employer_profile = self.get_employer_profile(user)
        
        if not employer_profile:
            return HRUser.objects.none()
        
        # Return HR users for the company
        return HRUser.objects.select_related('user', 'company').filter(
            company=employer_profile
        )

    def perform_create(self, serializer):
        """Handle HR user creation with validation"""
        user = self.request.user
        employer_profile = self.get_employer_profile(user)
        
        if not employer_profile:
            raise PermissionDenied(
                "You must have access to an employer profile to create HR users."
            )
        
        # Check if user has permission to manage HR team
        if not self.check_hr_management_permission(user):
            raise PermissionDenied(
                "You don't have permission to manage HR team members."
            )
        
        # The serializer will handle user creation and linking
        hr_user = serializer.save(company=employer_profile)
        
        logger.info(f"HR user created: {hr_user.user.email} for company {employer_profile.company_name} by {user.email}")

    def perform_update(self, serializer):
        """Handle HR user updates"""
        user = self.request.user
        
        # Check permission
        if not self.check_hr_management_permission(user):
            raise PermissionDenied(
                "You don't have permission to update HR team members."
            )
        
        hr_user = serializer.save()
        logger.info(f"HR user updated: {hr_user.user.email} by {user.email}")

    def perform_destroy(self, instance):
        """Delete both HR user and associated user account"""
        user = self.request.user
        
        # Check permission
        if not self.check_hr_management_permission(user):
            raise PermissionDenied(
                "You don't have permission to delete HR team members."
            )
        
        user_to_delete = instance.user
        
        # Delete the HRUser record first
        instance.delete()
        
        # Then delete the associated User record
        user_to_delete.delete()
        
        logger.info(f"HR user and associated user account deleted: {user_to_delete.email} by {user.email}")

    def create(self, request, *args, **kwargs):
        """Override create to provide better error handling"""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            
            return Response({
                'success': True,
                'message': 'HR user created successfully',
                'data': serializer.data,
                'created_by': {
                    'email': request.user.email,
                    'role': request.user.role
                }
            }, status=status.HTTP_201_CREATED, headers=headers)
            
        except PermissionDenied as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"HR user creation failed: {str(e)}")
            return Response({
                'success': False,
                'message': 'Failed to create HR user',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """Override update to provide better error handling"""
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            return Response({
                'success': True,
                'message': 'HR user updated successfully',
                'data': serializer.data,
                'updated_by': {
                    'email': request.user.email,
                    'role': request.user.role
                }
            })
            
        except PermissionDenied as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"HR user update failed: {str(e)}")
            return Response({
                'success': False,
                'message': 'Failed to update HR user',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Override destroy to provide proper success response"""
        try:
            instance = self.get_object()
            user_email = instance.user.email
            self.perform_destroy(instance)
        
            return Response({
                'success': True,
                'message': f'HR user {user_email} has been deleted successfully',
                'deleted_by': {
                    'email': request.user.email,
                    'role': request.user.role
                }
            }, status=status.HTTP_200_OK)
            
        except PermissionDenied as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def reactivate(self, request, pk=None):
        """Reactivate a soft-deleted HR user"""
        try:
            employer_profile = self.get_employer_profile(request.user)
            
            if not employer_profile:
                return Response({
                    'success': False,
                    'message': 'You must have access to an employer profile'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if not self.check_hr_management_permission(request.user):
                return Response({
                    'success': False,
                    'message': 'You don\'t have permission to reactivate HR team members'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get HR user including soft-deleted ones
            hr_user = get_object_or_404(
                HRUser.objects.select_related('user', 'company'),
                pk=pk,
                company=employer_profile
            )
            
            # Reactivate both HR user and associated user account
            hr_user.is_deleted = False
            hr_user.user.is_active = True
            
            hr_user.save(update_fields=['is_deleted'])
            hr_user.user.save(update_fields=['is_active'])
            
            return Response({
                'success': True,
                'message': f'HR user {hr_user.user.email} has been reactivated',
                'reactivated_by': {
                    'email': request.user.email,
                    'role': request.user.role
                }
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Failed to reactivate HR user',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def permissions_list(self, request):
        """Get available permissions for HR users"""
        permissions_data = {
            'available_permissions': [
                {'key': 'can_post_jobs', 'label': 'Can Post Jobs', 'description': 'Allow posting and managing job posts'},
                {'key': 'can_view_applicants', 'label': 'Can View Applicants', 'description': 'Allow viewing job applications'},
                {'key': 'can_edit_profile', 'label': 'Can Edit Profile', 'description': 'Allow editing company profile'},
                {'key': 'can_post_feed', 'label': 'Can Post Feed', 'description': 'Allow posting company updates'},
                {'key': 'can_manage_team', 'label': 'Can Manage Team', 'description': 'Allow managing HR team members'},
            ],
            'role_choices': [
                {'value': 'HR Manager', 'label': 'HR Manager'},
                {'value': 'Recruiter', 'label': 'Recruiter'},
                {'value': 'Interviewer', 'label': 'Interviewer'},
            ],
            'current_user': {
                'email': request.user.email,
                'role': request.user.role,
                'can_manage_team': self.check_hr_management_permission(request.user)
            }
        }
        return Response(permissions_data)


class CompanyProfileViewSet(viewsets.ModelViewSet):
    """
    Company profile management - supports both Employer and HR users
    """
    permission_classes = [IsAuthenticated, IsEmployerOrHR]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'put', 'patch']

    def get_employer_profile(self, user):
        try:
            if user.role == 'employer':
                return getattr(user, 'employer_profile', None)
            elif user.role == 'hr':
                hr_record = getattr(user, 'hr_user', None)
                return hr_record.company if hr_record else None
            return None
        except AttributeError:
            return None

    def check_edit_permission(self, user):
        if user.role == 'employer':
            return True
        elif user.role == 'hr':
            hr_record = getattr(user, 'hr_user', None)
            return hr_record and hr_record.can_edit_profile
        return False

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update', 'update_profile']:
            return CompanyProfileEditSerializer
        return CompanyProfileViewSerializer

    def get_object(self):
        employer_profile = self.get_employer_profile(self.request.user)
        if not employer_profile:
            raise PermissionDenied("You don't have access to any company profile")
        return employer_profile

    def list(self, request):
        try:
            profile = self.get_object()
            serializer = self.get_serializer(profile)
            return Response({
                'success': True,
                'data': serializer.data,
                'user_info': {
                    'email': request.user.email,
                    'role': request.user.role,
                    'can_edit': self.check_edit_permission(request.user)
                }
            })
        except PermissionDenied as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        return self._update_profile(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_profile(request, partial=True)

    def _update_profile(self, request, partial=False):
        try:
            if not self.check_edit_permission(request.user):
                return Response({
                    'success': False,
                    'message': 'You don\'t have permission to edit the company profile',
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)

            instance = self.get_object()

            # ✅ DRF automatically merges request.data + request.FILES with MultiPartParser
            serializer = self.get_serializer(instance, data=request.data, partial=partial)

            if serializer.is_valid():
                serializer.save()
                return Response({
                    'success': True,
                    'message': 'Company profile updated successfully',
                    'data': serializer.data,
                    'updated_by': {
                        'email': request.user.email,
                        'role': request.user.role
                    }
                })

            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except PermissionDenied as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Company profile update failed: {str(e)}")
            return Response({
                'success': False,
                'message': 'Failed to update company profile',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_update(self, serializer):
        serializer.save()
        logger.info(f"Company profile updated by {self.request.user.email} ({self.request.user.role})")

    # ✅ Custom endpoint - /update-profile/
    @action(detail=False, methods=['put', 'patch'], url_path='update-profile')
    def update_profile(self, request):
        return self._update_profile(request, partial=(request.method.lower() == 'patch'))
    
class JobApplicationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing job applications with HR/Employer filtering"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobApplicationListSerializer
        return JobApplicantSerializer
    
    def get_queryset(self):
        """Filter applications based on user role (HR/Employer)"""
        user = self.request.user
        
        # Optimize with select_related and prefetch_related
        queryset = JobApplication.objects.select_related(
            'applicant', 'applicant__jobseeker_profile', 'job_post', 'job_post__company'
        ).prefetch_related(
            'applicant__jobseeker_profile__resumes',
            Prefetch(
                'job_post__ai_remarks',
                queryset=AIRemarks.objects.filter(analysis_status='completed')
            )
        )
        
        # Filter based on user role
        if user.role == 'employer':
            # If user is employer, show applications for their company's jobs
            try:
                employer_profile = user.employer_profile
                queryset = queryset.filter(job_post__company=employer_profile)
            except:
                return queryset.none()
                
        elif user.role == 'hr':
            # If user is HR, show applications for their company's jobs
            try:
                # Assuming HR user has a company relation
                hr_company = user.hr_profile.company  # Adjust based on your HR model
                queryset = queryset.filter(job_post__company=hr_company)
            except:
                return queryset.none()
        else:
            # If not HR or Employer, return empty queryset
            return queryset.none()
        
        return queryset.order_by('-applied_at')
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update application status"""
        application = self.get_object()
        new_status = request.data.get('status')
        
        if new_status in dict(JobApplication.STATUS_CHOICES):
            application.status = new_status
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save()
            
            serializer = self.get_serializer(application)
            return Response(serializer.data)
        
        return Response({'error': 'Invalid status'}, status=400)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        """Filter applications by status"""
        status = request.query_params.get('status')
        queryset = self.get_queryset()
        
        if status:
            queryset = queryset.filter(status=status)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def high_fit_candidates(self, request):
        """Get candidates with high AI fit scores"""
        queryset = self.get_queryset()
        
        # Filter by AI remarks with high fit scores
        high_fit_apps = []
        for app in queryset:
            try:
                ai_remark = app.job_post.ai_remarks.filter(
                    job_seeker=app.applicant.jobseeker_profile
                ).first()
                if ai_remark and ai_remark.fit_score and ai_remark.fit_score >= 75:
                    high_fit_apps.append(app)
            except:
                continue
        
        serializer = self.get_serializer(high_fit_apps, many=True)
        return Response(serializer.data)
    

class JobPostViewSets(viewsets.ReadOnlyModelViewSet):
    serializer_class = JobPostListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'hr':
            return JobPost.objects.filter(created_by=user)
        elif user.role == 'employer':
            return JobPost.objects.filter(company=user.employer_profile)
        
        return JobPost.objects.none()


class JobApplicantsListView(generics.ListAPIView):
    """
    List applicants for a specific job post with AI remarks included.
    Allowed: Employer (owner of company) OR HR users of same company.
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        job_id = self.kwargs.get("job_id")
        job_post = get_object_or_404(JobPost, id=job_id)

        user = self.request.user

        # Case 1: Superuser
        if user.is_superuser:
            pass

        # Case 2: Employer (company owner)
        elif hasattr(user, "employer_profile") and job_post.company == user.employer_profile:
            pass

        # Case 3: HR User of the same company with view permission
        elif hasattr(user, "hr_user") and job_post.company == user.hr_user.company:
            if not user.hr_user.can_view_applicants:
                raise PermissionDenied("You don't have permission to view applicants.")
        else:
            raise PermissionDenied("You do not have permission to view applicants for this job.")

        queryset = JobApplication.objects.filter(job_post=job_post)

        # Optional filter by application status
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset
    

class JobApplicationStatusUpdateView(generics.UpdateAPIView):
    """
    Update status of a job application.
    Allowed: Employer (owner of company) OR HR users of same company.
    Restricted: Cannot set to 'user_rejected' or 'withdrawn'.
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "application_id"  # expects /applications/<id>/status/

    def get_object(self):
        application = get_object_or_404(JobApplication, id=self.kwargs[self.lookup_url_kwarg])
        job_post = application.job_post
        user = self.request.user

        # Case 1: Superuser can always update
        if user.is_superuser:
            return application

        # Case 2: Employer (company owner)
        elif hasattr(user, "employer_profile") and job_post.company == user.employer_profile:
            return application

        # Case 3: HR user of the same company with permission
        elif hasattr(user, "hr_user") and job_post.company == user.hr_user.company:
            if not user.hr_user.can_manage_applicants:
                raise PermissionDenied("You don't have permission to update applicant status.")
            return application

        # Else not allowed
        raise PermissionDenied("You do not have permission to update this application.")

    def update(self, request, *args, **kwargs):
        application = self.get_object()
        new_status = request.data.get("status")

        if not new_status:
            raise ValidationError({"status": "This field is required."})

        # Restrict user-controlled statuses
        restricted_statuses = ["user_rejected", "withdrawn"]
        if new_status in restricted_statuses:
            raise ValidationError({"status": f"Cannot update status to '{new_status}'."})

        # Validate against STATUS_CHOICES
        valid_statuses = [choice[0] for choice in JobApplication.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"status": f"Invalid status '{new_status}'."})

        # Update fields
        application.status = new_status
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        return Response(
            {"detail": f"Application status updated to '{new_status}'."},
            status=status.HTTP_200_OK
        )

class ApplicationRemarkViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Application Remarks.
    - HR/Employer/Interviewer can create remarks.
    - Users can list remarks on applications.
    - Only remark owners (or staff) can delete.
    """
    serializer_class = ApplicationRemarkSerializer
    queryset = ApplicationRemark.objects.select_related('application', 'reviewer').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Example: Employers/HR can see remarks on their job posts only
        user = self.request.user
        qs = super().get_queryset()

        if user.role in ['hr', 'employer']:
            return qs.filter(application__job_post__created_by=user)
        elif user.role == 'interviewer':
            return qs.filter(reviewer=user)
        elif user.role == 'jobseeker':
            # Jobseeker can only see remarks on their own applications
            return qs.filter(application__applicant=user)
        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ['hr', 'employer', 'interviewer']:
            raise PermissionDenied("You are not allowed to add remarks.")
        serializer.save(reviewer=user)

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.reviewer != user and not user.is_staff:
            raise PermissionDenied("You can only delete your own remarks.")
        instance.delete()






class ApplicationProfileView(APIView):
    permission_classes = [IsAuthenticated, CanViewApplicationProfile]

    def get(self, request, pk, *args, **kwargs):
        # Optimize cross-relations
        qs = (
            JobApplication.all_objects  # includes soft-deleted manager if needed
            .select_related("job_post", "applicant", "applicant__jobseeker_profile")
            .prefetch_related(
                Prefetch(
                    "applicant__jobseeker_profile__resumes",
                    queryset=Resume.objects.filter(is_active=True).order_by("-is_default", "-updated_at"),
                    to_attr="prefetched_resumes",
                )
            )
        )
        application = get_object_or_404(qs, pk=pk)

        # Object-level permission
        self.check_object_permissions(request, application)

        profile = application.applicant.jobseeker_profile

        # Pick default resume; fallback to most recent active
        default_resume = None
        resumes = getattr(profile, "prefetched_resumes", None)
        if resumes:
            default_resume = next((r for r in resumes if r.is_default), None) or resumes[0]
        else:
            default_resume = (
                Resume.objects.filter(profile=profile, is_active=True)
                .order_by("-is_default", "-updated_at")
                .first()
            )

        # Unique AI remark per (job_post, job_seeker)
        ai_remark = AIRemarks.objects.filter(job_post=application.job_post, job_seeker=profile).first()

        # Remarks history (most recent first in model ordering; return ascending by time if preferred)
        remarks_qs = application.remarks_history.all().order_by("created_at")

        payload = {
            "ai_analysis": ai_remark,
            "resume": default_resume,
            "profile": profile,
            "application": application,
            "remarks": remarks_qs,
        }
        return Response(ApplicationProfileViewSerializer(payload).data, status=status.HTTP_200_OK)


