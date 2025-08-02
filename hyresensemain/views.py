# hyresensemain/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from .serializers import *

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