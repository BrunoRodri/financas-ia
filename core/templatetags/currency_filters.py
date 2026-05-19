"""Filtros de template para formatação de moeda BRL."""

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def brl(value):
    """Formata um valor decimal como moeda brasileira: R$ 1.234,56"""
    if value is None:
        return 'R$ 0,00'
    try:
        value = Decimal(str(value))
    except Exception:
        return str(value)

    negative = value < 0
    value = abs(value)

    # Formata com separador de milhar (.) e decimal (,)
    int_part = int(value)
    dec_part = int(round((value - int_part) * 100))

    int_str = f'{int_part:,}'.replace(',', '.')
    formatted = f'R$ {int_str},{dec_part:02d}'

    if negative:
        formatted = f'-{formatted}'

    return formatted


@register.filter
def signed_brl(value):
    """Formata com sinal explícito: +R$ 500,00 ou -R$ 200,00"""
    if value is None:
        return 'R$ 0,00'
    try:
        value = Decimal(str(value))
    except Exception:
        return str(value)

    sign = '+' if value >= 0 else '-'
    abs_value = abs(value)

    int_part = int(abs_value)
    dec_part = int(round((abs_value - int_part) * 100))

    int_str = f'{int_part:,}'.replace(',', '.')

    return f'{sign}R$ {int_str},{dec_part:02d}'


@register.filter
def percentage(value):
    """Formata como percentual: 75.5 -> 75,5%"""
    if value is None:
        return '0%'
    try:
        return f'{float(value):.1f}%'.replace('.', ',')
    except (ValueError, TypeError):
        return '0%'
