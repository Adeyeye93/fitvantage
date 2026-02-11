"""
Celery Tasks
============
Background jobs for product refresh, lead processing, billing, etc.

Key Tasks:
- refresh_affiliate_products: Refresh product cache from Amazon API
- process_leads: Check lead status and qualification
- cleanup_expired_leads: Mark old leads as expired
- bill_providers: Calculate and process provider billing
"""

from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# AFFILIATE TASKS
# ============================================================================


@shared_task(bind=True, max_retries=3)
def refresh_affiliate_products(self, category_id=None, tier="all"):
    """
    Refresh product cache for categories.

    This is the CORE OF PHASE 1.

    Runs on a schedule:
    - Top categories: Every 24 hours
    - Other categories: Every 7 days

    Args:
        category_id: Specific category to refresh (optional)
        tier: 'top' or 'other' (default: 'all')

    Returns:
        dict with refresh results
    """
    try:
        from apps.affiliate.models import AffiliateCategory
        from apps.core.utils import AmazonAPIClient
        from apps.core.models import TaskLog

        # Determine which categories to refresh
        if category_id:
            categories = AffiliateCategory.objects.filter(id=category_id)
        elif tier == "top":
            # Top 20 categories get refreshed more frequently
            categories = AffiliateCategory.objects.filter(
                status="ACTIVE", is_featured=True
            )[:20]
        else:
            categories = AffiliateCategory.objects.filter(status="ACTIVE")

        # Refresh each category
        refresh_count = 0
        error_count = 0

        for category in categories:
            try:
                _refresh_category_cache(category)
                refresh_count += 1
            except Exception as e:
                logger.error(f"Error refreshing {category.name}: {e}")
                error_count += 1

        # Log the task
        TaskLog.objects.create(
            task_name="refresh_affiliate_products",
            task_id=self.request.id,
            status="SUCCESS",
            result={
                "refreshed": refresh_count,
                "errors": error_count,
                "tier": tier,
            },
        )

        logger.info(f"Product refresh: {refresh_count} success, {error_count} errors")

        return {
            "refreshed": refresh_count,
            "errors": error_count,
        }

    except Exception as e:
        logger.error(f"Product refresh failed: {e}")

        # Retry up to 3 times
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


def _refresh_category_cache(category):
    """
    Helper to refresh a single category's product cache.

    Args:
        category: AffiliateCategory instance
    """
    from apps.affiliate.models import AffiliateProductCache, AffiliateProductFilter
    from apps.core.utils import AmazonAPIClient, ProductRanker

    try:
        # Get filter rules
        filter_rules = AffiliateProductFilter.objects.get(category=category)
    except:
        logger.warning(f"No filter rules for {category.name}")
        return

    # Query Amazon API (placeholder)
    api_client = AmazonAPIClient()
    products = api_client.get_category_products(
        category.amazon_category_id or category.id,
        {
            "min_rating": filter_rules.min_rating,
            "min_review_count": filter_rules.min_review_count,
        },
    )

    # Rank products
    ranked = ProductRanker.rank_products(products)

    # Extract ASINs
    asins = [p.get("asin") for p in ranked if p.get("asin")]

    # Update cache
    cache_obj, created = AffiliateProductCache.objects.update_or_create(
        category=category,
        defaults={
            "cached_asins": asins[:20],  # Top 20 products
            "product_count": len(asins),
            "is_fresh": True,
            "next_refresh": timezone.now() + timedelta(days=1),
        },
    )

    logger.info(f"Refreshed {category.name}: {len(asins)} products")


@shared_task
def cleanup_expired_categories():
    """
    Mark categories with no products as needing refresh.

    Runs daily.
    """
    from apps.affiliate.models import AffiliateProductCache

    try:
        empty_caches = AffiliateProductCache.objects.filter(product_count=0)

        for cache_obj in empty_caches:
            cache_obj.is_fresh = False
            cache_obj.save()

        logger.info(f"Marked {empty_caches.count()} caches as stale")

        return {"marked_stale": empty_caches.count()}

    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return {"error": str(e)}


# ============================================================================
# LEAD TASKS (Phase 2)
# ============================================================================


