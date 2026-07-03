# hyresensemain/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from .serializers import *
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests
from rest_framework.views import APIView
from django.db import transaction
from django.utils.crypto import get_random_string
from .utils.google_auth import verify_google_token
from .utils.jwt import generate_tokens

from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = []  # Koi permission nahi chahiye registration ke liye
    
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            'message': 'User created successfully',
            'user_id': user.id,
            'email': user.email
        }, status=status.HTTP_201_CREATED)


class EmployerRegisterView(generics.CreateAPIView):
    serializer_class = EmployerRegistrationSerializer
    permission_classes = []  # No permissions required for registration

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)  # preferred over hardcoding class
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": "Employer registered successfully",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role
            }
        }, status=status.HTTP_201_CREATED)


class GenerateOTPView(generics.CreateAPIView):
    serializer_class = OTPGenerateSerializer
    permission_classes = []
    def post(self, request):
        serializer = OTPGenerateSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(generics.CreateAPIView):
    serializer_class = OTPVerifySerializer
    permission_classes = []
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class JobSeekerRegisterView(generics.CreateAPIView):
    serializer_class = JobSeekerRegistrationSerializer
    permission_classes = []  # No permissions required for registration

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)  # preferred over hardcoding class
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": "JobSeeker registered successfully",
            "user": {
                "id": str(user.id),  # Convert UUID to string for JSON serialization
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        }, status=status.HTTP_201_CREATED)
    
from rest_framework import generics, permissions
class EarlyAccessRequestCreateView(generics.CreateAPIView):
    serializer_class = EarlyAccessRequestSerializer
    permission_classes = [permissions.AllowAny]


class ContactMessageCreateView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [permissions.AllowAny]



class GoogleLoginView(APIView):
    permission_classes = []

    @transaction.atomic
    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                {"error": "Google token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify Google token
        google_data = verify_google_token(token)
        if not google_data:
            return Response(
                {"error": "Invalid or expired Google token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        email = google_data["email"]
        first_name = google_data["first_name"]
        last_name = google_data["last_name"]

        # Get or create user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email.split("@")[0],
                "first_name": first_name,
                "last_name": last_name,
                "role": User.Roles.JOBSEEKER,
                "is_active": True,
            },
        )

        if created:
            user.set_password(get_random_string(32))
            user.save()

        if not user.is_active:
            return Response(
                {"error": "Account is disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = generate_tokens(user)

        return Response(
            {
                "message": "Login successful",
                "is_new_user": created,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )

