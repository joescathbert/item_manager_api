from rest_framework.routers import DefaultRouter
from users.views import UserViewSet
from items.views import ItemViewSet, TagViewSet, LinkViewSet, FileGroupViewSet, FileViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'items', ItemViewSet)
router.register(r'tags', TagViewSet)
router.register(r'links', LinkViewSet)
router.register(r'file-groups', FileGroupViewSet)
router.register(r'files', FileViewSet)

urlpatterns = router.urls
