import json
import re
import urllib.parse
from datetime import datetime, date, timedelta
import requests
import streamlit as st

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="⚡", layout="wide")

st.title("⚡ 全阅读学情打卡生成器")

# 读取 URL 参数中的持久化数据
query_params = st.query_params

stored_token = query_params.get("token", "")
stored_rules = query_params.get("rules", "")
stored_maps = query_params.get("maps", "")

# 解析 JSON 规则
try:
    init_rules = json.loads(urllib.parse.unquote(stored_rules)) if stored_rules else {}
except Exception:
    init_rules = {}

try:
    init_maps = json.loads(urllib.parse.unquote(stored_maps)) if stored_maps else {}
except Exception:
    init_maps = {}

# Session 状态同步
if "class_rules" not in st.session_state:
    st.session_state.class_rules = init_rules

if "name_maps" not in st.session_state:
    st.session_state.name_maps = init_maps

if "token" not in st.session_state:
    st.session_state.token = stored_token

# 同步并更新当前的 URL 参数
def update_url_params():
    rules_str = urllib.parse.quote(json.dumps(st.session_state.class_rules, ensure_ascii=False))
    maps_str = urllib.parse.quote(json.dumps(st.session_state.name_maps, ensure_ascii=False))
    st.query_params["token"] = st.session_state.token
    st.query_params["rules"] = rules_str
    st.query_params["maps"] = maps_str

# ==================== 工具函数 ====================
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
    class_mapping = parse_name_map(name_map_str)
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

def generate_markdown(class_name, date_title, student_list, req_listen, req_anim, req_books, name_map_str):
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
    
    return f"""[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟【今日光荣榜】
{tops_formatted}

💪【再努努力】
{mids_formatted}

⏰【该起床打卡啦】
{zeros_formatted}
"""

# ==================== 3. 自动登录与 API 抓取逻辑 ====================
def auto_login(username, password):
    login_url = "https://v2.ireadabc.com/api/login"
    payload = {
        "phone": str(username).strip(),
        "password": str(password).strip()
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://v2.ireadabc.com",
        "Referer": "https://v2.ireadabc.com/"
    }
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            res = resp.json()
            data = res.get("data", {}) if isinstance(res.get("data"), dict) else {}
            token = data.get("token") or data.get("access_token") or res.get("token") or res.get("access_token")
            if token:
                return token, None
            else:
                msg = res.get("msg") or res.get("message") or res.get("error") or "账号或密码不匹配"
                return None, msg
        else:
            return None, f"服务器响应异常({resp.status_code})"
    except Exception as e:
        return None, f"网络连接异常：{str(e)}"

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Token": auth_token,
        "Accept": "application/json, text/plain, */*",
        "Client-Type": "BROWSER"
    }
    reports_dict = {}

    try:
        classes_url = "https://v2.ireadabc.com/api/v3/reports/classes/all" 
        resp = requests.get(classes_url, headers=headers, timeout=10)
        
        classes_data = []
        if resp.status_code == 200:
            res_json = resp.json()
            classes_data = res_json.get("data", []) if isinstance(res_json, dict) else res_json

        if not classes_data or not isinstance(classes_data, list):
            classes_data = [
                {"id": "17985", "name": "康乐E4"},
                {"id": "17988", "name": "康乐K11"},
                {"id": "27935", "name": "康乐K24"},
                {"id": "49420", "name": "康乐K31"}
            ]

        if report_type == "周汇报":
            s_date = (date.today() - timedelta(days=date.today().weekday())).strftime("%Y-%m-%d")
            e_date = date.today().strftime("%Y-%m-%d")
            date_title = "本周"
        elif report_type == "月汇报":
            s_date = date.today().replace(day=1).strftime("%Y-%m-%d")
            e_date = date.today().strftime("%Y-%m-%d")
            date_title = "本月"
        else:
            s_date = start_date.strftime("%Y-%m-%d")
            e_date = end_date.strftime("%Y-%m-%d")
            date_title = start_date.strftime("%m月%d日")

        for item in classes_data:
            class_id = str(item.get("id") or item.get("class_id"))
            class_name = item.get("name") or item.get("class_name") or f"班级_{class_id}"
            
            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            params = {"start": s_date, "end": e_date}
            stat_resp = requests.get(stats_url, headers=headers, params=params, timeout=10)

            if stat_resp.status_code == 200:
                s_json = stat_resp.json()
                students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("list", []) or students_raw.get("students", [])

                students_data = []
                for s in students_raw:
                    s_name = s.get("name") or s.get("student_name") or s.get("realname", "")
                    s_listen = s.get("listen") or s.get("audio_time") or s.get("audio") or 0
                    s_anim = s.get("anim") or s.get("video_time") or s.get("video") or 0
                    s_books = s.get("book") or s.get("book_count") or s.get("homework") or 0

                    students_data.append({
                        "name": s_name, "listen": s_listen, "anim": s_anim, "books": s_books
                    })

                matched_rule = next((class_rules_config[k] for k in class_rules_config if k in class_name or class_name in k), default_rule)
                matched_name_map = next((name_maps_config[k] for k in name_maps_config if k in class_name or class_name in k), "")

                md_res = generate_markdown(
                    class_name, date_title, students_data,
                    matched_rule["listen"], matched_rule["anim"], matched_rule["books"],
                    matched_name_map
                )
                reports_dict[class_name] = md_res

        return reports_dict, None
    except Exception as e:
        return None, str(e)

