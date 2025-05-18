from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    User, 
    Experiments, 
    EquipmentData, 
    Results, 
    Calculations
)


class EquipmentDataInline(admin.TabularInline):
    model = EquipmentData
    extra = 0
    fields = ('time_ms', 'microphone_signal', 'tube_position', 'voltage')
    readonly_fields = fields

class ResultsInline(admin.StackedInline):
    model = Results
    extra = 0
    fields = (
        'gamma_reference', 
        'status',
        'detailed_results'
    )
    readonly_fields = (
        'gamma_reference', 
        'status',
        'detailed_results'
    )

class CalculationsInline(admin.TabularInline):
    model = Calculations
    extra = 0
    fields = ('step_number', 'description', 'formula_used', 'input_data', 'output_data', 'timestamp')
    readonly_fields = ('timestamp',)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Настройки отображения в списке
    list_display = ('email', 'full_name', 'group_name', 'role', 'is_staff', 'is_active')
    list_display_links = ('email', 'full_name')
    list_filter = ('role', 'is_staff', 'is_active', 'group_name')
    search_fields = ('email', 'full_name', 'group_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)
    
    # Группировка полей в форме редактирования
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('full_name', 'group_name', 'role')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        # Убрали блок с date_joined, так как поле нередактируемое
    )
    
    # Добавляем date_joined только для чтения в форму изменения
    readonly_fields = ('date_joined', 'last_login')
    
    # Поля при создании пользователя
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 
                'full_name',
                'group_name',
                'role',
                'password1',
                'password2',
                'is_staff',
                'is_active'
            ),
        }),
    )
    
    # Дополнительные настройки
    actions = ['activate_users', 'deactivate_users']
    
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
    activate_users.short_description = _("Activate selected users")
    
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_users.short_description = _("Deactivate selected users")
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Дополнительные настройки формы если нужно
        return form
    
    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()

@admin.register(Experiments)
class ExperimentsAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'assistant',
        'status',
        'created_at',
        'completed_at',
        'temperature',
        'student_speed_stage1', 'student_gamma_stage1',
        'student_speed_stage2', 'student_gamma_stage2',
        'student_speed_stage3', 'student_gamma_stage3',
        'system_speed_stage1', 'system_gamma_stage1',
        'system_speed_stage2', 'system_gamma_stage2',
        'system_speed_stage3', 'system_gamma_stage3',
        'error_percent_speed_stage1', 'error_percent_gamma_stage1',
        'error_percent_speed_stage2', 'error_percent_gamma_stage2',
        'error_percent_speed_stage3', 'error_percent_gamma_stage3',
        'student_final_gamma', 
        'system_final_gamma', 
        'error_percent_final_gamma',
    )
    list_filter = ('status', 'user', 'assistant', 'created_at')
    search_fields = ('id', 'user__full_name', 'user__email', 'assistant__full_name')
    readonly_fields = (
        'created_at', 
        'completed_at',
        'system_final_gamma', 
        'error_percent_final_gamma',
    )
    fieldsets = (
        (None, {
            'fields': ('user', 'assistant', 'status', 'step')
        }),
        ('Параметры эксперимента', {
            'fields': ('temperature', 'tube_length', 'stages')
        }),
        ('Результаты студента (поэтапно)', {
            'fields': (
                'student_speed_stage1', 'student_gamma_stage1',
                'student_speed_stage2', 'student_gamma_stage2',
                'student_speed_stage3', 'student_gamma_stage3',
            )
        }),
        ('Расчетные системные значения и ошибки (поэтапно)', {
            'fields': (
                'system_speed_stage1', 'system_gamma_stage1',
                'system_speed_stage2', 'system_gamma_stage2',
                'system_speed_stage3', 'system_gamma_stage3',
                'error_percent_speed_stage1', 'error_percent_gamma_stage1',
                'error_percent_speed_stage2', 'error_percent_gamma_stage2',
                'error_percent_speed_stage3', 'error_percent_gamma_stage3',
            )
        }),
        ('Финальные результаты Гамма', {
            'fields': (
                'student_final_gamma', 
                'system_final_gamma', 
                'error_percent_final_gamma',
            )
        }),
        ('Даты', {
            'fields': ('created_at', 'completed_at')
        }),
    )
    inlines = [EquipmentDataInline, ResultsInline, CalculationsInline]

@admin.register(EquipmentData)
class EquipmentDataAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'time_ms', 'microphone_signal', 'tube_position', 'voltage')
    list_filter = ('experiment',)
    search_fields = ('experiment__id',)
    list_per_page = 20

@admin.register(Results)
class ResultsAdmin(admin.ModelAdmin):
    list_display = (
        'experiment', 
        'gamma_reference', 
        'status'
    )
    list_filter = ('status',)
    search_fields = ('experiment__id',)
    readonly_fields = (
        'experiment', 
        'gamma_reference', 
        'status',
        'detailed_results' 
    )

@admin.register(Calculations)
class CalculationsAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'step_number', 'timestamp')
    list_filter = ('experiment', 'step_number')
    search_fields = ('experiment__id', 'description')
    date_hierarchy = 'timestamp'