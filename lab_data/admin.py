from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    User, 
    Experiments, 
    EquipmentData, 
    Results, 
    Protocols, 
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
        'gamma_calculated', 
        'gamma_reference', 
        'error_percent', 
        'status',
        'detailed_results'
    )
    readonly_fields = fields

class ProtocolsInline(admin.TabularInline):
    model = Protocols
    extra = 0
    fields = ('generated_at', 'protocol_path', 'status')
    readonly_fields = ('generated_at',)

class CalculationsInline(admin.TabularInline):
    model = Calculations
    extra = 0
    fields = ('step_number', 'description', 'formula_used', 'timestamp')
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
    list_display = ('id', 'user', 'date', 'temperature', 'tube_length')
    list_filter = ('user', 'date')
    search_fields = ('user__email', 'user__full_name')
    date_hierarchy = 'date'
    inlines = [EquipmentDataInline, ResultsInline, ProtocolsInline, CalculationsInline]

@admin.register(EquipmentData)
class EquipmentDataAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'time_ms', 'microphone_signal', 'tube_position', 'voltage')
    list_filter = ('experiment',)
    search_fields = ('experiment__id',)
    list_per_page = 20

@admin.register(Results)
class ResultsAdmin(admin.ModelAdmin):
    list_display = ('experiment', 'gamma_calculated', 'gamma_reference', 'error_percent', 'status')
    list_filter = ('status',)
    search_fields = ('experiment__id',)
    readonly_fields = ('experiment',)

@admin.register(Protocols)
class ProtocolsAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'generated_at', 'status', 'protocol_path')
    list_filter = ('status', 'generated_at')
    search_fields = ('experiment__id',)
    date_hierarchy = 'generated_at'

@admin.register(Calculations)
class CalculationsAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'step_number', 'timestamp')
    list_filter = ('experiment', 'step_number')
    search_fields = ('experiment__id', 'description')
    date_hierarchy = 'timestamp'