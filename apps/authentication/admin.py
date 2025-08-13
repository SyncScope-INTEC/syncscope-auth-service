from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Company, UserSession


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'domain']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'company', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff', 'company', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name']
    readonly_fields = ['id', 'date_joined', 'updated_at', 'last_login']
    ordering = ['-date_joined']
    
    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'timezone')}),
        ('Company info', {'fields': ('company', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'role', 'company'),
        }),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'created_at', 'expires_at', 'last_used', 'ip_address']
    list_filter = ['is_active', 'created_at', 'expires_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'ip_address']
    readonly_fields = ['id', 'token_hash', 'created_at', 'last_used']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('id', 'user', 'is_active')}),
        ('Session info', {'fields': ('token_hash', 'user_agent', 'ip_address')}),
        ('Timestamps', {'fields': ('created_at', 'expires_at', 'last_used')}),
    )
    
    actions = ['deactivate_sessions']
    
    def deactivate_sessions(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f'{queryset.count()} sessions deactivated.')
    deactivate_sessions.short_description = "Deactivate selected sessions"