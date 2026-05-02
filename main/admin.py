from django.contrib import admin
from .models import User, Game
from integrations.lichess.models import LichessToken

# Register your models here.
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    readonly_fields = ('password', 'last_login', 'date_joined')  # replace with your field names

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'date', 'result', 'analysed')
    search_fields = ('user__username', 'task_id')
    list_filter = ('result', 'analysed', 'user__username')
    ordering = ('-date',)

admin.site.register(LichessToken)
