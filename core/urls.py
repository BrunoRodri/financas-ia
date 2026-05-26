from django.urls import path

from core import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Transactions
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:pk>/toggle/', views.transaction_toggle, name='transaction_toggle'),
    path('transactions/<int:pk>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),

    # Recurring Rules
    path('recurring/', views.recurring_list, name='recurring_list'),
    path('recurring/create/', views.recurring_create, name='recurring_create'),
    path('recurring/<int:pk>/toggle/', views.recurring_toggle, name='recurring_toggle'),
    path('recurring/<int:pk>/delete/', views.recurring_delete, name='recurring_delete'),
    path('recurring/<int:pk>/delete/confirm/', views.recurring_delete_confirm, name='recurring_delete_confirm'),

    # Goals
    path('goals/', views.goal_list, name='goal_list'),
    path('goals/create/', views.goal_create, name='goal_create'),
    path('goals/<int:pk>/update/', views.goal_update, name='goal_update'),
    path('goals/<int:pk>/delete/', views.goal_delete, name='goal_delete'),

    # Credit Cards
    path('cards/', views.card_list, name='card_list'),
    path('cards/create/', views.card_create, name='card_create'),
    path('cards/<int:pk>/delete/', views.card_delete, name='card_delete'),
    path('cards/<int:pk>/edit/', views.card_edit, name='card_edit'),

    # Settings
    path('settings/', views.settings_view, name='settings'),
]
