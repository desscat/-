import json
import re
from datetime import datetime, date, timedelta
import requests
import streamlit as st

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="⚡", layout="centered")

st.title("⚡ 全阅读学情打卡生成器")

# 默认的 DIY 模板样式
default_template = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟【今日光荣榜】
{tops}

💪【再努努力】
{mids}

⏰【该起床打卡啦】
{zeros}"""

# Session 状态安全初始化
if "class_rules" not in st.session_state:
    st.session_state.class_rules = {}

if "name_maps" not in st.session_state:
    st.session_state.name_maps = {}

if "token" not in st.session_state:
    st.session_state.token = ""

if "custom_template" not in st.session_state:
    st.session_state.custom_template = default_template

# ==================== 2. 工具函数 ====================
def parse_name_map(map_str):
    mapping = {}
    if not map_str:
        return mapping
    pairs = re.split(r'[,，\n]', map_str)
    for pair in pairs:
        if ":" in pair or "：" in pair:
            key, val = re.split(r'[:：]', pair, 1)
            mapping[key.strip()] = val.strip()
    return mapping

def clean_num(text):
    if text is None:
        return 0
    nums = re.findall(r'\d+', str(text))
    return int(nums[0]) if nums else 0

def process_student_data(class_name, name, listen, anim, books, req_listen, req_anim, req_books, name_map_str):
    listen = clean_num(listen)
    anim = clean_num(anim)
    books = clean_num(books)
    
    clean_name = re.sub(r'[a-zA-Z\s]', '', name)
    class_mapping = parse_name_map(map_str=name_map_str)
    eng_name = class_mapping.get(clean_name, class_mapping.get(name, name))
    
    if listen >= req_listen and anim >= req_anim and books >= req_books:
        return "TOP", f"{eng_name} (听音{listen}min, 动画{anim}min, 绘本{books}本)"
    
    if listen == 0 and anim == 0 and books == 0:
        return "ZERO", f"{eng_name}"
    
    missing = []
    if listen < req_listen:
        missing.append(f"听音{req_listen - listen}min")
    if anim < req_anim:
        missing.append(f"动画{req_anim - anim}min")
    if books < req_books:
        missing.append(f"绘本{req_books - books}本")
        
    missing_str = ", ".join(missing)
    return "MID", f"{eng_name}：已达标 (距离全勤还缺：{missing_str})"

def generate_custom_report(template_str, class_name, date_title, student_list, req_listen, req_anim, req_books, name_map_str):
    tops, mids, zeros = [], [], []
    for student in student_list:
        status, text = process_student_data(
            class_name, student['name'], student['listen'], student['anim'], student['books'],
            req_listen, req_anim, req_books, name_map_str
        )
        if status == "TOP":
            tops.append(text)
        elif status == "MID":
            mids.append(text)
        else:
            zeros.append(text)
            
    tops_formatted = "\n".join(tops) if tops else "（暂无）"
    mids_formatted = "\n\n".join(mids) if mids else "（无）"
    zeros_formatted = "\n\n".join(zeros) if zeros else "（无）"
    
    return template_str.format(
        class_name=class_name,
        date_title=date_title,
        tops=tops_formatted,
        mids=mids_formatted,
        zeros=zeros_formatted
    )

# ==================== 3. API 请求逻辑 ====================
def auto_login(username, password):
    login_url = "https://v2.ireadabc.com/api/login"
    payload = {"phone": str(username).strip(), "password": str(password).strip()}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            res = resp.json()
            # 严格对应你截图中 data 里面的 token
            data = res.get("data")
            if isinstance(data, dict):
                token = data.get("token")
                if token:
                    return token, None
            return None, res.get("message") or "登录成功但未解析到 Token"
        return None, f"服务器返回异常({resp.status_code})"
    except Exception as e:
        return None, f"网络错误：{str(e)}"

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, template_str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Token": auth_token.strip(),
        "Client-Type": "BROWSER"
    }
    reports_dict = {}

    try:
        classes_url = "https://v2.ireadabc.com/api/v3/reports/classes/all" 
        resp = requests.get(classes_url, headers=headers, timeout=20)
        
        if resp.status_code != 200:
            return None, f"Token 验证失效或服务器返回异常 ({resp.status_code})，请检查账号密码或 Token 是否正确。"
            
        res_json = resp.json()
        classes_data = res_json.get("data", [])

        if not classes_data:
            return None, "当前账号获取到的班级列表为空，可能是账号错误或该账号下无管理班级。"

        days_count = 1
        if report_type == "昨日汇报":
            yest = date.today() - timedelta(days=1)
            s_date = yest.strftime("%Y-%m-%d")
            e_date = s_date
            date_title = yest.strftime("%m月%d日")
            days_count = 1
        elif report_type == "周汇报":
            d_start = date.today() - timedelta(days=date.today().weekday())
            d_end = date.today()
            s_date = d_start.strftime("%Y-%m-%d")
            e_date = d_end.strftime("%Y-%m-%d")
            date_title = f"{s_date}至{e_date}"
            days_count = (d_end - d_start).days + 1
        elif report_type == "月汇报":
            d_start = date.today().replace(day=1)
            d_end = date.today()
            s_date = d_start.strftime("%Y-%m-%d")
            e_date = s_date
            date_title = f"{s_date}至{e_date}"
            days_count = (d_end - d_start).days + 1
        elif report_type == "自定义时间":
            s_date = start_date.strftime("%Y-%m-%d")
            e_date = end_date.strftime("%Y-%m-%d")
            date_title = f"{s_date}至{e_date}" if s_date != e_date else start_date.strftime("%m月%d日")
            days_count = (end_date - start_date).days + 1
            if days_count < 1:
                days_count = 1
        else:
            yest = date.today() - timedelta(days=1)
            s_date = yest.strftime("%Y-%m-%d")
            e_date = s_date
            date_title = yest.strftime("%m月%d日")
            days_count = 1

        for item in classes_data:
            class_id = str(item.get("id") or item.get("class_id"))
            class_name = item.get("name") or item.get("class_name") or f"班级_{class_id}"
            
            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            params = {"start": s_date, "end": e_date}
            stat_resp = requests.get(stats_url, headers=headers, params=params, timeout=20)

            if stat_resp.status_code == 200:
                s_json = stat_resp.json()
                students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("list", []) or students_raw.get("students", [])

                students_data = []
                for s in students_raw:
                    students_data.append({
                        "name": s.get("name") or s.get("student_name") or "",
                        "listen": s.get("listen") or s.get("audio_time") or 0,
                        "anim": s.get("animation") or s.get("anim") or s.get("video_time") or 0,
                        "books": s.get("grading") or s.get("read") or s.get("book") or s.get("book_count") or 0
                    })

                base_rule = next((class_rules_config[k] for k in class_rules_config if k in class_name or class_name in k), default_rule)
                matched_rule = {
                    "listen": base_rule["listen"] * days_count,
                    "anim": base_rule["anim"] * days_count,
                    "books": base_rule["books"] * days_count
                }

                matched_name_map = next((name_maps_config[k] for k in name_maps_config if k in class_name or class_name in k), "")

                md_res = generate_custom_report(
                    template_str, class_name, date_title, students_data,
                    matched_rule["listen"], matched_rule["anim"], matched_rule["books"],
                    matched_name_map
                )
                reports_dict[class_name] = md_res

        return reports_dict, None
    except Exception as e:
        return None, str(e)

# ==================== 4. 界面展示 ====================
st.subheader("1. 身份凭证与时间选择")

# 重置按钮
if st.button("🧹 清空当前凭证缓存", type="secondary"):
    st.session_state.token = ""
    st.session_state.class_rules = {}
    st.session_state.name_maps = {}
    st.session_state.custom_template = default_template
    st.rerun()

login_tab1, login_tab2 = st.tabs(["🔐 账号密码登录 (推荐)", "🔑 Token 凭证"])
with login_tab1:
    username_input = st.text_input("👤 手机号", placeholder="请输入要切换账号的手机号")
    password_input = st.text_input("🔒 密码", type="password", placeholder="请输入对应的密码")
with login_tab2:
    token_input = st.text_input("🔑 Token 凭证", value=st.session_state.token, type="password")
    if token_input != st.session_state.token:
        st.session_state.token = token_input

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
with st.expander("✨ 点击展开/收起：自由编辑排版和文案样式", expanded=False):
    custom_template_input = st.text_area(
        "修改下方的模板内容：",
        value=st.session_state.custom_template,
        height=220
    )
    if custom_template_input != st.session_state.custom_template:
        st.session_state.custom_template = custom_template_input

st.subheader("4. ⚙️ 班级规则与英文映射")
new_class_input = st.text_input("➕ 添加班级全称：", placeholder="例如：康乐E4")
if st.button("添加班级"):
    if new_class_input and new_class_input not in st.session_state.class_rules:
        st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
        st.session_state.name_maps[new_class_input] = ""
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
            st.rerun()

    c1, c2, c3 = st.columns(3)
    l_v = c1.number_input(f"每日听音", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}")
    a_v = c2.number_input(f"每日动画", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}")
    b_v = c3.number_input(f"每日绘本", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}")
    
    n_m = st.text_area(f"映射 (中文:英文)", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=65)
    
    st.session_state.class_rules[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
    st.session_state.name_maps[c_name] = n_m
    class_rules_config[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
    name_maps_config[c_name] = n_m

st.divider()
submit_button = st.button("⚡ 一键生成所有班级打卡报告", type="primary", use_container_width=True)

if submit_button:
    final_token = ""
    
    # 如果在 Tab 1 填了手机号和密码，直接通过登录接口换取新 Token
    if username_input and password_input:
        with st.spinner("🔑 正在通过账号密码自动登录获取新凭证..."):
            login_token, login_err = auto_login(username_input, password_input)
            if login_err:
                st.error(f"❌ 登录失败：{login_err}")
                st.stop()
            else:
                final_token = login_token
    else:
        # 否则使用 Tab 2 的 Token
        final_token = st.session_state.token

    if not final_token:
        st.warning("⚠️ 请在上方“账号密码登录”标签页输入手机号和密码，或在“Token 凭证”标签页输入 Token！")
    else:
        with st.spinner("⚡ 正在获取对应账号的全阅读打卡数据..."):
            reports, err = fetch_data_via_api(
                final_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, default_rule, 
                st.session_state.custom_template
            )
            if err:
                st.error(f"❌ 错误：{err}")
            elif reports:
                st.success("🎉 数据获取成功！")
                for c_name, c_content in reports.items():
                    st.markdown(f"### 📍 {c_name} 打卡报告")
                    st.code(c_content, language=None)
