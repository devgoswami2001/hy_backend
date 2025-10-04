from django.shortcuts import render
from django.http import Http404
from django.db.models import Q
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets, status, generics
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from jobseaker.services.ai_matcher import JobAIAnalyzer
from rest_framework.throttling import UserRateThrottle
from django.core.exceptions import ValidationError
from employer.models import JobPost, JobApplication
from .models import JobSeekerProfile, Resume, User, AIRemarks
from .serializers import *
from .permissions import IsJobseekerPermission
import logging
from django.http import JsonResponse
from django.views import View
from django.urls import reverse
from employer.models import EmployerProfile ,CompanyFollower
from datetime import timedelta
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.viewsets import ModelViewSet
from rest_framework.exceptions import PermissionDenied
logger = logging.getLogger(__name__)

@api_view(['GET'])
def check_resume_exists(request):
    user = request.user
    
    try:
        profile = JobSeekerProfile.objects.get(user=user)
        has_resume = Resume.objects.filter(profile=profile).exists()
        return Response({'has_resume': has_resume})
    except JobSeekerProfile.DoesNotExist:
        return Response({'has_resume': False})


def analyze_application(job_post_id, seeker):
    """
    Analyze a job application using AI and return structured results.
    """
    try:
        job_post = JobPost.objects.get(id=job_post_id)
        
        # Handle seeker parameter (could be instance or ID)
        if isinstance(seeker, JobSeekerProfile):
            job_seeker = seeker
        else:
            job_seeker = JobSeekerProfile.objects.get(id=seeker.id if hasattr(seeker, 'id') else seeker)
        
        # Check if analysis already exists
        existing_analysis = AIRemarks.objects.filter(
            job_post=job_post, 
            job_seeker=job_seeker,
            analysis_status=AIRemarks.AnalysisStatus.COMPLETED
        ).first()
        
        if existing_analysis:
            result = existing_analysis
        else:
            analyzer = JobAIAnalyzer(job_post, job_seeker)
            result = analyzer.analyze()
        
        # Convert to dict format
        return {
            "id": str(result.id),
            "job_post": result.job_post.id,
            "job_seeker": result.job_seeker.id,
            "fit_score": float(result.fit_score) if result.fit_score else None,
            "fit_level": result.fit_level,
            "is_fit": result.is_fit,
            "remarks": result.remarks,
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "missing_skills": result.missing_skills,
            "matching_skills": result.matching_skills,
            "interview_recommendation": result.interview_recommendation,
            "suggested_interview_questions": result.suggested_interview_questions,
            "analysis_status": result.analysis_status,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
        
    except Exception as e:
        raise Exception(f"Application analysis failed: {e}")


class JobSeekerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSeekerProfile
        exclude = ['first_name', 'last_name']  # Excluding since they're in User model
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

class JobSeekerProfileViewSet(viewsets.ModelViewSet):
    serializer_class = JobSeekerProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return JobSeekerProfile.objects.filter(user=self.request.user)
    
    def get_object(self):
        try:
            return JobSeekerProfile.objects.get(user=self.request.user)
        except JobSeekerProfile.DoesNotExist:
            raise Http404("Profile not found")
    
    def create(self, request, *args, **kwargs):
        if request.user.role != User.Roles.JOBSEEKER:
            return Response({'detail': 'User role must be jobseeker'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if hasattr(request.user, 'jobseeker_profile'):
            return Response({'detail': 'Profile already exists'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)




class ResumeViewSet(viewsets.ModelViewSet):
    serializer_class = ResumeCreateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            profile = JobSeekerProfile.objects.get(user=self.request.user)
            return Resume.objects.filter(profile=profile)
        except JobSeekerProfile.DoesNotExist:
            return Resume.objects.none()
    
    def create(self, request, *args, **kwargs):
        try:
            profile = JobSeekerProfile.objects.get(user=request.user)
        except JobSeekerProfile.DoesNotExist:
            return Response({'detail': 'JobSeeker profile not found'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            resume = serializer.save(profile=profile)
            resume.calculate_completion()
            resume.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_resume(request):
    serializer = ResumeUploadSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        result = serializer.save()
        return Response({
            "success": True,
            "profile_id": str(result['profile'].id),
            "resume_id": str(result['resume'].id),
            "completion_percentage": result['resume'].completion_percentage
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def jobs_by_skills(request):
    try:
        # Get jobseeker profile
        profile = JobSeekerProfile.objects.get(user=request.user)
        resume = Resume.objects.filter(profile=profile, is_default=True).first()

        if not resume:
            return Response({"error": "No resume found"}, status=400)

        # Extract skills from resume JSON
        user_skills = []
        if resume.skills_data and isinstance(resume.skills_data, dict):
            for _, skills in resume.skills_data.items():
                if isinstance(skills, list):
                    user_skills.extend(skills)

        if not user_skills:
            return Response({"jobs": [], "message": "Add skills first"})

        # Get jobs already applied by the user
        applied_job_ids = JobApplication.objects.filter(
            applicant=request.user
        ).values_list("job_post_id", flat=True)

        # Convert user skills to lowercase for matching
        user_skills_lower = [s.lower() for s in user_skills]

        matching_jobs = []

        # Filter active jobs excluding applied ones
        for job in JobPost.active_jobs.exclude(id__in=applied_job_ids):
            job_skills = job.required_skills or []
            job_skills_lower = [s.lower() for s in job_skills]

            # Check skill overlap
            if any(skill in job_skills_lower for skill in user_skills_lower):
                company_profile_image = None
                if hasattr(job.company, "profile_image") and job.company.profile_image:
                    company_profile_image = request.build_absolute_uri(
                        job.company.profile_image.url
                    )

                matching_jobs.append({
                    "id": job.id,
                    "title": job.title,
                    "slug": job.slug,
                    "company_name": job.company_name,
                    "company_profile_image": company_profile_image,
                    "location": job.location,
                    "employment_type": job.employment_type,
                    "experience_level": job.experience_level,
                    "working_mode": job.working_mode,
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "deadline": job.deadline,
                    "description": job.description,
                    "required_skills": job.required_skills,
                    "screening_questions": job.screening_questions,
                    "applications_count": job.applications_count,
                    "views_count": job.views_count,
                    "is_featured": job.is_featured,
                    "created_at": job.created_at,
                    "created_by": job.created_by.email if job.created_by else None,
                })

        return Response({
            "jobs": matching_jobs,
            "total": len(matching_jobs),
        })

    except JobSeekerProfile.DoesNotExist:
        return Response({"error": "Profile not found"}, status=404)
    
@api_view(["POST"])
def analyze_application_api(request):
    """
    API endpoint to analyze a job seeker's fit for a job post.
    Expected JSON:
    {
        "job_post_id": "<uuid>"
    }
    """
    job_post_id = request.data.get("job_post_id")

    if not job_post_id:
        return Response(
            {"error": "job_post_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        seeker = JobSeekerProfile.objects.get(user=request.user)
        result = analyze_application(job_post_id, seeker)  # pass seeker_id here
        return Response({"success": True, "result": result}, status=status.HTTP_200_OK)

    except JobPost.DoesNotExist:
        return Response({"error": "Job post not found"}, status=status.HTTP_404_NOT_FOUND)
    except JobSeekerProfile.DoesNotExist:
        return Response({"error": "Job seeker profile not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



class JobApplicationRateThrottle(UserRateThrottle):
    scope = 'job_application'
    rate = '10/hour'

class JobApplicationCreateView(generics.CreateAPIView):
    """
    Create a new job application with subscription + auto-resume selection
    """
    queryset = JobApplication.objects.all()
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [JobApplicationRateThrottle]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        try:
            job_post_id = request.data.get("job_post")
            status_value = request.data.get("status")

            # ✅ Validate status
            if status_value not in ["applied", "user_rejected"]:
                return Response(
                    {"error": "Invalid status. Allowed values: 'applied' or 'user_rejected'"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            with transaction.atomic():
                # ✅ Subscription check
                job_seeker = request.user.jobseeker_profile
                subscription = getattr(job_seeker, "subscription", None)

                if not subscription or not subscription.is_active:
                    return Response(
                        {"error": "You need an active subscription to apply for jobs."},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # ✅ Daily swipe limit check (only if applying, not rejecting)
                if status_value == "applied":
                    if not subscription.can_swipe_job():
                        return Response(
                            {"error": "You have reached your daily job application limit."},
                            status=status.HTTP_403_FORBIDDEN
                        )

                # ✅ Auto-fetch default resume
                default_resume = None
                if status_value == "applied":
                    default_resume = job_seeker.resumes.filter(is_default=True).first()
                    if not default_resume:
                        return Response(
                            {'error': 'No default resume found. Please set a default resume.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if not default_resume.resume_pdf:
                        return Response(
                            {'error': 'Default resume does not have a PDF file.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # ✅ Save application
                validated_data = serializer.validated_data
                validated_data['applicant'] = request.user
                validated_data['status'] = status_value
                if default_resume:
                    validated_data['resume'] = default_resume.resume_pdf

                application = JobApplication.objects.create(**validated_data)

                # ✅ Increment swipe if applied
                if status_value == "applied":
                    subscription.increment_swipe()

                logger.info(
                    f"Job application created. ID: {application.id}, "
                    f"User: {request.user.id}, Job: {application.job_post.id}, Status: {status_value}"
                )

                return Response(
                    {
                        "message": f"Job {status_value} successfully",
                        "application": JobApplicationSerializer(application).data
                    },
                    status=status.HTTP_201_CREATED
                )

        except serializers.ValidationError as e:
            logger.warning(f"Validation error: {e.detail} - User: {request.user.id}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)} - User: {request.user.id}")
            return Response(
                {"error": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





class JobApplicationComprehensiveView(generics.ListAPIView):
    """Complete comprehensive view with ALL job application information"""
    serializer_class = JobApplicationComprehensiveSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return JobApplication.objects.filter(
            applicant=self.request.user,
            is_deleted=False
        ).select_related(
            'job_post', 
            'job_post__company',
            'reviewed_by'
        ).prefetch_related(
            'job_post__ai_remarks'
        ).order_by('-applied_at')

class JobApplicationDetailComprehensiveView(generics.RetrieveAPIView):
    """Single job application detailed view"""
    serializer_class = JobApplicationComprehensiveSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        return JobApplication.objects.filter(
            applicant=self.request.user,
            is_deleted=False
        ).select_related(
            'job_post', 
            'job_post__company',
            'reviewed_by'
        ).prefetch_related(
            'job_post__ai_remarks'
        )
# Usage example in your Django views
# def generate_stunning_resume_pdf(request, resume_id):
#     """Django view to generate stunning resume PDF"""
#     try:
#         from .models import Resume
        
#         resume = Resume.objects.select_related('profile', 'profile__user').get(id=resume_id)
#         pdf_url = create_modern_resume_pdf(resume)
        
#         return JsonResponse({
#             'success': True,
#             'pdf_url': pdf_url,
#             'message': 'Stunning resume PDF generated successfully!'
#         })
    
#     except Resume.DoesNotExist:
#         return JsonResponse({
#             'success': False,
#             'message': 'Resume not found'
#         }, status=404)
#     except Exception as e:
#         return JsonResponse({
#             'success': False,
#             'message': f'Error generating PDF: {str(e)}'
#         }, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_job_post_by_id(request, pk):
    """
    Get detailed information of a specific job post by ID
    """
    try:
        job_post = get_object_or_404(JobPost.active_jobs, id=pk)
        
        # Increment views count
        job_post.views_count += 1
        job_post.save(update_fields=['views_count'])
        
        serializer = JobPostSerializer(job_post)
        
        return Response({
            'success': True,
            'message': 'Job post retrieved successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving job post: {str(e)}',
            'data': None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

class JobApplicationStatusUpdateView(generics.UpdateAPIView):
    queryset = JobApplication.objects.all()
    serializer_class = JobApplicationStatusUpdateSerializer
    
    def patch(self, request, *args, **kwargs):
        application = self.get_object()
        serializer = self.get_serializer(application, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Status updated successfully'}, status=status.HTTP_200_OK)


class EmployerSearchView(View):
    def get(self, request):
        query = request.GET.get('name', '')
        
        if len(query) < 2:
            return JsonResponse([], safe=False)
        
        employers = EmployerProfile.objects.filter(
            company_name__icontains=query
        )[:10]
        
        results = []
        for emp in employers:
            results.append({
                "id": emp.id,
                "name": emp.company_name,
            })
        
        return JsonResponse(results, safe=False)
    


class EmployerProfileSearchView(generics.ListAPIView):
    """
    Search employer profiles by company name with pagination
    """
    serializer_class = EmployerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EmployerProfile.objects.select_related('user').filter(is_active=True)
        
        # Search parameters
        company_name = self.request.query_params.get('company_name')
        location = self.request.query_params.get('location')
        
        if company_name:
            queryset = queryset.filter(company_name__icontains=company_name)
        
        # Additional filters can be added here
        return queryset.order_by('-followers_count', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })

class EmployerProfileDetailView(generics.RetrieveAPIView):
    """
    Get detailed employer profile with latest posts and jobs using ID
    """
    queryset = EmployerProfile.objects.select_related('user')
    serializer_class = EmployerProfileSerializer
    lookup_field = 'id'  # Changed from 'slug' to 'id'
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Get employer profile by ID
        employer_profile = self.get_object()
        
        # Rest of the code remains same...
        latest_company_posts = CompanyPost.objects.filter(
            company=employer_profile
        ).select_related('created_by').order_by('-is_pinned', '-created_at')[:10]
        
        latest_job_posts = JobPost.objects.filter(
            company=employer_profile,
            is_active=True
        ).select_related('created_by').order_by('-is_featured', '-created_at')[:10]

        employer_profile_data = EmployerProfileSerializer(employer_profile).data
        company_posts_data = CompanyPostSerializer(latest_company_posts, many=True).data
        job_posts_data = JobPostSerializer(latest_job_posts, many=True).data

        return Response({
            'employer_profile': employer_profile_data,
            'latest_company_posts': {
                'count': latest_company_posts.count(),
                'results': company_posts_data
            },
            'latest_job_posts': {
                'count': latest_job_posts.count(),
                'results': job_posts_data
            },
            'navigation_urls': {
                'all_company_posts': f"/api/v1/jobseeker/companies/{employer_profile.id}/posts/",
                'all_job_posts': f"/api/v1/jobseeker/companies/{employer_profile.id}/jobs/"
            }
        })

class CompanyPostsListView(generics.ListAPIView):
    """
    List all company posts for a specific employer using ID
    """
    serializer_class = CompanyPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        company_id = self.kwargs.get('id')  # Changed from 'slug' to 'id'
        employer_profile = get_object_or_404(EmployerProfile, id=company_id)
        
        return CompanyPost.objects.filter(
            company=employer_profile,
            is_active=True
        ).select_related('created_by').order_by('-is_pinned', '-created_at')

class CompanyJobsListView(generics.ListAPIView):
    """
    List all job posts for a specific employer using ID
    """
    serializer_class = JobPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        company_id = self.kwargs.get('id')  # Changed from 'slug' to 'id'
        employer_profile = get_object_or_404(EmployerProfile, id=company_id)
        
        return JobPost.objects.filter(
            company=employer_profile,
            is_active=True
        ).select_related('created_by').order_by('-is_featured', '-created_at')
    



class FollowCompanyView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        company_id = request.data.get('company_id')
        
        try:
            company = EmployerProfile.objects.get(id=company_id)
            
            # Get or create follow record
            follow, created = CompanyFollower.objects.get_or_create(
                company=company, 
                user=request.user,
                defaults={'is_active': True}
            )
            
            if created:
                return Response({'message': 'Following company', 'is_following': True}, status=201)
            else:
                # Toggle follow status
                follow.is_active = not follow.is_active
                follow.save()
                
                if follow.is_active:
                    return Response({'message': 'Following company', 'is_following': True}, status=200)
                else:
                    return Response({'message': 'Unfollowed company', 'is_following': False}, status=200)
            
        except EmployerProfile.DoesNotExist:
            return Response({'message': 'Company not found'}, status=404)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_follow_status(request, company_id):
    is_following = CompanyFollower.objects.filter(
        company_id=company_id,
        user=request.user,
        is_active=True
    ).exists()
    
    return Response({'is_following': is_following})



class CompanyPostViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for viewing company posts
    """
    serializer_class = CompanyPostSerializer
    permission_classes = []  # or [IsAuthenticated] if required

    def get_queryset(self):
        user = self.request.user
        print("DEBUG >>> User:", user, "| Authenticated:", user.is_authenticated)

        # Companies user follows
        following_companies = CompanyFollower.objects.filter(
            user=user,
        ).values_list("company_id", flat=True)
        print("DEBUG >>> Following companies:", list(following_companies))

        # Posts from followed companies
        followed_posts = CompanyPost.objects.filter(
            company_id__in=following_companies,
        ).order_by("-is_pinned", "-created_at")
        print("DEBUG >>> Followed posts:", list(followed_posts.values("id", "title")))

        if followed_posts.count() >= 20:
            print("DEBUG >>> Returning only followed posts (20 max)")
            return followed_posts[:20]

        # Fill remaining with posts from all companies
        remaining_count = 20 - followed_posts.count()
        followed_ids = list(followed_posts.values_list("id", flat=True))

        additional_posts = CompanyPost.objects.filter(
        ).exclude(id__in=followed_ids).order_by("-is_pinned", "-created_at")[:remaining_count]
        print("DEBUG >>> Additional posts:", list(additional_posts.values("id", "title")))

        all_ids = list(followed_ids) + list(additional_posts.values_list("id", flat=True))
        print("DEBUG >>> Final IDs for queryset:", all_ids)

        qs = CompanyPost.objects.filter(id__in=all_ids).order_by("-is_pinned", "-created_at")
        print("DEBUG >>> Final queryset count:", qs.count())
        return qs

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        """Like/Unlike a post"""
        post = self.get_object()
        like, created = PostLike.objects.get_or_create(
            post=post,
            user=request.user
        )

        if not created:
            like.delete()
            post.likes_count = max(0, post.likes_count - 1)
            liked = False
        else:
            post.likes_count += 1
            liked = True

        post.save(update_fields=["likes_count"])
        return Response({"liked": liked, "likes_count": post.likes_count})

    @action(detail=True, methods=["post"])
    def comment(self, request, pk=None):
        """Add comment to post"""
        post = self.get_object()
        serializer = PostCommentSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            comment = serializer.save(post=post, user=request.user)
            post.comments_count += 1
            post.save(update_fields=["comments_count"])
            return Response(PostCommentSerializer(comment, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PostCommentViewSet(ModelViewSet):
    serializer_class = PostCommentSerializer
    permission_classes = []
    
    def get_queryset(self):
        # For list view, filter by post_id
        post_id = self.request.query_params.get('post_id')
        if post_id:
            return PostComment.all_objects.filter(
                post_id=post_id
            ).order_by('-created_at')
        
        # For detail views (like /comments/2/like/), return all comments
        # so get_object() can find the specific comment
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy', 'like', 'reply']:
            return PostComment.all_objects.all()
            
        return PostComment.all_objects.none()
    
    def perform_destroy(self, instance):
        """
        Delete comment only if user is the comment owner
        Also delete all replies if it's a main comment
        """
        user = self.request.user
        
        # Check if user owns the comment
        if instance.user != user:
            raise PermissionDenied("You can only delete your own comments.")
        
        with transaction.atomic():
            # If it's a main comment, delete all replies first
            if not instance.parent:
                replies = PostComment.all_objects.filter(parent=instance)
                replies_count = replies.count()
                replies.delete()
                
                # Update post comments count
                instance.post.comments_count = max(0, instance.post.comments_count - (1 + replies_count))
                instance.post.save(update_fields=['comments_count'])
            else:
                # If it's a reply, update parent's reply count
                parent = instance.parent
                parent.replies_count = max(0, parent.replies_count - 1)
                parent.save(update_fields=['replies_count'])
                
                # Update post comments count
                instance.post.comments_count = max(0, instance.post.comments_count - 1)
                instance.post.save(update_fields=['comments_count'])
            
            # Delete the comment
            instance.delete()
    
    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        """Reply to a comment"""
        parent_comment = self.get_object()
        serializer = PostCommentSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            reply = serializer.save(
                post=parent_comment.post,
                user=request.user,
                parent=parent_comment
            )
            parent_comment.replies_count += 1
            parent_comment.save(update_fields=['replies_count'])
            
            # Update post comments count
            parent_comment.post.comments_count += 1
            parent_comment.post.save(update_fields=['comments_count'])
            
            return Response(PostCommentSerializer(reply, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """Like/Unlike a comment"""
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(
            comment=comment,
            user=request.user
        )
        
        if not created:
            like.delete()
            comment.likes_count = max(0, comment.likes_count - 1)
            liked = False
        else:
            comment.likes_count += 1
            liked = True
            
        comment.save(update_fields=['likes_count'])
        return Response({'liked': liked, 'likes_count': comment.likes_count})

