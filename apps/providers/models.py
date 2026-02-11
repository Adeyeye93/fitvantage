"""
Provider App Models
====================
Service provider management (Phase 2 scaffolding).
Models for handling provider onboarding, verification, and coverage.

Key Models:
- Provider: Service provider details
- ProviderCoverage: Which services/cities each provider covers
"""

from django.db import models
from django.core.validators import URLValidator, MinValueValidator
from django.utils import timezone
from decimal import Decimal


class Provider(models.Model):
    """
    Service provider (e.g., fitness trainer, nutrition coach, etc.).

    Phase 1: Scaffolded (empty)
    Phase 2: Fully implemented with:
        - Onboarding forms
        - Admin dashboard
        - Payment integration
        - Status management
    """

    # Basic info
    name = models.CharField(max_length=200, help_text="Provider/business name")
    email = models.EmailField(help_text="Contact email")
    phone = models.CharField(max_length=20, help_text="Contact phone number")
    phone_verified = models.BooleanField(
        default=False, help_text="Whether phone has been verified"
    )

    # Company details
    company_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Official company name (if different from provider name)",
    )
    company_website = models.URLField(blank=True, help_text="Provider's website")

    # Credentials & Bio
    bio = models.TextField(blank=True, help_text="Professional biography")
    qualifications = models.TextField(
        blank=True, help_text="Certifications, degrees, experience"
    )

    # Services & Coverage (stored as JSON for flexibility)
    # Example: {"services": ["Fitness Training", "Nutrition"], "cities": ["London", "Manchester"]}
    services = models.JSONField(
        default=list, help_text="List of services provided (e.g., ['Fitness Training'])"
    )
    cities = models.JSONField(
        default=list, help_text="List of cities served (e.g., ['London', 'Manchester'])"
    )

    # Contact preference
    CONTACT_METHOD_CHOICES = [
        ("PHONE", "Phone Call"),
        ("EMAIL", "Email"),
        ("WHATSAPP", "WhatsApp"),
        ("SMS", "SMS"),
        ("FORM", "Contact Form"),
    ]
    contact_method = models.CharField(
        max_length=20,
        choices=CONTACT_METHOD_CHOICES,
        default="PHONE",
        help_text="Preferred contact method",
    )

    # Pricing model
    PRICING_MODEL_CHOICES = [
        ("PAY_PER_LEAD", "Pay per qualified lead"),
        ("PAY_PER_BOOKING", "Pay per booking"),
        ("SUBSCRIPTION", "Monthly subscription"),
    ]
    pricing_model = models.CharField(
        max_length=30,
        choices=PRICING_MODEL_CHOICES,
        default="PAY_PER_LEAD",
        help_text="How provider is charged",
    )
    price_per_lead = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cost per qualified lead (GBP)",
    )

    # Status
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("PAUSED", "Paused"),
        ("INACTIVE", "Inactive"),
        ("PENDING_VERIFICATION", "Pending Verification"),
    ]
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="PENDING_VERIFICATION",
        help_text="Onboarding/activation status",
    )

    # Rating & Reviews (for Phase 2)
    rating = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MinValueValidator(5)],
        help_text="Average rating from consumer feedback (0-5)",
    )
    total_leads_received = models.IntegerField(
        default=0, help_text="Total qualified leads sent to this provider"
    )
    total_paid = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Total amount paid by provider (GBP)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(
        null=True, blank=True, help_text="When provider was verified"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Provider"
        verbose_name_plural = "Providers"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def is_active(self):
        """Check if provider is currently receiving leads"""
        return self.status == "ACTIVE"


class ProviderCoverage(models.Model):
    """
    Detailed service × city coverage for each provider.

    Allows providers to specify which services they offer in which cities,
    with optional pricing variations per location.

    Example:
        - Provider: "John's Fitness Training"
        - Service: "Fitness Training"
        - City: "London"
        - Price: £20 per lead (could differ from their base price)
    """

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="coverage",
        help_text="Which provider this coverage applies to",
    )

    # Service & City
    service = models.CharField(
        max_length=200, help_text="Service name (e.g., 'Fitness Training')"
    )
    city = models.CharField(max_length=100, help_text="City name (e.g., 'London')")

    # Optional: Local variation in pricing
    price_for_this_location = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price override for this service-city combo (if different)",
    )

    # Availability
    is_available = models.BooleanField(
        default=True, help_text="Currently accepting leads for this service-city"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["provider", "service", "city"]
        verbose_name = "Provider Coverage"
        verbose_name_plural = "Provider Coverages"
        indexes = [
            models.Index(fields=["provider", "service"]),
            models.Index(fields=["service", "city"]),
        ]

    def __str__(self):
        return f"{self.provider.name} - {self.service} in {self.city}"


__all__ = [
    "Provider",
    "ProviderCoverage",
]
