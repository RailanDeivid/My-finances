from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(email__iexact=username)
            except User.DoesNotExist:
                return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
