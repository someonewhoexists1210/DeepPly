from django.db import models
from django.contrib.auth.models import AbstractUser
import random

# Create your models here.

def generate_game_id():
    id = random.randint(100000, 999999)
    while Game.objects.filter(id=id).exists():
        id = random.randint(100000, 999999)
    return id

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

class Game(models.Model):
    id = models.IntegerField(primary_key=True, default=generate_game_id)
    lichess_id = models.CharField(max_length=50, blank=True, null=True)
    chesscom_id = models.CharField(max_length=50, blank=True, null=True)
    task_id = models.CharField(max_length=255, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_games')
    plies = models.IntegerField(blank=False)
    middle_game_start = models.IntegerField(blank=True, null=True)
    end_game_start = models.IntegerField(blank=True, null=True)
    moves = models.TextField(blank=False) # space separated list of moves in PGN Notation format
    positions = models.ManyToManyField('analysis.Position', blank=True, related_name='appearances')
    # critical_positions = models.ManyToManyField('analysis.CriticalMoment', blank=True, related_name='critical_appearances')
    color = models.BooleanField(blank=False) # white = 1
    result = models.FloatField(blank=False, default=0.5) # 1.0 for win, 0.5 for draw, 0.0 for loss
    date = models.DateTimeField(auto_now_add=False, blank=False)
    time_control = models.CharField(max_length=50, blank=True, null=True)
    import_date = models.DateTimeField(auto_now_add=True)
    analysed = models.BooleanField(default=False, blank=False)
    analysis = models.OneToOneField('analysis.AnalysisResult', on_delete=models.CASCADE, blank=True, null=True, related_name='game')

    


