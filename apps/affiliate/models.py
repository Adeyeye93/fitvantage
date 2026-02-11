"""
Affiliate App Models
====================
Amazon affiliate categories, products, and product automation.
This is the CORE of Phase 1.

Key Models:
- AffiliateCategory: Category taxonomy (parent/child)
- AffiliateProduct: Amazon products with ratings and availability
- AffiliateProductFilter: Rule-based product eligibility
- AffiliateProductCache: Local cache of eligible products (CORE PILLAR)
- AffiliatePost: Blog posts and guide content
"""

from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator
from django.utils import timezone
from decimal import Decimal


class AffiliateCategory(models.Model):
    """
    Category taxonomy for affiliate products.
    Supports parent/child relationships for hierarchical browsing.

    Examples:
        - Fitness (parent)
            - Equipment (child)
            - Supplements (child)
            - Clothing (child)

    Important: Categories are NOT product pages.
    Products are dynamic blocks loaded via AffiliateProductCache.
    """

    # Hierarchy
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent category (for subcategories)",
    )

    # Naming & URLs
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Category name (e.g., 'Fitness Equipment')",
    )
    slug = models.SlugField(unique=True, help_text="URL-friendly name")

    # Description & SEO
    description = models.TextField(
        blank=True, help_text="Category description (appears on page)"
    )
    meta_title = models.CharField(max_length=200, blank=True, help_text="SEO title tag")
    meta_description = models.TextField(
        max_length=160, blank=True, help_text="SEO meta description (160 chars max)"
    )
    meta_keywords = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated keywords for SEO"
    )

    # Amazon API
    amazon_category_id = models.CharField(
        max_length=50, blank=True, help_text="Amazon browse node ID for API queries"
    )

    # Visuals
    featured_image = models.ImageField(
        upload_to="affiliate/categories/",
        null=True,
        blank=True,
        help_text="Featured image for category",
    )

    # Status & Publishing
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("DRAFT", "Draft"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )
    is_featured = models.BooleanField(
        default=False, help_text="Show in featured categories section"
    )

    # Sorting
    display_order = models.IntegerField(
        default=0, help_text="Order in category listings"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Affiliate Category"
        verbose_name_plural = "Affiliate Categories"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "display_order"]),
            models.Index(fields=["parent", "status"]),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the URL for this category"""
        return f"/affiliate/{self.slug}/"

    def get_children(self):
        """Get all subcategories"""
        return self.children.filter(status="ACTIVE")

    def get_product_count(self):
        """Get count of cached products for this category"""
        try:
            cache = self.affiliate_product_cache
            return len(cache.cached_asins) if cache.cached_asins else 0
        except:
            return 0


class AffiliateProduct(models.Model):
    """
    Amazon product details.

    Important: These are NOT permanent pages.
    Instead, they are stored in AffiliateProductCache based on filter rules.
    The cache is refreshed via Celery tasks, and products rotate based on:
    - Rating (≥ 4.0)
    - Review count (≥ threshold)
    - Best Seller Rank (top %)
    - Availability (in stock, UK marketplace)
    """

    # Amazon details
    asin = models.CharField(
        max_length=20, unique=True, help_text="Amazon Standard Identification Number"
    )
    title = models.CharField(max_length=500, help_text="Product title from Amazon")
    url = models.URLField(max_length=500, help_text="Direct Amazon product link")

    # Pricing
    price_gbp = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price in GBP"
    )
    price_original = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original/list price",
    )
    currency = models.CharField(max_length=3, default="GBP", help_text="Currency code")

    # Ratings & Reviews
    rating = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Average rating (0-5 stars)",
    )
    review_count = models.IntegerField(
        default=0, help_text="Number of customer reviews"
    )

    # Availability
    in_stock = models.BooleanField(default=True, help_text="Currently in stock")
    availability_text = models.CharField(
        max_length=100, blank=True, help_text="Availability description from Amazon"
    )

    # Search Ranking
    bsr_rank = models.IntegerField(
        null=True, blank=True, help_text="Best Seller Rank in category"
    )
    bsr_category = models.CharField(
        max_length=100, blank=True, help_text="Category for BSR"
    )

    # Images
    image_url = models.URLField(
        max_length=500, blank=True, help_text="Product image URL from Amazon"
    )

    # Category
    categories = models.ManyToManyField(
        AffiliateCategory,
        related_name="products",
        help_text="Which categories this product appears in",
    )

    # Data freshness
    last_verified = models.DateTimeField(
        auto_now=True, help_text="Last time this product data was verified"
    )
    added_date = models.DateTimeField(
        auto_now_add=True, help_text="When this product was first added"
    )

    # Status
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("DISCONTINUED", "Discontinued"),
        ("OUT_OF_STOCK", "Out of Stock"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    # Raw data from API (for reference)
    raw_data = models.JSONField(
        null=True, blank=True, help_text="Full API response from Amazon"
    )

    class Meta:
        ordering = ["-rating", "-review_count"]
        verbose_name = "Affiliate Product"
        verbose_name_plural = "Affiliate Products"
        indexes = [
            models.Index(fields=["asin"]),
            models.Index(fields=["status", "in_stock"]),
            models.Index(fields=["rating", "review_count"]),
            models.Index(fields=["-added_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.asin})"

    def meets_filter_criteria(self, filter_rules):
        """
        Check if this product meets filter criteria.
        Used in product cache refresh logic.

        Args:
            filter_rules (dict): Rules from settings.PRODUCT_FILTER_RULES

        Returns:
            bool: True if product meets all criteria
        """
        if self.rating is None or self.rating < filter_rules.get("min_rating", 4.0):
            return False

        if self.review_count < filter_rules.get("min_review_count", 200):
            return False

        if not self.in_stock and filter_rules.get("in_stock_only"):
            return False

        # Note: Marketplace check would require additional data from API

        return True


class AffiliateProductFilter(models.Model):
    """
    Rule-based product filtering configuration.

    Defines which products are eligible for a category based on:
    - Minimum rating
    - Minimum review count
    - Best Seller Rank threshold
    - Availability (in stock, UK marketplace)

    CORE PILLAR: This enables automated product rotation without manual updates.
    """

    category = models.OneToOneField(
        AffiliateCategory,
        on_delete=models.CASCADE,
        related_name="filter_rules",
        help_text="Category these filter rules apply to",
    )

    # Rating criteria
    min_rating = models.FloatField(
        default=4.0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Minimum average rating required",
    )

    # Review count criteria
    min_review_count = models.IntegerField(
        default=200,
        validators=[MinValueValidator(0)],
        help_text="Minimum number of reviews required",
    )

    # Best Seller Rank criteria
    max_bsr_percentile = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Top X% of category by BSR (lower = more exclusive)",
    )

    # Availability
    uk_marketplace_only = models.BooleanField(
        default=True, help_text="Only products available in UK marketplace"
    )
    in_stock_only = models.BooleanField(
        default=True, help_text="Only in-stock products"
    )

    # Price constraints
    min_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum acceptable price (GBP)",
    )
    max_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum acceptable price (GBP)",
    )

    # Active?
    is_active = models.BooleanField(
        default=True, help_text="Whether these filter rules are currently applied"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Affiliate Product Filter"
        verbose_name_plural = "Affiliate Product Filters"

    def __str__(self):
        return f"Filter Rules: {self.category.name}"


class AffiliateProductCache(models.Model):
    """
    LOCAL CACHE of eligible products per category.

    CORE PILLAR: This is how we avoid calling Amazon API on every page load.

    Strategy:
    1. Celery cron job runs periodically (daily for top categories, weekly for others)
    2. Job queries Amazon API once and gets eligible products
    3. Filters products based on AffiliateProductFilter rules
    4. Stores list of eligible ASINs in this cache
    5. When page loads, we query cached ASINs (fast!) instead of API
    6. If cache is stale, background job updates it async

    Benefits:
    - No API calls on page load (fast pages)
    - Respects API rate limits
    - Products automatically rotate as ratings/reviews change
    - Fallback to parent category if cache is empty
    """

    category = models.OneToOneField(
        AffiliateCategory,
        on_delete=models.CASCADE,
        related_name="affiliate_product_cache",
        help_text="Category this cache is for",
    )

    # Cached ASINs (list of product IDs)
    cached_asins = models.JSONField(
        default=list,
        help_text="List of ASIN codes for eligible products in this category",
    )

    # Cache metadata
    last_updated = models.DateTimeField(
        auto_now=True, help_text="When this cache was last refreshed"
    )
    next_refresh = models.DateTimeField(
        null=True, blank=True, help_text="When this cache should be refreshed next"
    )

    # Status
    is_fresh = models.BooleanField(
        default=False, help_text="Whether cache is fresh enough to use"
    )
    product_count = models.IntegerField(
        default=0, help_text="Number of products in cache"
    )

    # Fallback handling
    uses_parent_fallback = models.BooleanField(
        default=False,
        help_text="Whether this cache uses parent category products as fallback",
    )
    parent_fallback_asins = models.JSONField(
        default=list,
        blank=True,
        help_text="Parent category product ASINs (fallback only)",
    )

    # Error tracking
    last_error = models.TextField(
        blank=True, help_text="Last error encountered during refresh"
    )
    error_count = models.IntegerField(
        default=0, help_text="Number of consecutive refresh failures"
    )

    class Meta:
        verbose_name = "Affiliate Product Cache"
        verbose_name_plural = "Affiliate Product Caches"

    def __str__(self):
        return f"Cache: {self.category.name} ({self.product_count} products)"

    def get_products(self):
        """
        Get actual Product objects from cached ASINs.
        Returns products in order (for consistent display).
        """
        if not self.cached_asins:
            return AffiliateProduct.objects.none()

        # Preserve order of ASINs
        asins = self.cached_asins
        products = AffiliateProduct.objects.filter(asin__in=asins, status="ACTIVE")

        # Sort by original order
        preserved_order = {asin: i for i, asin in enumerate(asins)}
        return sorted(products, key=lambda x: preserved_order.get(x.asin, 999))

    def is_cache_stale(self):
        """Check if cache needs refreshing"""
        if not self.is_fresh:
            return True
        if self.next_refresh and timezone.now() > self.next_refresh:
            return True
        return False


class AffiliatePost(models.Model):
    """
    Blog posts and guide content for affiliate traffic.

    Each post can include:
    - Main content (rich text/HTML)
    - Embedded product blocks (from AffiliateProductCache)
    - CTA placeholders for future service pages
    - Internal links to categories and other posts

    Example:
        Title: "5 Best Home Fitness Equipment in 2024"
        Category: Fitness Equipment
        Content: Blog post about equipment...
        [Product Block: Top 4 products from cache]
        CTA: "Ready to start your fitness journey? Find a trainer near you."
    """

    # Basic info
    title = models.CharField(max_length=300, help_text="Blog post title")
    slug = models.SlugField(unique=True, help_text="URL slug")
    excerpt = models.TextField(
        max_length=500, help_text="Short preview text (appears in listings)"
    )

    # Content
    content = models.TextField(help_text="Main blog content (HTML allowed)")

    # Category
    category = models.ForeignKey(
        AffiliateCategory,
        on_delete=models.CASCADE,
        related_name="posts",
        help_text="Which category this post belongs to",
    )

    # Featured image
    featured_image = models.ImageField(
        upload_to="affiliate/blogs/",
        null=True,
        blank=True,
        help_text="Featured image for blog post",
    )

    # Author & Attribution
    author = models.CharField(max_length=200, blank=True, help_text="Post author name")
    author_bio = models.TextField(blank=True, help_text="Short author biography")

    # SEO
    meta_title = models.CharField(max_length=200, blank=True, help_text="SEO title tag")
    meta_description = models.TextField(
        max_length=160, blank=True, help_text="SEO meta description"
    )
    meta_keywords = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated keywords"
    )

    # CTA placeholder for Phase 2
    cta_text = models.CharField(
        max_length=200,
        default="Find a professional near you",
        help_text="CTA text placeholder (will link to service pages in Phase 2)",
    )
    cta_service = models.CharField(
        max_length=200,
        blank=True,
        help_text="Service name for CTA (e.g., 'Fitness Training')",
    )

    # Publishing
    status = models.CharField(
        max_length=20,
        choices=[
            ("DRAFT", "Draft"),
            ("PUBLISHED", "Published"),
            ("ARCHIVED", "Archived"),
        ],
        default="DRAFT",
    )
    published_at = models.DateTimeField(
        null=True, blank=True, help_text="When post was published"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # SEO Ranking tracking
    view_count = models.IntegerField(default=0, help_text="Number of page views")

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Affiliate Post"
        verbose_name_plural = "Affiliate Posts"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["-published_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)

        # Auto-publish if transitioning to PUBLISHED
        if self.status == "PUBLISHED" and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return URL for this blog post"""
        return f"/blog/{self.slug}/"

    def get_featured_products(self, limit=4):
        """Get featured products from this post's category"""
        try:
            cache = self.category.affiliate_product_cache
            products = cache.get_products()[:limit]
            return products
        except:
            return []


__all__ = [
    "AffiliateCategory",
    "AffiliateProduct",
    "AffiliateProductFilter",
    "AffiliateProductCache",
    "AffiliatePost",
]
