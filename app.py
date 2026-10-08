import json
import time
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, datetime, timedelta, timezone
from emoji_presets import (
    DEFAULT_EMOJIS,
    EMOJI_KEYS,
    export_emoji_presets,
    import_emoji_presets,
    normalize_custom_emoji_presets,
    normalize_emoji_config,
    validate_emoji_config,
)
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE, AUTH_EXPIRED_MESSAGE, DEFAULT_RULE, class_config
from login_memory import LOGIN_MEMORY_SECONDS, normalize_saved_login

# 尝试引入 Supabase 云端数据库客户端
try:
    from supabase import create_client, Client
    SUPABASE_URL = "https://sxjdncrkkjcnkyozmbzo.supabase.co"
    # ⚠️ 请确保这里使用的是 Supabase 项目设置中的 anon_key（以 eyJhbG 开头的长字符串）
    SUPABASE_KEY = "sb_publishable_PM_84SFDUCbhpiQLJjYT5w_cMziV-vt"
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    has_supabase = True
except Exception:
    has_supabase = False

# 🛑 核心清理：如果 URL 带有任何多余参数，强行在第一次加载时清空它
if len(st.query_params) > 0:
    st.query_params.clear()
    st.rerun()

if "btn_clicked" not in st.session_state:
    st.session_state.btn_clicked = False

sidebar_state = "collapsed" if st.session_state.btn_clicked and st.session_state.get("token") else "expanded"

st.set_page_config(
    page_title="全阅读学情打卡生成器", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state=sidebar_state
)

st.title("⚡ 全阅读学情打卡生成器")

