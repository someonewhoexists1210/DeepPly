from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from main.models import Game
from .models import AnalysisResult
from .tasks import analyse_game
from celery.result import AsyncResult

# Create your views here.
class AnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        game_id = request.data.get('gameId')
        game = Game.objects.filter(id=game_id, user=request.user).first()
        if not game:
            return Response({'error': 'Game not found'}, status=404)
        if game.analysed:
            return Response({'message': 'Game already analysed', 'gameId': game.id}, status=200)
        
        task = analyse_game.delay(game_id)  # pyright: ignore[reportCallIssue]
        game.task_id = task.id
        game.save()
        return Response({'task_id': task.id}, status=202)
    
class AnalysisStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        game = Game.objects.filter(task_id=task_id, user=request.user).first()
        if not game:
            return Response({'error': 'Invalid task ID'}, status=404)
        
        result = AsyncResult(task_id)
        print(result.state)
        if result.state == 'STARTED' or result.state == "PENDING":
            return Response({'status': 'PROGRESS', 'meta': result.info, 'gameId': game.id}, status=200)
        elif result.state == 'SUCCESS':
            result_data_id = result.result
            obj = AnalysisResult.objects.filter(id=result_data_id).first()
            if obj:
                return Response({'status': 'Completed', 'meta': result.info, 'gameId': game.id}, status=200)
        return Response({'status': 'FAILED', 'error': str(result.info)}, status=200)

        
