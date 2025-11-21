from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Clinic, CustomUser, DoctorProfile, PatientProfile, LegalDocument, UserConsent

# 1. Configuração da Clínica (Tenant)
@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'is_active', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_active',)

# 2. Configuração do Usuário Customizado
# Precisamos herdar de UserAdmin para manter a gestão segura de senhas
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'clinic', 'is_staff')
    list_filter = ('role', 'clinic', 'is_staff', 'is_active')
    
    # Adicionamos nossos campos customizados na edição do usuário
    fieldsets = UserAdmin.fieldsets + (
        ('SaaS Info', {'fields': ('clinic', 'role', 'is_verified')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('SaaS Info', {'fields': ('clinic', 'role', 'is_verified')}),
    )

# 3. Perfis e Documentos
@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('get_doctor_name', 'crm', 'specialty')
    search_fields = ('user__username', 'crm')

    def get_doctor_name(self, obj):
        return obj.user.get_full_name()
    get_doctor_name.short_description = 'Médico'

@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'clinic', 'cpf', 'phone')
    list_filter = ('clinic',)
    search_fields = ('full_name', 'cpf')

@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_type', 'version', 'is_active', 'updated_at')
    list_filter = ('doc_type', 'is_active')

@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    list_display = ('user', 'document', 'agreed_at', 'ip_address')
    readonly_fields = ('ip_address', 'user_agent', 'agreed_at') # Auditoria não pode ser editada