EMOJI_PRESETS = {
    "自定义": None,
    "🍓 水果派对": {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"},
    "🌟 星光闪耀": {"full": "⭐", "part": "✨", "zero": "⚪", "badge": "👑"},
    "🚀 太空探索": {"full": "🚀", "part": "🛸", "zero": "🌑", "badge": "🌌"},
    "🏆 勋章荣誉": {"full": "🏆", "part": "🥇", "zero": "❌", "badge": "🎖️"}
}

CHINA_TZ = timezone(timedelta(hours=8))

# 🛡️ 状态初始化
if "username_key" not in st.session_state:
    st.session_state.username_key = ""
if "token" not in st.session_state:
    st.session_state.token = ""
if "class_rules" not in st.session_state:
    st.session_state.class_rules = {}
if "name_maps" not in st.session_state:
    st.session_state.name_maps = {}
if "custom_template" not in st.session_state:
    st.session_state.custom_template = DEFAULT_TEMPLATE
if "matrix_template" not in st.session_state:
    st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
if "emojis" not in st.session_state:
    st.session_state.emojis = DEFAULT_EMOJIS.copy()
if "emoji_presets" not in st.session_state:
    st.session_state.emoji_presets = {}
if "emoji_preset_select" not in st.session_state:
    st.session_state.emoji_preset_select = "🏆 勋章荣誉"
if "emoji_input_scope" not in st.session_state:
    st.session_state.emoji_input_scope = 0
if "emoji_config_valid" not in st.session_state:
    st.session_state.emoji_config_valid = True
if "cloud_sync_status" not in st.session_state:
    st.session_state.cloud_sync_status = {"state": "idle", "message": "尚未同步云端配置。"}

for key, value in {
    "remember_login": False,
    "login_storage_loaded": False,
    "login_storage_error": False,
    "login_authenticated": False,
    "login_expires_at": 0,
    "login_notice": "",
    "login_notice_kind": "info",
}.items():
    st.session_state.setdefault(key, value)

browser_login = components.declare_component(
    "browser_login", path=str(Path(__file__).parent / "browser_login")
)


def set_cloud_sync_status(state, message):
    st.session_state.cloud_sync_status = {"state": state, "message": message}


def load_user_data_from_cloud(username: str):
    """从 Supabase 云端拉取该用户的专属配置"""
    if not has_supabase or not username:
        set_cloud_sync_status("failed", "云端服务当前不可用。")
        return False
    try:
        response = supabase.table("user_configs").select("config_json").eq("username", username).execute()
        if response.data and len(response.data) > 0:
            stored_config = response.data[0]["config_json"]
            data = json.loads(stored_config) if isinstance(stored_config, str) else stored_config
            if not isinstance(data, dict) or not isinstance(data.get("class_rules", {}), dict) or not isinstance(data.get("name_maps", {}), dict):
                raise ValueError("云端配置格式不可用")
            for class_name in data.get("class_rules", {}):
                class_config(class_name, data["class_rules"], {}, DEFAULT_RULE)
            # Recreated widgets must use the loaded configuration, not stale edits.
            for class_name in set(st.session_state.class_rules) | set(data.get("class_rules", {})):
                for prefix in ("l", "a", "b", "m"):
                    st.session_state.pop(f"{prefix}_{class_name}", None)
            st.session_state.class_rules = data.get("class_rules", {})
            st.session_state.name_maps = data.get("name_maps", {})
            st.session_state.custom_template = data.get("custom_template", DEFAULT_TEMPLATE)
            st.session_state.matrix_template = data.get("matrix_template", DEFAULT_MATRIX_TEMPLATE)
            st.session_state.emojis = normalize_emoji_config(data.get("emojis", DEFAULT_EMOJIS))
            st.session_state.emoji_presets = normalize_custom_emoji_presets(
                data.get("emoji_presets", {}), EMOJI_PRESETS
            )
            st.session_state.emoji_preset_select = "自定义"
            st.session_state.emoji_input_scope += 1
            set_cloud_sync_status("synced", f"已从云端加载 · {datetime.now(CHINA_TZ):%H:%M}")
            return True
        set_cloud_sync_status("empty", "云端暂无配置，首次保存后会自动建立。")
    except Exception as e:
        print(f"云端加载失败: {e}")
        set_cloud_sync_status("failed", "云端加载失败，请检查网络后重试。")
    return False

def save_user_data_to_cloud(show_toast=True):
    """将当前的配置同步到 Supabase 云端"""
    if not has_supabase:
        set_cloud_sync_status("failed", "云端服务当前不可用。")
        if show_toast:
            st.warning("⚠️ 未检测到 Supabase 客户端初始化！请检查 SUPABASE_KEY 是否有效。")
        return False
    
    u_name = st.session_state.get("username_key", "").strip()
    if not u_name:
        set_cloud_sync_status("idle", "填写老师手机号后才能同步云端。")
        if show_toast:
            st.warning("⚠️ 请先在上方输入老师手机号，再进行保存！")
        return False

    if st.session_state.cloud_sync_status["state"] not in ("synced", "empty"):
        if show_toast:
            st.warning("尚未成功读取云端配置，已暂停保存，避免覆盖原有班级和映射。请先点击‘重新加载云端配置’。")
        return False
    
    payload_data = {
        "class_rules": st.session_state.class_rules,
        "name_maps": st.session_state.name_maps,
        "custom_template": st.session_state.custom_template,
        "matrix_template": st.session_state.matrix_template,
        "emojis": st.session_state.emojis,
        "emoji_presets": st.session_state.emoji_presets
    }
    try:
        supabase.table("user_configs").upsert({
            "username": u_name,
            "config_json": json.dumps(payload_data, ensure_ascii=False)
        }).execute()
        set_cloud_sync_status("synced", f"已保存到云端 · {datetime.now(CHINA_TZ):%H:%M}")
        if show_toast:
            st.toast("☁️ 专属配置已成功保存到云端！", icon="🎉")
        return True
    except Exception as e:
        set_cloud_sync_status("failed", "云端保存失败，请检查网络后重试。")
        if show_toast:
            st.error(f"❌ 云端同步失败: {e}")
        return False

def reset_account_config():
    for class_name in st.session_state.class_rules:
        for prefix in ("l", "a", "b", "m"):
            st.session_state.pop(f"{prefix}_{class_name}", None)
    st.session_state.class_rules = {}
    st.session_state.name_maps = {}
    st.session_state.custom_template = DEFAULT_TEMPLATE
    st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
    st.session_state.emojis = DEFAULT_EMOJIS.copy()
    st.session_state.emoji_presets = {}
    st.session_state.emoji_preset_select = "🏆 勋章荣誉"
    st.session_state.emoji_input_scope += 1
    st.session_state.emoji_config_valid = True
    set_cloud_sync_status("idle", "尚未同步云端配置。")


def clear_login(clear_account=False):
    st.session_state.token = ""
    st.session_state.login_authenticated = False
    st.session_state.login_expires_at = 0
    st.session_state.login_storage_loaded = True
    st.session_state.clear_login_fields = True
    st.session_state.btn_clicked = False
    if clear_account:
        st.session_state.username_key = ""
        st.session_state.input_username_widget = ""
        st.session_state.remember_login = False
        reset_account_config()
    st.session_state.login_notice = ""


def on_username_change():
    entered_name = st.session_state.input_username_widget.strip()
    if entered_name != st.session_state.username_key:
        restore_pending = not st.session_state.login_storage_loaded
        clear_login()
        # Phone entry can arrive before the browser component on a slow device.
        st.session_state.login_storage_loaded = not restore_pending
        reset_account_config()
        st.session_state.username_key = entered_name
        if entered_name:
            load_user_data_from_cloud(entered_name)


def on_token_change():
    st.session_state.token = st.session_state.manual_token.strip()
    st.session_state.login_authenticated = False
    st.session_state.login_storage_loaded = True
    st.session_state.login_notice = ""
    st.session_state.btn_clicked = False


def login_with_password():
    username = st.session_state.username_key.strip()
    password = st.session_state.get("login_password", "")
    if not username or not password:
        st.session_state.login_notice = "请填写老师手机号和打卡平台密码。"
        st.session_state.login_notice_kind = "warning"
        return
    token, error = auto_login(username, password)
    if error or not token:
        st.session_state.login_notice = f"登录失败：{error or '未获取到登录凭证'}"
        st.session_state.login_notice_kind = "error"
        return
    st.session_state.token = token
    st.session_state.login_authenticated = True
    st.session_state.login_storage_loaded = True
    st.session_state.login_expires_at = time.time() + LOGIN_MEMORY_SECONDS
    st.session_state.clear_password_field = True
    st.session_state.sync_token_field = True
    st.session_state.login_notice = ""
    if st.session_state.cloud_sync_status["state"] in ("idle", "failed"):
        load_user_data_from_cloud(username)


def on_remember_change():
    # Unchecking forgets this device; checking must not cancel a pending restore.
    if not st.session_state.remember_login:
        st.session_state.login_storage_loaded = True


if st.session_state.pop("clear_login_fields", False):
    st.session_state.login_password = ""
    st.session_state.manual_token = ""
if st.session_state.pop("clear_password_field", False):
    st.session_state.login_password = ""
if st.session_state.pop("sync_token_field", False):
    st.session_state.manual_token = st.session_state.token

with st.sidebar:
    saved_login = None
    storage_action = "load"
    if st.session_state.login_storage_loaded:
        storage_action = "clear"
        if st.session_state.remember_login and st.session_state.login_authenticated and st.session_state.token:
            saved_login = normalize_saved_login({
                "version": 1,
                "username": st.session_state.username_key,
                "token": st.session_state.token,
                "expires_at": st.session_state.login_expires_at,
            })
            if saved_login:
                storage_action = "save"
    storage_result = browser_login(
        action=storage_action, login=saved_login, key="browser_login", default=None
    )
    if isinstance(storage_result, dict) and storage_result.get("loaded"):
        st.session_state.login_storage_error = bool(storage_result.get("error"))
        if not st.session_state.login_storage_loaded:
            st.session_state.login_storage_loaded = True
            restored = normalize_saved_login(storage_result.get("login"))
            if (restored and not st.session_state.token
                    and st.session_state.username_key in ("", restored["username"])):
                st.session_state.username_key = restored["username"]
                st.session_state.input_username_widget = restored["username"]
                st.session_state.token = restored["token"]
                st.session_state.manual_token = restored["token"]
                st.session_state.login_expires_at = restored["expires_at"]
                st.session_state.login_authenticated = True
                st.session_state.remember_login = True
                if restored["username"] and st.session_state.cloud_sync_status["state"] in ("idle", "failed"):
                    load_user_data_from_cloud(restored["username"])
            elif storage_result.get("status") in ("expired", "invalid"):
                st.session_state.login_notice = "本机保存的登录已过期或不可用，请重新登录。"
                st.session_state.login_notice_kind = "warning"
            st.rerun()

    st.header("⚙️ 参数配置")

    if st.button("🧹 清空/重置所有配置", type="secondary", use_container_width=True):
        st.query_params.clear()
        clear_login(clear_account=True)
        st.rerun()

    st.subheader("1. 身份与凭证")
    if st.session_state.login_authenticated and st.session_state.token:
        st.success("已登录，可直接生成打卡报告。")
        st.button("退出登录 / 切换账号", on_click=clear_login, args=(True,), use_container_width=True)
    elif not st.session_state.login_storage_loaded:
        st.info("正在读取本机保存的登录，请稍候。")
    elif not st.session_state.token:
        st.warning("尚未登录。请先填写密码并点击“登录”；成功后才能在本机记住登录。")
    if st.session_state.login_notice:
        getattr(st, st.session_state.login_notice_kind)(st.session_state.login_notice)

    st.session_state.setdefault("input_username_widget", st.session_state.username_key)
    st.text_input(
        "老师手机号",
        placeholder="请输入您的手机号",
        help="用于打卡平台登录和云端配置同步。",
        key="input_username_widget",
        on_change=on_username_change,
    )
    st.checkbox("在这台设备记住登录（30 天）", key="remember_login", on_change=on_remember_change)
    st.caption("勾选后，下次打开自动恢复登录；仅保存手机号和登录凭证，不保存密码。公用设备请勿勾选。")
    if st.session_state.login_storage_error:
        st.warning("浏览器未能保存登录状态。本次仍可使用；请允许本站存储后再试。")
    elif st.session_state.remember_login and st.session_state.login_authenticated and st.session_state.token:
        if (isinstance(storage_result, dict) and storage_result.get("status") == "saved"
                and storage_result.get("username") == st.session_state.username_key
                and storage_result.get("expires_at") == st.session_state.login_expires_at):
            st.caption("✅ 本机已保存登录。下次用同一浏览器打开，会自动恢复；密码框留空即可。")
        else:
            st.caption("正在保存到本机，请等到出现‘本机已保存登录’后再关闭页面。")

    sync_status = st.session_state.cloud_sync_status
    if sync_status["state"] == "synced":
        st.success(f"☁️ 班级与模板配置：{sync_status['message']}")
    elif sync_status["state"] == "failed":
        st.error(f"☁️ {sync_status['message']}")
    elif sync_status["state"] == "empty":
        st.info(f"☁️ {sync_status['message']}")
    else:
        st.caption(f"☁️ {sync_status['message']}")

    login_tab1, login_tab2 = st.tabs(["🔐 账号密码", "🔑 Token"])
    with login_tab1:
        with st.form("login_credentials"):
            st.text_input("打卡平台密码", type="password", key="login_password")
            st.form_submit_button("登录", on_click=login_with_password, use_container_width=True)
    with login_tab2:
        st.session_state.setdefault("manual_token", st.session_state.token)
        st.text_input("Token", type="password", key="manual_token", on_change=on_token_change)

    st.subheader("2. 模式与时间选择")
    output_mode = st.radio("选择输出格式", ["🍓 矩阵式周打卡榜", "📋 传统分组文字汇总"], index=0)
    
    # 🎯 严丝合缝的日期计算逻辑：
    # 1. 结束日期一律锁定为「昨天」
    # 2. 如果今天是周一：昨天是周日，统计范围为【上周一 到 上周日】
    # 3. 如果今天是周二至周日：统计范围为【本周一 到 昨天】
    today = datetime.now(CHINA_TZ).date()
    yesterday = today - timedelta(days=1)
    
    if today.weekday() == 0:
        calc_end_date = yesterday
        calc_start_date = yesterday - timedelta(days=6)
    else:
        calc_end_date = yesterday
        calc_start_date = yesterday - timedelta(days=yesterday.weekday())

    if output_mode == "🍓 矩阵式周打卡榜":
        st.caption(f"💡 矩阵模式：自动统计区间为 **{calc_start_date} 至 {calc_end_date}**")
        report_type = "周汇报"
        start_date, end_date = calc_start_date, calc_end_date
    else:
        report_type = st.radio("统计周期", ["昨日汇报", "周汇报", "月汇报", "自定义时间"])
        if report_type == "昨日汇报":
            start_date, end_date = yesterday, yesterday
        elif report_type == "周汇报":
            start_date, end_date = calc_start_date, calc_end_date
        elif report_type == "月汇报":
            start_date = yesterday.replace(day=1)
            end_date = yesterday
        else:
            start_date = st.date_input("开始日期", value=calc_start_date)
            end_date = st.date_input("结束日期", value=calc_end_date)

    st.subheader("3. 🎨 DIY 格式与 Emoji 主题")
    with st.expander("✨ 点击展开/修改模板与 Emoji 主题", expanded=False):
        if output_mode == "🍓 矩阵式周打卡榜":
            preset_options = list(EMOJI_PRESETS.keys()) + [
                name for name in st.session_state.emoji_presets
                if name not in EMOJI_PRESETS
            ]
            pending_preset = st.session_state.pop("pending_emoji_preset_select", None)
            if pending_preset in preset_options:
                st.session_state.emoji_preset_select = pending_preset
            if st.session_state.emoji_preset_select not in preset_options:
                st.session_state.emoji_preset_select = "自定义"

            selected_preset = st.selectbox(
                "选择 Emoji 预设主题",
                preset_options,
                key="emoji_preset_select"
            )

            selected_config = EMOJI_PRESETS.get(selected_preset)
            if selected_config is None:
                selected_config = st.session_state.emoji_presets.get(selected_preset, st.session_state.emojis)
            st.session_state.emojis = normalize_emoji_config(selected_config)
            input_keys = {
                key: f"emoji_{key}_{st.session_state.emoji_input_scope}_{selected_preset}"
                for key in EMOJI_KEYS
            }

            st.markdown("**自定义 Emoji 标记：**")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_full = st.text_input("全勤达标", value=st.session_state.emojis["full"], key=input_keys["full"])
                e_part = st.text_input("部分达标", value=st.session_state.emojis["part"], key=input_keys["part"])
            with col_e2:
                e_zero = st.text_input("未打卡", value=st.session_state.emojis["zero"], key=input_keys["zero"])
                e_badge = st.text_input("满勤尾巴标记", value=st.session_state.emojis["badge"], key=input_keys["badge"])

            current_emojis, emoji_errors = validate_emoji_config({
                "full": e_full,
                "part": e_part,
                "zero": e_zero,
                "badge": e_badge,
            })
            st.session_state.emoji_config_valid = not emoji_errors
            if emoji_errors:
                for error in emoji_errors:
                    st.error(f"⚠️ {error}")
            else:
                st.session_state.emojis = current_emojis

            preview_emojis = {
                key: current_emojis[key] or "⬜"
                for key in EMOJI_KEYS
            }
            st.markdown("**主题效果预览：**")
            st.code(
                f"{preview_emojis['full']}{preview_emojis['part']}{preview_emojis['zero']}  Amy\n"
                f"{preview_emojis['full']}{preview_emojis['full']}{preview_emojis['full']}  Jack {preview_emojis['badge']}",
                language=None,
            )

            st.markdown("**保存自己的预设：**")
            st.caption("保存后会出现在上方主题列表；填写老师手机号并保存云端配置后，可在其他设备继续使用。")
            preset_name = st.text_input(
                "预设名称",
                placeholder="例如：周末鼓励主题",
                key="new_emoji_preset_name"
            ).strip()
            save_label = "💾 覆盖当前预设" if preset_name in st.session_state.emoji_presets else "💾 保存为新预设"
            save_col, delete_col = st.columns([2, 1])
            with save_col:
                if st.button(
                    save_label,
                    use_container_width=True,
                    key="save_emoji_preset",
                    disabled=bool(emoji_errors),
                ):
                    if not preset_name:
                        st.warning("⚠️ 请先填写预设名称。")
                    elif preset_name in EMOJI_PRESETS:
                        st.warning("⚠️ 这个名称属于内置主题，请换一个名称。")
                    else:
                        st.session_state.emoji_presets[preset_name] = current_emojis.copy()
                        st.session_state.pending_emoji_preset_select = preset_name
                        if st.session_state.get("username_key", "").strip():
                            if save_user_data_to_cloud(show_toast=False):
                                st.toast(f"☁️ 预设“{preset_name}”已保存并同步到云端！", icon="🎉")
                            else:
                                st.toast(f"✅ 预设“{preset_name}”已保存，但云端同步失败。", icon="⚠️")
                        else:
                            st.toast(f"✅ 预设“{preset_name}”已保存！填写老师手机号后可跨设备同步。", icon="🎉")
                        st.rerun()
            with delete_col:
                if selected_preset in st.session_state.emoji_presets:
                    if st.button("🗑️ 删除预设", use_container_width=True, key="delete_emoji_preset"):
                        del st.session_state.emoji_presets[selected_preset]
                        st.session_state.pending_emoji_preset_select = "自定义"
                        if st.session_state.get("username_key", "").strip():
                            save_user_data_to_cloud(show_toast=False)
                        st.toast(f"🗑️ 预设“{selected_preset}”已删除。")
                        st.rerun()

            st.markdown("**备份与导入预设：**")
            st.caption("可下载全部自定义预设；导入时，同名预设会被文件中的版本覆盖。")
            if st.session_state.emoji_presets:
                st.download_button(
                    "⬇️ 导出全部预设",
                    data=export_emoji_presets(st.session_state.emoji_presets),
                    file_name="iread-emoji-presets.json",
                    mime="application/json",
                    use_container_width=True,
                )
            else:
                st.caption("暂无可导出的自定义预设。")

            uploaded_presets = st.file_uploader(
                "选择预设文件",
                type=["json"],
                key="emoji_preset_upload",
            )
            if st.button(
                "⬆️ 导入预设",
                use_container_width=True,
                disabled=uploaded_presets is None,
                key="import_emoji_presets",
            ):
                try:
                    imported_presets = import_emoji_presets(
                        uploaded_presets.getvalue().decode("utf-8-sig"),
                        EMOJI_PRESETS,
                    )
                    st.session_state.emoji_presets.update(imported_presets)
                    st.session_state.emoji_input_scope += 1
                    st.session_state.pending_emoji_preset_select = next(iter(imported_presets))
                    if st.session_state.get("username_key", "").strip():
                        save_user_data_to_cloud(show_toast=False)
                    st.toast(f"✅ 已导入 {len(imported_presets)} 个 Emoji 预设。", icon="🎉")
                    st.rerun()
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    st.error(f"❌ 导入失败：{error}")

            st.markdown("**自定义矩阵模板：**")
            st.session_state.matrix_template = st.text_area("矩阵模板", value=st.session_state.matrix_template, height=180)
        else:
            st.markdown("**自定义传统分组模板：**")
            st.session_state.custom_template = st.text_area("文字模板", value=st.session_state.custom_template, height=180)

    st.subheader("4. ⚙️ 班级与映射管理")
    st.button(
        "🔄 重新加载云端配置",
        on_click=load_user_data_from_cloud,
        args=(st.session_state.username_key,),
        disabled=not st.session_state.username_key,
        use_container_width=True,
    )
    if not st.session_state.class_rules:
        st.caption("填写原来保存配置时的老师手机号后，班级和姓名映射会从云端加载。加载失败时，可点击上方按钮重试。")
    st.caption("自定义班级目标优先；未匹配的班级使用默认 60 分钟听音、15 分钟动画、2 本分级绘本。课外阅读不计入分级绘本。")
    new_class_input = st.text_input("➕ 添加班级：", placeholder="例如：万达K12班").strip()
    if st.button("添加班级", use_container_width=True):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = DEFAULT_RULE.copy()
            st.session_state.name_maps[new_class_input] = ""
            st.rerun()

    class_rules_config = {}
    name_maps_config = {}

    for c_name in list(st.session_state.class_rules.keys()):
        with st.expander(f"📍 {c_name}", expanded=False):
            if st.button("❌ 删除此班级", key=f"del_{c_name}", type="secondary"):
                del st.session_state.class_rules[c_name]
                if c_name in st.session_state.name_maps:
                    del st.session_state.name_maps[c_name]
                st.rerun()

            st.session_state.class_rules[c_name]["listen"] = st.number_input("每日听音(分)", value=st.session_state.class_rules[c_name]["listen"], min_value=0, step=5, key=f"l_{c_name}")
            st.session_state.class_rules[c_name]["anim"] = st.number_input("每日动画(分)", value=st.session_state.class_rules[c_name]["anim"], min_value=0, step=5, key=f"a_{c_name}")
            st.session_state.class_rules[c_name]["books"] = st.number_input("每日分级绘本(本)", value=st.session_state.class_rules[c_name]["books"], min_value=0, step=1, key=f"b_{c_name}")
            st.session_state.name_maps[c_name] = st.text_area("姓名映射 (中文:英文)", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=60)

        class_rules_config[c_name] = st.session_state.class_rules[c_name]
        name_maps_config[c_name] = st.session_state.name_maps.get(c_name, "")

    st.divider()
    
    if st.button("💾 手动保存当前配置到云端", type="secondary", use_container_width=True):
        save_user_data_to_cloud(show_toast=True)

    emoji_blocked = output_mode == "🍓 矩阵式周打卡榜" and not st.session_state.emoji_config_valid
    if emoji_blocked:
        st.caption("⚠️ 修正 Emoji 设置后才能生成矩阵报告。")
    btn_generate = st.button(
        "⚡ 一键生成打卡报告",
        type="primary",
        use_container_width=True,
        disabled=emoji_blocked,
    )

    if btn_generate:
        st.session_state.btn_clicked = True
        # An empty screen must never overwrite previously saved class mappings.
        if st.session_state.class_rules or st.session_state.name_maps:
            save_user_data_to_cloud(show_toast=False)
        st.rerun()

if st.session_state.btn_clicked:
    final_token = st.session_state.token

    if not final_token:
        if not st.session_state.login_storage_loaded:
            st.info("正在恢复本机登录，恢复完成后会继续生成报告。")
        else:
            st.warning("本机没有可用的登录凭证。请在侧栏填写密码并点击“登录”，或填写 Token；云端配置保存成功不代表已登录。")
    else:
        with st.spinner("⚡ 正在抓取打卡数据并生成报告..."):
            mode_key = "matrix" if output_mode.startswith("🍓") else "traditional"
            curr_tmpl = st.session_state.matrix_template if mode_key == "matrix" else st.session_state.custom_template
            
            diagnostics = []
            reports, err = fetch_data_via_api(
                final_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, DEFAULT_RULE, 
                curr_tmpl, mode=mode_key, emoji_config=st.session_state.emojis, diagnostics=diagnostics
            )
            if diagnostics:
                with st.expander("🔎 核对抓取数据与达标依据"):
                    st.caption("查看学生原始数据、换算后的分钟数、实际使用的目标和未达标原因；抓取失败时不会继续发布不完整报告。")
                    st.dataframe(diagnostics, use_container_width=True, hide_index=True)
            if err == AUTH_EXPIRED_MESSAGE:
                clear_login()
                st.session_state.login_notice = AUTH_EXPIRED_MESSAGE
                st.session_state.login_notice_kind = "warning"
                st.rerun()
            elif err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                if not st.session_state.login_authenticated:
                    st.session_state.login_authenticated = True
                    st.session_state.login_expires_at = time.time() + LOGIN_MEMORY_SECONDS
                    st.rerun()
                st.toast("🎉 打卡报告生成成功！", icon="🚀")
                
                for idx, (c_name, c_content) in enumerate(reports.items()):
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    
                    final_share_content = c_content.strip()

                    escaped_content = (
                        final_share_content.replace("\\", "\\\\")
                        .replace("`", "\\`")
                        .replace("${", "\\${")
                    )
                    
                    custom_copy_card = f"""
                    <div style="background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 16px; font-family: monospace; position: relative;">
                        <div style="position: absolute; top: 10px; right: 10px; display: flex; gap: 8px;">
                            <button id="share-btn-{idx}" onclick="shareText_{idx}()" style="
                                background-color: #07c160;
                                color: white;
                                border: none;
                                padding: 6px 12px;
                                border-radius: 6px;
                                cursor: pointer;
                                font-size: 13px;
                                font-weight: bold;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                transition: all 0.2s ease;
                            ">📱 分享</button>

                            <button id="copy-btn-{idx}" onclick="copyText_{idx}()" style="
                                background-color: #ff4b4b;
                                color: white;
                                border: none;
                                padding: 6px 14px;
                                border-radius: 6px;
                                cursor: pointer;
                                font-size: 13px;
                                font-weight: bold;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                transition: all 0.2s ease;
                            ">📋 复制本班报告</button>
                        </div>
                        
                        <pre style="margin-top: 30px; margin-bottom: 0; white-space: pre-wrap; word-break: break-word; font-size: 14px; line-height: 1.6; color: #31333f;">{final_share_content}</pre>
                    </div>

                    <script>
                    const rawText_{idx} = `{escaped_content}`;

                    function showSuccess_{idx}(msg) {{
                        const btn = document.getElementById('copy-btn-{idx}');
                        btn.innerText = "✅ " + msg;
                        btn.style.backgroundColor = "#28a745";
                        setTimeout(() => {{
                            btn.innerText = "📋 复制本班报告";
                            btn.style.backgroundColor = "#ff4b4b";
                        }}, 2000);
                    }}

                    function copyText_{idx}() {{
                        if (navigator.clipboard && window.isSecureContext) {{
                            navigator.clipboard.writeText(rawText_{idx}).then(() => showSuccess_{idx}("复制成功！")).catch(err => {{
                                fallbackCopy_{idx}(rawText_{idx});
                            }});
                        }} else {{
                            fallbackCopy_{idx}(rawText_{idx});
                        }}
                    }}

                    function fallbackCopy_{idx}(text) {{
                        const textArea = document.createElement("textarea");
                        textArea.value = text;
                        textArea.style.position = "fixed";
                        textArea.style.left = "-999999px";
                        document.body.appendChild(textArea);
                        textArea.focus();
                        textArea.select();
                        try {{
                            document.execCommand('copy');
                            showSuccess_{idx}("复制成功！");
                        }} catch (err) {{
                            alert('复制失败，请手动选择框内文字复制');
                        }}
                        document.body.removeChild(textArea);
                    }}

                    function shareText_{idx}() {{
                        if (navigator.share) {{
                            navigator.share({{
                                title: '{c_name} 打卡报告',
                                text: rawText_{idx}
                            }}).catch(console.error);
                        }} else {{
                            copyText_{idx}();
                            alert('文本已自动复制！手机端可在微信等应用中直接长按粘贴。');
                        }}
                    }}
                    </script>
                    """
                    
                    line_count = len(final_share_content.split('\n'))
                    card_height = max(220, line_count * 24 + 80)
                    
                    components.html(custom_copy_card, height=card_height)
else:
    st.info("👈 请在左侧边栏配置班级与规则，点击 **〈💾 手动保存当前配置到云端〉** 或 **〈⚡ 一键生成打卡报告〉** 即可。")

