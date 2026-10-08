import unittest
from datetime import date
from unittest.mock import Mock, patch

from iread_core import DEFAULT_MATRIX_TEMPLATE, DEFAULT_RULE, DEFAULT_TEMPLATE, clean_num, duration_minutes, fetch_data_via_api


class ReportAccuracyTests(unittest.TestCase):
    def fetch(self, daily_rows, *, mode="matrix", rules=None, class_name="万达K12", start=date(2026, 10, 5), end=None):
        if end is None:
            end = date(2026, 10, 5 + len(daily_rows) - 1)
        classes = Mock(status_code=200, json=lambda: {"data": [{"id": 12, "name": class_name}]})
        responses = [classes] + [row if hasattr(row, "status_code") else Mock(status_code=200, json=lambda row=row: {"data": {"students": row}}) for row in daily_rows]
        details = []
        with patch("iread_core.requests.get", side_effect=responses) as requests:
            reports, error = fetch_data_via_api(
                "test-token", "周汇报", start, end, rules or {}, {}, DEFAULT_RULE,
                DEFAULT_MATRIX_TEMPLATE if mode == "matrix" else DEFAULT_TEMPLATE,
                mode=mode, emoji_config={"full": "🏆", "part": "🥇", "zero": "❌", "badge": "🎖️"}, diagnostics=details,
            )
        return reports, error, details, requests

    def student(self, **overrides):
        return {"id": 100, "name": "Ethan", "listen": 30, "animation": 10, "grading": 2, **overrides}

    def test_ethan_custom_goal_overrides_default_and_normalizes_class_name(self):
        rules = {" 万达Ｋ１２班 ": {"listen": 30, "anim": 10, "books": 2}}
        for mode in ("matrix", "traditional"):
            reports, error, details, _ = self.fetch([[self.student()]], mode=mode, rules=rules)
            self.assertIsNone(error)
            self.assertEqual(details[0]["判断"], "全部达标")
            self.assertEqual(details[0]["听音目标"], 30)
            self.assertIn("班级配置", details[0]["规则来源"])
            self.assertIn("Ethan", reports["万达K12"])
        reports, _, details, _ = self.fetch([[self.student()]], rules={"万达K1": rules[" 万达Ｋ１２班 "]})
        self.assertEqual(details[0]["判断"], "部分完成")
        self.assertIn("默认规则", reports["万达K12"])

    def test_missing_day_does_not_shift_later_icons(self):
        reports, error, details, request = self.fetch([[], [self.student(listen=60, animation=15)], [self.student(listen=1)]])
        self.assertIsNone(error)
        self.assertIn("❌🏆🥇  Ethan", reports["万达K12"])
        self.assertIn("10.05、10.06、10.07", reports["万达K12"])
        self.assertEqual([c.kwargs["params"]["start"] for c in request.call_args_list[1:]], ["2026-10-05", "2026-10-06", "2026-10-07"])

    def test_partial_every_day_is_not_full_attendance(self):
        reports, error, _, _ = self.fetch([[self.student()], [self.student()]])
        self.assertIsNone(error)
        self.assertIn("全勤达标：0 人", reports["万达K12"])
        self.assertIn("持续加油：1 人", reports["万达K12"])
        self.assertNotIn("Ethan 🎖️", reports["万达K12"])

    def test_zero_grading_is_not_replaced_by_extracurricular_reading(self):
        reports, error, details, _ = self.fetch([[self.student(listen=0, audio_time=90, animation=0, grading=0, read=9)]])
        self.assertIsNone(error)
        self.assertEqual(details[0]["听音分钟"], 0)
        self.assertEqual(details[0]["分级本数"], 0)
        self.assertEqual(details[0]["判断"], "未打卡")

    def test_duration_units_and_decimal_progress(self):
        self.assertEqual(duration_minutes("1小时30分钟"), 90)
        self.assertEqual(duration_minutes("3600秒"), 60)
        self.assertEqual(duration_minutes("60分钟"), 60)
        self.assertEqual(clean_num("0.5"), 0.5)
        reports, error, details, _ = self.fetch([[self.student(listen="3600秒", animation="15分钟")]])
        self.assertIsNone(error)
        self.assertEqual(details[0]["判断"], "全部达标")
        for bad in ("-1", "未知", "60/90", "nan"):
            with self.assertRaises(ValueError):
                clean_num(bad)

    def test_failed_or_unrecognized_api_data_never_publishes_partial_report(self):
        cases = [Mock(status_code=503), Mock(status_code=200, json=lambda: {"code": 401}), Mock(status_code=200, json=lambda: {"data": {"unexpected": []}})]
        for bad in cases:
            for mode in ("matrix", "traditional"):
                reports, error, _, _ = self.fetch([bad], mode=mode)
                self.assertIsNone(reports)
                self.assertTrue(error)
        incomplete = self.student()
        del incomplete["grading"]
        reports, error, _, _ = self.fetch([[incomplete]])
        self.assertIsNone(reports)
        self.assertIn("grading", error)

    def test_same_display_name_does_not_merge_different_students(self):
        reports, error, details, _ = self.fetch([[self.student(id=1, listen=60, animation=15), self.student(id=2)]])
        self.assertIsNone(error)
        self.assertEqual(len(details), 2)
        self.assertEqual(reports["万达K12"].count("  Ethan"), 2)

    def test_traditional_total_target_and_invalid_dates(self):
        reports, error, details, _ = self.fetch([[self.student(listen=120, animation=30, grading=4)]], mode="traditional", end=date(2026, 10, 6))
        self.assertIsNone(error)
        self.assertEqual(details[0]["听音目标"], 120)
        self.assertEqual(details[0]["判断"], "全部达标")
        reports, error, _, requests = self.fetch([[]], end=date(2026, 10, 4))
        self.assertIsNone(reports)
        self.assertIn("日期", error)
        requests.assert_not_called()

    def test_app_displays_verification_details(self):
        import sys
        from types import SimpleNamespace
        from streamlit.testing.v1 import AppTest
        from test_login_memory import BrowserMemory, ConfigCloud

        cloud = ConfigCloud()
        module = SimpleNamespace(create_client=lambda *args: cloud, Client=ConfigCloud)
        classes = Mock(status_code=200, json=lambda: {"data": [{"id": 12, "name": "万达K12"}]})
        stats = Mock(status_code=200, json=lambda: {"data": {"students": [self.student(listen=60, animation=15)]}})
        def response(url, **kwargs):
            return classes if "/teacher/classes/" in url else stats

        with patch.dict(sys.modules, {"supabase": module}), patch("streamlit.components.v1.declare_component", return_value=BrowserMemory()), patch("iread_core.requests.get", side_effect=response), patch("iread_core.fetch_data_via_api", wraps=fetch_data_via_api) as fetch:
            app = AppTest.from_file("app.py", default_timeout=15).run()
            app.text_input("input_username_widget").set_value("test-teacher").run()
            app.text_input("manual_token").set_value("test-token").run()
            next(button for button in app.button if button.label == "⚡ 一键生成打卡报告").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe), 1)
            self.assertEqual(app.dataframe[0].value.iloc[0]["学生"], "Ethan")
            self.assertEqual(app.dataframe[0].value.iloc[0]["判断"], "全部达标")



if __name__ == "__main__":
    unittest.main()
