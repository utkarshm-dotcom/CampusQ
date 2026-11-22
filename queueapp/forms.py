from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Service

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

class TokenForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.filter(is_active=True), empty_label="Choose a service")
