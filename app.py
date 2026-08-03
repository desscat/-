import os
import re
import json
import time
import subprocess
from datetime import datetime, date, timedelta
import streamlit as st
from streamlit_local_storage import LocalStorage

# 云端自动补全下载 Chromium 驱动
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    subprocess.run(["pip", "install", "playwright"])
    subprocess.run(["playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright

# 初始化本地存储对象
local_storage = LocalStorage()

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="📚", layout="wide")

st.title("📚 全阅读学情打卡生成器")
st.caption("支持动态识别班级、自定义英文名映射、多班级独立考核标准（数据保存在本地浏览器，不影响他人）")

# ==================== 2. Session状态初始化 (默认清空，由用户自己填) ====================
if "user_input" not in st.session_state:
    st.session_state.user_input = ""
if "pwd_input" not in st.session_state:
    st.session_state.pwd_input = ""
if "class_rules" not in st.session_state:
    st.session_state.class_rules = {}
if "name_maps" not in st.session_state:
    st.session_state.name_maps = {}

# ==================== 本地缓存读写逻辑 ====================
st.sidebar.title("🛠️ 本地偏好设置")
st.sidebar.caption("数据保存在您的浏览器本地，其他人无法查看。")

col_save, col_load = st.sidebar.columns(2)

with col_save:
    if st.button("💾 保存配置到本地", use_container_width=True):
        config_to_save = {
            "user": st.session_state.get("user_input_val", ""),
            "pwd": st.session_state.get("pwd_input_val", ""),
            "rules": st.session_state.class_rules,
            "maps": st.session_state.name_maps
        }
        local_storage.setItem("iread_user_config", json.dumps(config_to_save, ensure_ascii=False))
        st.sidebar.success("✅ 配置已成功保存至当前浏览器！")

with col_load:
    if st.button("🔄 读取本地已存配置", use_container_width=True):
        saved_data = local_storage.getItem("iread_user_config")
        if saved_data:
            try:
                data = json.loads(saved_data)
                st.session_state.user_input = data.get("user", "")
                st.session_state.pwd_input = data.get("pwd", "")
                st.session_state.class_rules = data.get("rules", {})
                st.session_state.name_maps = data.get("maps", {})
                st.sidebar.success("✅ 读取成功！")
                st.rerun()
            except Exception:
                st.sidebar.error("❌ 读取失败，本地数据解析异常。")
        else:
            st.sidebar.warning("⚠️ 未检测到本地历史配置。")

if st.sidebar.button("🗑️ 清空本地已存配置", use_container_width=True):
    local_storage.deleteItem("iread_user_config")
    st.session_state.class_rules = {}
    st.session_state.name_maps = {}
    st.session_state.user_input = ""
    st.session_state.pwd_input = ""
    st.sidebar.info("已清空本地配置！")
    st.rerun()

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

# ==================== 3. 核心无头抓取逻辑 ====================
def run_automation_web(username, password, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, status_placeholder):
    login_url = "https://v2.ireadabc.com/#/admin/classes/index"
    all_reports = []

    with sync_playwright() as p:
        status_placeholder.info("🚀 正在启动后台程序...")
        
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        status_placeholder.info("🔑 正在打开登录页面...")
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_selector("input", timeout=20000)
        
        inputs = page.query_selector_all("input[type='text'], input[type='password'], input:not([type='checkbox'])")
        if len(inputs) >= 2:
            inputs[0].fill(username)
            inputs[1].fill(password)

        checkbox = page.query_selector("input[type='checkbox']")
        if checkbox and not checkbox.is_checked():
            checkbox.click()
            page.wait_for_timeout(300)

        login_button = page.query_selector("button:has-text('登录'), .el-button--primary")
        if login_button:
            login_button.click()
            page.wait_for_timeout(1500)

        try:
            modal_agree_btn = page.query_selector(".el-message-box .el-button--primary, .el-dialog .el-button--primary")
            if modal_agree_btn:
                modal_agree_btn.click()
                page.wait_for_timeout(1000)
                if login_button:
                    login_button.click()
        except Exception:
            pass

        status_placeholder.info("⏳ 正在验证登录...")
        page.wait_for_selector("text=班级管理", timeout=25000)
        status_placeholder.success("✅ 登录成功！开始抓取班级学情数据...")

        if report_type == "今日汇报":
            date_title = datetime.now().strftime("%m月%d日")
        elif report_type == "周汇报":
            date_title = "本周"
        elif report_type == "月汇报":
            date_title = "本月"
        else:
            date_title = f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}"

        page.wait_for_selector("tbody tr", timeout=15000)
        rows = page.query_selector_all("tbody tr")
        class_count = len(rows)

        for i in range(class_count):
            rows = page.query_selector_all("tbody tr")
            if i >= len(rows):
                break
            row = rows[i]
            
            class_name_elem = row.query_selector("td:nth-child(3)")
            if not class_name_elem:
                continue
            class_name = class_name_elem.inner_text().strip()
            
            status_placeholder.info(f"📊 正在处理班级：{class_name} ({i+1}/{class_count})...")
            
            stat_btn = row.query_selector("text=学情统计")
            if stat_btn:
                stat_btn.click()
                page.wait_for_timeout(3000)
                
                if report_type in ["今日汇报", "周汇报", "月汇报"]:
                    tab_elem = page.query_selector(f"text={report_type}")
                    if tab_elem:
                        tab_elem.click()
                        page.wait_for_timeout(2500)
                elif report_type == "自定义":
                    custom_tab = page.query_selector("text=自定义")
                    if custom_tab:
                        custom_tab.click()
                        page.wait_for_timeout(1500)
                    
                    date_inputs = page.query_selector_all(".el-range-input, input[placeholder*='日期']")
                    if len(date_inputs) >= 2:
                        date_inputs[0].click()
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        date_inputs[0].type(start_date.strftime("%Y-%m-%d"))
                        page.wait_for_timeout(300)

                        date_inputs[1].click()
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        date_inputs[1].type(end_date.strftime("%Y-%m-%d"))
                        page.wait_for_timeout(300)
                        
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(500)
                    
                    search_btn = page.query_selector("button:has-text('查看')")
                    if search_btn:
                        search_btn.click()
                        page.wait_for_timeout(3000)

                page.wait_for_selector("tbody tr", timeout=10000)
                student_rows = page.query_selector_all("tbody tr")
                students_data = []
                
                for s_row in student_rows:
                    cols = s_row.query_selector_all("td")
                    if len(cols) >= 5:
                        s_name = cols[1].inner_text().strip()
                        s_listen = cols[2].inner_text().strip() or "0"
                        s_anim = cols[3].inner_text().strip() or "0"
                        s_books = cols[4].inner_text().strip() or "0"
                        
                        students_data.append({
                            "name": s_name,
                            "listen": s_listen,
                            "anim": s_anim,
                            "books": s_books
                        })
                
                matched_rule = None
                matched_name_map = ""
                
                for key in class_rules_config:
                    if key in class_name or class_name in key:
                        matched_rule = class_rules_config[key]
                        break
                if not matched_rule:
                    matched_rule = default_rule

                for key in name_maps_config:
                    if key in class_name or class_name in key:
                        matched_name_map = name_maps_config[key]
                        break

                req_listen = matched_rule["listen"]
                req_anim = matched_rule["anim"]
                req_books = matched_rule["books"]
                
                md_res = generate_markdown(class_name, date_title, students_data, req_listen, req_anim, req_books, matched_name_map)
                all_reports.append(md_res)
                
                page.go_back()
                page.wait_for_timeout(2500)

        browser.close()
        return "\n\n" + ("=" * 40) + "\n\n".join(all_reports)

