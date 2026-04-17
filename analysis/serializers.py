from rest_framework import serializers
from .models import AnalysisResult

class AnalysisSerializer(serializers.Serializer):
    class Meta:
        model = AnalysisResult
        fields = ("model_output",)
