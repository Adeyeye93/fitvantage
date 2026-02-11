"""
Providers App Services
======================
Business logic for provider management, onboarding, and coverage.

Services:
- ProviderService: Provider CRUD and status management
- ProviderVerificationService: Phone and email verification
- ProviderAnalyticsService: Performance tracking
- CoverageService: Service-city coverage management
"""

from django.utils import timezone
from django.db.models import Count, Q, Avg
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class ProviderService:
    """
    Provider management service.

    Handles:
    - Creating providers
    - Managing provider status
    - Provider information updates
    - Provider listing and filtering
    """

    @staticmethod
    def create_provider(name, email, phone, services=None, cities=None, **kwargs):
        """
        Create a new provider.

        Args:
            name: Provider name
            email: Provider email
            phone: Provider phone
            services: List of services offered (e.g., ["Fitness Training"])
            cities: List of cities served (e.g., ["London", "Manchester"])
            **kwargs: Additional fields (company_name, bio, qualifications, etc.)

        Returns:
            dict with provider and status
        """
        from apps.providers.models import Provider

        try:
            # Create provider
            provider = Provider.objects.create(
                name=name,
                email=email,
                phone=phone,
                services=services or [],
                cities=cities or [],
                status="PENDING_VERIFICATION",  # Always start as pending
                **kwargs,
            )

            logger.info(f"Created provider: {provider.id} - {name}")

            return {
                "success": True,
                "provider": provider,
                "message": "Provider created. Awaiting verification.",
            }

        except Exception as e:
            logger.error(f"Error creating provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def update_provider(provider_id, **kwargs):
        """
        Update provider information.

        Args:
            provider_id: Provider ID
            **kwargs: Fields to update

        Returns:
            dict with updated provider
        """
        from apps.providers.models import Provider

        try:
            provider = Provider.objects.get(id=provider_id)

            # Update fields
            for field, value in kwargs.items():
                if hasattr(provider, field):
                    setattr(provider, field, value)

            provider.updated_at = timezone.now()
            provider.save()

            logger.info(f"Updated provider: {provider_id}")

            return {"success": True, "provider": provider}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Error updating provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def activate_provider(provider_id):
        """
        Activate a provider (after verification).

        Args:
            provider_id: Provider ID

        Returns:
            dict with result
        """
        from apps.providers.models import Provider

        try:
            provider = Provider.objects.get(id=provider_id)

            provider.status = "ACTIVE"
            provider.verified_at = timezone.now()
            provider.save()

            logger.info(f"Activated provider: {provider_id}")

            return {"success": True, "provider": provider}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Error activating provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def pause_provider(provider_id, reason=None):
        """
        Pause a provider (temporarily stop receiving leads).

        Args:
            provider_id: Provider ID
            reason: Reason for pause

        Returns:
            dict with result
        """
        from apps.providers.models import Provider

        try:
            provider = Provider.objects.get(id=provider_id)

            provider.status = "PAUSED"
            provider.save()

            logger.info(f"Paused provider: {provider_id} - {reason}")

            return {"success": True, "provider": provider}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Error pausing provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def deactivate_provider(provider_id, reason=None):
        """
        Deactivate a provider (stop all operations).

        Args:
            provider_id: Provider ID
            reason: Reason for deactivation

        Returns:
            dict with result
        """
        from apps.providers.models import Provider

        try:
            provider = Provider.objects.get(id=provider_id)

            provider.status = "INACTIVE"
            provider.save()

            logger.info(f"Deactivated provider: {provider_id} - {reason}")

            return {"success": True, "provider": provider}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Error deactivating provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_providers(status="ACTIVE", service=None, city=None):
        """
        Get providers with optional filtering.

        Args:
            status: Filter by status
            service: Filter by service offered
            city: Filter by city covered

        Returns:
            QuerySet of providers
        """
        from apps.providers.models import Provider

        providers = Provider.objects.all()

        if status:
            providers = providers.filter(status=status)

        # Filter by service and city if provided
        if service or city:
            filtered = []
            for provider in providers:
                if service and service not in provider.services:
                    continue
                if city and city not in provider.cities:
                    continue
                filtered.append(provider)
            return filtered

        return providers

    @staticmethod
    def get_provider_details(provider_id):
        """
        Get detailed provider information.

        Args:
            provider_id: Provider ID

        Returns:
            dict with provider data and stats
        """
        from apps.providers.models import Provider

        try:
            provider = Provider.objects.get(id=provider_id)

            return {
                "provider": provider,
                "services": provider.services,
                "cities": provider.cities,
                "total_leads": provider.total_leads_received,
                "total_paid": provider.total_paid,
                "rating": provider.rating,
                "status": provider.status,
                "coverage_count": provider.coverage.count(),
            }

        except Provider.DoesNotExist:
            return None


class ProviderVerificationService:
    """
    Verify provider details during onboarding.

    Handles:
    - Phone verification
    - Email verification
    - Document verification (future)
    """

    @staticmethod
    def send_phone_verification(provider_id):
        """
        Send verification code via SMS to provider's phone.

        Args:
            provider_id: Provider ID

        Returns:
            dict with verification result
        """
        from apps.providers.models import Provider
        from apps.core.utils import CacheHelper
        import random

        try:
            provider = Provider.objects.get(id=provider_id)

            # Generate verification code
            code = str(random.randint(100000, 999999))

            # Store in cache (valid for 10 minutes)
            cache_key = f"provider_verify:{provider_id}"
            CacheHelper.set_cache(cache_key, code, timeout=600)

            # In production, send via Twilio
            # from apps.core.utils import TwilioService
            # TwilioService.send_message(
            #     to_number=provider.phone,
            #     message=f"Your verification code is: {code}"
            # )

            logger.info(f"Phone verification sent to provider {provider_id}")

            return {
                "success": True,
                "message": f"Verification code sent to {provider.phone}",
            }

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_phone_code(provider_id, code):
        """
        Verify phone verification code.

        Args:
            provider_id: Provider ID
            code: Verification code entered by user

        Returns:
            dict with verification result
        """
        from apps.providers.models import Provider
        from apps.core.utils import CacheHelper

        try:
            provider = Provider.objects.get(id=provider_id)

            # Get stored code from cache
            cache_key = f"provider_verify:{provider_id}"
            stored_code = CacheHelper.get_or_none(cache_key)

            if not stored_code:
                return {"success": False, "error": "Verification code expired"}

            if str(code) != str(stored_code):
                return {"success": False, "error": "Invalid verification code"}

            # Mark as verified
            provider.phone_verified = True
            provider.save()

            # Clear cache
            from django.core.cache import cache

            cache.delete(cache_key)

            logger.info(f"Phone verified for provider {provider_id}")

            return {"success": True, "message": "Phone verified successfully"}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def send_email_verification(provider_id):
        """
        Send email verification link to provider.

        Args:
            provider_id: Provider ID

        Returns:
            dict with result
        """
        from apps.providers.models import Provider
        from apps.core.utils import CacheHelper
        import uuid

        try:
            provider = Provider.objects.get(id=provider_id)

            # Generate verification token
            token = str(uuid.uuid4())

            # Store in cache (valid for 24 hours)
            cache_key = f"provider_email_verify:{provider_id}"
            CacheHelper.set_cache(cache_key, token, timeout=86400)

            # In production, send email with verification link
            # from django.core.mail import send_mail
            # verification_url = f"https://fitvantage.com/verify-email/{token}"
            # send_mail(
            #     subject='Verify your email',
            #     message=f'Click here to verify: {verification_url}',
            #     from_email='noreply@fitvantage.com',
            #     recipient_list=[provider.email]
            # )

            logger.info(f"Email verification sent to {provider.email}")

            return {
                "success": True,
                "message": f"Verification email sent to {provider.email}",
            }

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return {"success": False, "error": str(e)}


class CoverageService:
    """
    Manage provider service-city coverage.

    Allows providers to specify:
    - Which services they offer
    - Which cities they serve
    - Location-specific pricing
    """

    @staticmethod
    def add_coverage(provider_id, service, city, price=None):
        """
        Add service-city coverage for a provider.

        Args:
            provider_id: Provider ID
            service: Service name
            city: City name
            price: Optional price override for this location

        Returns:
            dict with coverage object
        """
        from apps.providers.models import Provider, ProviderCoverage

        try:
            provider = Provider.objects.get(id=provider_id)

            # Create or update coverage
            coverage, created = ProviderCoverage.objects.update_or_create(
                provider=provider,
                service=service,
                city=city,
                defaults={"price_for_this_location": price, "is_available": True},
            )

            # Update provider's services/cities lists
            if service not in provider.services:
                provider.services.append(service)
            if city not in provider.cities:
                provider.cities.append(city)
            provider.save()

            logger.info(f"Added coverage: {provider_id} - {service} in {city}")

            return {"success": True, "coverage": coverage, "created": created}

        except Provider.DoesNotExist:
            return {"success": False, "error": "Provider not found"}
        except Exception as e:
            logger.error(f"Coverage error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def remove_coverage(provider_id, service, city):
        """
        Remove service-city coverage from provider.

        Args:
            provider_id: Provider ID
            service: Service name
            city: City name

        Returns:
            dict with result
        """
        from apps.providers.models import Provider, ProviderCoverage

        try:
            coverage = ProviderCoverage.objects.get(
                provider_id=provider_id, service=service, city=city
            )

            coverage.delete()

            logger.info(f"Removed coverage: {provider_id} - {service} in {city}")

            return {"success": True}

        except ProviderCoverage.DoesNotExist:
            return {"success": False, "error": "Coverage not found"}
        except Exception as e:
            logger.error(f"Error removing coverage: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_coverage(provider_id):
        """
        Get all coverage for a provider.

        Args:
            provider_id: Provider ID

        Returns:
            QuerySet of ProviderCoverage
        """
        from apps.providers.models import ProviderCoverage

        return ProviderCoverage.objects.filter(provider_id=provider_id).order_by(
            "service", "city"
        )

    @staticmethod
    def toggle_availability(coverage_id):
        """
        Toggle whether provider is accepting leads for this coverage.

        Args:
            coverage_id: ProviderCoverage ID

        Returns:
            dict with result
        """
        from apps.providers.models import ProviderCoverage

        try:
            coverage = ProviderCoverage.objects.get(id=coverage_id)

            coverage.is_available = not coverage.is_available
            coverage.save()

            logger.info(
                f"Toggled availability: {coverage_id} - {coverage.is_available}"
            )

            return {"success": True, "is_available": coverage.is_available}

        except ProviderCoverage.DoesNotExist:
            return {"success": False, "error": "Coverage not found"}
        except Exception as e:
            logger.error(f"Error toggling availability: {e}")
            return {"success": False, "error": str(e)}


class ProviderAnalyticsService:
    """
    Track provider performance and analytics.

    Metrics:
    - Total leads received
    - Lead qualification rate
    - Total revenue
    - Average rating
    """

    @staticmethod
    def get_provider_stats(provider_id):
        """
        Get comprehensive statistics for a provider.

        Args:
            provider_id: Provider ID

        Returns:
            dict with provider statistics
        """
        from apps.providers.models import Provider
        from apps.leads.models import Lead
        from datetime import timedelta

        try:
            provider = Provider.objects.get(id=provider_id)

            # Get leads for this provider
            all_leads = Lead.objects.filter(provider_id=provider_id)
            leads_this_month = all_leads.filter(
                created_at__gte=timezone.now() - timedelta(days=30)
            )

            # Calculate stats
            total_leads = all_leads.count()
            qualified_leads = all_leads.filter(status="QUALIFIED").count()
            converted_leads = all_leads.filter(status="CONVERTED").count()

            qualification_rate = (
                (qualified_leads / total_leads * 100) if total_leads > 0 else 0
            )
            conversion_rate = (
                (converted_leads / total_leads * 100) if total_leads > 0 else 0
            )

            stats = {
                "provider_id": provider_id,
                "name": provider.name,
                "status": provider.status,
                "total_leads": total_leads,
                "leads_this_month": leads_this_month.count(),
                "qualified_leads": qualified_leads,
                "converted_leads": converted_leads,
                "qualification_rate": round(qualification_rate, 2),
                "conversion_rate": round(conversion_rate, 2),
                "total_revenue": provider.total_paid,
                "average_lead_value": (
                    float(provider.total_paid / total_leads) if total_leads > 0 else 0
                ),
                "rating": provider.rating or 0,
                "coverage_count": provider.coverage.count(),
            }

            return stats

        except Provider.DoesNotExist:
            return None

    @staticmethod
    def get_top_providers(limit=10):
        """
        Get top providers by rating and leads.

        Args:
            limit: Number of providers to return

        Returns:
            List of top providers with stats
        """
        from apps.providers.models import Provider
        from apps.leads.models import Lead

        providers = (
            Provider.objects.filter(status="ACTIVE")
            .annotate(lead_count=Count("leads"), avg_rating=Avg("rating"))
            .order_by("-avg_rating", "-lead_count")[:limit]
        )

        top_providers = []
        for provider in providers:
            stats = ProviderAnalyticsService.get_provider_stats(provider.id)
            if stats:
                top_providers.append(stats)

        return top_providers


__all__ = [
    "ProviderService",
    "ProviderVerificationService",
    "CoverageService",
    "ProviderAnalyticsService",
]
