"""
Affiliate App Views
===================
Display categories, blog posts, and products.

Views:
- CategoryListView: Display all categories
- CategoryDetailView: Display category with products from cache
- BlogListView: Display all blog posts
- BlogDetailView: Display blog post with products
- SearchView: Search across categories and posts
"""

from django.views.generic import ListView, DetailView
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

from apps.affiliate.models import AffiliateCategory, AffiliatePost, AffiliateProduct


class CategoryListView(ListView):
    """
    Display all affiliate categories (parent categories only).

    Features:
    - Shows main categories (no children)
    - Features some categories first
    - Pagination (12 per page)
    - Shows featured image and product count
    """

    model = AffiliateCategory
    template_name = "affiliate/category_list.html"
    context_object_name = "categories"
    paginate_by = 12

    def get_queryset(self):
        """Get active parent categories only"""
        return (
            AffiliateCategory.objects.filter(
                status="ACTIVE", parent__isnull=True
            )  # Parent categories only
            .annotate(post_count=Count("posts"))
            .order_by("-is_featured", "display_order")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add featured categories at top
        context["featured_categories"] = AffiliateCategory.objects.filter(
            status="ACTIVE", is_featured=True, parent__isnull=True
        ).order_by("display_order")[:3]
        context["total_categories"] = self.get_queryset().count()
        return context


class CategoryDetailView(DetailView):
    """
    Display category detail page.

    Features:
    - Category description and image
    - **Products from AffiliateProductCache (NO API CALLS!)**
    - Subcategories
    - Related blog posts
    - SEO meta tags

    CORE: Products loaded from cache, not API!
    """

    model = AffiliateCategory
    template_name = "affiliate/category_detail.html"
    context_object_name = "category"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        """Only show active categories"""
        return AffiliateCategory.objects.filter(status="ACTIVE")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object

        # Get subcategories
        context["subcategories"] = (
            category.get_children()
            .annotate(post_count=Count("posts"))
            .order_by("display_order")
        )

        # Get products from cache (CORE FEATURE - no API calls!)
        try:
            cache = category.affiliate_product_cache
            context["products"] = cache.get_products()[:8]  # Top 8 products
            context["products_available"] = len(cache.cached_asins) > 0
            context["product_count"] = cache.product_count
        except:
            context["products"] = []
            context["products_available"] = False
            context["product_count"] = 0

        # Get related blog posts
        context["related_posts"] = AffiliatePost.objects.filter(
            category=category, status="PUBLISHED"
        ).order_by("-published_at")[:6]

        # Breadcrumb
        context["breadcrumbs"] = []
        if category.parent:
            context["breadcrumbs"] = [
                {
                    "name": category.parent.name,
                    "url": category.parent.get_absolute_url(),
                },
                {"name": category.name, "url": category.get_absolute_url()},
            ]

        return context


class BlogListView(ListView):
    """
    Display all published blog posts.

    Features:
    - Paginated list (12 per page)
    - Filter by category
    - Show featured post first
    - Show publication date and author
    """

    model = AffiliatePost
    template_name = "affiliate/blog_list.html"
    context_object_name = "posts"
    paginate_by = 12

    def get_queryset(self):
        """Get published posts"""
        queryset = (
            AffiliatePost.objects.filter(status="PUBLISHED")
            .select_related("category")
            .order_by("-published_at")
        )

        # Filter by category if provided
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Featured post (most recent)
        context["featured_post"] = (
            AffiliatePost.objects.filter(status="PUBLISHED")
            .order_by("-published_at")
            .first()
        )

        # Categories for filter sidebar
        context["categories"] = (
            AffiliateCategory.objects.filter(status="ACTIVE", parent__isnull=True)
            .annotate(post_count=Count("posts"))
            .filter(post_count__gt=0)
        )

        # Active category (if filtering)
        category_slug = self.request.GET.get("category")
        if category_slug:
            try:
                context["active_category"] = AffiliateCategory.objects.get(
                    slug=category_slug
                )
            except:
                context["active_category"] = None

        return context


class BlogDetailView(DetailView):
    """
    Display blog post detail.

    Features:
    - Full post content (HTML)
    - Author bio
    - Featured image
    - **Related products from post's category**
    - Related posts
    - CTA placeholder (will link to service pages in Phase 2)
    - View count tracking
    """

    model = AffiliatePost
    template_name = "affiliate/blog_detail.html"
    context_object_name = "post"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        """Only show published posts"""
        return AffiliatePost.objects.filter(status="PUBLISHED")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object

        # Increment view count
        post.view_count += 1
        post.save(update_fields=["view_count"])

        # Get featured products from category
        try:
            cache = post.category.affiliate_product_cache
            context["products"] = cache.get_products()[:4]
        except:
            context["products"] = []

        # Get related posts (same category, excluding this one)
        context["related_posts"] = (
            AffiliatePost.objects.filter(category=post.category, status="PUBLISHED")
            .exclude(id=post.id)
            .order_by("-published_at")[:3]
        )

        # Breadcrumb
        context["breadcrumbs"] = [
            {"name": "Blog", "url": "/blog/"},
            {"name": post.category.name, "url": post.category.get_absolute_url()},
            {"name": post.title, "url": post.get_absolute_url()},
        ]

        # CTA for Phase 2
        context["cta_text"] = post.cta_text
        context["cta_service"] = post.cta_service

        return context


def product_block_view(request, category_slug):
    """
    Reusable product block component (AJAX).

    Returns HTML fragment showing products for a category.
    Useful for embedding product blocks in multiple places.

    Usage:
        {% include 'components/product_block.html' with category=category %}

    Or via AJAX:
        GET /affiliate/api/product-block/<category_slug>/
    """

    try:
        category = AffiliateCategory.objects.get(slug=category_slug, status="ACTIVE")

        # Get products from cache
        try:
            cache = category.affiliate_product_cache
            products = cache.get_products()[:4]
        except:
            products = []

        context = {
            "category": category,
            "products": products,
        }

        return render(request, "components/product_block.html", context)

    except AffiliateCategory.DoesNotExist:
        return JsonResponse({"error": "Category not found"}, status=404)


def search_view(request):
    """
    Search across categories and blog posts.

    Query Parameters:
    - q: Search query
    - type: 'all', 'categories', 'posts' (default: all)
    - page: Page number

    Returns results grouped by type.
    """

    query = request.GET.get("q", "").strip()
    search_type = request.GET.get("type", "all")

    categories = []
    posts = []

    if query:
        # Search categories
        if search_type in ["all", "categories"]:
            categories = AffiliateCategory.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                status="ACTIVE",
            ).order_by("name")

        # Search posts
        if search_type in ["all", "posts"]:
            posts = (
                AffiliatePost.objects.filter(
                    Q(title__icontains=query)
                    | Q(content__icontains=query)
                    | Q(excerpt__icontains=query),
                    status="PUBLISHED",
                )
                .select_related("category")
                .order_by("-published_at")
            )

    # Pagination
    page_number = request.GET.get("page", 1)

    # Combine and paginate all results
    all_results = list(categories) + list(posts)
    paginator = Paginator(all_results, 12)  # 12 results per page

    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    context = {
        "query": query,
        "search_type": search_type,
        "page_obj": page_obj,
        "categories": categories,
        "posts": posts,
        "total_results": paginator.count,
    }

    return render(request, "affiliate/search_results.html", context)


