# dashboard/views/users/views_auth_2fa.py
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login as dj_login, authenticate
from django.conf import settings
from django import forms

from django_otp import login as otp_login
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

import logging
USE_2FA = getattr(settings, "USE_TWO_FACTOR", False)
from dashboard.views.users.user_views import (
    _seconds_left, _register_failure, _clear_failures,
)

logger = logging.getLogger("dashboard.views.users.views_auth_2fa")
User = get_user_model()

# ----- local helpers (avoid importing OTP in the non-2FA module) -----

def _next_url(request):
    return request.GET.get('next') or request.POST.get('next') or 'home'

def _should_log_2fa_token() -> bool:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    return (
        settings.DEBUG
        or "console.EmailBackend" in backend
        or "locmem.EmailBackend" in backend
    )

def _post_login_redirect(request, user):
    """
    Same routing as non-2FA version, but defined here too to avoid circular imports.
    """
    if request.session.get('2fa_admin', False):
        if user.is_superuser or getattr(user, 'role', None) in ['product_support','sales_rep','customer_success','implementation_rep']:
            return reverse('it_admin_dashboard')
        elif getattr(user, 'position_type', None) == 'agency_user' and getattr(user, 'agency', None):
            return reverse('agency_dashboard')
        elif hasattr(user, 'organization') and user.organization:
            return reverse('admin_dashboard', kwargs={'org_id': user.organization.id})
        return reverse('login')
    return reverse('dashboard')

def _ensure_pre_2fa(request):
    if not request.session.get('pre_2fa_authenticated') or not request.session.get('2fa_user_id'):
        return None, redirect('admin_login' if request.session.get('2fa_admin') else 'login')
    try:
        user = User.objects.get(id=request.session['2fa_user_id'])
    except User.DoesNotExist:
        for k in ('pre_2fa_authenticated','2fa_user_id','2fa_admin','2fa_method','email_device_id'):
            request.session.pop(k, None)
        messages.error(request, "Your session expired. Please log in again.")
        return None, redirect('admin_login' if request.session.get('2fa_admin') else 'login')
    return user, None

# ----- forms (duplicated here so this file is self-contained) -----

class Choose2FAForm(forms.Form):
    method = forms.ChoiceField(
        choices=(('email', 'Email code'), ('totp', 'Authenticator app')),
        widget=forms.RadioSelect
    )

class TOTPForm(forms.Form):
    token = forms.CharField(max_length=6, strip=True)

# ----- views (2FA only) -----

def select_2fa_method(request):
    if not USE_2FA:
        return redirect('dashboard')
    # Guard: if someone hits this when 2FA is off, send them home.
    if not getattr(settings, "USE_TWO_FACTOR", False):
        messages.info(request, "Two-factor authentication is disabled.")
        return redirect('dashboard')

    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    has_totp = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    if request.method == 'POST':
        form = Choose2FAForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data['method']

            if method == 'email':
                request.session['2fa_method'] = 'email'
                logger.info("User %s selected email 2FA method.", user.id)
                return send_email_token(request)

            request.session['2fa_method'] = method

            if has_totp:
                return redirect('totp_challenge')

            org_id = getattr(getattr(user, 'organization', None), 'id', None)
            if not org_id:
                messages.info(request, "Authenticator isn’t set up yet—using email this time.")
                return send_email_token(request)
            return redirect('totp_setup', org_id=org_id)
    else:
        form = Choose2FAForm(initial={'method': 'email'})

    return render(request, 'auth/select_2fa.html', {
        'form': form, 'has_totp': has_totp, 'next': _next_url(request),
    })

