import json
import re
from datetime import datetime, date, timedelta
import requests
import streamlit as st

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="全阅读学情打卡生成器 (API极速版)", page_icon="⚡", layout="wide")

st.title("⚡ 全阅读学情打卡生成器 (API直连版)")
st.caption("采用后端 API 直接通信，毫秒级响应，告别浏览器卡顿与超时问题")

# ==================== 2. Session状态初始化 ====================
if "class_rules" not in st.session_state:
    st.session_state.class_rules = {}

if "name_maps" not in st.session_state:
    st.session_state.name_maps = {}

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

# ==================== 3. 核心 API 抓取逻辑 ====================
def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Authorization": auth_token,
        "Accept": "application/json, text/plain, */*"
    }
    
    reports_dict = {}

    # 1. 请求班级列表 API（如果网络请求路径有差别，可根据 F12 微调 URL）
    classes_url = "https://v2.ireadabc.com/api/admin/classes" 
    
    try:
        resp = requests.get(classes_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"Token 无效或接口响应异常，状态码：{resp.status_code}")
        
        classes_data = resp.json().get("data", [])
        if not classes_data:
            return {}, "未获取到班级信息，请检查 Token 是否过期。"

        # 2. 遍历班级获取学情数据
        for item in classes_data:
            class_id = item.get("id")
            class_name = item.get("name", f"班级_{class_id}")
            
            # 构建学情查询 API 参数
            stats_url = f"https://v2.ireadabc.com/api/admin/classes/{class_id}/student-statistics"
            params = {}
            
            if report_type == "周汇报":
                params["type"] = "week"
                date_title = "本周"
            elif report_type == "月汇报":
                params["type"] = "month"
                date_title = "本月"
            else:
                params["start_date"] = start_date.strftime("%Y-%m-%d")
                params["end_date"] = end_date.strftime("%Y-%m-%d")
                date_title = start_date.strftime("%m月%d日")

            stat_resp = requests.get(stats_url, headers=headers, params=params, timeout=10)
            if stat_resp.status_code == 200:
                students_raw = stat_resp.json().get("data", [])
                students_data = []
                for s in students_raw:
                    students_data.append({
                        "name": s.get("name", ""),
                        "listen": s.get("audio_time", 0),  # 根据实际字段替换
                        "anim": s.get("video_time", 0),
                        "books": s.get("book_count", 0)
                    })

                # 匹配规则与英文名映射
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
    st.subheader("1. 凭证与时间选择")
    
    auth_token = st.text_input("🔑 Authorization / Token", type="password", placeholder="粘贴从 F12 获取的 Token 字符串")
    
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
    submit_button = st.button("⚡ 毫秒级生成报告", type="primary", use_container_width=True)

with col_right:
    st.subheader("3. ⚙️ 班级配置管理")
    
    new_class_input = st.text_input("➕ 添加要配置的班级全称：", placeholder="例如：康乐K25")
    if st.button("添加班级"):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
            st.session_state.name_maps[new_class_input] = ""
            st.success(f"已成功添加班级：{new_class_input}")
            st.rerun()

    class_rules_config = {}
    name_maps_config = {}

    if st.session_state.class_rules:
        with st.expander("📋 各班级配置列表", expanded=True):
            for c_name in list(st.session_state.class_rules.keys()):
                col_c1, col_c2 = st.columns([4, 1])
                with col_c1:
                    st.markdown(f"#### 📍 班级：{c_name}")
                with col_c2:
                    if st.button("❌ 删除", key=f"del_{c_name}"):
                        del st.session_state.class_rules[c_name]
                        if c_name in st.session_state.name_maps:
                            del st.session_state.name_maps[c_name]
                        st.rerun()

                c1, c2, c3 = st.columns(3)
                with c1:
                    l_v = st.number_input(f"听音(分)", value=st.session_state.class_rules[c_name]["listen"], step=5, key=f"l_{c_name}")
                with c2:
                    a_v = st.number_input(f"动画(分)", value=st.session_state.class_rules[c_name]["anim"], step=5, key=f"a_{c_name}")
                with c3:
                    b_v = st.number_input(f"绘本(本)", value=st.session_state.class_rules[c_name]["books"], step=1, key=f"b_{c_name}")
                
                n_m = st.text_area(f"英文名映射", value=st.session_state.name_maps.get(c_name, ""), key=f"m_{c_name}", height=65)
                
                st.session_state.class_rules[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                st.session_state.name_maps[c_name] = n_m
                
                class_rules_config[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                name_maps_config[c_name] = n_m
                st.divider()

# ==================== 5. 执行逻辑 ====================
if submit_button:
    if not auth_token:
        st.warning("⚠️ 请输入从浏览器获取的 Token 凭证！")
    else:
        with st.spinner("正在请求 API 获取学情数据..."):
            reports, err = fetch_data_via_api(
                auth_token, report_type, start_date, end_date, 
                class_rules_config, name_maps_config, default_rule
            )
            
            if err:
                st.error(f"❌ 获取失败：{err}")
            elif reports:
                st.success(f"🎉 成功生成 {len(reports)} 个班级的打卡报告！")
                for c_name, c_content in reports.items():
                    st.markdown(f"#### 📍 班级：{c_name}")
                    st.code(c_content, language=None)
