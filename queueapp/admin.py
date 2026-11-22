from django.contrib import admin
from .models import Service, Counter, QueueToken

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "average_service_minutes", "is_active")
    list_filter = ("is_active",)

@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display = ("name", "service", "is_active")
    list_filter = ("service", "is_active")
    search_fields = ("name", "service__name")

@admin.register(QueueToken)
class QueueTokenAdmin(admin.ModelAdmin):
    list_display = ("token_number", "user", "service", "counter", "queue_date", "status", "created_at")
    list_filter = ("service", "counter", "queue_date", "status")
    search_fields = ("token_number", "user__username")
