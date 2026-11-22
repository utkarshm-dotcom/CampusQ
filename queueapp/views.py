from datetime import date, timedelta
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import Max, Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .forms import RegisterForm, TokenForm
from .models import Service, Counter, QueueToken

def home(request):
    services = Service.objects.filter(is_active=True)
    return render(request, "queueapp/home.html", {"services": services})

def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("student_dashboard")
    else:
        form = RegisterForm()
    return render(request, "queueapp/form.html", {"form": form, "heading": "Create student account"})

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("admin_dashboard" if form.get_user().is_staff else "student_dashboard")
    else:
        form = AuthenticationForm(request)
    return render(request, "queueapp/form.html", {"form": form, "heading": "Login"})

@login_required
def student_dashboard(request):
    user_tokens = QueueToken.objects.filter(user=request.user).select_related("service")
    tokens = user_tokens.order_by("-created_at")[:30]
    active_tokens = user_tokens.filter(
        status__in=[QueueToken.WAITING, QueueToken.SERVING]
    ).order_by("queue_date", "sequence")
    context = {
        "tokens": tokens,
        "active_tokens": active_tokens,
        "token_total": user_tokens.count(),
        "active_total": active_tokens.count(),
        "completed_total": user_tokens.filter(status=QueueToken.COMPLETED).count(),
        "cancelled_total": user_tokens.filter(status=QueueToken.CANCELLED).count(),
    }
    return render(request, "queueapp/student_dashboard.html", context)


@login_required
def cancel_token(request, token_id):
    if request.method != "POST":
        return redirect("student_dashboard")
    token = get_object_or_404(QueueToken, id=token_id, user=request.user)
    if token.status == QueueToken.WAITING:
        token.status = QueueToken.CANCELLED
        token.save(update_fields=["status"])
        messages.success(request, f"Token {token.token_number} was cancelled.")
    else:
        messages.error(request, "Only waiting tokens can be cancelled. Serving or completed tokens cannot be cancelled.")
    return redirect("token_detail", token_id=token.id)

@login_required
def generate_token(request):
    if request.method == "POST":
        form = TokenForm(request.POST)
        if form.is_valid():
            service = form.cleaned_data["service"]
            today = timezone.localdate()
            with transaction.atomic():
                last = QueueToken.objects.filter(service=service, queue_date=today).aggregate(n=Max("sequence"))["n"] or 0
                sequence = last + 1
                token = QueueToken.objects.create(
                    user=request.user, service=service, sequence=sequence,
                    token_number=f"{service.id}-{sequence:03d}", queue_date=today
                )
            messages.success(request, f"Your token is {token.token_number}.")
            return redirect("token_detail", token_id=token.id)
    else:
        form = TokenForm()
    return render(request, "queueapp/form.html", {"form": form, "heading": "Generate a queue token"})

@login_required
def token_detail(request, token_id):
    token = get_object_or_404(QueueToken.objects.select_related("service"), id=token_id, user=request.user)
    ahead = QueueToken.objects.filter(
        service=token.service, queue_date=token.queue_date,
        status=QueueToken.WAITING, sequence__lt=token.sequence
    ).count()
    if token.status == QueueToken.SERVING:
        position = 0
    elif token.status in (QueueToken.COMPLETED, QueueToken.SKIPPED):
        position = None
    else:
        position = ahead + 1
    waiting_minutes = ahead * token.service.average_service_minutes
    return render(request, "queueapp/token_detail.html", {
        "token": token, "position": position, "waiting_minutes": waiting_minutes
    })

