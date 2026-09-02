import json
import re
import os
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

# 尝试引入 Supabase 云端数据库客户端
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://sxjdncrkkjcnkyozmbzo.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_PM_84SFDUCbhpiQLJjYT5w_cMziV-vt")
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

# ================= 侧边栏全部 UI 控制区 =================
with st.sidebar:
    st.header("⚙️ 系统设置 & 配置存储")
    
    st.subheader("🔑 账号登录")
    
    def on_username_change():
        entered_name = st.session_state.get("input_username_widget", "").strip()
        if entered_name:
            st.session_state.username_key = entered_name
            found = load_user_data_from_cloud(entered_name)
            if found:
                st.toast(f"☁️ 账号 [{entered_name}] 的专属配置已从云端同步成功！", icon="🎉")

    st.text_input(
        "手机号", 
        value=st.session_state.username_key, 
        placeholder="请输入手机号", 
        key="input_username_widget",
        on_change=on_username_change
    )
    
    password_input = st.text_input("密码", type="password")

    if st.button("自动登录获取 Token", use_container_width=True):
        u_val = st.session_state.get("input_username_widget", "").strip()
        if u_val and password_input:
            with st.spinner("🔑 正在登录..."):
                t_code, err_msg = auto_login(u_val, password_input)
                if err_msg:
                    st.error(f"❌ 登录失败: {err_msg}")
                else:
                    st.session_state.token = t_code
                    st.session_state.username_key = u_val
                    save_user_data_to_cloud(show_toast=True)
                    st.success("登录成功！Token 已自动填入并保存")
        else:
            st.warning("请填写手机号和密码")

    token_input = st.text_input("Token (可手动粘贴)", value=st.session_state.token, type="password")
    if token_input != st.session_state.token:
        st.session_state.token = token_input

    st.markdown("---")
    
    # 🎯 模式与时间范围
    output_mode = st.radio("选择汇报模式", ["矩阵日历模式 (matrix)", "传统分组模式 (traditional)"], index=0)
    mode_key = "matrix" if "matrix" in output_mode else "traditional"

    date_option = st.radio("时间范围", ["本周 (周一至昨天)", "自定义日期"], index=0)

    today = date.today()
    yesterday = today - timedelta(days=1)

    # 🎯 兼容周一特判逻辑
    if date_option == "本周 (周一至昨天)":
        if today.weekday() == 0:  # 今天刚好是周一
            start_date = today - timedelta(days=7)  # 上周一
            end_date = yesterday                    # 上周日
        else:
            start_date = today - timedelta(days=today.weekday())  # 本周一
            end_date = yesterday                                  # 昨天
        report_type = "周汇报"
    else:
        report_type = "自定义时间"
        start_date = st.date_input("开始日期", value=today - timedelta(days=7))
        end_date = st.date_input("结束日期", value=yesterday)

    st.markdown("---")
    
    # 🎯 高级配置 (班级规则、姓名映射、模板)
    with st.expander("⚙️ 高级配置 (班级规则与姓名映射)", expanded=False):
        tab_rules, tab_maps, tab_tpls = st.tabs(["🎯 规则配置", "🔤 姓名映射", "📝 模板编辑"])
        
        with tab_rules:
            new_c = st.text_input("➕ 添加班级名称：", placeholder="例如：康乐E4", key="new_c_input")
            if st.button("添加班级", use_container_width=True):
                if new_c and new_c not in st.session_state.class_rules:
                    st.session_state.class_rules[new_c] = {"listen": 20, "anim": 10, "books": 1}
                    st.session_state.name_maps[new_c] = ""
                    st.rerun()

            for c_name in list(st.session_state.class_rules.keys()):
                st.markdown(f"**📍 {c_name}**")
                c_l = st.number_input("听音(分)", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}")
                c_a = st.number_input("动画(分)", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}")
                c_b = st.number_input("绘本(本)", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}")
                st.session_state.class_rules[c_name] = {"listen": c_l, "anim": c_a, "books": c_b}
                if st.button("❌ 删除此班级", key=f"del_{c_name}"):
                    del st.session_state.class_rules[c_name]
                    if c_name in st.session_state.name_maps:
                        del st.session_state.name_maps[c_name]
                    st.rerun()

        with tab_maps:
            for c_name in list(st.session_state.class_rules.keys()):
                st.markdown(f"**📍 {c_name} 映射**")
                st.session_state.name_maps[c_name] = st.text_area(
                    "中文:英文 (每行一个)", 
                    value=st.session_state.name_maps.get(c_name, ""), 
                    key=f"m_{c_name}", 
                    height=80
                )

        with tab_tpls:
            if mode_key == "matrix":
                st.session_state.matrix_template = st.text_area("矩阵模板", value=st.session_state.matrix_template, height=140)
            else:
                st.session_state.custom_template = st.text_area("传统模板", value=st.session_state.custom_template, height=140)

        if st.button("💾 保存高级配置到云端", use_container_width=True):
            save_user_data_to_cloud(show_toast=True)

    st.markdown("---")
    
    # 🎯 图标设置
    st.subheader("🎨 矩阵模式图标配置")
    selected_preset = st.selectbox("选择 Emoji 预设主题", list(EMOJI_PRESETS.keys()), index=1)
    if selected_preset != "自定义" and EMOJI_PRESETS[selected_preset]:
        st.session_state.emojis = EMOJI_PRESETS[selected_preset]

    full_in = st.text_input("全勤图标 (三项全满)", value=st.session_state.emojis.get("full", "🥇"))
    part_in = st.text_input("部分达标图标 (加油)", value=st.session_state.emojis.get("part", "🏆"))
    zero_in = st.text_input("未打卡图标", value=st.session_state.emojis.get("zero", "❌"))
    badge_in = st.text_input("全勤尾巴徽章", value=st.session_state.emojis.get("badge", "👑"))
    st.session_state.emojis = {"full": full_in, "part": part_in, "zero": zero_in, "badge": badge_in}

    st.markdown("---")
    
    # 🎯 按钮区域
    btn_generate = st.button("🚀 立即生成学情报告", type="primary", use_container_width=True)

    if btn_generate:
        st.session_state.btn_clicked = True
        save_user_data_to_cloud(show_toast=False)
        st.rerun()

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

