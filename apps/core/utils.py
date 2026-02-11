"""
Core Utilities
==============
Amazon API client, helpers, and utility functions.

Key:
- AmazonAPIClient: Interface to Amazon Product Advertising API
- Product filtering and ranking
- Caching utilities
"""

import requests
import os
from decimal import Decimal
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AmazonAPIClient:
    """
    Client for Amazon Product Advertising API.

    IMPORTANT: This is scaffolded. In production, use:
    - Official AWS SDK for Python (boto3)
    - Proper authentication with API keys
    - Rate limiting

    For now, this demonstrates the interface.
    """

    def __init__(self, region="co.uk"):
        """
        Initialize Amazon API client.

        Args:
            region: Amazon region (e.g., 'co.uk', 'com')
        """
        self.region = region
        self.api_key = os.getenv("AMAZON_API_KEY", "")
        self.secret_key = os.getenv("AMAZON_SECRET_KEY", "")
        self.partner_tag = os.getenv("AMAZON_PARTNER_TAG", "")
        self.base_url = f"https://api.amazon.{region}"

    def search_products(
        self, keywords: str, category_id: Optional[str] = None, max_results: int = 10
    ) -> List[Dict]:
        """
        Search for products by keywords.

        Args:
            keywords: Search terms (e.g., "fitness equipment")
            category_id: Optional Amazon category ID
            max_results: Max results to return

        Returns:
            List of product data dicts

        Note:
            In production, this would call Amazon's API.
            For Phase 1, this is a placeholder.
        """
        try:
            # In real implementation:
            # 1. Sign request with AWS credentials
            # 2. Call Amazon PA API
            # 3. Parse response
            # 4. Return product data

            logger.info(f"Amazon API: Searching for '{keywords}'")

            # Placeholder: return empty for now
            return []

        except Exception as e:
            logger.error(f"Amazon API error: {e}")
            return []

    def get_product_details(self, asin: str) -> Optional[Dict]:
        """
        Get details for a specific product.

        Args:
            asin: Amazon ASIN (product ID)

        Returns:
            Product data dict or None
        """
        try:
            logger.info(f"Amazon API: Getting details for ASIN {asin}")

            # In real implementation:
            # 1. Call Amazon API for single product
            # 2. Parse response
            # 3. Return data

            return None

        except Exception as e:
            logger.error(f"Amazon API error: {e}")
            return None

    def get_category_products(self, category_node: str, filters: Dict) -> List[Dict]:
        """
        Get products for a category with filters.

        Args:
            category_node: Amazon browse node ID
            filters: Filter rules (min_rating, min_reviews, etc.)

        Returns:
            List of filtered products
        """
        try:
            logger.info(f"Amazon API: Getting category {category_node} products")

            # In real implementation:
            # 1. Query Amazon API for category
            # 2. Filter results by rules
            # 3. Rank by BSR/rating
            # 4. Return top results

            return []

        except Exception as e:
            logger.error(f"Amazon API error: {e}")
            return []

    @staticmethod
    def parse_product_data(raw_data: Dict) -> Optional[Dict]:
        """
        Parse raw Amazon API response.

        Args:
            raw_data: Raw response from Amazon API

        Returns:
            Cleaned product data
        """
        try:
            if not raw_data:
                return None

            product = {
                "asin": raw_data.get("ASIN"),
                "title": raw_data.get("ItemInfo", {})
                .get("Title", {})
                .get("DisplayValue"),
                "url": f"https://amazon.{os.getenv('AMAZON_REGION', 'co.uk')}/dp/{raw_data.get('ASIN')}",
                "price": Decimal(
                    str(
                        raw_data.get("Offers", {})
                        .get("Listings", [{}])[0]
                        .get("Price", {})
                        .get("Amount", 0)
                    )
                ),
                "rating": float(
                    raw_data.get("CustomerReviews", {}).get("StarRating", 0)
                ),
                "review_count": int(
                    raw_data.get("CustomerReviews", {}).get("Count", 0)
                ),
                "image_url": raw_data.get("Images", {})
                .get("Primary", {})
                .get("Large", {})
                .get("URL"),
            }

            return product

        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None