def staff_required(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(staff_required, login_url="login")
def admin_dashboard(request):
    today = timezone.localdate()
    services = Service.objects.filter(is_active=True)
    selected_service = request.GET.get("service")
    tokens = QueueToken.objects.filter(queue_date=today).select_related("user", "service")
    if selected_service:
        tokens = tokens.filter(service_id=selected_service)
    waiting = tokens.filter(status=QueueToken.WAITING)
    serving = tokens.filter(status=QueueToken.SERVING)
    stats = {
        "total": tokens.count(), "waiting": waiting.count(),
        "serving": serving.count(), "completed": tokens.filter(status=QueueToken.COMPLETED).count(),
        "skipped": tokens.filter(status=QueueToken.SKIPPED).count(),
    }
    return render(request, "queueapp/admin_dashboard.html", {
        "services": services, "tokens": tokens.order_by("sequence"),
        "waiting": waiting.order_by("sequence"), "serving": serving,
        "stats": stats, "selected_service": selected_service,
        "counters": Counter.objects.filter(is_active=True).select_related("service")
    })

@user_passes_test(staff_required, login_url="login")
def queue_action(request, token_id, action):
    if request.method != "POST":
        return redirect("admin_dashboard")
    token = get_object_or_404(
        QueueToken.objects.select_related("service", "counter"),
        id=token_id, queue_date=timezone.localdate()
    )

    if action == "next" and token.status == QueueToken.WAITING:
        counter_id = request.POST.get("counter_id")
        counter = get_object_or_404(
            Counter, id=counter_id, service=token.service, is_active=True
        )
        already_serving = QueueToken.objects.filter(
            service=token.service, counter=counter,
            queue_date=token.queue_date, status=QueueToken.SERVING
        ).exists()
        if already_serving:
            messages.error(request, f"{counter.name} already has a serving token. Complete it before calling another.")
        else:
            with transaction.atomic():
                next_token = QueueToken.objects.select_for_update().filter(
                    service=token.service, queue_date=token.queue_date,
                    status=QueueToken.WAITING
                ).order_by("sequence").first()
                if next_token and next_token.id == token.id:
                    next_token.counter = counter
                    next_token.status = QueueToken.SERVING
                    next_token.called_at = timezone.now()
                    next_token.save(update_fields=["counter", "status", "called_at"])
                    messages.success(request, f"{next_token.token_number} called at {counter.name}.")
                else:
                    messages.warning(request, "Please call the first waiting token in the queue.")
    elif action == "complete" and token.status == QueueToken.SERVING:
        token.status = QueueToken.COMPLETED
        token.completed_at = timezone.now()
        token.save(update_fields=["status", "completed_at"])
        messages.success(request, f"{token.token_number} completed.")
    elif action == "skip" and token.status == QueueToken.WAITING:
        token.status = QueueToken.SKIPPED
        token.save(update_fields=["status"])
        messages.info(request, f"{token.token_number} skipped.")
    return redirect("admin_dashboard")


@login_required
def token_status_api(request, token_id):
    """Return the latest status and queue estimate for the logged-in token owner."""
    token = get_object_or_404(
        QueueToken.objects.select_related("service", "counter"),
        id=token_id,
        user=request.user
    )
    ahead = QueueToken.objects.filter(
        service=token.service,
        queue_date=token.queue_date,
        status=QueueToken.WAITING,
        sequence__lt=token.sequence
    ).count()

    if token.status == QueueToken.SERVING:
        position = 0
    elif token.status in (QueueToken.COMPLETED, QueueToken.SKIPPED):
        position = None
    else:
        position = ahead + 1

    return JsonResponse({
        "token_number": token.token_number,
        "status": token.get_status_display(),
        "status_code": token.status,
        "counter": token.counter.name if token.counter_id else None,
        "position": position,
        "waiting_minutes": ahead * token.service.average_service_minutes,
        "updated_at": timezone.localtime().strftime("%H:%M:%S"),
    })


def live_display(request):
    services = Service.objects.filter(is_active=True).order_by("name")
    selected_id = request.GET.get("service")
    selected_service = services.filter(id=selected_id).first() if selected_id else services.first()
    return render(request, "queueapp/live_display.html", {
        "services": services, "selected_service": selected_service
    })


def live_display_api(request):
    service = get_object_or_404(Service, id=request.GET.get("service"), is_active=True)
    today = timezone.localdate()
    serving = QueueToken.objects.filter(
        service=service, queue_date=today, status=QueueToken.SERVING
    ).order_by("sequence").first()
    waiting = QueueToken.objects.filter(
        service=service, queue_date=today, status=QueueToken.WAITING
    ).order_by("sequence")
    return JsonResponse({
        "service": service.name,
        "serving": serving.token_number if serving else None,
        "serving_counter": serving.counter.name if serving and serving.counter_id else None,
        "waiting": [t.token_number for t in waiting[:3]],
        "waiting_count": waiting.count(),
        "updated_at": timezone.localtime().strftime("%H:%M:%S"),
    })


@user_passes_test(staff_required, login_url="login")
def analytics_dashboard(request):
    """Seven-day operational summary for campus queue administrators."""
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    period_tokens = QueueToken.objects.filter(queue_date__range=(start_date, today)).select_related(
        "service", "counter"
    )

    totals = {
        "total": period_tokens.count(),
        "waiting": period_tokens.filter(status=QueueToken.WAITING).count(),
        "serving": period_tokens.filter(status=QueueToken.SERVING).count(),
        "completed": period_tokens.filter(status=QueueToken.COMPLETED).count(),
        "skipped": period_tokens.filter(status=QueueToken.SKIPPED).count(),
        "cancelled": period_tokens.filter(status=QueueToken.CANCELLED).count(),
    }

    service_rows = list(
        period_tokens.values("service__name").annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=QueueToken.COMPLETED)),
            waiting=Count("id", filter=Q(status=QueueToken.WAITING)),
            serving=Count("id", filter=Q(status=QueueToken.SERVING)),
            skipped=Count("id", filter=Q(status=QueueToken.SKIPPED)),
            cancelled=Count("id", filter=Q(status=QueueToken.CANCELLED)),
        ).order_by("-total")
    )

    counter_rows = list(
        period_tokens.filter(counter__isnull=False).values(
            "counter__name", "service__name"
        ).annotate(
            assigned=Count("id"),
            completed=Count("id", filter=Q(status=QueueToken.COMPLETED)),
            serving=Count("id", filter=Q(status=QueueToken.SERVING)),
        ).order_by("service__name", "counter__name")
    )

    daily_rows = []
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        daily_rows.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%d %b"),
            "total": period_tokens.filter(queue_date=day).count(),
        })
    max_daily = max([row["total"] for row in daily_rows] or [0]) or 1
    for row in daily_rows:
        row["height"] = round(row["total"] / max_daily * 100) if row["total"] else 0

    wait_seconds = []
    for token in period_tokens.exclude(called_at__isnull=True):
        wait_seconds.append(max(0, (token.called_at - token.created_at).total_seconds()))
    avg_wait_minutes = round(sum(wait_seconds) / len(wait_seconds) / 60, 1) if wait_seconds else 0

    service_max = max([row["total"] for row in service_rows] or [0]) or 1
    for row in service_rows:
        row["percent"] = round(row["total"] / service_max * 100)

    return render(request, "queueapp/analytics.html", {
        "totals": totals,
        "service_rows": service_rows,
        "counter_rows": counter_rows,
        "daily_rows": daily_rows,
        "avg_wait_minutes": avg_wait_minutes,
        "start_date": start_date,
        "today": today,
    })


