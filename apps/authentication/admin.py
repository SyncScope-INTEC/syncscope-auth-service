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
    list_display = ['email', 'first_name', 'last_name', 'role', 'company', 'is_active', 'is_verified']
    list_filter = ['role', 'is_active', 'is_verified', 'is_staff', 'company', 'created_at']
    search_fields = ['email', 'first_name', 'last_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_login', 'date_joined']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'avatar_url')}),
        ('Company info', {'fields': ('company', 'role')}),
        ('GitHub info', {'fields': ('github_id',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')}),
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