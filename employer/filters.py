import django_filters
from django.db.models import Q
from .models import JobPost


class JobPostFilter(django_filters.FilterSet):
    """
    Advanced filtering for job posts
    """
    location = django_filters.CharFilter(lookup_expr='icontains')
    title = django_filters.CharFilter(lookup_expr='icontains')
    company_name = django_filters.CharFilter(lookup_expr='icontains')
    
    employment_type = django_filters.MultipleChoiceFilter(
        choices=JobPost.EmploymentTypeChoices.choices
    )
    experience_level = django_filters.MultipleChoiceFilter(
        choices=JobPost.ExperienceLevelChoices.choices
    )
    working_mode = django_filters.MultipleChoiceFilter(
        choices=JobPost.WorkingModeChoices.choices
    )
    
    salary_min = django_filters.NumberFilter(field_name='salary_min', lookup_expr='gte')
    salary_max = django_filters.NumberFilter(field_name='salary_max', lookup_expr='lte')
    
    skills = django_filters.CharFilter(method='filter_by_skills')
    
    deadline_after = django_filters.DateFilter(field_name='deadline', lookup_expr='gte')
    deadline_before = django_filters.DateFilter(field_name='deadline', lookup_expr='lte')
    
    is_featured = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    
    class Meta:
        model = JobPost
        fields = [
            'location', 'title', 'company_name', 'employment_type', 
            'experience_level', 'working_mode', 'salary_min', 'salary_max',
            'skills', 'deadline_after', 'deadline_before', 'is_featured', 'is_active'
        ]
    
    def filter_by_skills(self, queryset, name, value):
        """Filter by required skills"""
        skills = [skill.strip() for skill in value.split(',')]
        q_objects = Q()
        for skill in skills:
            q_objects |= Q(required_skills__icontains=skill)
        return queryset.filter(q_objects)