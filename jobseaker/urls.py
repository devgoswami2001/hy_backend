
from . import views

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
router = DefaultRouter()
router.register('jobseeker-profile', JobSeekerProfileViewSet, basename='jobseeker-profile')
router.register('resumes', ResumeViewSet, basename='resume')
router.register(r'company-posts', CompanyPostViewSet, basename='company-posts')
router.register(r'comments', PostCommentViewSet, basename='comments')


urlpatterns = [
    path('', include(router.urls)),
    path('check-resume/', views.check_resume_exists, name='check-resume'),
    path("users/me/", CurrentUserView.as_view(), name="current-user"),
    path('upload-resume/', views.upload_resume, name='upload_resume'),
    path('jobs/by-skills/', views.jobs_by_skills, name='jobs-by-skills'),
    path('jobs/<int:pk>/', views.get_job_post_by_id, name='job-detail-by-id'),
    path("analyze-application/", views.analyze_application_api, name="analyze_application_api"),
    path('job-applications/', JobApplicationCreateView.as_view(),name="JobApplicationCreateView"),
    path('applications/comprehensive/', 
         JobApplicationComprehensiveView.as_view(), 
         name='job-applications-comprehensive'),
    
    path('applications/<uuid:id>/comprehensive/', 
         JobApplicationDetailComprehensiveView.as_view(), 
         name='job-application-detail-comprehensive'),
     path('applications/<int:pk>/status/', JobApplicationStatusUpdateView.as_view(), name='update-application-status'),
     path('search/employers/', EmployerSearchView.as_view(), name='employer_search'),
     path('employer-profiles/search/', EmployerProfileSearchView.as_view(), name='employer-profile-search'),
    
    # Employer profile detail with ID instead of slug
    path('employer-profiles/<int:id>/', EmployerProfileDetailView.as_view(), name='employer-profile-detail'),
    
    # All company posts with ID instead of slug
    path('companies/<int:id>/posts/', CompanyPostsListView.as_view(), name='company-posts-list'),
    
    # All job posts with ID instead of slug
    path('companies/<int:id>/jobs/', CompanyJobsListView.as_view(), name='company-jobs-list'),
    path('follow-company/', views.FollowCompanyView.as_view(), name='follow-company'),
    path('company/<int:company_id>/follow-status/', views.check_follow_status, name='check-follow-status'),


]