class ProductRanker:
    """
    Rank products by relevance.

    Uses:
    - Best Seller Rank (BSR)
    - Rating
    - Review count
    """

    @staticmethod
    def rank_products(products: List, weights: Optional[Dict] = None) -> List:
        """
        Rank products by multiple factors.

        Args:
            products: List of product dicts
            weights: Weighting for factors (optional)

        Returns:
            Ranked list of products
        """
        if not weights:
            weights = {
                "rating": 0.4,
                "reviews": 0.3,
                "bsr": 0.3,
            }

        # Sort by rating first, then reviews, then BSR
        return sorted(
            products,
            key=lambda p: (
                -(p.get("rating", 0) * weights["rating"]),
                -(p.get("review_count", 0) * weights["reviews"]),
                (p.get("bsr_rank", float("inf")) * weights["bsr"]),
            ),
        )


class CacheHelper:
    """
    Cache-related helpers.
    """

    CACHE_TIMEOUT = 86400  # 24 hours
    CACHE_TIMEOUT_SHORT = 3600  # 1 hour

    @staticmethod
    def cache_key(prefix: str, identifier: str) -> str:
        """
        Generate cache key.

        Args:
            prefix: Cache prefix (e.g., 'affiliate_products')
            identifier: Unique identifier (e.g., category_slug)

        Returns:
            Cache key string
        """
        return f"{prefix}:{identifier}"

    @staticmethod
    def get_or_none(cache_obj, key: str, default=None):
        """
        Get from cache, return None if not found.
        """
        try:
            from django.core.cache import cache

            return cache.get(key, default)
        except:
            return default

    @staticmethod
    def set_cache(key: str, value, timeout: int = CACHE_TIMEOUT):
        """
        Set cache value.
        """
        try:
            from django.core.cache import cache

            cache.set(key, value, timeout)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False


class URLHelper:
    """
    URL generation helpers.
    """

    @staticmethod
    def amazon_affiliate_link(asin: str, partner_tag: Optional[str] = None) -> str:
        """
        Generate Amazon affiliate link.

        Args:
            asin: Amazon product ID
            partner_tag: Partner/tag (from settings)

        Returns:
            Affiliate URL
        """
        if not partner_tag:
            partner_tag = os.getenv("AMAZON_PARTNER_TAG", "")

        region = os.getenv("AMAZON_REGION", "co.uk")

        url = f"https://amazon.{region}/dp/{asin}"

        if partner_tag:
            url += f"?tag={partner_tag}"

        return url

    @staticmethod
    def add_utm_params(
        url: str,
        source: str = "fitvantage",
        medium: str = "affiliate",
        campaign: str = "products",
    ) -> str:
        """
        Add UTM parameters to URL for tracking.

        Args:
            url: Base URL
            source: UTM source
            medium: UTM medium
            campaign: UTM campaign

        Returns:
            URL with UTM parameters
        """
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}utm_source={source}&utm_medium={medium}&utm_campaign={campaign}"


class TextHelper:
    """
    Text formatting helpers.
    """

    @staticmethod
    def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """
        Truncate text to max length.

        Args:
            text: Text to truncate
            max_length: Max characters
            suffix: Suffix to add

        Returns:
            Truncated text
        """
        if len(text) > max_length:
            return text[: max_length - len(suffix)] + suffix
        return text

    @staticmethod
    def slugify_custom(text: str) -> str:
        """
        Custom slug generation.
        """
        from django.utils.text import slugify

        return slugify(text)


__all__ = [
    "AmazonAPIClient",
    "ProductRanker",
    "CacheHelper",
    "URLHelper",
    "TextHelper",
]
