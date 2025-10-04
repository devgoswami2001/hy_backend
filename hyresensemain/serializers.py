from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import OTP
from .utils import send_otp_email
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'role', 'first_name', 'last_name']
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user
    

class EmployerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'first_name', 'last_name']
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data['role'] = User.Roles.EMPLOYER  # Force employer role
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user

class OTPGenerateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
    def save(self):
        email = self.validated_data['email']
        user = User.objects.get(email=email)
        
        # Invalidate any existing OTPs for this user
        OTP.objects.filter(user=user, is_verified=False).update(is_verified=True)
        
        # Generate new OTP
        otp_code = OTP.generate_otp()
        otp_instance = OTP.objects.create(
            user=user,
            otp_code=otp_code
        )
        
        # Send OTP via email
        email_sent = send_otp_email(user, otp_code)
        
        if not email_sent:
            raise serializers.ValidationError("Failed to send OTP email.")
        
        return {
            'message': 'OTP sent successfully to your email.',
            'email': email,
            'expires_in': '10 minutes'
        }

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)
    
    def validate_email(self, value):
        print(f"Validating email: {value}")  # Debug log
        try:
            user = User.objects.get(email=value)
            print(f"User found: {user.email}")  # Debug log
        except User.DoesNotExist:
            print(f"User not found for email: {value}")  # Debug log
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
    def validate_otp_code(self, value):
        print(f"Validating OTP code: {value}")  # Debug log
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value
    
    def validate(self, attrs):
        email = attrs.get('email')
        otp_code = attrs.get('otp_code')
        
        print(f"Full validation - Email: {email}, OTP: {otp_code}")  # Debug log
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        
        # Check all OTPs for this user
        all_otps = OTP.objects.filter(user=user).order_by('-created_at')
        print(f"All OTPs for user: {[(otp.otp_code, otp.is_verified, otp.is_expired()) for otp in all_otps[:5]]}")
        
        try:
            otp_instance = OTP.objects.get(
                user=user,
                otp_code=otp_code,
                is_verified=False
            )
            print(f"OTP instance found: {otp_instance.otp_code}, expired: {otp_instance.is_expired()}")
        except OTP.DoesNotExist:
            print(f"No matching OTP found for user {user.email} with code {otp_code}")
            raise serializers.ValidationError("Invalid OTP code.")
        
        if otp_instance.is_expired():
            print(f"OTP expired. Created: {otp_instance.created_at}, Expires: {otp_instance.expires_at}")
            raise serializers.ValidationError("OTP has expired.")
        
        attrs['user'] = user
        attrs['otp_instance'] = otp_instance
        return attrs
    
    def save(self):
        user = self.validated_data['user']
        otp_instance = self.validated_data['otp_instance']
        
        # Mark OTP as verified
        otp_instance.is_verified = True
        otp_instance.save()
        
        print(f"OTP verified successfully for user: {user.email}")  # Debug log
        
        return {
            'message': 'OTP verified successfully.',
            'user_id': user.id,
            'email': user.email
        }



class JobSeekerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.CharField(read_only=True)  # Include role field as read-only
    
    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'first_name', 'last_name','role']
    
    def validate_password(self, value):
        """Validate password using Django's built-in validators"""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value
    
    def validate_email(self, value):
        """Ensure email is unique"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def create(self, validated_data):
        """Create a new job seeker user"""
        try:
            user = User.objects.create_user(
                email=validated_data['email'],
                username=validated_data.get('username'),
                password=validated_data['password'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                role=User.Roles.JOBSEEKER  # Explicitly setting role
            )
            return user
        except Exception as e:
            raise serializers.ValidationError(f"Error creating user: {str(e)}")

