
from django.db import models
from hyresensemain.models import User



# class JobSeekerProfile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE, limit_choices_to={'role': 'jobseeker'})
#     full_name = models.CharField(max_length=100)
#     resume = models.FileField(upload_to="resumes/", blank=True, null=True)

#     def __str__(self):
#         return self.full_name