def send_email_token(request):
    if not USE_2FA or not EmailDevice:
        return redirect('dashboard')
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    device, _ = EmailDevice.objects.get_or_create(
        user=user, name='default', defaults={'confirmed': True},
    )
    if not device.confirmed:
        device.confirmed = True
        device.save(update_fields=['confirmed'])

    if not getattr(device, 'email', None):
        device.email = getattr(user, 'email', '') or ''
        device.save(update_fields=['email'])

    device.generate_token()
    device.save()

    logger.info("Generated 2FA email token for user %s", user.id)

    try:
        if _should_log_2fa_token():
            token = getattr(device, "token", None)
            logger.info(
                "2FA EMAIL CODE (dev/test) for user %s (%s): %s",
                user.id, device.email or user.email or "no-email", token
            )
            print(f"[DEV] 2FA EMAIL CODE for user {user.id} ({device.email or user.email}): {token}")
        else:
            if not device.email:
                messages.error(request, "No email address is configured for your account.")
                return redirect('select_2fa_method')
            device.send_token()
            messages.success(request, "We emailed you a 6-digit code.")
    except Exception:
        logger.exception("2FA email send/log failed")
        messages.error(request, "Could not send verification code. Please try again.")
        return redirect('select_2fa_method')

    request.session['email_device_id'] = device.id
    return redirect('verify_email_token')

def verify_email_token(request):
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    ident = str(user.id)  # 2FA lockouts are per-user
    if request.method == 'POST':
        wait = _seconds_left('2fa', ident)
        if wait:
            messages.error(request, f"Too many invalid codes. Try again in {wait} seconds.")
            return render(request, 'auth/verify_2fa.html')

        code = (request.POST.get('code') or '').strip()
        dev_id = request.session.get('email_device_id')
        if not dev_id:
            messages.error(request, "Session expired. Please resend the code.")
            return redirect('send_email_token')

        try:
            device = EmailDevice.objects.get(id=dev_id, user=user)
        except EmailDevice.DoesNotExist:
            messages.error(request, "Invalid device. Please resend the code.")
            return redirect('send_email_token')

        if device.verify_token(code):
            _clear_failures('2fa', ident)
            dj_login(request, user)
            otp_login(request, device)

            target = _post_login_redirect(request, user)
            for k in ('email_device_id','pre_2fa_authenticated','2fa_user_id','2fa_admin','2fa_method'):
                request.session.pop(k, None)

            messages.success(request, "Two-factor authentication complete.")
            return redirect(target)

        _, locked = _register_failure('2fa', ident, thresholds=((4,60),(6,300)))
        messages.error(
            request,
            f"Too many invalid codes. Locked for {locked} seconds." if locked else "Invalid code. Please try again."
        )

    return render(request, 'auth/verify_2fa.html')

def totp_challenge(request):
    if not USE_2FA or not TOTPDevice:
        return redirect('dashboard')
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    if not TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        org_id = getattr(getattr(user, 'organization', None), 'id', None)
        if not org_id:
            messages.error(request, "No organization is associated with your account.")
            return redirect('select_2fa_method')
        return redirect('totp_setup', org_id=org_id)

    ident = str(user.id)
    if request.method == 'POST':
        wait = _seconds_left('2fa', ident)
        if wait:
            messages.error(request, f"Too many invalid codes. Try again in {wait} seconds.")
            return render(request, 'auth/totp_challenge.html', {'form': TOTPForm(), 'next': _next_url(request)})

        form = TOTPForm(request.POST)
        if form.is_valid():
            token = ''.join(ch for ch in form.cleaned_data['token'] if ch.isdigit())[:6]
            for device in TOTPDevice.objects.filter(user=user, confirmed=True):
                if token and device.verify_token(token):
                    _clear_failures('2fa', ident)
                    dj_login(request, user)
                    otp_login(request, device)

                    target = _post_login_redirect(request, user)
                    for k in ('pre_2fa_authenticated','2fa_user_id','2fa_admin','2fa_method'):
                        request.session.pop(k, None)

                    messages.success(request, "Two-factor authentication complete.")
                    return redirect(target)

            _, locked = _register_failure('2fa', ident, thresholds=((4,60),(6,300)))
            messages.error(
                request,
                f"Too many invalid codes. Locked for {locked} seconds." if locked else "Invalid authenticator code. Please try again."
            )
    else:
        form = TOTPForm()

    return render(request, 'auth/totp_challenge.html', {'form': form, 'next': _next_url(request)})
