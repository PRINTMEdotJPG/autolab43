from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Users, 
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

@admin.register(Users)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'full_name', 'group_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'group_name')
    search_fields = ('email', 'full_name', 'group_name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Персональная информация', {'fields': ('full_name', 'group_name', 'role')}),
        ('Права доступа', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Важные даты', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'group_name', 'role', 'password1', 'password2'),
        }),
    )

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