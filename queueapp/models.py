from django.conf import settings
from django.db import models

class Service(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=250, blank=True)
    average_service_minutes = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Counter(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="counters")
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["service", "name"], name="unique_counter_name_per_service")
        ]

    def __str__(self):
        return f"{self.service.name} - {self.name}"

class QueueToken(models.Model):
    WAITING = "WAITING"
    SERVING = "SERVING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (WAITING, "Waiting"), (SERVING, "Serving"),
        (COMPLETED, "Completed"), (SKIPPED, "Skipped"), (CANCELLED, "Cancelled"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    counter = models.ForeignKey(Counter, on_delete=models.SET_NULL, null=True, blank=True, related_name="tokens")
    token_number = models.CharField(max_length=20)
    sequence = models.PositiveIntegerField()
    queue_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=WAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    called_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["service", "queue_date", "sequence"], name="unique_daily_service_sequence"),
            models.UniqueConstraint(fields=["service", "queue_date", "token_number"], name="unique_daily_service_token"),
        ]

    def __str__(self):
        return f"{self.token_number} - {self.service.name}"
