import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

# 初始化 Session State
if "btn_clicked" not in st.session_state:
    st.session_state.btn_clicked = False

# 根据是否点击了生成按钮，动态控制侧边栏是展开还是自动折叠
sidebar_state = "collapsed" if st.session_state.btn_clicked else "expanded"

st.set_page_config(
    page_title="全阅读学情打卡生成器", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state=sidebar_state
)

st.title("⚡ 全阅读学情打卡生成器")

# ==================== Emoji 主题包配置 ====================
EMOJI_PRESETS = {
    "自定义": None,
    "🍓 水果派对": {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"},
    "🌟 星光闪耀": {"full": "⭐", "part": "✨", "zero": "⚪", "badge": "👑"},
    "🚀 太空探索": {"full": "🚀", "part": "🛸", "zero": "🌑", "badge": "🌌"},
    "🏆 勋章荣誉": {"full": "🏆", "part": "🥇", "zero": "❌", "badge": "🎖️"}
}

# ==================== 1. URL 持久化配置 ====================
params = st.query_params
url_token = params.get("token", "")

try:
    url_rules = json.loads(params.get("rules", "{}"))
except:
    url_rules = {}

try:
    url_maps = json.loads(params.get("maps", "{}"))
except:
    url_maps = {}

url_template = params.get("template", DEFAULT_TEMPLATE)
url_matrix_template = params.get("matrix_template", DEFAULT_MATRIX_TEMPLATE)

try:
    url_emojis = json.loads(params.get("emojis", '{"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}'))
except:
    url_emojis = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}

if "token" not in st.session_state:
    st.session_state.token = url_token
if "class_rules" not in st.session_state:
    st.session_state.class_rules = url_rules
if "name_maps" not in st.session_state:
    st.session_state.name_maps = url_maps
if "custom_template" not in st.session_state:
    st.session_state.custom_template = url_template
if "matrix_template" not in st.session_state:
    st.session_state.matrix_template = url_matrix_template
if "emojis" not in st.session_state:
    st.session_state.emojis = url_emojis

def save_to_url():
    st.query_params["token"] = st.session_state.token
    st.query_params["rules"] = json.dumps(st.session_state.class_rules, ensure_ascii=False)
    st.query_params["maps"] = json.dumps(st.session_state.name_maps, ensure_ascii=False)
    st.query_params["template"] = st.session_state.custom_template
    st.query_params["matrix_template"] = st.session_state.matrix_template
    st.query_params["emojis"] = json.dumps(st.session_state.emojis, ensure_ascii=False)

