"""
Affiliate App URLs
==================
URL routing for categories, posts, and products.

URL Patterns:
/                          → Homepage
/categories/               → All categories
/categories/<slug>/        → Category detail
/blog/                     → All posts
/blog/<slug>/              → Blog post detail
/search/                   → Search
/api/categories/           → Category API
/api/posts/                → Posts API
"""

from django.urls import path
from rest_framework.routers import DefaultRouter
from apps.affiliate import views

# Create API router
router = DefaultRouter()
router.register(r"categories", views.CategoryViewSet, basename="api-category")
router.register(r"posts", views.BlogViewSet, basename="api-post")

app_name = "affiliate"

urlpatterns = [
    # Homepage
    path("", views.homepage_view, name="homepage"),
    # Categories
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path(
        "categories/<slug:slug>/",
        views.CategoryDetailView.as_view(),
        name="category-detail",
    ),
    # Blog
    path("blog/", views.BlogListView.as_view(), name="blog-list"),
    path("blog/<slug:slug>/", views.BlogDetailView.as_view(), name="blog-detail"),
    # Product block (component)
    path(
        "api/product-block/<slug:category_slug>/",
        views.product_block_view,
        name="product-block",
    ),
    # Search
    path("search/", views.search_view, name="search"),
]

# Add API endpoints
urlpatterns += router.urls
