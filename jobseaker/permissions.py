from rest_framework.permissions import BasePermission

class IsJobseekerPermission(BasePermission):
    """
    Custom permission to only allow jobseekers to apply to jobs.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            getattr(request.user, 'role', None) == 'jobseeker'
        )
