from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from .models import User
from .serializers import UserSerializer

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                'username',
                openapi.IN_QUERY,
                description="Username of the user to fetch",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={200: UserSerializer()}
    )

    @action(detail=False, methods=['get'], url_path='by-username', permission_classes=[AllowAny])
    def get_by_username(self, request):
        username = request.query_params.get('username')
        if not username:
            return Response({"error": "username query parameter is required"}, status=400)

        user = get_object_or_404(User, username=username)
        serializer = self.get_serializer(user)
        return Response(serializer.data)