@shared_task(bind=True)
def process_new_leads(self):
    """
    Process new leads:
    1. Route to best provider
    2. Attempt contact via Twilio
    3. Mark qualified if contacted

    Runs every 5 minutes.
    """
    from apps.leads.models import Lead

    try:
        # Get new leads
        new_leads = Lead.objects.filter(status="NEW")[:10]  # Process 10 at a time

        processed = 0
        for lead in new_leads:
            try:
                _process_lead(lead)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing lead {lead.id}: {e}")

        logger.info(f"Processed {processed} leads")
        return {"processed": processed}

    except Exception as e:
        logger.error(f"Lead processing error: {e}")
        return {"error": str(e)}


def _process_lead(lead):
    """Helper to process a single lead."""
    from apps.leads.services import LeadService

    # Route to provider
    provider = LeadService.get_best_provider(lead.service, lead.city)

    if provider:
        lead.provider_id = provider.id
        lead.status = "CONTACTED"
        lead.save()

        # Attempt Twilio contact
        LeadService.contact_provider_via_twilio(lead, provider)


@shared_task
def cleanup_expired_leads():
    """
    Mark leads older than 30 days as expired.

    Runs daily.
    """
    from apps.leads.models import Lead

    try:
        cutoff = timezone.now() - timedelta(days=30)

        expired = Lead.objects.filter(
            status__in=["NEW", "CONTACTED"], created_at__lt=cutoff
        ).update(status="EXPIRED")

        logger.info(f"Marked {expired} leads as expired")
        return {"expired": expired}

    except Exception as e:
        logger.error(f"Expired cleanup error: {e}")
        return {"error": str(e)}


@shared_task
def bill_qualified_leads():
    """
    Bill providers for qualified leads.

    Runs daily.
    """
    from apps.leads.models import Lead

    try:
        qualified = Lead.objects.filter(status="QUALIFIED", is_billed=False)

        billed = 0
        for lead in qualified:
            try:
                _bill_lead(lead)
                billed += 1
            except Exception as e:
                logger.error(f"Billing error for lead {lead.id}: {e}")

        logger.info(f"Billed {billed} leads")
        return {"billed": billed}

    except Exception as e:
        logger.error(f"Billing error: {e}")
        return {"error": str(e)}


def _bill_lead(lead):
    """Helper to bill a single lead."""
    from apps.leads.models import Lead

    if not lead.provider:
        return

    # Calculate amount
    amount = lead.provider.price_per_lead or 0

    # Mark as billed
    lead.is_billed = True
    lead.billed_at = timezone.now()
    lead.amount_billed = amount
    lead.save()

    logger.info(f"Billed provider {lead.provider.name} £{amount} for lead {lead.id}")


# ============================================================================
# MAINTENANCE TASKS
# ============================================================================


@shared_task
def cleanup_old_api_logs():
    """
    Delete API logs older than 90 days.

    Runs weekly.
    """
    from apps.core.models import APILog

    try:
        cutoff = timezone.now() - timedelta(days=90)
        deleted, _ = APILog.objects.filter(created_at__lt=cutoff).delete()

        logger.info(f"Deleted {deleted} old API logs")
        return {"deleted": deleted}

    except Exception as e:
        logger.error(f"API log cleanup error: {e}")
        return {"error": str(e)}


@shared_task
def send_daily_report():
    """
    Send daily performance report.

    Runs every morning at 9 AM.
    """
    from apps.affiliate.models import AffiliatePost
    from apps.leads.models import Lead

    try:
        # Get today's stats
        today = timezone.now().date()

        stats = {
            "posts_published": AffiliatePost.objects.filter(
                status="PUBLISHED", published_at__date=today
            ).count(),
            "leads_created": Lead.objects.filter(created_at__date=today).count(),
            "leads_qualified": Lead.objects.filter(
                status="QUALIFIED", qualified_at__date=today
            ).count(),
        }

        # Send email or log
        logger.info(f"Daily report: {stats}")

        return stats

    except Exception as e:
        logger.error(f"Report error: {e}")
        return {"error": str(e)}


__all__ = [
    "refresh_affiliate_products",
    "cleanup_expired_categories",
    "process_new_leads",
    "cleanup_expired_leads",
    "bill_qualified_leads",
    "cleanup_old_api_logs",
    "send_daily_report",
]
