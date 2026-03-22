from django.shortcuts import render
from rest_framework.views import APIView, Response
from .utils import import_games, s_epoch_to_datetime
from main.models import Game
from rest_framework.permissions import IsAuthenticated


GameResultMap = {
    1.0: ['win'],
    0.5: ['agreed', 'repetition', 'stalemate', 'insufficient', 'timevsinsufficient', '50move'],
    0.0: ['checkmated', 'resigned', 'timeout', 'lose', 'abandoned']
}


# Create your views here.
class ChessComImport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        username = request.query_params.get('username')
        months = int(request.query_params.get('months', 1))
        if not username:
            return Response({"error": "Username is required"}, status=400)

        try:
            games = import_games(username, months)
            print('import success')
            if games.get('error'):
                return Response(games['error'], status=games['status_code'])
            
            for game in games['games']:
                player_color = 'white' if game['white']['username'] == username else 'black'
                res = 0.5
                for result, conditions in GameResultMap.items():
                    if game[player_color]['result'] in conditions:
                        res = result
                        break

                Game.objects.create(
                    chesscom_id=game['url'].split('/')[-1],
                    user=request.user,
                    plies=game['plies'],
                    color=game['black']['username'] == username,
                    moves=game['moves'],
                    result=res,
                    date=s_epoch_to_datetime(game['end_time']),
                    time_control=game['time_control']
                )
            return Response({'message': f"Chess.com import successful for {username} for {months} month(s)"}, status=200)
        except Exception as e:
            return Response({"error": "Error occured: " + str(e)}, status=500)
