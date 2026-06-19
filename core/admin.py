from django.contrib import admin

from core.models import CreditCard, Goal, RecurringRule, Tag, Transaction, UserSettings


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color']
    search_fields = ['name']


@admin.register(CreditCard)
class CreditCardAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'last_digits', 'due_day', 'closing_day']
    list_filter = ['brand']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'type', 'due_date', 'status', 'credit_card']
    list_filter = ['type', 'status', 'credit_card', 'tags', 'user']
    search_fields = ['description']
    date_hierarchy = 'due_date'
    filter_horizontal = ['tags']


@admin.register(RecurringRule)
class RecurringRuleAdmin(admin.ModelAdmin):
    list_display = [
        'description', 'amount', 'type', 'recurrence_type',
        'total_installments', 'is_active', 'credit_card',
    ]
    list_filter = ['type', 'recurrence_type', 'is_active', 'credit_card']
    search_fields = ['description']
    filter_horizontal = ['tags']


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ['name', 'target_amount', 'current_amount', 'deadline', 'progress_percent']
    search_fields = ['name']


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ['current_balance', 'balance_date']

    def has_add_permission(self, request):
        # Singleton: só permite 1 registro
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)
