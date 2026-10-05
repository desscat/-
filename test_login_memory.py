import copy
import json
import time
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from iread_core import AUTH_EXPIRED_MESSAGE, DEFAULT_TEMPLATE, fetch_data_via_api
from login_memory import LOGIN_MEMORY_SECONDS, normalize_saved_login


class BrowserMemory:
    def __init__(self):
        self.saved = None

    def __call__(self, action, login, **kwargs):
        result = {"loaded": True, "action": action, "login": None, "error": False, "status": "ok"}
        if action == "load":
            result["login"] = copy.deepcopy(self.saved)
        elif action == "save":
            self.saved = copy.deepcopy(login)
            result.update(status="saved", username=login["username"], expires_at=login["expires_at"])
        elif action == "clear":
            self.saved = None
        return result


class ConfigCloud:
    def __init__(self):
        self.config = {"class_rules": {"原班级": {"listen": 60, "anim": 15, "books": 2}}, "name_maps": {"原班级": "测试学生:Student"}}
        self.failed = False
        self.writes = []
        self.payload = None

    def table(self, *args):
        return self

    def select(self, *args):
        self.payload = None
        return self

    def eq(self, *args):
        return self

    def upsert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            self.writes.append(self.payload)
            return SimpleNamespace(data=[])
        if self.failed:
            raise ConnectionError("模拟云端读取失败")
        return SimpleNamespace(data=[{"config_json": json.dumps(self.config)}])


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
        self.assertTrue(any("✅ 本机已保存登录" in caption.value for caption in app.caption))
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

    def test_slow_browser_restore_survives_entering_same_phone_and_checking_remember(self):
        self.use_config_cloud()
        self.sign_in()
        saved = copy.deepcopy(self.browser.saved)
        ready = False

        def delayed_component(**kwargs):
            if kwargs["action"] == "load" and not ready:
                return None
            return self.browser(**kwargs)

        with patch("streamlit.components.v1.declare_component", return_value=delayed_component):
            app = self.app()
            app.text_input("input_username_widget").set_value("test-teacher").run()
            app.checkbox("remember_login").check().run()
            self.assertEqual(self.browser.saved, saved)
            ready = True
            app.run()
            self.assertEqual(app.session_state.token, saved["token"])
            self.assertTrue(app.session_state.login_authenticated)
            self.click(app, "⚡ 一键生成打卡报告")
            self.assertGreater(self.report.call_count, 0)
            self.assertEqual(self.login.call_count, 1)

            ready = False
            switched = self.app()
            switched.text_input("input_username_widget").set_value("another-teacher").run()
            switched.checkbox("remember_login").check().run()
            ready = True
            switched.run()
            self.assertEqual(switched.session_state.token, "")
            self.assertFalse(switched.session_state.login_authenticated)
            self.assertIsNone(self.browser.saved)

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

    def use_config_cloud(self):
        cloud = ConfigCloud()
        module = SimpleNamespace(create_client=lambda *args: cloud, Client=ConfigCloud)
        cloud_patch = patch.dict("sys.modules", {"supabase": module})
        cloud_patch.start()
        self.addCleanup(cloud_patch.stop)
        return cloud

    def test_remembered_login_restores_cloud_classes_and_name_mappings(self):
        cloud = self.use_config_cloud()
        self.sign_in()
        restored = self.app()
        self.assertEqual(restored.session_state.class_rules, cloud.config["class_rules"])
        self.assertEqual(restored.text_area("m_原班级").value, "测试学生:Student")
        restored.text_area("m_原班级").set_value("本地编辑:Local").run()
        self.click(restored, "🔄 重新加载云端配置")
        self.assertEqual(restored.text_area("m_原班级").value, "测试学生:Student")
        self.assertFalse(cloud.writes)

    def test_failed_cloud_load_cannot_overwrite_saved_mappings_and_can_retry(self):
        cloud = self.use_config_cloud()
        cloud.failed = True
        app = self.sign_in()
        self.click(app, "⚡ 一键生成打卡报告")
        self.click(app, "💾 手动保存当前配置到云端")
        self.assertFalse(cloud.writes)
        self.assertTrue(any("暂停保存" in warning.value for warning in app.warning))
        cloud.failed = False
        self.click(app, "🔄 重新加载云端配置")
        self.assertEqual(app.text_area("m_原班级").value, "测试学生:Student")
        self.click(app, "⚡ 一键生成打卡报告")
        self.assertEqual(json.loads(cloud.writes[-1]["config_json"])["name_maps"], cloud.config["name_maps"])

    def test_generation_does_not_auto_save_empty_configuration(self):
        cloud = self.use_config_cloud()
        cloud.config = {}
        app = self.sign_in()
        self.click(app, "⚡ 一键生成打卡报告")
        self.assertFalse(cloud.writes)


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
