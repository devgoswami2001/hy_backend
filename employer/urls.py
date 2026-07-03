# apps/employers/urls.py
from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from .views import *

app_name = 'employers'

router = DefaultRouter()
router.register(r'profiles', EmployerProfileViewSet, basename='employer-profile')
router.register(r'company-profile', CompanyProfileViewSet, basename='company-profile')
router.register(r'jobs', views.JobPostViewSet, basename='jobs')
router.register(r'job-posts', JobPostViewSets, basename='jobpost')
router.register(r'application-remarks', ApplicationRemarkViewSet, basename='application-remarks')
hr_user_list = HRUserViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

hr_user_detail = HRUserViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})

urlpatterns = [
    path('', include(router.urls)),
    path('check-profile/', views.check_employer_profile, name='check_employer_profile'),
    path('profile/create/', EmployerProfileCreateView.as_view(), name='create-profile'),#post
    path('profile/update/', EmployerProfileUpdateView.as_view(), name='update-profile'),#patch
    # Dashboard
    path('dashboard/employer/<int:pk>/', EmployerProfileViewSet.as_view({'get': 'dashboard'}), name='employer-dashboard'),
    #path('monthly-stats/', views.MonthlyApplicationsViewSet.as_view({'get': 'monthly_stats'}), name='monthly-applications'),
    path('monthly-stats/', views.monthly_applications_view, name='monthly-applications'),
    path('employer/me/', EmployerIdView.as_view(), name='employer-id'),

    path('jobs/', views.JobPostListCreateAPIView.as_view(), name='job-list-create'),
    # Specific job edit/delete/view
    path('employer/job-posts/<int:id>/', views.JobPostViewSet.as_view({
    'get': 'retrieve', 
    'put': 'update', 
    'patch': 'partial_update',
    'delete': 'destroy'
     })),
    
    # My jobs
    path('employer/my-jobs/', views.JobPostViewSet.as_view({'get': 'my_jobs'})),
    path('employer/job-posts/<int:id>/deactivate/', views.JobPostViewSet.as_view({
    'post': 'deactivate'
    })),
    path('jobs/<int:id>/', views.JobPostViewSet.as_view({'get': 'retrieve'})),
    # Featured jobs
    path('jobs/featured/', views.FeaturedJobPostListAPIView.as_view(), name='featured-jobs'),
    
    # Employer stats
    path('jobs/stats/', views.JobPostStatsAPIView.as_view(), name='job-stats'),

    path('posts/', views.CompanyPostListCreateView.as_view(), name='post-list-create'),
    path('posts/<int:pk>/', views.CompanyPostDetailView.as_view(), name='post-detail'),
    path('posts/my-company/', CompanyPostsByUserCompanyView.as_view(), name='posts-my-company'),
    path('posts/<int:pk>/like/', views.CompanyPostLikeView.as_view(), name='post-like'),
    path('posts/<int:pk>/unlike/', views.CompanyPostUnlikeView.as_view(), name='post-unlike'),

    # Comments for a given post (top-level only)
    path('posts/<int:pk>/comments/', views.CompanyPostCommentListCreateView.as_view(), name='post-comments-list-create'),

    # Comment Like/Unlike
    path('comments/<int:pk>/like/', views.PostCommentLikeView.as_view(), name='comment-like'),
    path('comments/<int:pk>/unlike/', views.PostCommentUnlikeView.as_view(), name='comment-unlike'),

    # Reply to a specific comment
    path('comments/<int:pk>/reply/', views.PostCommentReplyCreateView.as_view(), name='comment-reply'),
     # List all HR users, or create a new HR user
    path('hr-users/', hr_user_list, name='hruser-list'),

    # Retrieve, update, partially update, or delete a specific HR user by id
    path('hr-users/<int:pk>/', hr_user_detail, name='hruser-detail'),

    path('leadership/', EmployerLeadershipListView.as_view(), name='leadership-list'),
    path('leadership/create/', EmployerLeadershipCreateView.as_view(), name='leadership-create'),
    path('leadership/<int:pk>/update/', EmployerLeadershipUpdateView.as_view(), name='leadership-update'),
    path('leadership/<int:pk>/delete/', EmployerLeadershipDeleteView.as_view(), name='leadership-delete'),



    path("jobs/<int:job_id>/applicants/", JobApplicantsListView.as_view(), name="job-applicants"),
    path("applications/<int:application_id>/status/", JobApplicationStatusUpdateView.as_view(),name="job-application-status-update" ),
    path("applications/<int:pk>/profile/", ApplicationProfileView.as_view(), name="application-profile"),
    path(
        "job-chat/send-message/",
        SendJobApplicationMessageView.as_view(),
        name="send-job-application-message"
    ),

    path(
        "job-chat/messages/<int:job_application_id>/",
        JobApplicationChatMessagesView.as_view(),
        name="job-chat-messages"
    ),
    path(
        "subscription-plans/",
        EmployerSubscriptionPlanListView.as_view(),
        name="employer-subscription-plans"
    ),
    path(
        "start-payment/",
        start_employer_payu_payment,
        name="employer-start-payment"
    ),
    path(
        "payu/webhook/",
        employer_payu_webhook,
        name="employer-payu-webhook"
    ),

    path(
        "active-subscription/",
        EmployerActiveSubscriptionView.as_view(),
        name="employer-active-subscription"
    ),
    path(
        "request-hr-seats/",
        request_hr_seats,
        name="request-hr-seats"
    ),

]

