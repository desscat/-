import json
import re
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

# 尝试引入 Supabase 云端数据库客户端
try:
    from supabase import create_client, Client
    SUPABASE_URL = "https://sxjdncrkkjcnkyozmbzo.supabase.co"
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

sidebar_state = "collapsed" if st.session_state.btn_clicked else "expanded"

st.set_page_config(
    page_title="全阅读学情打卡生成器", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state=sidebar_state
)

st.title("⚡ 全阅读学情打卡生成器")

EMOJI_PRESETS = {
    "自定义": None,
    "🏆 勋章荣誉": {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"},
    "🌟 星光闪耀": {"full": "⭐", "part": "✨", "zero": "⚪", "badge": "👑"},
    "🍓 水果派对": {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"},
    "🚀 太空探索": {"full": "🚀", "part": "🛸", "zero": "🌑", "badge": "🌌"}
}

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
    st.session_state.emojis = {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"}

def load_user_data_from_cloud(username: str):
    """从 Supabase 云端拉取该用户的专属配置"""
    if not has_supabase or not username:
        return False
    try:
        response = supabase.table("user_configs").select("config_json").eq("username", username).execute()
        if response.data and len(response.data) > 0:
            data = json.loads(response.data[0]["config_json"])
            st.session_state.class_rules = data.get("class_rules", {})
            st.session_state.name_maps = data.get("name_maps", {})
            st.session_state.custom_template = data.get("custom_template", DEFAULT_TEMPLATE)
            st.session_state.matrix_template = data.get("matrix_template", DEFAULT_MATRIX_TEMPLATE)
            st.session_state.emojis = data.get("emojis", {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"})
            return True
    except Exception as e:
        print(f"云端加载失败: {e}")
    return False

def save_user_data_to_cloud(show_toast=True):
    """将当前的配置同步到 Supabase 云端"""
    if not has_supabase:
        if show_toast:
            st.warning("⚠️ 未检测到 Supabase 客户端初始化！")
        return
    
    u_name = st.session_state.get("username_key", "").strip()
    if not u_name:
        if show_toast:
            st.warning("⚠️ 请先在上方输入老师手机号，再进行保存！")
        return
    
    payload_data = {
        "class_rules": st.session_state.class_rules,
        "name_maps": st.session_state.name_maps,
        "custom_template": st.session_state.custom_template,
        "matrix_template": st.session_state.matrix_template,
        "emojis": st.session_state.emojis
    }
    try:
        supabase.table("user_configs").upsert({
            "username": u_name,
            "config_json": json.dumps(payload_data, ensure_ascii=False)
        }).execute()
        if show_toast:
            st.toast("☁️ 专属配置已成功保存到云端！", icon="🎉")
    except Exception as e:
        if show_toast:
            st.error(f"❌ 云端同步失败: {e}")

with st.sidebar:
    st.header("⚙️ 参数配置")
    
    if st.button("🧹 清空/重置所有配置", type="secondary", use_container_width=True):
        st.query_params.clear()
        st.session_state.username_key = ""
        st.session_state.token = ""
        st.session_state.class_rules = {}
        st.session_state.name_maps = {}
        st.session_state.custom_template = DEFAULT_TEMPLATE
        st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
        st.session_state.emojis = {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"}
        st.session_state.btn_clicked = False
        st.rerun()

    st.subheader("1. 身份与凭证")
    
    def on_username_change():
        entered_name = st.session_state.get("input_username_widget", "").strip()
        if entered_name:
            st.session_state.username_key = entered_name
            found = load_user_data_from_cloud(entered_name)
            if found:
                st.toast(f"☁️ 账号 [{entered_name}] 的专属配置已从云端同步成功！", icon="🎉")

    st.text_input(
        "老师手机号（用于云端同步配置）", 
        value=st.session_state.username_key, 
        placeholder="请输入您的手机号", 
        key="input_username_widget",
        on_change=on_username_change
    )

    login_tab1, login_tab2 = st.tabs(["🔐 账号密码", "🔑 Token"])
    with login_tab1:
        username_input = st.text_input("打卡平台手机号", value=st.session_state.username_key)
        password_input = st.text_input("打卡平台密码", type="password")
    with login_tab2:
        token_input = st.text_input("Token", value=st.session_state.token, type="password")
        if token_input != st.session_state.token:
            st.session_state.token = token_input

    if username_input and username_input != st.session_state.username_key:
        st.session_state.username_key = username_input
        load_user_data_from_cloud(username_input)

    st.subheader("2. 模式与时间选择")
    output_mode = st.radio("选择输出格式", ["🍓 矩阵式周打卡榜", "📋 传统分组文字汇总"], index=0)
    
    today = date.today()
    yesterday = today - timedelta(days=1)

    if output_mode == "🍓 矩阵式周打卡榜":
        st.caption("💡 矩阵模式：自动统计本周一至昨天的每日打卡情况，实时生成 Emoji 矩阵。")
        report_type = "周汇报"
        start_date = today - timedelta(days=today.weekday())
        end_date = yesterday if yesterday >= start_date else start_date
    else:
        report_type = st.radio("统计周期", ["昨日汇报", "周汇报", "月汇报", "自定义时间"])
        start_date, end_date = today, yesterday
        if report_type == "周汇报":
            start_date = today - timedelta(days=today.weekday())
            end_date = yesterday if yesterday >= start_date else start_date
        elif report_type == "自定义时间":
            start_date = st.date_input("开始日期", value=today - timedelta(days=7))
            end_date = st.date_input("结束日期", value=yesterday)

    st.subheader("3. 🎨 DIY 格式与 Emoji 主题")
    with st.expander("✨ 点击展开/修改模板与 Emoji 主题", expanded=False):
        if output_mode == "🍓 矩阵式周打卡榜":
            selected_preset = st.selectbox("选择 Emoji 预设主题", list(EMOJI_PRESETS.keys()), index=1)
            if selected_preset != "自定义" and EMOJI_PRESETS[selected_preset]:
                st.session_state.emojis = EMOJI_PRESETS[selected_preset]

            st.markdown("**自定义 Emoji 标记：**")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_full = st.text_input("全勤达标", value=st.session_state.emojis.get("full", "🥇"))
                e_part = st.text_input("部分达标", value=st.session_state.emojis.get("part", "🏆"))
            with col_e2:
                e_zero = st.text_input("未打卡", value=st.session_state.emojis.get("zero", "❌"))
                e_badge = st.text_input("满勤尾巴标记", value=st.session_state.emojis.get("badge", "👑"))
            
            st.session_state.emojis = {"full": e_full, "part": e_part, "zero": e_zero, "badge": e_badge}
            
            st.markdown("**自定义矩阵模板：**")
            st.session_state.matrix_template = st.text_area("矩阵模板", value=st.session_state.matrix_template, height=180)
        else:
            st.markdown("**自定义传统分组模板：**")
            st.session_state.custom_template = st.text_area("文字模板", value=st.session_state.custom_template, height=180)

    st.subheader("4. ⚙️ 班级与映射管理")
    new_class_input = st.text_input("➕ 添加班级：", placeholder="例如：万达K12班")
    if st.button("添加班级", use_container_width=True):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 20, "anim": 10, "books": 1}
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

            st.session_state.class_rules[c_name]["listen"] = st.number_input("每日听音(分)", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}")
            st.session_state.class_rules[c_name]["anim"] = st.number_input("每日动画(分)", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}")
            st.session_state.class_rules[c_name]["books"] = st.number_input("每日绘本(本)", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}")
            st.session_state.name_maps[c_name] = st.text_area("姓名映射 (中文:英文)", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=60)

        class_rules_config[c_name] = st.session_state.class_rules[c_name]
        name_maps_config[c_name] = st.session_state.name_maps.get(c_name, "")

    st.divider()
    
    if st.button("💾 手动保存当前配置到云端", type="secondary", use_container_width=True):
        save_user_data_to_cloud(show_toast=True)

    btn_generate = st.button("⚡ 一键生成打卡报告", type="primary", use_container_width=True)

    if btn_generate:
        st.session_state.btn_clicked = True
        save_user_data_to_cloud(show_toast=False)
        st.rerun()

# ---------------- 右侧主界面呈现区域 ----------------
if st.session_state.btn_clicked:
    final_token = ""
    if username_input and password_input:
        with st.spinner("🔑 正在登录..."):
            login_token, login_err = auto_login(username_input, password_input)
            if login_err:
                st.error(f"❌ 登录失败：{login_err}")
                st.stop()
            else:
                final_token = login_token
                st.session_state.token = login_token
                save_user_data_to_cloud(show_toast=True)
    else:
        final_token = st.session_state.token

    if not final_token:
        st.warning("⚠️ 请先在左侧边栏填写账号密码或 Token！")
    else:
        with st.spinner("⚡ 正在抓取打卡数据并生成报告..."):
            mode_key = "matrix" if output_mode.startswith("🍓") else "traditional"
            curr_tmpl = st.session_state.matrix_template if mode_key == "matrix" else st.session_state.custom_template
            
            reports, err = fetch_data_via_api(
                final_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, {"listen": 20, "anim": 10, "books": 1}, 
                curr_tmpl, mode=mode_key, emoji_config=st.session_state.emojis
            )
            if err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                st.toast("🎉 打卡报告生成成功！", icon="🚀")
                
                # 动态获得图标配置
                f_emoji = st.session_state.emojis.get("full", "🥇")
                p_emoji = st.session_state.emojis.get("part", "🏆")
                z_emoji = st.session_state.emojis.get("zero", "❌")
                yesterday_str = end_date.strftime("%m.%d").lstrip("0").replace(".0", ".")

                for idx, (c_name, c_content) in enumerate(reports.items()):
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    
                    # 强制将表头日期止于昨天
                    c_content = re.sub(r'--\d+\.\d+', f'--{yesterday_str}', c_content)

                    lines = c_content.split('\n')
                    full_cnt, part_cnt, zero_cnt = 0, 0, 0
                    
                    for line in lines:
                        line_str = line.strip()
                        if not line_str or "--" in line_str or "学情" in line_str or "提醒" in line_str or "全阅读" in line_str or "打卡" in line_str or "达标" in line_str:
                            continue
                        
                        parts = line_str.split()
                        if parts:
                            emojis_part = parts[0]
                            # 🎯 精确全勤判定：必须包含 full 图标，且绝无 part 图标与 zero 图标
                            if p_emoji not in emojis_part and z_emoji not in emojis_part and f_emoji in emojis_part:
                                full_cnt += 1
                            elif f_emoji not in emojis_part and p_emoji not in emojis_part and z_emoji in emojis_part:
                                zero_cnt += 1
                            else:
                                part_cnt += 1

                    total_students = full_cnt + part_cnt + zero_cnt
                    pct = round(full_cnt / total_students * 100) if total_students > 0 else 0
                    
                    stats_text = (
                        f"📊 学情统计汇总：\n"
                        f"🌟 全勤达标：{full_cnt} 人（{pct}%）\n"
                        f"💪 持续加油：{part_cnt} 人\n"
                        f"⚠️ 未打卡提醒：{zero_cnt} 人"
                    )
                    
                    if "{stats}" in c_content:
                        final_share_content = c_content.replace("{stats}", stats_text).strip()
                    else:
                        final_share_content = re.sub(r'📊 学情统计汇总：[\s\S]*?(?=💡|$)', stats_text + "\n\n", c_content).strip()

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
    st.info("👈 请在左侧边栏配置班级与规则，点击 **「💾 手动保存当前配置到云端」** 或 **「⚡ 一键生成打卡报告」** 即可。")
