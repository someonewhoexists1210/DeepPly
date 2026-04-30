from django.db import models
from main.models import User

# Create your models here.
class LichessToken(models.Model):
    lichessUserId = models.CharField(max_length=100, blank=False)
    lichessUsername = models.CharField(max_length=200, blank=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lichess_token')
    access_token = models.CharField(max_length=255, blank=False)
    expires_at = models.DateTimeField(blank=False)
    last_seen = models.DateTimeField(blank=True, null=True)