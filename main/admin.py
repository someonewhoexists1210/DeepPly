from django.contrib import admin
from .models import User, Game
from integrations.lichess.models import LichessToken

# Register your models here.
admin.site.register(Game)
class UserAdmin(admin.ModelAdmin):
    readonly_fields = ('password', 'last_login', 'date_joined')  # replace with your field names

admin.site.register(User, UserAdmin)
admin.site.register(LichessToken)
