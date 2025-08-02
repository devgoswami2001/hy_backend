# hyresense/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from django.conf import settings
from django.conf.urls.static import static

schema_view = get_schema_view(
    openapi.Info(
        title="HyreSense Job Portal API",
        default_version='v1',
        description="API documentation for the HyreSense Job Platform",
        terms_of_service="https://www.hyresense.com/terms/",
        contact=openapi.Contact(email="support@hyresense.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Admin Panel
    path('adminthedevrocks/', admin.site.urls),

    # JWT Authentication
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # App-specific routes (use versioning and consistent structure)
    path('api/v1/', include('hyresensemain.urls')),       # Home or Core App
    path('api/v1/jobseeker/', include('jobseaker.urls')), # Jobseeker App
    path('api/v1/employer/', include('employer.urls')),   # Employer App

    # API Documentation (Swagger and ReDoc)
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
