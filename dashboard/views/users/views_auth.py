# dashboard/views/users/views_auth.py
from django.urls import reverse
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django import forms

from django.contrib.auth import get_user_model, login, authenticate
from django.conf import settings

from django_otp import login as otp_login
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

import logging

# --- Import shared lockout helpers / thresholds from user_views ---
from dashboard.views.users.user_views import (
    _seconds_left, _register_failure, _clear_failures,
    _PW_LOCK_1, _PW_LOCK_2, _fail_count
)

logger = logging.getLogger("dashboard.views.users.views_auth")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _ident_from_request(request) -> str:
    """
    Username|IP identifier. Kept for compatibility in case you still need it
    elsewhere, but for PASSWORD lockouts we now use _ip_ident(...) only.
    """
    uname = (request.POST.get('username') or request.GET.get('username') or '').strip().lower()
    ip = request.META.get('REMOTE_ADDR', '')
    return f"{uname}|{ip}" if uname else (ip or 'unknown')


def _ip_ident(request) -> str:
    """IP-only identifier for password lockouts (stable across POST/GET)."""
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _user_has_totp(user) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def _next_url(request):
    return request.GET.get('next') or request.POST.get('next') or 'home'


def _should_log_2fa_token() -> bool:
    """
    True when it's safe to echo the token to logs/terminal during dev/test:
    - DEBUG on, or
    - using console/locmem email backends.
    """
    backend = getattr(settings, "EMAIL_BACKEND", "")
    return (
        settings.DEBUG
        or "console.EmailBackend" in backend
        or "locmem.EmailBackend" in backend
    )


User = get_user_model()

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


# -------------------------------------------------------------------
# Forms
# -------------------------------------------------------------------

class Choose2FAForm(forms.Form):
    method = forms.ChoiceField(
        choices=(('email', 'Email code'), ('totp', 'Authenticator app')),
        widget=forms.RadioSelect
    )

class TOTPForm(forms.Form):
    token = forms.CharField(max_length=6, strip=True)


# -------------------------------------------------------------------
# Lockout-aware LoginView
# -------------------------------------------------------------------

class LockoutMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            ident = _ip_ident(request)  # IP-only for password lockout
            wait = _seconds_left('pw', ident)
            if wait:
                username = (request.POST.get('username') or '').strip()
                return redirect(f"{request.path}?username={username}")
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        ident = _ip_ident(self.request)  # IP-only for password lockout
        _register_failure('pw', ident, thresholds=(_PW_LOCK_1, _PW_LOCK_2))
        messages.error(self.request, "Invalid username or password.")
        username = (self.request.POST.get('username') or '').strip()
        return redirect(f"{self.request.path}?username={username}")


class RoleAwareLoginView(LockoutMixin, LoginView):
    template_name = 'auth/login.html'

    def get_success_url(self):
        # Always go to 2FA selection after a valid password
        return reverse('select_2fa_method')

    def form_valid(self, form):
        # Clear any password-failure counters for this IP
        ident = _ip_ident(self.request)
        _clear_failures('pw', ident)

        user = form.get_user()
        
        # Log remember_me status
        logger.info(f"User {user.username} (ID: {user.id}) authenticated successfully.")
        logger.info(f"remember_me value: {getattr(user, 'remember_me', False)}")
        
        # Gate IT admins to the admin portal
        if getattr(user, 'position_type', None) == 'it_admin':
            messages.error(self.request, "IT Admins must log in through the Admin portal.")
            return redirect('admin_login')

        # Check remember_me flag - if True, skip 2FA entirely
        if getattr(user, 'remember_me', False):
            logger.info(f"User {user.username} has remember_me enabled, skipping 2FA")
            # Log the user in directly
            login(self.request, user)
            # Determine where to redirect based on admin flag
            is_admin = bool(
                self.request.POST.get('admin') == 'true' or self.request.GET.get('admin') == 'true'
            )
            if is_admin:
                if user.is_superuser or user.role in ['product_support', 'sales_rep', 'customer_success', 'implementation_rep']:
                    return redirect('it_admin_dashboard')
                elif getattr(user, 'position_type', None) == 'agency_user' and getattr(user, 'agency', None):
                    return redirect('agency_dashboard')
                elif hasattr(user, 'organization') and user.organization:
                    return redirect('admin_dashboard', org_id=user.organization.id)
                return redirect('login')
            return redirect('dashboard')

        # 2FA handoff (do NOT call super().form_valid)
        self.request.session['pre_2fa_authenticated'] = True
        self.request.session['2fa_user_id'] = user.id
        self.request.session['2fa_admin'] = bool(
            self.request.POST.get('admin') == 'true' or self.request.GET.get('admin') == 'true'
        )
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ident = _ip_ident(self.request)  # IP-only for consistent UX
        locked_for = _seconds_left('pw', ident)
        fails = _fail_count('pw', ident)

        # Only show attempts_left after at least one failure, or 0 if locked
        attempts_left = 0 if locked_for else (max(0, _PW_LOCK_1[0] - fails) if fails > 0 else None)

        ctx['locked_for'] = locked_for
        ctx['attempts_left'] = attempts_left
        return ctx


