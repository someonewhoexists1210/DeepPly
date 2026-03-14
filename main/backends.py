from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class UorEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(Q(username=username) | Q(email=username))
        except User.MultipleObjectsReturned:
            return None
        except User.DoesNotExist:
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user): # type: ignore
            return user
        return None