# ==================== 4. 前端交互界面 ====================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1. 账号与时间选择")
    col1, col2 = st.columns(2)
    with col1:
        user_input = st.text_input("📱 账号", value=st.session_state.user_input, placeholder="请输入全阅读账号", key="user_input_val")
    with col2:
        pwd_input = st.text_input("🔒 密码", value=st.session_state.pwd_input, type="password", placeholder="请输入密码", key="pwd_input_val")

    report_type = st.radio("选择统计周期：", ["今日汇报", "周汇报", "月汇报", "自定义"], horizontal=True)

    start_date, end_date = date.today(), date.today()
    if report_type == "自定义":
        st.info("📅 请选择自定义的时间段：")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("开始日期", value=date.today() - timedelta(days=1))
        with col_d2:
            end_date = st.date_input("结束日期", value=date.today() - timedelta(days=1))

    st.subheader("2. 通用兜底标准（未单独配置时的默认值）")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        def_listen = st.number_input("听音要求(分)", value=60, step=5)
    with col_g2:
        def_anim = st.number_input("动画要求(分)", value=15, step=5)
    with col_g3:
        def_books = st.number_input("绘本要求(本)", value=2, step=1)
    default_rule = {"listen": def_listen, "anim": def_anim, "books": def_books}

    st.write("")
    submit_button = st.button("🚀 开始一键生成报告", type="primary", use_container_width=True)

