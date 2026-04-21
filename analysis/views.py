from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from main.models import Game
from .models import TaskResult, AnalysisResult
from .serializers import AnalysisSerializer
from .tasks import analyse_game
from celery.result import AsyncResult

# Create your views here.
class AnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        game_id = request.query_params.get('game_id')
        game = Game.objects.filter(id=game_id, user=request.user).first()
        if not game:
            return Response({'error': 'Game not found'}, status=404)
        
        if game.analysed:
            serialized_data = AnalysisSerializer(game).data
            return Response(serialized_data, status=200)
        
        task = analyse_game.delay(game_id)  # pyright: ignore[reportCallIssue]
        game.task_id = task.id
        game.save()
        return Response({'task_id': task.id}, status=202)
    
class AnalysisStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        if not Game.objects.filter(task_id=task_id, user=request.user).exists():
            return Response({'error': 'Invalid task ID'}, status=404)
        
        result = AsyncResult(task_id)
        print(result.state)
        print(result.info)
        if result.state == 'PENDING':
            return Response({'status': "PENDING"}, status=200)
        elif result.state == 'STARTED':
            return Response({'status': 'PROGRESS', 'meta': result.info}, status=200)
        elif result.state == 'SUCCESS':
            result_data_id = result.result
            obj = AnalysisResult.objects.filter(id=result_data_id).first()
            if obj:
                return Response({'status': 'Complete', 'data': obj.model_output}, status=200)
        return Response({'status': 'FAILURE', 'error': str(result.info)}, status=200)

        
