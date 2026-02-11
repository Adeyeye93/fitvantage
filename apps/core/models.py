"""
Core App Models
===============
Shared models and utilities for all FitVantage apps.
Models here are used across all phases (1, 2, and 3).

Key Models:
- ServiceCity: Service × City relationships (for Phase 2 & 3)
- Base models for extensibility
"""

from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model that provides created_at and updated_at timestamps.
    All models should inherit from this for consistency.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ServiceCity(TimeStampedModel):
    """
    Service × City relationship model.

    Purpose: Link services to cities for Phase 2 & 3 service pages.
    Used in: Phase 2 (provider routing), Phase 3 (page generation)

    Example:
        - Fitness Training × London
        - Nutrition Coaching × Manchester
        - Mental Health Counseling × Bristol

    Why separate from Provider?
        - ServiceCity is about service availability in a location
        - Provider is about an individual provider
        - Multiple providers can service the same ServiceCity
    """

    # Service information
    service_name = models.CharField(
        max_length=200,
        help_text="Name of the service (e.g., 'Fitness Training', 'Nutrition Coaching')",
    )
    service_slug = models.SlugField(
        unique=True, help_text="URL-friendly version of service name"
    )
    service_description = models.TextField(
        blank=True, help_text="Description of what this service entails"
    )

    # City information
    city_name = models.CharField(
        max_length=100, help_text="City name (e.g., 'London', 'Manchester')"
    )
    city_slug = models.SlugField(help_text="URL-friendly version of city name")

    # Combined slug for unique URL identification (e.g., "fitness-training-london")
    page_slug = models.SlugField(
        unique=True, help_text="Combined slug for page URL: service-city"
    )

    # Local details (for Phase 3)
    local_areas = models.TextField(
        blank=True,
        help_text="JSON or comma-separated list of areas/postcodes in this city",
    )
    region = models.CharField(
        max_length=100,
        blank=True,
        help_text="Region/County (e.g., 'Greater London', 'Manchester Area')",
    )
    country = models.CharField(
        max_length=50, default="United Kingdom", help_text="Country name"
    )

    # Status tracking
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("PLANNED", "Planned"),
        ("ARCHIVED", "Archived"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PLANNED",
        help_text="Publication status",
    )

    # SEO fields (for Phase 3)
    meta_title = models.CharField(max_length=200, blank=True, help_text="SEO title tag")
    meta_description = models.TextField(
        max_length=160, blank=True, help_text="SEO meta description"
    )
    meta_keywords = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated SEO keywords"
    )

    # Content fields (for Phase 3)
    hero_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Page hero title (e.g., 'Best Fitness Training in London')",
    )
    hero_subtitle = models.CharField(
        max_length=300, blank=True, help_text="Page hero subtitle"
    )

    # Publishing info
    is_published = models.BooleanField(
        default=False, help_text="Whether this service-city page is published"
    )
    published_at = models.DateTimeField(
        null=True, blank=True, help_text="When this page was first published"
    )

    class Meta:
        ordering = ["service_name", "city_name"]
        unique_together = ["service_slug", "city_slug"]
        verbose_name = "Service × City"
        verbose_name_plural = "Services × Cities"
        indexes = [
            models.Index(fields=["service_slug", "status"]),
            models.Index(fields=["city_slug", "status"]),
            models.Index(fields=["page_slug"]),
            models.Index(fields=["status", "is_published"]),
        ]

    def __str__(self):
        return f"{self.service_name} in {self.city_name}"

    def save(self, *args, **kwargs):
        # Auto-generate slugs if not provided
        if not self.service_slug:
            self.service_slug = slugify(self.service_name)
        if not self.city_slug:
            self.city_slug = slugify(self.city_name)
        if not self.page_slug:
            self.page_slug = f"{self.service_slug}-{self.city_slug}"

        # Set published_at when status changes to ACTIVE
        if self.status == "ACTIVE" and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the URL for this service-city page"""
        return f"/{self.page_slug}/"


class APILog(TimeStampedModel):
    """
    Log API calls for monitoring and debugging.
    Useful for tracking Amazon API usage, error rates, etc.
    """

    API_CHOICES = [
        ("AMAZON", "Amazon Product Advertising API"),
        ("TWILIO", "Twilio API"),
        ("INTERNAL", "Internal API"),
    ]

    api_name = models.CharField(
        max_length=50, choices=API_CHOICES, help_text="Which API was called"
    )
    endpoint = models.CharField(max_length=300, help_text="API endpoint called")
    method = models.CharField(
        max_length=10, default="GET", help_text="HTTP method (GET, POST, etc.)"
    )
    status_code = models.IntegerField(
        null=True, blank=True, help_text="HTTP response status code"
    )
    response_time_ms = models.IntegerField(
        null=True, blank=True, help_text="Response time in milliseconds"
    )
    error_message = models.TextField(
        blank=True, help_text="Error message if request failed"
    )
    request_data = models.JSONField(
        null=True, blank=True, help_text="Request parameters (sanitized)"
    )
    response_data = models.JSONField(
        null=True, blank=True, help_text="Response data (first 1KB)"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API Log"
        verbose_name_plural = "API Logs"
        indexes = [
            models.Index(fields=["api_name", "-created_at"]),
            models.Index(fields=["status_code"]),
        ]

    def __str__(self):
        return f"{self.api_name} - {self.endpoint} ({self.status_code})"


class Setting(models.Model):
    """
    Global application settings.
    Store configuration that might change without code deployment.
    """

    key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Setting key (e.g., 'MIN_PRODUCT_RATING')",
    )
    value = models.TextField(help_text="Setting value (can be JSON)")
    description = models.TextField(
        blank=True, help_text="Description of what this setting does"
    )
    data_type = models.CharField(
        max_length=20,
        default="string",
        choices=[
            ("string", "String"),
            ("integer", "Integer"),
            ("float", "Float"),
            ("boolean", "Boolean"),
            ("json", "JSON"),
        ],
        help_text="Data type for validation",
    )

    class Meta:
        verbose_name = "Setting"
        verbose_name_plural = "Settings"

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key, default=None):
        """Get a setting value by key"""
        try:
            setting = cls.objects.get(key=key)
            return setting.value
        except cls.DoesNotExist:
            return default


class TaskLog(TimeStampedModel):
    """
    Log scheduled tasks (Celery jobs).
    Useful for monitoring background job execution.
    """

    task_name = models.CharField(
        max_length=200,
        help_text="Name of the task (e.g., 'refresh_affiliate_products')",
    )
    task_id = models.CharField(max_length=100, unique=True, help_text="Celery task ID")

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("STARTED", "Started"),
        ("SUCCESS", "Success"),
        ("FAILURE", "Failure"),
        ("RETRY", "Retry"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    duration_seconds = models.FloatField(
        null=True, blank=True, help_text="How long the task took to complete"
    )
    error_message = models.TextField(
        blank=True, help_text="Error message if task failed"
    )
    result = models.JSONField(null=True, blank=True, help_text="Task result data")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Task Log"
        verbose_name_plural = "Task Logs"
        indexes = [
            models.Index(fields=["task_name", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.task_name} - {self.status}"


__all__ = [
    "TimeStampedModel",
    "ServiceCity",
    "APILog",
    "Setting",
    "TaskLog",
]
