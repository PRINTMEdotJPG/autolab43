# forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User

class StudentLoginForm(AuthenticationForm):
    full_name = forms.CharField(label="ФИО", max_length=100)
    group_name = forms.CharField(label="Группа", max_length=20)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username')  # Удаляем стандартное поле username

    def clean(self):
        full_name = self.cleaned_data.get('full_name')
        group_name = self.cleaned_data.get('group_name')
        password = self.cleaned_data.get('password')

        if full_name and group_name and password:
            # Ищем пользователя по ФИО и группе
            try:
                user = User.objects.get(full_name=full_name, group_name=group_name, role='student')
                if user.check_password(password):
                    self.user_cache = user
                else:
                    raise forms.ValidationError("Неверный пароль")
            except User.DoesNotExist:
                raise forms.ValidationError("Студент с такими данными не найден")
        return self.cleaned_data

class TeacherLoginForm(AuthenticationForm):
    # Используем стандартную форму аутентификации по email и паролю
    username = forms.EmailField(label="Email")
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)

    def clean(self):
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email, role='teacher')
                if user.check_password(password):
                    self.user_cache = user
                else:
                    raise forms.ValidationError("Неверный пароль")
            except User.DoesNotExist:
                raise forms.ValidationError("Преподаватель с таким email не найден")
        return self.cleaned_data