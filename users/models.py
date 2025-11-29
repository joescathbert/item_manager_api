import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_admin', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)
        return self._create_user(username, email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    currency = models.CharField(max_length=8, default='USD')
    phone_number = models.CharField(max_length=30, blank=True, null=True)
    avatar_url = models.URLField(max_length=1024, blank=True, null=True)
    preferred_language = models.CharField(max_length=10, default='en')
    settings = models.JSONField(default=dict, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)
    auth_provider = models.CharField(max_length=32, default='local')
    recovery_email = models.EmailField(blank=True, null=True)
    role = models.CharField(max_length=32, default='user')
    is_staff = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    objects = UserManager()

    def __str__(self):
        return self.username

    @property
    def is_active(self):
        return self.deleted_at is None