def homepage_view(request):
    """
    Homepage - show featured categories and posts.

    Features:
    - Featured categories (up to 6)
    - Recent blog posts (up to 6)
    - Total stats
    """

    context = {
        "featured_categories": (
            AffiliateCategory.objects.filter(
                status="ACTIVE", is_featured=True, parent__isnull=True
            ).order_by("display_order")[:6]
        ),
        "recent_posts": (
            AffiliatePost.objects.filter(status="PUBLISHED").order_by("-published_at")[
                :6
            ]
        ),
        "total_categories": AffiliateCategory.objects.filter(
            status="ACTIVE", parent__isnull=True
        ).count(),
        "total_posts": AffiliatePost.objects.filter(status="PUBLISHED").count(),
    }

    return render(request, "affiliate/homepage.html", context)


# API Views (for future mobile app or AJAX)

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from apps.affiliate.serializers import CategorySerializer, PostSerializer

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for categories.

    Endpoints:
    - GET /api/categories/ → List all
    - GET /api/categories/<id>/ → Detail
    - GET /api/categories/<id>/products/ → Products
    """

    queryset = AffiliateCategory.objects.filter(status="ACTIVE")
    serializer_class = CategorySerializer
    lookup_field = "slug"

    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        """Get products for a category"""
        category = self.get_object()

        try:
            cache = category.affiliate_product_cache
            products = cache.get_products()
        except:
            products = []

        return Response(
            {
                "category": self.serializer_class(category).data,
                "products": products,
                "count": len(products),
            }
        )


class BlogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for blog posts.

    Endpoints:
    - GET /api/posts/ → List all
    - GET /api/posts/<id>/ → Detail
    """

    queryset = AffiliatePost.objects.filter(status="PUBLISHED")
    serializer_class = PostSerializer
    lookup_field = "slug"
    filterset_fields = ["category", "author"]


__all__ = [
    "CategoryListView",
    "CategoryDetailView",
    "BlogListView",
    "BlogDetailView",
    "product_block_view",
    "search_view",
    "homepage_view",
    "CategoryViewSet",
    "BlogViewSet",
]
