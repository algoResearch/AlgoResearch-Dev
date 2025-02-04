from django.contrib import admin
from .models import MiniStep, MiniStepField, ProtocolMiniStepData, Organization

@admin.register(MiniStep)
class MiniStepAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'order', 'is_required')
    ordering = ('order',)
    list_filter = ('organization',)
    search_fields = ('name',)
    

class MiniStepFieldAdmin(admin.ModelAdmin):
    list_display = ('mini_step', 'label', 'field_type', 'required_display')  # Change 'required' to 'required_display'

    def required_display(self, obj):
        return obj.required  # Returns True/False
    required_display.boolean = True  # Tells Django it's a boolean field
    required_display.short_description = 'Required'

admin.site.register(MiniStepField, MiniStepFieldAdmin)
@admin.register(ProtocolMiniStepData)
class ProtocolMiniStepDataAdmin(admin.ModelAdmin):
    list_display = ('protocol', 'mini_step', 'field', 'value')
    list_filter = ('protocol', 'mini_step')

admin.site.register(Organization)
