from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("display/", views.live_display, name="live_display"),
    path("display/status/", views.live_display_api, name="live_display_api"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("token/new/", views.generate_token, name="generate_token"),
    path("token/<int:token_id>/", views.token_detail, name="token_detail"),
    path("token/<int:token_id>/cancel/", views.cancel_token, name="cancel_token"),
    path("token/<int:token_id>/status/", views.token_status_api, name="token_status_api"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/analytics/", views.analytics_dashboard, name="analytics_dashboard"),
    path("admin-dashboard/reports/", views.reports_center, name="reports_center"),
    path("queue/<int:token_id>/<str:action>/", views.queue_action, name="queue_action"),
]
