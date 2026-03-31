from django.db import models

# Create your models here.
class Position(models.Model):
    user = models.ForeignKey('main.User', on_delete=models.CASCADE, related_name='user_positions')
    fen = models.CharField(max_length=150, unique=True, primary_key=True)

class CriticalMoment(Position):
    evaluation_delta = models.FloatField(blank=True, null=True)

class Analysis(models.Model):
    pass ## ADD FIELDS AS PIPELINE DEVELOPS