with col_right:
    st.subheader("3. ⚙️ 班级管理与个性化配置")
    
    new_class_input = st.text_input("➕ 添加要配置的班级全称：", placeholder="例如：康乐K25")
    if st.button("添加班级"):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
            st.session_state.name_maps[new_class_input] = ""
            st.success(f"已成功添加班级：{new_class_input}")

    class_rules_config = {}
    name_maps_config = {}

    if not st.session_state.class_rules:
        st.info("💡 提示：当前暂未配置任何特定班级，系统将使用左侧的【通用兜底标准】。您可以在上方输入班级名进行自定义。")
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
                                   key=f"m_{c_name}", height=65, placeholder="例如：张三:Tom, 李四:Jerry")
                
                class_rules_config[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                name_maps_config[c_name] = n_m
                st.divider()

    st.markdown("##### 📁 配置 JSON 文件的备份/恢复")
    export_data = json.dumps({"rules": class_rules_config, "maps": name_maps_config}, ensure_ascii=False, indent=2)
    st.download_button("📥 导出当前配置JSON", data=export_data, file_name="my_class_config.json", mime="application/json")

    uploaded_file = st.file_uploader("📂 导入配置 JSON", type=["json"])
    if uploaded_file is not None:
        try:
            config_data = json.load(uploaded_file)
            st.session_state.class_rules = config_data.get("rules", {})
            st.session_state.name_maps = config_data.get("maps", {})
            st.success("✅ 配置导入成功！")
        except Exception:
            st.error("导入失败，文件格式有误。")

# ==================== 5. 执行逻辑 ====================
if submit_button:
    if not user_input or not pwd_input:
        st.warning("⚠️ 请先填写账号和密码！")
    else:
        status = st.empty()
        try:
            with st.spinner("数据抓取中，请稍候..."):
                final_result = run_automation_web(
                    user_input, pwd_input, report_type, start_date, end_date, 
                    class_rules_config, name_maps_config, default_rule, status
                )
                if final_result and final_result.strip():
                    status.success("🎉 打卡报告生成完毕！")
                    st.subheader("📋 报告内容：")
                    st.text_area("复制结果", value=final_result, height=450)
                    
                    today_file = f"{datetime.now().strftime('%Y-%m-%d')}_{report_type}_打卡反馈.md"
                    st.download_button(
                        label="📥 下载 Markdown 文件",
                        data=final_result,
                        file_name=today_file,
                        mime="text/markdown"
                    )
                else:
                    status.error("⚠️ 未能获取到有效的班级数据，请检查账号密码或网络连接。")
        except Exception as e:
            status.error(f"❌ 运行遇到错误：{str(e)}")