def select_2fa_method(request):
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    has_totp = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    if request.method == 'POST':
        form = Choose2FAForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data['method']

            if method == 'email':
                # set session + log, then actually send and return its redirect to /verify/
                request.session['2fa_method'] = 'email'
                logger.info("User %s selected email 2FA method.", user.id)
                return send_email_token(request)

            request.session['2fa_method'] = method

            if has_totp:
                return redirect('totp_challenge')

            # need org_id to direct to setup if TOTP not configured
            org_id = getattr(getattr(user, 'organization', None), 'id', None)
            if not org_id:
                messages.info(request, "Authenticator isn’t set up yet—using email this time.")
                return send_email_token(request)  # also send + redirect to verify
            return redirect('totp_setup', org_id=org_id)
    else:
        form = Choose2FAForm(initial={'method': 'email'})

    return render(request, 'auth/select_2fa.html', {
        'form': form, 'has_totp': has_totp, 'next': _next_url(request),
    })


def send_email_token(request):
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    # Create/get a device and ensure it points somewhere sensible
    device, _ = EmailDevice.objects.get_or_create(
        user=user, name='default', defaults={'confirmed': True},
    )
    if not device.confirmed:
        device.confirmed = True
        device.save(update_fields=['confirmed'])

    # Prefer the device email; fall back to user's email
    if not getattr(device, 'email', None):
        device.email = getattr(user, 'email', '') or ''
        device.save(update_fields=['email'])

    # Always (re)generate a fresh token for this attempt
    device.generate_token()
    device.save()

    # Always emit a neutral INFO log so tests can assert on it (no token here)
    logger.info("Generated 2FA email token for user %s", user.id)

    try:
        if _should_log_2fa_token():
            # DEV/console/locmem: log and print the actual token to terminal
            token = getattr(device, "token", None)
            logger.info(
                "2FA EMAIL CODE (dev/test) for user %s (%s): %s",
                user.id, device.email or user.email or "no-email", token
            )
            print(f"[DEV] 2FA EMAIL CODE for user {user.id} ({device.email or user.email}): {token}")
        else:
            # PROD: send the actual email
            if not device.email:
                messages.error(request, "No email address is configured for your account.")
                return redirect('select_2fa_method')

            # If you set OTP_EMAIL_SENDER/DEFAULT_FROM_EMAIL, django-otp will use it
            device.send_token()
            messages.success(request, "We emailed you a 6-digit code.")
    except Exception:
        logger.exception("2FA email send/log failed")
        messages.error(request, "Could not send verification code. Please try again.")
        return redirect('select_2fa_method')

    request.session['email_device_id'] = device.id
    return redirect('verify_email_token')


def _post_2fa_redirect(request, user):
    """Preserve your admin vs. user routing after successful 2FA."""
    if request.session.get('2fa_admin', False):
        if user.is_superuser or getattr(user, 'role', None) in ['product_support','sales_rep','customer_success','implementation_rep']:
            return reverse('it_admin_dashboard')
        elif getattr(user, 'position_type', None) == 'agency_user' and getattr(user, 'agency', None):
            return reverse('agency_dashboard')
        elif hasattr(user, 'organization') and user.organization:
            return reverse('admin_dashboard', kwargs={'org_id': user.organization.id})
        return reverse('login')
    return reverse('dashboard')


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
            login(request, user)          # authenticate user
            otp_login(request, device)    # mark OTP verified
            for k in ('email_device_id','pre_2fa_authenticated','2fa_user_id','2fa_admin','2fa_method'):
                request.session.pop(k, None)
            messages.success(request, "Two-factor authentication complete.")
            return redirect(_post_2fa_redirect(request, user))

        # invalid → increment 2FA failure count
        _, locked = _register_failure('2fa', ident, thresholds=((4,60),(6,300)))
        messages.error(
            request,
            f"Too many invalid codes. Locked for {locked} seconds." if locked else "Invalid code. Please try again."
        )

    return render(request, 'auth/verify_2fa.html')


def totp_challenge(request):
    user, redir = _ensure_pre_2fa(request)
    if redir:
        return redir

    if not TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        org_id = getattr(getattr(user, 'organization', None), 'id', None)
        if not org_id:
            messages.error(request, "No organization is associated with your account.")
            return redirect('select_2fa_method')
        return redirect('totp_setup', org_id=org_id)

    ident = str(user.id)  # 2FA lockouts are per-user
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
                    login(request, user)       # authenticate user
                    otp_login(request, device) # mark OTP verified
                    for k in ('pre_2fa_authenticated','2fa_user_id','2fa_admin','2fa_method'):
                        request.session.pop(k, None)
                    messages.success(request, "Two-factor authentication complete.")
                    return redirect(_post_2fa_redirect(request, user))

            # invalid → increment 2FA failure count
            _, locked = _register_failure('2fa', ident, thresholds=((4,60),(6,300)))
            messages.error(
                request,
                f"Too many invalid codes. Locked for {locked} seconds." if locked else "Invalid authenticator code. Please try again."
            )
    else:
        form = TOTPForm()

    return render(request, 'auth/totp_challenge.html', {'form': form, 'next': _next_url(request)})