# ==================== 2. 左侧边栏配置区 ====================
with st.sidebar:
    st.header("⚙️ 参数配置")
    
    if st.button("🧹 清空/重置所有配置", type="secondary", use_container_width=True):
        st.query_params.clear()
        st.session_state.token = ""
        st.session_state.class_rules = {}
        st.session_state.name_maps = {}
        st.session_state.custom_template = DEFAULT_TEMPLATE
        st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
        st.session_state.emojis = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}
        st.session_state.btn_clicked = False
        st.rerun()

    st.subheader("1. 身份凭证")
    login_tab1, login_tab2 = st.tabs(["🔐 账号密码", "🔑 Token"])
    with login_tab1:
        username_input = st.text_input("手机号")
        password_input = st.text_input("密码", type="password")
    with login_tab2:
        token_input = st.text_input("Token", value=st.session_state.token, type="password")
        if token_input != st.session_state.token:
            st.session_state.token = token_input
            save_to_url()

    st.subheader("2. 模式与时间选择")
    output_mode = st.radio("选择输出格式", ["🍓 矩阵式周打卡榜", "📋 传统分组文字汇总"], index=0)
    
    if output_mode == "🍓 矩阵式周打卡榜":
        st.caption("💡 矩阵模式：自动统计本周一至今天的每日打卡情况，实时生成 Emoji 矩阵。")
        report_type = "周汇报"
        start_date, end_date = date.today(), date.today()
    else:
        report_type = st.radio("统计周期", ["昨日汇报", "周汇报", "月汇报", "自定义时间"])
        start_date, end_date = date.today(), date.today()
        if report_type == "自定义时间":
            start_date = st.date_input("开始日期", value=date.today() - timedelta(days=1))
            end_date = st.date_input("结束日期", value=date.today())

    st.subheader("3. 🎨 DIY 格式与 Emoji 主题")
    with st.expander("✨ 点击展开/修改模板与 Emoji 主题", expanded=False):
        if output_mode == "🍓 矩阵式周打卡榜":
            selected_preset = st.selectbox("选择 Emoji 预设主题", list(EMOJI_PRESETS.keys()), index=1)
            if selected_preset != "自定义" and EMOJI_PRESETS[selected_preset]:
                st.session_state.emojis = EMOJI_PRESETS[selected_preset]
                save_to_url()

            st.markdown("**自定义 Emoji 标记：**")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_full = st.text_input("全勤达标", value=st.session_state.emojis.get("full", "🍓"))
                e_part = st.text_input("部分达标", value=st.session_state.emojis.get("part", "✅"))
            with col_e2:
                e_zero = st.text_input("未打卡", value=st.session_state.emojis.get("zero", "🚫"))
                e_badge = st.text_input("满勤尾巴标记", value=st.session_state.emojis.get("badge", "✔️"))
            
            new_emojis = {"full": e_full, "part": e_part, "zero": e_zero, "badge": e_badge}
            if new_emojis != st.session_state.emojis:
                st.session_state.emojis = new_emojis
                save_to_url()
            
            st.markdown("**自定义矩阵模板：**")
            mat_tmpl_input = st.text_area("矩阵模板", value=st.session_state.matrix_template, height=120)
            if mat_tmpl_input != st.session_state.matrix_template:
                st.session_state.matrix_template = mat_tmpl_input
                save_to_url()
        else:
            st.markdown("**自定义传统分组模板：**")
            custom_tmpl_input = st.text_area("文字模板", value=st.session_state.custom_template, height=180)
            if custom_tmpl_input != st.session_state.custom_template:
                st.session_state.custom_template = custom_tmpl_input
                save_to_url()

    st.subheader("4. ⚙️ 班级与映射管理")
    new_class_input = st.text_input("➕ 添加班级：", placeholder="例如：万达K12班")
    if st.button("添加班级", use_container_width=True):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
            st.session_state.name_maps[new_class_input] = ""
            save_to_url()
            st.rerun()

    class_rules_config = {}
    name_maps_config = {}

    for c_name in list(st.session_state.class_rules.keys()):
        with st.expander(f"📍 {c_name}", expanded=False):
            if st.button("❌ 删除此班级", key=f"del_{c_name}", type="secondary"):
                del st.session_state.class_rules[c_name]
                if c_name in st.session_state.name_maps:
                    del st.session_state.name_maps[c_name]
                save_to_url()
                st.rerun()

            def update_rule(c=c_name):
                st.session_state.class_rules[c]["listen"] = st.session_state[f"l_{c}"]
                st.session_state.class_rules[c]["anim"] = st.session_state[f"a_{c}"]
                st.session_state.class_rules[c]["books"] = st.session_state[f"b_{c}"]
                save_to_url()

            def update_map(c=c_name):
                st.session_state.name_maps[c] = st.session_state[f"m_{c}"]
                save_to_url()

            st.number_input("每日听音(分)", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}", on_change=update_rule)
            st.number_input("每日动画(分)", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}", on_change=update_rule)
            st.number_input("每日绘本(本)", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}", on_change=update_rule)
            st.text_area("姓名映射 (中文:英文)", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=60, on_change=update_map)

        class_rules_config[c_name] = st.session_state.class_rules[c_name]
        name_maps_config[c_name] = st.session_state.name_maps.get(c_name, "")

    st.divider()
    btn_generate = st.button("⚡ 一键生成打卡报告", type="primary", use_container_width=True)

    if btn_generate:
        st.session_state.btn_clicked = True
        st.rerun()

# ==================== 3. 主界面展示区 ====================
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
                save_to_url()
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
                class_rules_config, name_maps_config, {"listen": 60, "anim": 15, "books": 2}, 
                curr_tmpl, mode=mode_key, emoji_config=st.session_state.emojis
            )
            if err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                st.toast("🎉 打卡报告生成成功！点击下方按钮即可复制/分享！", icon="✅")
                
                for idx, (c_name, c_content) in enumerate(reports.items()):
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    
                    # 💡 关键改动：计算全勤/加油/未打卡数据，并自动追加在文字下方一起复制
                    lines = c_content.split('\n')
                    f_emoji = st.session_state.emojis.get("full", "🍓")
                    p_emoji = st.session_state.emojis.get("part", "✅")
                    z_emoji = st.session_state.emojis.get("zero", "🚫")
                    
                    full_cnt, part_cnt, zero_cnt = 0, 0, 0
                    for line in lines:
                        if f_emoji in line:
                            full_cnt += 1
                        elif p_emoji in line:
                            part_cnt += 1
                        elif z_emoji in line:
                            zero_cnt += 1

                    total_students = full_cnt + part_cnt + zero_cnt
                    
                    # 拼接统计文案到报告尾部
                    final_share_content = c_content.strip()
                    if total_students > 0:
                        pct = round(full_cnt / total_students * 100)
                        stats_text = (
                            f"\n\n--------------------\n"
                            f"📊 学情统计汇总：\n"
                            f"🌟 全勤达标：{full_cnt} 人 ({pct}%)\n"
                            f"💪 持续加油：{part_cnt} 人\n"
                            f"⚠️ 未打卡提醒：{zero_cnt} 人"
                        )
                        final_share_content += stats_text

                    # 对文本中的特殊字符进行转义
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
    st.info("👈 请在左侧边栏配置班级与规则，点击 **「⚡ 一键生成打卡报告」** 即可。")