# ================= 主界面结果展示区 =================
if st.session_state.btn_clicked:
    final_token = st.session_state.token

    if not final_token:
        st.warning("⚠️ 请先在左侧边栏填写账号密码或 Token！")
    else:
        with st.spinner("⚡ 正在抓取打卡数据并生成报告..."):
            curr_tmpl = st.session_state.matrix_template if mode_key == "matrix" else st.session_state.custom_template
            
            reports, err = fetch_data_via_api(
                final_token, report_type, start_date, end_date, 
                st.session_state.class_rules, st.session_state.name_maps, {"listen": 20, "anim": 10, "books": 1}, 
                curr_tmpl, mode=mode_key, emoji_config=st.session_state.emojis
            )
            if err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                st.toast("🎉 打卡报告生成成功！", icon="🚀")
                
                f_emoji = st.session_state.emojis.get("full", "🥇")
                p_emoji = st.session_state.emojis.get("part", "🏆")
                z_emoji = st.session_state.emojis.get("zero", "❌")
                yesterday_str = end_date.strftime("%m.%d").lstrip("0").replace(".0", ".")

                for idx, (c_name, c_content) in enumerate(reports.items()):
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    
                    # 强制纠正日期表头
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
                            # 🎯 精确全勤判定逻辑
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
                    
                    # 微信端 HTML 分享卡片
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
    st.info("👈 请在左侧边栏配置班级与规则，点击 **「🚀 立即生成学情报告」** 即可。")
