import copy
import time
import unittest
from datetime import date
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from iread_core import AUTH_EXPIRED_MESSAGE, DEFAULT_TEMPLATE, fetch_data_via_api
from login_memory import LOGIN_MEMORY_SECONDS, normalize_saved_login


class BrowserMemory:
    def __init__(self):
        self.saved = None

    def __call__(self, action, login, **kwargs):
        result = {"loaded": True, "login": None, "error": False, "status": "ok"}
        if action == "load":
            result["login"] = copy.deepcopy(self.saved)
        elif action == "save":
            self.saved = copy.deepcopy(login)
        elif action == "clear":
            self.saved = None
        return result


class LoginFlowTests(unittest.TestCase):
    def setUp(self):
        self.browser = BrowserMemory()
        self.component_patch = patch("streamlit.components.v1.declare_component", return_value=self.browser)
        self.component_patch.start()
        self.addCleanup(self.component_patch.stop)
        self.login_patch = patch("iread_core.auto_login", return_value=("test-token", None))
        self.login = self.login_patch.start()
        self.addCleanup(self.login_patch.stop)
        self.report_patch = patch("iread_core.fetch_data_via_api", return_value=({"测试班": "测试报告"}, None))
        self.report = self.report_patch.start()
        self.addCleanup(self.report_patch.stop)

    def app(self):
        app = AppTest.from_file("app.py", default_timeout=15).run()
        self.assertFalse(app.exception)
        return app

    def click(self, app, label):
        next(button for button in app.button if button.label == label).click().run()
        self.assertFalse(app.exception)

    def sign_in(self, remember=True):
        app = self.app()
        app.text_input("input_username_widget").set_value("test-teacher").run()
        app.checkbox("remember_login").set_value(remember).run()
        app.text_input("login_password").set_value("test-password").run()
        self.click(app, "登录")
        return app

    def test_remembered_login_survives_a_new_session_without_password_or_relogin(self):
        app = self.sign_in()
        self.assertEqual(app.text_input("login_password").value, "")
        self.assertEqual(set(self.browser.saved), {"version", "username", "token", "expires_at"})
        self.assertEqual(self.login.call_count, 1)
        restored = self.app()
        self.assertEqual(restored.session_state.token, "test-token")
        self.assertEqual(restored.text_input("input_username_widget").value, "test-teacher")
        self.assertTrue(restored.checkbox("remember_login").value)
        self.click(restored, "⚡ 一键生成打卡报告")
        restored.run()
        self.assertEqual(self.login.call_count, 1)
        self.assertGreater(self.report.call_count, 0)

    def test_remember_is_opt_in_and_unchecking_forgets_future_sessions(self):
        self.sign_in(remember=False)
        self.assertIsNone(self.browser.saved)
        app = self.sign_in()
        app.checkbox("remember_login").uncheck().run()
        self.assertIsNone(self.browser.saved)
        self.assertEqual(app.session_state.token, "test-token")
        self.assertEqual(self.app().session_state.token, "")

    def test_switching_accounts_and_logout_clear_credentials_and_old_config(self):
        app = self.sign_in()
        app.session_state.class_rules = {"旧班级": {"listen": 1, "anim": 1, "books": 1}}
        app.text_input("input_username_widget").set_value("another-teacher").run()
        self.assertEqual(app.session_state.token, "")
        self.assertEqual(app.text_input("manual_token").value, "")
        self.assertEqual(app.session_state.class_rules, {})
        self.assertIsNone(self.browser.saved)
        app = self.sign_in()
        self.click(app, "退出登录 / 切换账号")
        self.assertEqual(app.session_state.username_key, "")
        self.assertEqual(app.session_state.token, "")
        self.assertIsNone(self.browser.saved)
        self.assertEqual(self.app().session_state.token, "")

    def test_expired_upstream_login_is_forgotten_but_network_error_keeps_login(self):
        app = self.sign_in()
        self.report.return_value = (None, "请求超时")
        self.click(app, "⚡ 一键生成打卡报告")
        self.assertEqual(app.session_state.token, "test-token")
        self.assertIsNotNone(self.browser.saved)
        self.report.return_value = (None, AUTH_EXPIRED_MESSAGE)
        self.click(app, "⚡ 一键生成打卡报告")
        self.assertEqual(app.session_state.token, "")
        self.assertEqual(app.text_input("manual_token").value, "")
        self.assertIsNone(self.browser.saved)
        self.assertTrue(any(AUTH_EXPIRED_MESSAGE in warning.value for warning in app.warning))

    def test_failed_login_is_not_saved_and_preserves_input(self):
        self.login.return_value = (None, "账号或密码错误")
        app = self.sign_in()
        self.assertEqual(app.session_state.token, "")
        self.assertEqual(app.text_input("login_password").value, "test-password")
        self.assertIsNone(self.browser.saved)

    def test_generation_requires_login_and_does_not_submit_password_implicitly(self):
        app = self.app()
        app.text_input("input_username_widget").set_value("test-teacher").run()
        app.checkbox("remember_login").check().run()
        app.text_input("login_password").set_value("test-password").run()
        self.click(app, "⚡ 一键生成打卡报告")
        self.assertEqual(self.login.call_count, 0)
        self.assertIsNone(self.browser.saved)
        self.assertTrue(any("点击“登录”" in warning.value for warning in app.warning))


class LoginBoundaryTests(unittest.TestCase):
    def test_stored_record_validation_and_password_exclusion(self):
        value = {"version": 1, "username": " teacher ", "token": " token ", "expires_at": 1001, "password": "never-save"}
        self.assertEqual(normalize_saved_login(value, now=1000), {"version": 1, "username": "teacher", "token": "token", "expires_at": 1001})
        for bad in (None, "broken", {}, {**value, "token": ""}, {**value, "token": "token\nheader"}, {**value, "expires_at": 1000}, {**value, "expires_at": True}, {**value, "expires_at": float("nan")}, {**value, "expires_at": 1000 + LOGIN_MEMORY_SECONDS + 301}):
            self.assertIsNone(normalize_saved_login(bad, now=1000))

    def test_auth_expiry_in_all_data_fetch_paths_and_network_failure(self):
        classes = Mock(status_code=200, json=lambda: {"data": [{"id": 1, "name": "测试班"}]})
        auth_error = Mock(status_code=401)
        kwargs = dict(auth_token="test-token", report_type="昨日汇报", start_date=date(2026, 10, 2), end_date=date(2026, 10, 2), class_rules_config={}, name_maps_config={}, default_rule={"listen": 1, "anim": 1, "books": 1}, template_str=DEFAULT_TEMPLATE)
        for responses, mode in (([auth_error], "traditional"), ([classes, auth_error], "traditional"), ([classes, auth_error], "matrix")):
            with patch("iread_core.requests.get", side_effect=responses):
                self.assertEqual(fetch_data_via_api(**kwargs, mode=mode), (None, AUTH_EXPIRED_MESSAGE))
        with patch("iread_core.requests.get", return_value=Mock(status_code=503)):
            _, error = fetch_data_via_api(**kwargs)
            self.assertNotEqual(error, AUTH_EXPIRED_MESSAGE)


if __name__ == "__main__":
    unittest.main()