# ==================== 4. 前端交互界面 ====================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1. 身份凭证与时间选择")
    
    login_tab1, login_tab2 = st.tabs(["🔐 账号密码登录", "🔑 Token 凭证"])
    
    with login_tab1:
        username_input = st.text_input("👤 手机号", placeholder="请输入全阅读手机号")
        password_input = st.text_input("🔒 密码", type="password", placeholder="请输入密码")
        
    with login_tab2:
        token_input = st.text_input("🔑 Token 凭证", value=st.session_state.token, type="password", placeholder="粘贴 Token 凭证")
        if token_input != st.session_state.token:
            st.session_state.token = token_input
            update_url_params()

    st.write("")
    report_type = st.radio("选择统计周期：", ["今日汇报", "周汇报", "月汇报", "自定义"], horizontal=True)

    start_date, end_date = date.today(), date.today()
    if report_type == "自定义":
        st.info("📅 请选择自定义的时间段：")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("开始日期", value=date.today() - timedelta(days=1))
        with col_d2:
            end_date = st.date_input("结束日期", value=date.today() - timedelta(days=1))

    st.subheader("2. 通用兜底标准（未配置班级时的默认值）")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        def_listen = st.number_input("听音要求(分)", value=60, step=5)
    with col_g2:
        def_anim = st.number_input("动画要求(分)", value=15, step=5)
    with col_g3:
        def_books = st.number_input("绘本要求(本)", value=2, step=1)
    default_rule = {"listen": def_listen, "anim": def_anim, "books": def_books}

    st.write("")
    submit_button = st.button("⚡ 一键生成所有班级打卡报告", type="primary", use_container_width=True)

with col_right:
    st.subheader("3. ⚙️ 班级配置与共享管理")
    
    new_class_input = st.text_input("➕ 添加要配置的班级全称：", placeholder="例如：康乐E4")
    if st.button("添加班级"):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
            st.session_state.name_maps[new_class_input] = ""
            update_url_params()
            st.success(f"已成功添加班级：{new_class_input}")
            st.rerun()

    class_rules_config = {}
    name_maps_config = {}

    if not st.session_state.class_rules:
        st.info("💡 提示：配置好班级后，浏览器地址栏链接会自动更新，收藏当前链接即可永久保存状态！")
    else:
        with st.expander("📋 各班级【英文名映射】与【考核标准】配置列表", expanded=True):
            for c_name in list(st.session_state.class_rules.keys()):
                col_c1, col_c2 = st.columns([4, 1])
                with col_c1:
                    st.markdown(f"#### 📍 班级：{c_name}")
                with col_c2:
                    if st.button("❌ 删除", key=f"del_{c_name}"):
                        del st.session_state.class_rules[c_name]
                        if c_name in st.session_state.name_maps:
                            del st.session_state.name_maps[c_name]
                        update_url_params()
                        st.rerun()

                c1, c2, c3 = st.columns(3)
                with c1:
                    l_v = st.number_input(f"听音(分)", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}")
                with c2:
                    a_v = st.number_input(f"动画(分)", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}")
                with c3:
                    b_v = st.number_input(f"绘本(本)", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}")
                
                n_m = st.text_area(f"英文名映射 (格式：中文名:英文名，用逗号隔开)", 
                                   value=st.session_state.name_maps.get(c_name, ""), 
                                   key=f"m_{c_name}", height=65, placeholder="例如：陈羿安:Luca, 周滢萱:Yisan")
                
                st.session_state.class_rules[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                st.session_state.name_maps[c_name] = n_m
                
                class_rules_config[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                name_maps_config[c_name] = n_m
                st.divider()

            update_url_params()

    st.markdown("##### 📁 配置导出与恢复 (跨设备共享)")
    export_data = json.dumps({"rules": st.session_state.class_rules, "maps": st.session_state.name_maps}, ensure_ascii=False, indent=2)
    
    col_exp, col_imp = st.columns(2)
    with col_exp:
        st.download_button("📥 导出当前配置 JSON", data=export_data, file_name="my_config.json", mime="application/json", use_container_width=True)
    
    uploaded_file = st.file_uploader("📂 恢复本地备份 (JSON文件)", type=["json"])
    if uploaded_file is not None:
        try:
            config_data = json.load(uploaded_file)
            st.session_state.class_rules = config_data.get("rules", {})
            st.session_state.name_maps = config_data.get("maps", {})
            update_url_params()
            st.success("✅ 配置加载成功！")
            st.rerun()
        except Exception:
            st.error("导入失败，文件格式有误。")

# ==================== 5. 执行逻辑 ====================
if submit_button:
    current_token = st.session_state.token
    
    if username_input and password_input:
        with st.spinner("🔑 正在自动登录全阅读账号..."):
            login_token, login_err = auto_login(username_input, password_input)
            if login_err:
                st.error(f"❌ 登录遇到问题：{login_err}")
            else:
                current_token = login_token
                st.session_state.token = login_token
                update_url_params()
                st.success("✅ 登录成功，Token 已记住在链接中！")

    if not current_token:
        st.warning("⚠️ 请输入有效的账号密码或粘贴 Token 凭证！")
    else:
        with st.spinner("⚡ 正在获取所有班级数据..."):
            reports, err = fetch_data_via_api(
                current_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, default_rule
            )
            
            if err:
                st.error(f"❌ 获取失败：{err}")
            elif reports:
                st.success(f"🎉 成功生成 {len(reports)} 个班级的打卡报告！")
                st.divider()
                st.subheader("📋 各班级打卡报告预览")
                
                for c_name, c_content in reports.items():
                    st.markdown(f"#### 📍 班级：{c_name}")
                    st.code(c_content, language=None)
                    c_file_name = f"{datetime.now().strftime('%Y-%m-%d')}_{c_name}_打卡反馈.md"
                    st.download_button(
                        label="📥 下载 Markdown 文件",
                        data=c_content,
                        file_name=c_file_name,
                        mime="text/markdown",
                        key=f"dl_{c_name}"
                    )
                    st.markdown("---")
