from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

# Import your lock helpers / thresholds so tests don't duplicate constants
from dashboard.views.users.user_views import _PW_LOCK_1

User = get_user_model()


def _mk_user(**overrides):
    """
    Create a user while tolerating custom fields on your AUTH_USER_MODEL.
    We set only fields that actually exist to keep tests portable.
    """
    field_names = {f.name for f in User._meta.get_fields()}
    data = dict(
        username="alice",
        email="alice@example.com",
        password="testpass123",
        first_name="Alice",
        last_name="Tester",
    )
    data.update(overrides or {})

    # If your custom model has optional fields, you can prefill them here:
    # e.g., if "position_type" in field_names: data.setdefault("position_type", "researcher")
    # Keep this generic:
    create_kwargs = {k: v for k, v in data.items() if k in field_names and k != "password"}
    user = User.objects.create_user(**create_kwargs)
    user.set_password(data["password"])
    user.save()
    return user


@override_settings(DEBUG=True)  # dev-mode: send_email_token logs, not emails
class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _mk_user()
        # Keep a stable IP so lockout keys are consistent
        self.ip = "9.9.9.9"

    # -----------------------------
    # Login page UI / attempts_left
    # -----------------------------
    def test_user_login_first_load_hides_attempts_left(self):
        resp = self.client.get(reverse("login"), REMOTE_ADDR=self.ip)
        # View sets attempts_left = None on first load
        self.assertIn("attempts_left", resp.context)
        self.assertIsNone(resp.context["attempts_left"])

    def test_user_login_attempts_left_after_one_failure(self):
        # Fail once
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "wrong"},
            REMOTE_ADDR=self.ip,
            follow=True,
        )
        # Redirect back to GET with username prefilled
        self.assertEqual(resp.status_code, 200)
        # Now attempts_left should be shown (threshold minus 1)
        # _PW_LOCK_1 = (4, 60) -> 3 remaining after 1 failure
        self.assertIn("attempts_left", resp.context)
        self.assertEqual(resp.context["attempts_left"], max(0, _PW_LOCK_1[0] - 1))

    def test_user_login_lock_after_threshold(self):
        # Hit threshold for lock (4 bad attempts if _PW_LOCK_1 == (4, 60))
        for _ in range(_PW_LOCK_1[0]):
            self.client.post(
                reverse("login"),
                {"username": self.user.username, "password": "nope"},
                REMOTE_ADDR=self.ip,
            )
        # Next GET should show lockout
        resp = self.client.get(reverse("login"), REMOTE_ADDR=self.ip)
        self.assertIn("locked_for", resp.context)
        self.assertGreater(resp.context["locked_for"], 0)

    def test_admin_login_first_load_hides_attempts_left(self):
        resp = self.client.get(reverse("admin_login"), REMOTE_ADDR=self.ip)
        self.assertIn("attempts_left", resp.context)
        self.assertIsNone(resp.context["attempts_left"])

    # -----------------------------
    # Email 2FA (dev) end-to-end
    # -----------------------------
    def test_email_2fa_logged_not_exposed_and_verifies(self):
        # Step 1: Password login succeeds → redirected to select_2fa
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "testpass123"},
            REMOTE_ADDR=self.ip,
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("select_2fa_method"))

        # Step 2: Choose email 2FA → send_email_token (dev logs the code; no UI reveal)
        with self.assertLogs("dashboard.views.users.views_auth", level="INFO") as cm:
            resp = self.client.post(
                reverse("select_2fa_method"),
                {"method": "email"},
                REMOTE_ADDR=self.ip,
                follow=False,
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("verify_email_token"))

        # Ensure a dev log with the token was written (but nothing shown to user)
        # Example log line contains: "[DEV] 2FA EMAIL CODE for user ..."
        joined_logs = "\n".join(cm.output)
        self.assertIn("2FA EMAIL CODE", joined_logs)

        # Step 3: Pull the token from the EmailDevice and verify
        from django_otp.plugins.otp_email.models import EmailDevice

        device = EmailDevice.objects.get(user=self.user, name="default")
        token = getattr(device, "token", None)
        self.assertTrue(token, "EmailDevice didn't have a token set in dev mode")

        # Submit the code
        resp = self.client.post(
            reverse("verify_email_token"),
            {"code": token},
            REMOTE_ADDR=self.ip,
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)

        # Should land on normal user dashboard (not admin)
        self.assertEqual(resp["Location"], reverse("dashboard"))

        # And the user should now be authenticated in the session
        session = self.client.session
        self.assertEqual(str(self.user.pk), session.get("_auth_user_id"))
