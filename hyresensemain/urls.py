from django.urls import path
from .views import *

urlpatterns = [
    #path('register/', UserRegistrationView.as_view(), name='register'),
    path('register/employer', EmployerRegisterView.as_view(), name='register'),
    path('register/jobseeker', JobSeekerRegisterView.as_view(), name='jobseeker-register'),
    path('otp/generate', GenerateOTPView.as_view(), name='generate_otp'),
    path('otp/verify', VerifyOTPView.as_view(), name='verify_otp'),
]
