from rest_framework.routers import DefaultRouter
from django.urls import path
from users.views import UserViewSet
from items.views import ItemViewSet, TagViewSet, LinkViewSet, FileGroupViewSet, FileViewSet, MediaURLViewSet
from .views import media_proxy_view

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'items', ItemViewSet)
router.register(r'tags', TagViewSet)
router.register(r'links', LinkViewSet)
router.register(r'media-url', MediaURLViewSet)
router.register(r'file-groups', FileGroupViewSet)
router.register(r'files', FileViewSet)

urlpatterns = router.urls + [
    path('proxy-media/', media_proxy_view, name='media-proxy'),
]
