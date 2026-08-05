import json
import streamlit as st
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="⚡", layout="wide")

st.title("⚡ 全阅读学情打卡生成器")

# ==================== 1. URL 持久化 ====================
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
url_emojis = json.loads(params.get("emojis", '{"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}'))

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

# ==================== 2. 左侧边栏 ====================
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
        report_type = "周汇报"
        start_date, end_date = date.today(), date.today()
    else:
        report_type = st.radio("统计周期", ["昨日汇报", "周汇报", "月汇报", "自定义时间"])
        start_date, end_date = date.today(), date.today()
        if report_type == "自定义时间":
            start_date = st.date_input("开始日期", value=date.today() - timedelta(days=1))
            end_date = st.date_input("结束日期", value=date.today())

    st.subheader("3. 🎨 DIY 格式与 Emoji 自定义")
    with st.expander("✨ 点击展开/修改模板与 Emoji", expanded=False):
        if output_mode == "🍓 矩阵式周打卡榜":
            st.markdown("**自定义 Emoji 标记：**")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_full = st.text_input("全勤达标", value=st.session_state.emojis.get("full", "🍓"))
                e_part = st.text_input("部分达标", value=st.session_state.emojis.get("part", "✅"))
            with col_e2:
                e_zero = st.text_input("未打卡", value=st.session_state.emojis.get("zero", "🚫"))
                e_badge = st.text_input("满勤尾巴标记", value=st.session_state.emojis.get("badge", "✔️"))
            
            st.session_state.emojis = {"full": e_full, "part": e_part, "zero": e_zero, "badge": e_badge}
            
            st.markdown("**自定义矩阵模板：**")
            mat_tmpl_input = st.text_area("矩阵模板", value=st.session_state.matrix_template, height=150)
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

# ==================== 3. 主界面（打卡结果） ====================
if btn_generate:
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
        with st.spinner("⚡ 正在获取全阅读打卡数据..."):
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
                st.success("🎉 打卡报告生成成功！")
                for c_name, c_content in reports.items():
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    st.code(c_content, language=None)
else:
    st.info("👈 请在左侧边栏设置规则与 Emoji，点击 **「⚡ 一键生成打卡报告」** 即可。")
