from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """
    Кастомный менеджер пользователей для модели User.
    Реализует методы создания обычных пользователей, суперпользователей,
    преподавателей и студентов.
    """
    
    def create_superuser(self, email, full_name, password=None, **extra_fields):
        """
        Создает и возвращает суперпользователя с указанными email, ФИО и паролем.
        
        Args:
            email (str): Email суперпользователя
            full_name (str): Полное имя пользователя
            password (str, optional): Пароль. Defaults to None.
            
        Returns:
            User: Созданный суперпользователь
            
        Raises:
            ValueError: Если is_staff или is_superuser не установлены в True
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

    def create_teacher(self, email, full_name, password=None, **extra_fields):
        """
        Создает и возвращает пользователя с ролью преподавателя.
        
        Args:
            email (str): Email преподавателя
            full_name (str): Полное имя преподавателя
            password (str, optional): Пароль. Defaults to None.
            
        Returns:
            User: Созданный пользователь с ролью преподавателя
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('role', 'teacher')
        return self._create_user(email, full_name, password, **extra_fields)

    def create_student(self, full_name, group_name, password=None, **extra_fields):
        """
        Создает и возвращает пользователя с ролью студента.
        Автоматически генерирует email, если он не предоставлен.
        
        Args:
            full_name (str): Полное имя студента
            group_name (str): Название учебной группы
            password (str, optional): Пароль. Defaults to None.
            
        Returns:
            User: Созданный пользователь с ролью студента
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('role', 'student')
        # Генерируем email на основе имени и группы, если не предоставлен
        if 'email' not in extra_fields:
            extra_fields['email'] = f"{full_name.replace(' ', '.').lower()}.{group_name.lower()}@example.com"
        return self._create_user(extra_fields['email'], full_name, password, group_name=group_name, **extra_fields)

    def _create_user(self, email, full_name, password, group_name=None, **extra_fields):
        """
        Внутренний метод для создания пользователя.
        Выполняет нормализацию email и сохранение пользователя.
        
        Args:
            email (str): Email пользователя
            full_name (str): Полное имя пользователя
            password (str): Пароль
            group_name (str, optional): Название группы. Defaults to None.
            
        Returns:
            User: Созданный пользователь
            
        Raises:
            ValueError: Если email не указан
        """
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, group_name=group_name, **extra_fields)
        user.set_password(password)
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    Кастомная модель пользователя для системы аутентификации.
    Заменяет стандартную модель пользователя Django.
    Поддерживает две роли: студент и преподаватель.
    """
    
    # Выбор ролей пользователя
    ROLE_CHOICES = [
        ('student', 'Студент'),
        ('teacher', 'Преподаватель'),
    ]
    
    # Поля модели
    full_name = models.CharField(
        "ФИО", 
        max_length=100, 
        blank=False,
        help_text="Полное имя пользователя (только кириллица)"
    )
    
    # Отключаем стандартное поле username
    username = None
    
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
        help_text="Определяет, может ли пользователь входить в админ-панель"
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
    USERNAME_FIELD = 'email'  # Поле для входа в систему
    REQUIRED_FIELDS = ['full_name']  # Обязательные поля при создании пользователя

    objects = UserManager()  # Кастомный менеджер пользователей

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['full_name']

    def __str__(self):
        """
        Строковое представление пользователя.
        
        Returns:
            str: Представление пользователя в формате "ФИО (Группа)" или "ФИО"
        """
        return f"{self.full_name} ({self.group_name})" if self.group_name else self.full_name
    

class Experiments(models.Model):
    # id = pk
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='experiments',
        verbose_name="Пользователь"
    )
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата эксперимента")
    temperature = models.FloatField(verbose_name="Температура (°C)")
    tube_length = models.FloatField(verbose_name="Длина трубы (м)")

    class Meta:
        verbose_name = "Эксперимент"
        verbose_name_plural = "Эксперименты"

    def __str__(self):
        return f"Эксперимент #{self.id} ({self.user.full_name})"
    
class EquipmentData(models.Model):
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

    def __str__(self):
        return f"Данные #{self.id} (Эксперимент {self.experiment.id})"
    

class Results(models.Model):
    STATUS_CHOICES = [
        ('success', 'Успешно'),
        ('fail', 'Неудача'),
    ]

    experiment = models.OneToOneField(
        Experiments,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="Эксперимент"
    )
    gamma_calculated = models.FloatField(verbose_name="Рассчитанное γ")
    gamma_reference = models.FloatField(verbose_name="Эталонное γ")
    error_percent = models.FloatField(verbose_name="Отклонение (%)")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        verbose_name="Статус"
    )
    detailed_results = models.JSONField(verbose_name="Детальные результаты")

    class Meta:
        verbose_name = "Результат"
        verbose_name_plural = "Результаты"

    def __str__(self):
        return f"Результат эксперимента #{self.experiment.id}"
    

class Protocols(models.Model):
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
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата генерации")
    protocol_path = models.CharField(max_length=255, verbose_name="Путь к протоколу")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Статус"
    )

    class Meta:
        verbose_name = "Протокол"
        verbose_name_plural = "Протоколы"

    def __str__(self):
        return f"Протокол #{self.id} ({self.get_status_display()})"
    

class Calculations(models.Model):
    experiment = models.ForeignKey(
        Experiments,
        on_delete=models.CASCADE,
        related_name='calculations',
        verbose_name="Эксперимент"
    )
    step_number = models.IntegerField(verbose_name="Номер шага")
    description = models.TextField(verbose_name="Описание")
    formula_used = models.TextField(verbose_name="Использованная формула", blank=True)
    input_data = models.JSONField(verbose_name="Входные данные")
    output_data = models.JSONField(verbose_name="Выходные данные")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время выполнения")

    class Meta:
        verbose_name = "Расчёт"
        verbose_name_plural = "Расчёты"
        ordering = ['step_number']

    def __str__(self):
        return f"Шаг #{self.step_number} (Эксперимент {self.experiment.id})"
    
