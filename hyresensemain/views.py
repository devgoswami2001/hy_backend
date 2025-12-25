# hyresensemain/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from .serializers import *
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests
from django.contrib.auth.models import User
from rest_framework.views import APIView



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
    


@api_view(['POST'])
def google_login(request):
    token = request.data.get('token')
    try:
        # ✅ Verify token with Google
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(),
            "678219388222-er6kua6quleaj7slhp515qil27inh2f2.apps.googleusercontent.com"
        )

        email = idinfo['email']
        name = idinfo.get('name', '')
        username = email.split('@')[0]

        # ✅ Create or get user
        user, created = User.objects.get_or_create(email=email, defaults={
            'username': username
        })

        # ✅ Issue JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'email': user.email,
                'username': user.username,
            }
        })

    except Exception as e:
        return Response({'error': str(e)}, status=400)



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