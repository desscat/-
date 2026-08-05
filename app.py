import json
import streamlit as st
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, DEFAULT_TEMPLATE

st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="⚡", layout="centered")

st.title("⚡ 全阅读学情打卡生成器")

# ==================== 1. URL 链接持久化保存 ====================
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

if "token" not in st.session_state:
    st.session_state.token = url_token
if "class_rules" not in st.session_state:
    st.session_state.class_rules = url_rules
if "name_maps" not in st.session_state:
    st.session_state.name_maps = url_maps
if "custom_template" not in st.session_state:
    st.session_state.custom_template = url_template

def save_to_url():
    """将规则、映射与模板自动保存至 URL 参数"""
    st.query_params["token"] = st.session_state.token
    st.query_params["rules"] = json.dumps(st.session_state.class_rules, ensure_ascii=False)
    st.query_params["maps"] = json.dumps(st.session_state.name_maps, ensure_ascii=False)
    st.query_params["template"] = st.session_state.custom_template

# ==================== 2. 界面展示 ====================
st.subheader("1. 身份凭证与时间选择")

if st.button("🧹 重置并清空所有配置", type="secondary"):
    st.query_params.clear()
    st.session_state.token = ""
    st.session_state.class_rules = {}
    st.session_state.name_maps = {}
    st.session_state.custom_template = DEFAULT_TEMPLATE
    st.rerun()

login_tab1, login_tab2 = st.tabs(["🔐 账号密码登录 (推荐)", "🔑 Token 凭证"])
with login_tab1:
    username_input = st.text_input("👤 手机号", placeholder="请输入账号手机号")
    password_input = st.text_input("🔒 密码", type="password", placeholder="请输入密码")
with login_tab2:
    token_input = st.text_input("🔑 Token 凭证", value=st.session_state.token, type="password")
    if token_input != st.session_state.token:
        st.session_state.token = token_input
        save_to_url()

report_type = st.radio("选择统计周期：", ["昨日汇报", "周汇报", "月汇报", "自定义时间"], horizontal=True)

start_date, end_date = date.today(), date.today()
if report_type == "自定义时间":
    st.info("📅 请选择开始和结束日期：")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("开始日期", value=date.today() - timedelta(days=1))
    with col_d2:
        end_date = st.date_input("结束日期", value=date.today())

st.subheader("2. 通用兜底标准（每日基准）")
col_g1, col_g2, col_g3 = st.columns(3)
with col_g1:
    def_listen = st.number_input("每日默认听音(分)", value=60, step=5)
with col_g2:
    def_anim = st.number_input("每日默认动画(分)", value=15, step=5)
with col_g3:
    def_books = st.number_input("每日默认绘本(本)", value=2, step=1)
default_rule = {"listen": def_listen, "anim": def_anim, "books": def_books}

st.subheader("3. 🎨 DIY 自定义报告模板样式")
with st.expander("✨ 点击展开/编辑文案排版样式", expanded=False):
    custom_template_input = st.text_area("编辑模板内容：", value=st.session_state.custom_template, height=200)
    if custom_template_input != st.session_state.custom_template:
        st.session_state.custom_template = custom_template_input
        save_to_url()

st.subheader("4. ⚙️ 动态添加/配置班级与英文映射")
new_class_input = st.text_input("➕ 添加班级全称：", placeholder="例如：万达K12班")
if st.button("添加班级"):
    if new_class_input and new_class_input not in st.session_state.class_rules:
        st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
        st.session_state.name_maps[new_class_input] = ""
        save_to_url()
        st.rerun()

class_rules_config = {}
name_maps_config = {}

for c_name in list(st.session_state.class_rules.keys()):
    c_head, c_del = st.columns([4, 1])
    with c_head:
        st.markdown(f"**📍 班级：{c_name}**")
    with c_del:
        if st.button("❌ 删除", key=f"del_{c_name}"):
            del st.session_state.class_rules[c_name]
            if c_name in st.session_state.name_maps:
                del st.session_state.name_maps[c_name]
            save_to_url()
            st.rerun()

    c1, c2, c3 = st.columns(3)
    def update_rule(c=c_name):
        st.session_state.class_rules[c]["listen"] = st.session_state[f"l_{c}"]
        st.session_state.class_rules[c]["anim"] = st.session_state[f"a_{c}"]
        st.session_state.class_rules[c]["books"] = st.session_state[f"b_{c}"]
        save_to_url()

    def update_map(c=c_name):
        st.session_state.name_maps[c] = st.session_state[f"m_{c}"]
        save_to_url()

    c1.number_input("每日听音", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}", on_change=update_rule)
    c2.number_input("每日动画", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}", on_change=update_rule)
    c3.number_input("每日绘本", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}", on_change=update_rule)
    st.text_area("姓名映射 (中文:英文)", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=65, on_change=update_map)

    class_rules_config[c_name] = st.session_state.class_rules[c_name]
    name_maps_config[c_name] = st.session_state.name_maps.get(c_name, "")

st.divider()
if st.button("⚡ 一键生成所有班级打卡报告", type="primary", use_container_width=True):
    final_token = ""
    if username_input and password_input:
        with st.spinner("🔑 正在登录获取凭证..."):
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
        st.warning("⚠️ 请在上方输入手机号密码或 Token！")
    else:
        with st.spinner("⚡ 正在获取全阅读打卡数据..."):
            reports, err = fetch_data_via_api(
                final_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, default_rule, 
                st.session_state.custom_template
            )
            if err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                st.success("🎉 数据生成成功！")
                for c_name, c_content in reports.items():
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    st.code(c_content, language=None)
