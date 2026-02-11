"""
Affiliate App Serializers & Forms
==================================
Data serialization for API and form handling.
"""

from rest_framework import serializers
from django import forms
from django.db.models import Count
from apps.affiliate.models import AffiliateCategory, AffiliateProduct, AffiliatePost


# ============================================================================
# SERIALIZERS (REST Framework)
# ============================================================================


class CategorySerializer(serializers.ModelSerializer):
    """
    Serialize AffiliateCategory to JSON.

    Includes:
    - Basic category info
    - Nested children
    - Product count
    """

    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    post_count = serializers.SerializerMethodField()
    absolute_url = serializers.SerializerMethodField()

    class Meta:
        model = AffiliateCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "featured_image",
            "meta_title",
            "meta_description",
            "children",
            "product_count",
            "post_count",
            "is_featured",
            "absolute_url",
        ]
        read_only_fields = fields

    def get_children(self, obj):
        """Get nested children"""
        children = obj.get_children()
        if children.exists():
            return CategorySerializer(children, many=True).data
        return []

    def get_product_count(self, obj):
        """Get number of products in cache"""
        try:
            return obj.affiliate_product_cache.product_count
        except:
            return 0

    def get_post_count(self, obj):
        """Get number of posts"""
        return obj.posts.filter(status="PUBLISHED").count()

    def get_absolute_url(self, obj):
        """Get absolute URL"""
        return obj.get_absolute_url()


class ProductSerializer(serializers.ModelSerializer):
    """
    Serialize AffiliateProduct to JSON.

    Includes:
    - Product details
    - Pricing and ratings
    - Availability
    - Amazon link
    """

    category_names = serializers.SerializerMethodField()

    class Meta:
        model = AffiliateProduct
        fields = [
            "id",
            "asin",
            "title",
            "url",
            "price_gbp",
            "price_original",
            "rating",
            "review_count",
            "in_stock",
            "image_url",
            "category_names",
            "status",
        ]
        read_only_fields = fields

    def get_category_names(self, obj):
        """Get category names"""
        return [cat.name for cat in obj.categories.all()]


class PostSerializer(serializers.ModelSerializer):
    """
    Serialize AffiliatePost to JSON.

    Includes:
    - Post content
    - Author info
    - Category
    - Publication date
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    absolute_url = serializers.SerializerMethodField()

    class Meta:
        model = AffiliatePost
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "featured_image",
            "author",
            "category_name",
            "category_slug",
            "published_at",
            "view_count",
            "absolute_url",
        ]
        read_only_fields = fields

    def get_absolute_url(self, obj):
        """Get absolute URL"""
        return obj.get_absolute_url()


# ============================================================================
# FORMS (User Input)
# ============================================================================


class CategoryFilterForm(forms.Form):
    """
    Form for filtering categories.
    """

    parent = forms.ModelChoiceField(
        queryset=AffiliateCategory.objects.filter(status="ACTIVE", parent__isnull=True),
        required=False,
        label="Main Category",
        empty_label="All Categories",
    )

    order_by = forms.ChoiceField(
        choices=[
            ("name", "Name (A-Z)"),
            ("-name", "Name (Z-A)"),
            ("display_order", "Featured First"),
        ],
        required=False,
        initial="display_order",
    )


class PostFilterForm(forms.Form):
    """
    Form for filtering blog posts.
    """

    category = forms.ModelChoiceField(
        queryset=AffiliateCategory.objects.filter(status="ACTIVE"),
        required=False,
        label="Category",
        empty_label="All Categories",
    )

    order_by = forms.ChoiceField(
        choices=[
            ("-published_at", "Newest First"),
            ("published_at", "Oldest First"),
            ("title", "Title (A-Z)"),
        ],
        required=False,
        initial="-published_at",
    )


class SearchForm(forms.Form):
    """
    Search form for categories and posts.
    """

    q = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search categories, products, or guides...",
                "autocomplete": "off",
            }
        ),
    )

    search_type = forms.ChoiceField(
        choices=[
            ("all", "Everything"),
            ("categories", "Categories Only"),
            ("posts", "Blog Posts Only"),
        ],
        required=False,
        initial="all",
        widget=forms.RadioSelect(),
    )


class ProductFilterForm(forms.Form):
    """
    Form for filtering products.
    """

    min_rating = forms.FloatField(
        required=False,
        min_value=0,
        max_value=5,
        label="Minimum Rating",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    max_price = forms.DecimalField(
        required=False,
        decimal_places=2,
        label="Max Price (£)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    in_stock_only = forms.BooleanField(
        required=False, initial=True, label="In Stock Only"
    )


__all__ = [
    # Serializers
    "CategorySerializer",
    "ProductSerializer",
    "PostSerializer",
    # Forms
    "CategoryFilterForm",
    "PostFilterForm",
    "SearchForm",
    "ProductFilterForm",
]
