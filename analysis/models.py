from django.db import models

class Position(models.Model):
    fen = models.CharField(primary_key=True)
    user = models.ForeignKey('main.User', on_delete=models.CASCADE, related_name='positions')
    hits = models.IntegerField(default=0)
    last_hit = models.DateTimeField(auto_now=True)
    first_hit = models.DateTimeField(auto_now_add=True)

class TaskResult(models.Model):
    task_id = models.CharField(primary_key=True)
    status = models.CharField(max_length=20)
    progress = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)
    started = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# Create your models here.
class AnalysisResult(models.Model):
    id=models.AutoField(primary_key=True)
    model_input = models.JSONField()
    tokens_input = models.IntegerField()
    model_output = models.JSONField()
    tokens_output = models.IntegerField()
    llm_latency = models.FloatField()
    completion_time = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)