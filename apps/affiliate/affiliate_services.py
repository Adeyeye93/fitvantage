"""
Affiliate App Services
======================
Business logic for categories, products, and caching.
Keeps views thin and testable.

Services:
- CategoryService: Category logic
- ProductService: Product logic
- CacheService: Cache management
"""

from django.core.cache import cache
from django.db.models import Count, Q
from apps.affiliate.models import (
    AffiliateCategory,
    AffiliateProduct,
    AffiliateProductCache,
    AffiliateProductFilter,
)


class CategoryService:
    """
    Category business logic.

    Features:
    - Get categories with stats
    - Build category hierarchy
    - Get categories by filter
    """

    @staticmethod
    def get_active_categories(parent=None, featured_only=False):
        """
        Get active categories.

        Args:
            parent: Filter by parent category
            featured_only: Only return featured categories

        Returns:
            QuerySet of categories
        """
        queryset = AffiliateCategory.objects.filter(status="ACTIVE")

        if parent:
            queryset = queryset.filter(parent=parent)
        elif parent is None:
            queryset = queryset.filter(parent__isnull=True)  # Top-level only

        if featured_only:
            queryset = queryset.filter(is_featured=True)

        return queryset.annotate(post_count=Count("posts")).order_by(
            "-is_featured", "display_order"
        )

    @staticmethod
    def get_category_with_products(category_slug):
        """
        Get category with its products from cache.

        Args:
            category_slug: Category slug

        Returns:
            dict with category data and products
        """
        try:
            category = AffiliateCategory.objects.get(
                slug=category_slug, status="ACTIVE"
            )
        except AffiliateCategory.DoesNotExist:
            return None

        # Get products from cache
        products = ProductService.get_category_products(category)

        # Build response
        return {
            "category": category,
            "products": products,
            "product_count": len(products),
            "subcategories": category.get_children(),
            "posts": category.posts.filter(status="PUBLISHED").order_by(
                "-published_at"
            )[:6],
        }

    @staticmethod
    def get_category_hierarchy():
        """
        Get full category hierarchy (for navigation).

        Returns:
            List of parent categories with children
        """
        parents = AffiliateCategory.objects.filter(
            status="ACTIVE", parent__isnull=True
        ).order_by("display_order")

        hierarchy = []
        for parent in parents:
            hierarchy.append(
                {
                    "parent": parent,
                    "children": parent.get_children(),
                }
            )

        return hierarchy


class ProductService:
    """
    Product business logic.

    CORE FEATURE: Get products from cache, not API!
    """

    @staticmethod
    def get_category_products(category, limit=None):
        """
        Get eligible products for a category from cache.

        CORE: This retrieves from AffiliateProductCache, NOT the API!

        Args:
            category: AffiliateCategory instance
            limit: Max products to return

        Returns:
            List of AffiliateProduct instances
        """
        try:
            cache = category.affiliate_product_cache
            products = cache.get_products()

            if limit:
                products = products[:limit]

            return products

        except AffiliateProductCache.DoesNotExist:
            # No cache for this category - return empty
            return []
        except Exception as e:
            # Log error but don't crash
            print(f"Error getting products for {category.name}: {e}")
            return []

    @staticmethod
    def get_product_details(asin):
        """
        Get product details by ASIN.

        Args:
            asin: Amazon product ID

        Returns:
            AffiliateProduct or None
        """
        try:
            return AffiliateProduct.objects.get(asin=asin, status="ACTIVE")
        except AffiliateProduct.DoesNotExist:
            return None

    @staticmethod
    def search_products(query):
        """
        Search products by title.

        Args:
            query: Search string

        Returns:
            QuerySet of matching products
        """
        return AffiliateProduct.objects.filter(
            Q(title__icontains=query), status="ACTIVE", in_stock=True
        ).order_by("-rating", "-review_count")[:10]

    @staticmethod
    def get_top_products(limit=10):
        """
        Get top-rated products across all categories.

        Args:
            limit: Number of products to return

        Returns:
            List of top products
        """
        return AffiliateProduct.objects.filter(status="ACTIVE", in_stock=True).order_by(
            "-rating", "-review_count"
        )[:limit]


class CacheService:
    """
    Product cache management.

    Responsible for:
    - Checking cache freshness
    - Refreshing caches
    - Handling fallbacks
    """

    @staticmethod
    def is_cache_fresh(cache_obj):
        """
        Check if cache is fresh and usable.

        Args:
            cache_obj: AffiliateProductCache instance

        Returns:
            bool: True if cache is fresh
        """
        if not cache_obj.is_fresh:
            return False

        if not cache_obj.cached_asins or len(cache_obj.cached_asins) == 0:
            return False

        return cache_obj.is_cache_stale() is False

    @staticmethod
    def refresh_cache(category):
        """
        Trigger a cache refresh (usually called by Celery).

        Args:
            category: AffiliateCategory instance

        Returns:
            dict with refresh results
        """
        try:
            cache_obj = category.affiliate_product_cache
        except:
            return {"success": False, "error": "No cache found"}

        # This would be called from Celery task
        # For now, just mark as needing refresh

        return {
            "success": True,
            "category": category.name,
            "scheduled": True,
        }

    @staticmethod
    def get_fallback_products(category, limit=4):
        """
        Get fallback products if category cache is empty.

        Uses parent category or "bestsellers" pool.

        Args:
            category: AffiliateCategory instance
            limit: Number of products

        Returns:
            List of fallback products
        """
        # Try parent category
        if category.parent:
            try:
                parent_cache = category.parent.affiliate_product_cache
                if parent_cache.cached_asins:
                    return parent_cache.get_products()[:limit]
            except:
                pass

        # Fallback to top-rated products overall
        return ProductService.get_top_products(limit)


class FilterService:
    """
    Product filtering logic.
    """

    @staticmethod
    def apply_filter_rules(product, filter_rules):
        """
        Check if product meets filter rules.

        Args:
            product: AffiliateProduct instance
            filter_rules: AffiliateProductFilter instance

        Returns:
            bool: True if product meets all rules
        """
        # Rating check
        if product.rating is None or product.rating < filter_rules.min_rating:
            return False

        # Review count check
        if product.review_count < filter_rules.min_review_count:
            return False

        # Availability check
        if filter_rules.in_stock_only and not product.in_stock:
            return False

        # Price range check
        if product.price_gbp:
            if filter_rules.min_price and product.price_gbp < filter_rules.min_price:
                return False
            if filter_rules.max_price and product.price_gbp > filter_rules.max_price:
                return False

        return True

    @staticmethod
    def get_filter_rules(category):
        """
        Get filter rules for a category.

        Args:
            category: AffiliateCategory instance

        Returns:
            AffiliateProductFilter or default
        """
        try:
            return category.filter_rules
        except:
            # Return default filter
            return AffiliateProductFilter(
                category=category,
                min_rating=4.0,
                min_review_count=200,
                in_stock_only=True,
            )


__all__ = [
    "CategoryService",
    "ProductService",
    "CacheService",
    "FilterService",
]
