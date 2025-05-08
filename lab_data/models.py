from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """
    Кастомный менеджер пользователей для модели User.
    Реализует методы создания пользователей разных типов.
    """

    def create_superuser(
        self,
        email: str,
        full_name: str,
        password: str = None,
        **extra_fields
    ) -> 'User':
        """
        Создает и возвращает суперпользователя.

        Args:
            email: Email суперпользователя
            full_name: Полное имя пользователя
            password: Пароль (опционально)
            **extra_fields: Дополнительные поля

        Returns:
            User: Созданный суперпользователь

        Raises:
            ValueError: Если is_staff или is_superuser не True
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'teacher')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, full_name, password, **extra_fields)

    def create_teacher(
        self,
        email: str,
        full_name: str,
        password: str = None,
        **extra_fields
    ) -> 'User':
        """
        Создает пользователя с ролью преподавателя.

        Args:
            email: Email преподавателя
            full_name: Полное имя преподавателя
            password: Пароль (опционально)
            **extra_fields: Дополнительные поля

        Returns:
            User: Созданный преподаватель
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('role', 'teacher')
        return self._create_user(email, full_name, password, **extra_fields)

    def create_student(
        self,
        full_name: str,
        group_name: str,
        password: str = None,
        **extra_fields
    ) -> 'User':
        """
        Создает пользователя с ролью студента.

        Args:
            full_name: Полное имя студента
            group_name: Название учебной группы
            password: Пароль (опционально)
            **extra_fields: Дополнительные поля

        Returns:
            User: Созданный студент
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('role', 'student')
        
        if 'email' not in extra_fields:
            # Генерация email если не предоставлен
            email = (
                f"{full_name.replace(' ', '.').lower()}."
                f"{group_name.lower()}@example.com"
            )
            extra_fields['email'] = email
            
        return self._create_user(
            extra_fields['email'],
            full_name,
            password,
            group_name=group_name,
            **extra_fields
        )

    def _create_user(
        self,
        email: str,
        full_name: str,
        password: str,
        group_name: str = None,
        **extra_fields
    ) -> 'User':
        """
        Внутренний метод создания пользователя.

        Args:
            email: Email пользователя
            full_name: Полное имя
            password: Пароль
            group_name: Название группы (опционально)
            **extra_fields: Дополнительные поля

        Returns:
            User: Созданный пользователь

        Raises:
            ValueError: Если email не указан
        """
        if not email:
            raise ValueError('The Email must be set')
            
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            full_name=full_name,
            group_name=group_name,
            **extra_fields
        )
        user.set_password(password)
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    Кастомная модель пользователя системы.
    Заменяет стандартную модель пользователя Django.
    """

    # Выбор ролей пользователя
    ROLE_CHOICES = [
        ('student', 'Студент'),
        ('teacher', 'Преподаватель'),
    ]

    # Основные поля модели
    full_name = models.CharField(
        "ФИО",
        max_length=100,
        blank=False,
        help_text="Полное имя пользователя (только кириллица)"
    )

    email = models.EmailField(
        unique=True,
        verbose_name="Email",
        help_text="Уникальный email пользователя"
    )

    group_name = models.CharField(
        max_length=20,
        verbose_name="Группа",
        blank=True,  # Для преподавателей может быть пустым
        null=True,
        help_text="Название учебной группы (кириллица + цифры)"
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='student',
        verbose_name="Роль",
        help_text="Роль пользователя в системе"
    )

    is_staff = models.BooleanField(
        default=False,
        help_text="Определяет доступ к админ-панели"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Активен ли пользователь"
    )

    date_joined = models.DateTimeField(
        _('date joined'),
        default=timezone.now,
        editable=False
    )

    # Поля для аутентификации
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['full_name']

    def __str__(self) -> str:
        """Строковое представление пользователя."""
        return (
            f"{self.full_name} ({self.group_name})"
            if self.group_name
            else self.full_name
        )