@user_passes_test(staff_required, login_url="login")
def reports_center(request):
    """Admin-only export centre with optional date and department filters."""
    from datetime import date
    import csv
    from django.http import HttpResponse

    today = timezone.localdate()
    start_text = request.GET.get("start", (today - timedelta(days=6)).isoformat())
    end_text = request.GET.get("end", today.isoformat())
    service_id = request.GET.get("service", "")
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
        if start > end:
            raise ValueError
    except ValueError:
        messages.error(request, "Choose a valid date range (start date must not be after end date).")
        start, end = today - timedelta(days=6), today
        start_text, end_text = start.isoformat(), today.isoformat()

    rows = QueueToken.objects.filter(queue_date__range=(start, end)).select_related(
        "user", "service", "counter"
    ).order_by("queue_date", "service__name", "sequence")
    if service_id:
        rows = rows.filter(service_id=service_id)

    export_format = request.GET.get("format")
    if export_format in {"csv", "xlsx", "pdf"}:
        records = [[
            "Date", "Token", "Student", "Department", "Counter", "Status",
            "Created At", "Called At", "Completed At"
        ]]
        for token in rows:
            records.append([
                token.queue_date.isoformat(), token.token_number, token.user.username,
                token.service.name, token.counter.name if token.counter else "",
                token.get_status_display(),
                timezone.localtime(token.created_at).strftime("%Y-%m-%d %H:%M") if token.created_at else "",
                timezone.localtime(token.called_at).strftime("%Y-%m-%d %H:%M") if token.called_at else "",
                timezone.localtime(token.completed_at).strftime("%Y-%m-%d %H:%M") if token.completed_at else "",
            ])
        filename = f"campusq-report-{start.isoformat()}-to-{end.isoformat()}"
        if export_format == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
            response.write("\ufeff")
            csv.writer(response).writerows(records)
            return response

        if export_format == "xlsx":
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "CampusQ Report"
            for record in records:
                sheet.append(record)
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="263B5A")
                cell.alignment = Alignment(horizontal="center")
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                width = min(max(len(str(cell.value or "")) for cell in column) + 3, 32)
                sheet.column_dimensions[get_column_letter(column[0].column)].width = width
            response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
            workbook.save(response)
            return response

        if export_format == "pdf":
            from io import BytesIO
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import landscape, A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.units import mm
            buffer = BytesIO()
            document = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
            styles = getSampleStyleSheet()
            story = [
                Paragraph("CampusQ Queue Report", styles["Title"]),
                Paragraph(f"Period: {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}", styles["Normal"]),
                Spacer(1, 8*mm)
            ]
            table = Table([[str(v) for v in row] for row in records], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#263B5A")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,-1), 7),
                ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F1F5F9")]),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("LEFTPADDING", (0,0), (-1,-1), 4),
                ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ]))
            story.append(table)
            document.build(story)
            response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
            return response

    return render(request, "queueapp/reports.html", {
        "services": Service.objects.filter(is_active=True).order_by("name"),
        "start": start_text, "end": end_text, "selected_service": service_id,
        "record_count": rows.count(),
    })
