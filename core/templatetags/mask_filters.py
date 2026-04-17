from django import template
from core.utils import mask_email, mask_phone

register = template.Library()

@register.filter(name='mask_pii_email')
def mask_pii_email_filter(value):
    return mask_email(value)

@register.filter(name='mask_pii_phone')
def mask_pii_phone_filter(value):
    return mask_phone(value)