class Experiments(models.Model):
    """Модель для хранения данных о проведенных экспериментах."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='experiments',
        verbose_name="Пользователь"
    )
    step = models.IntegerField(default=1)  # Добавить

    temperature = models.FloatField(verbose_name="Температура (°C)")
    tube_length = models.FloatField(verbose_name="Длина трубы (м)")

    frequency = models.FloatField()  # Заменить frequencies

    student_speed = models.FloatField(null=True)  # Добавить
    student_gamma = models.FloatField(null=True)  # Добавить
    
    
    system_gamma = models.FloatField(null=True)
    error_percent = models.FloatField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)  # Заменить date

    class Meta:
        verbose_name = "Эксперимент"
        verbose_name_plural = "Эксперименты"
        ordering = ['-created_at']  # This is the correct field name

    def __str__(self) -> str:
        return f"Эксперимент #{self.id} ({self.user.full_name})"


class EquipmentData(models.Model):
    """Модель для хранения данных с оборудования во время эксперимента."""

    experiment = models.ForeignKey(
        Experiments,
        on_delete=models.CASCADE,
        related_name='equipment_data',
        verbose_name="Эксперимент"
    )
    time_ms = models.IntegerField(verbose_name="Время (мс)")
    microphone_signal = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(1023)],
        verbose_name="Сигнал микрофона"
    )
    tube_position = models.FloatField(verbose_name="Положение трубы (мм)")
    voltage = models.FloatField(verbose_name="Напряжение (В)")

    class Meta:
        verbose_name = "Данные оборудования"
        verbose_name_plural = "Данные оборудования"
        ordering = ['time_ms']

    def __str__(self) -> str:
        return f"Данные #{self.id} (Эксперимент {self.experiment.id})"


class Results(models.Model):
    """Модель для хранения результатов экспериментов."""

    STATUS_CHOICES = [
        ('success', 'Успешно'),
        ('fail', 'Неудача'),
        ('pending', 'Ожидает проверки'),
    ]

    experiment = models.OneToOneField(
        Experiments,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="Эксперимент"
    )
    gamma_calculated = models.FloatField(verbose_name="Рассчитанное γ")
    student_gamma = models.FloatField(
        verbose_name="Студенческое γ",
        null=True,
        blank=True
    )
    gamma_reference = models.FloatField(verbose_name="Эталонное γ")
    error_percent = models.FloatField(verbose_name="Отклонение (%)")
    student_error = models.FloatField(
        verbose_name="Студенческое отклонение",
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Статус"
    )
    visualization_data = models.JSONField(
        verbose_name="Данные для визуализации",
        null=True,
        blank=True
    )
    detailed_results = models.JSONField(verbose_name="Детальные результаты")

    class Meta:
        verbose_name = "Результат"
        verbose_name_plural = "Результаты"

    def __str__(self) -> str:
        return f"Результат эксперимента #{self.experiment.id}"


class Protocols(models.Model):
    """Модель для хранения протоколов экспериментов."""

    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('final', 'Финальный'),
    ]

    experiment = models.ForeignKey(
        Experiments,
        on_delete=models.CASCADE,
        related_name='protocols',
        verbose_name="Эксперимент"
    )
    generated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата генерации"
    )
    protocol_path = models.CharField(
        max_length=255,
        verbose_name="Путь к протоколу"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Статус"
    )

    class Meta:
        verbose_name = "Протокол"
        verbose_name_plural = "Протоколы"
        ordering = ['-generated_at']

    def __str__(self) -> str:
        return f"Протокол #{self.id} ({self.get_status_display()})"


class Calculations(models.Model):
    """Модель для хранения промежуточных расчетов."""

    experiment = models.ForeignKey(
        Experiments,
        on_delete=models.CASCADE,
        related_name='calculations',
        verbose_name="Эксперимент"
    )
    step_number = models.IntegerField(verbose_name="Номер шага")
    description = models.TextField(verbose_name="Описание")
    formula_used = models.TextField(
        verbose_name="Использованная формула",
        blank=True
    )
    input_data = models.JSONField(verbose_name="Входные данные")
    output_data = models.JSONField(verbose_name="Выходные данные")
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время выполнения"
    )

    class Meta:
        verbose_name = "Расчёт"
        verbose_name_plural = "Расчёты"
        ordering = ['step_number']

    def __str__(self) -> str:
        return f"Шаг #{self.step_number} (Эксперимент {self.experiment.id})"