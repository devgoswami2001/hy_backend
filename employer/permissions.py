from rest_framework import permissions
from django.core.exceptions import ObjectDoesNotExist
from jobseaker.models import JobApplication

class IsEmployer(permissions.BasePermission):
    """
    Allows access only to users who are employers with active profiles.
    """
    message = "You must be an employer to access this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        try:
            # Check if user has employer profile and it's not soft deleted
            employer_profile = getattr(request.user, 'employer_profile', None)
            return (employer_profile is not None and 
                   not employer_profile.is_deleted and
                   request.user.role == 'employer')
        except (AttributeError, ObjectDoesNotExist):
            return False



class IsHRUser(permissions.BasePermission):
    """Permission for HR role users"""
    message = "You must be an HR user to access this resource."
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.role == 'hr' and
            hasattr(request.user, 'hr_user')
        )


class IsEmployerOrHR(permissions.BasePermission):
    """
    Allows access to both employers and HR users.
    """
    message = "You must be an employer or HR user to access this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Check if user is either employer or HR user
        is_employer = IsEmployer().has_permission(request, view)
        is_hr = IsHRUser().has_permission(request, view)
        
        return is_employer or is_hr



class IsEmployerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow employers to create/edit job posts.
    """
    
    def has_permission(self, request, view):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for authenticated employers
        return (request.user.is_authenticated and 
                hasattr(request.user, 'employer_profile'))
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for the owner or company admin
        return (request.user == obj.created_by or 
                request.user.employer_profile == obj.company)
    

class IsEmployerOrJobseeker(permissions.BasePermission):
    """
    Allows access only to authenticated users with role 'employer' or 'jobseeker'.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Adjust this logic to match your User model's role attribute
        return getattr(user, 'role', None) in ('employer', 'jobseeker')
    
class IsEmployerOrHRTeam(permissions.BasePermission):
    """
    Permission to allow:
    - Employers to manage their HR users
    - HR Users to view (and possibly edit) their own or their team's data depending on your logic
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'employer' or hasattr(request.user, 'hr_user')
        )

    def has_object_permission(self, request, view, obj):
        # Allow if requesting user is employer and it's their company HRUser
        if request.user.role == 'employer':
            return obj.company == request.user.employer_profile
        # Allow HR users maybe to view themselves, optionally extend for team members here
        if hasattr(request.user, 'hr_user'):
            return obj.user == request.user or obj.company == request.user.hr_user.company
        return False
    

class IsEmployerUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "employer"
    
class CanViewApplicationProfile(permissions.BasePermission):
    """
    Applicant can view own application; HR/Employer/Interviewer can view for evaluation.
    Extend this to enforce organization/job ownership rules if available.
    """
    def has_object_permission(self, request, view, obj: JobApplication):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user == obj.applicant:
            return True
        role = getattr(user, "role", None)
        if role in ("hr", "employer", "interviewer"):
            return True
        return False