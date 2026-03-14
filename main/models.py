from django.db import models
from django.contrib.auth.models import AbstractUser
import random

# Create your models here.

def generate_game_id():
    id = random.randint(100000, 999999)
    while Game.objects.filter(id=id).exists():
        id = random.randint(100000, 999999)
    return id

class Game(models.Model):
    id = models.IntegerField(primary_key=True, default=generate_game_id)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='user_games')
    plies = models.IntegerField(blank=False)
    middle_game_start = models.CharField(max_length=10, blank=True, null=True)
    end_game_start = models.CharField(max_length=10, blank=True, null=True)
    positions = models.ManyToManyField('Position', blank=True, related_name='appearances')
    critical_positions = models.ManyToManyField('CriticalMoment', blank=True, related_name='critical_appearances')
    color = models.BooleanField(blank=False) # white = False
    result = models.FloatField(blank=False, default=0.5) # 1.0 for win, 0.5 for draw, 0.0 for loss
    date = models.DateTimeField(auto_now_add=True)

class Position(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='user_positions')
    fen = models.CharField(max_length=150, unique=True, primary_key=True)
    evaluation = models.FloatField(blank=True, null=True)
    best_line = models.CharField(max_length=100, blank=True, null=True)

class CriticalMoment(Position):
    evaluation_delta = models.FloatField(blank=True, null=True)

class User(AbstractUser):
    email = models.EmailField(blank=True, null=True)
    elo = models.IntegerField(default=800, blank=False)
    profile_picture = models.URLField(blank=True, null=True)
    is_coach = models.BooleanField(blank=False, default=False)
    paid_user = models.BooleanField(default=False, blank=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(elo__gte=0) & models.Q(elo__lte=3000),
                name="elo_range"
            )
        ]

class LichessToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lichess_tokens')
    access_token = models.CharField(max_length=255, blank=False)
    expires_at = models.DateTimeField(blank=False)