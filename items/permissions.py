from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwnerOrReadOnly(BasePermission):
    """
    Only owners can edit/delete. Others can read-only.
    """

    def has_object_permission(self, request, view, obj):
        # Read-only permissions for safe methods
        if request.method in SAFE_METHODS:
            return True
        # Write permissions only for the owner
        return obj.owner == request.user
