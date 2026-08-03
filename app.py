import os
import re
import json
import time
import subprocess
from datetime import datetime, date, timedelta
import streamlit as st

# 自动补全驱动
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    subprocess.run(["pip", "install", "playwright"])
    subprocess.run(["playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="全阅读学情打卡生成器", page_icon="📚", layout="wide")

st.title("📚 全阅读学情打卡生成器")
st.caption("支持动态识别班级、自定义英文名映射、多班级独立考核标准及便捷的配置备份恢复")

# ==================== 2. Session状态初始化 ====================
if "class_rules" not in st.session_state:
    st.session_state.class_rules = {}

if "name_maps" not in st.session_state:
    st.session_state.name_maps = {}

if "username" not in st.session_state:
    st.session_state.username = ""

if "password" not in st.session_state:
    st.session_state.password = ""

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

# ==================== 3. 核心抓取逻辑 ====================
def run_automation_web(username, password, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, status_placeholder):
    login_url = "https://v2.ireadabc.com/#/admin/classes/index"
    reports_dict = {}

    with sync_playwright() as p:
        status_placeholder.info("🚀 正在启动云端后台浏览器...")
        
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

        try:
            status_placeholder.info("🔑 正在打开全阅读登录页面...")
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
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
                page.wait_for_timeout(2000)

            try:
                modal_agree_btn = page.query_selector(".el-message-box .el-button--primary, .el-dialog .el-button--primary")
                if modal_agree_btn:
                    modal_agree_btn.click()
                    page.wait_for_timeout(1000)
                    if login_button:
                        login_button.click()
            except Exception:
                pass

            status_placeholder.info("⏳ 正在进入班级列表...")
            page.wait_for_selector("tbody tr", timeout=25000)
            status_placeholder.success("✅ 登录成功！开始抓取数据...")

            rows = page.query_selector_all("tbody tr")
            class_count = len(rows)

            if class_count == 0:
                status_placeholder.warning("⚠️ 登录成功，但在该账号下没有找到任何班级。")
                browser.close()
                return {}

            for i in range(class_count):
                page.wait_for_selector("tbody tr", timeout=10000)
                rows = page.query_selector_all("tbody tr")
                if i >= len(rows):
                    break
                row = rows[i]
                
                class_name_elem = row.query_selector("td:nth-child(3)")
                if not class_name_elem:
                    continue
                class_name = class_name_elem.inner_text().strip()
                
                status_placeholder.info(f"📊 正在处理班级 ({i+1}/{class_count})：【{class_name}】...")
                
                stat_btn = row.query_selector("text=学情统计")
                if stat_btn:
                    stat_btn.click()
                    page.wait_for_timeout(3000)
                    
                    if report_type in ["周汇报", "月汇报"]:
                        date_title = "本周" if report_type == "周汇报" else "本月"
                        tab_elem = page.query_selector(f"text={report_type}")
                        if tab_elem:
                            tab_elem.click()
                            page.wait_for_timeout(3000)
                    else:
                        date_title = f"{start_date.strftime('%m月%d日')}"
                        
                        try:
                            page.click("text=自定义", timeout=5000)
                        except:
                            pass
                        page.wait_for_timeout(1500)
                        
                        try:
                            date_inputs = page.locator(".el-range-input").all()
                            if len(date_inputs) < 2:
                                date_inputs = page.locator("input[placeholder*='日期'], input.el-input__inner").all()
                            
                            if len(date_inputs) >= 2:
                                date_inputs[0].click()
                                page.keyboard.press("Control+A")
                                page.keyboard.press("Backspace")
                                date_inputs[0].fill(start_date.strftime("%Y-%m-%d"))
                                page.wait_for_timeout(300)

                                date_inputs[1].click()
                                page.keyboard.press("Control+A")
                                page.keyboard.press("Backspace")
                                date_inputs[1].fill(end_date.strftime("%Y-%m-%d"))
                                page.wait_for_timeout(300)
                                
                                page.keyboard.press("Enter")
                                page.wait_for_timeout(500)
                        except Exception as e:
                            print(f"[WARN] 填入日期异常: {e}")
                        
                        try:
                            page.click("button:has-text('查看')", timeout=5000)
                        except:
                            pass
                        page.wait_for_timeout(3000)

                    page.wait_for_selector("tbody tr", timeout=15000)
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
                    reports_dict[class_name] = md_res
                    
                    page.go_back()
                    page.wait_for_timeout(2500)

            browser.close()
            return reports_dict

        except Exception as err:
            browser.close()
            raise Exception(f"抓取中断，详细原因：{str(err)}")

# ==================== 4. 前端交互界面 ====================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1. 账号与时间选择")
    
    col1, col2 = st.columns(2)
    with col1:
        user_input = st.text_input("📱 账号", value=st.session_state.username, placeholder="请输入全阅读账号")
        st.session_state.username = user_input
    with col2:
        pwd_input = st.text_input("🔒 密码", value=st.session_state.password, type="password", placeholder="请输入密码")
        st.session_state.password = pwd_input

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
    submit_button = st.button("🚀 开始一键生成报告", type="primary", use_container_width=True)

with col_right:
    st.subheader("3. ⚙️ 班级配置与共享管理")
    
    new_class_input = st.text_input("➕ 添加要配置的班级全称：", placeholder="例如：康乐K25")
    if st.button("添加班级"):
        if new_class_input and new_class_input not in st.session_state.class_rules:
            st.session_state.class_rules[new_class_input] = {"listen": 60, "anim": 15, "books": 2}
            st.session_state.name_maps[new_class_input] = ""
            st.success(f"已成功添加班级：{new_class_input}")
            st.rerun()

    class_rules_config = {}
    name_maps_config = {}

    if not st.session_state.class_rules:
        st.info("💡 提示：您当前未设置特定班级，系统将使用左侧的【通用兜底标准】。也可以在下方快速【导入 JSON】填充数据。")
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
                
                st.session_state.class_rules[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                st.session_state.name_maps[c_name] = n_m
                
                class_rules_config[c_name] = {"listen": l_v, "anim": a_v, "books": b_v}
                name_maps_config[c_name] = n_m
                st.divider()

    st.markdown("##### 📁 本地配置文件 (导出/导入备份)")
    export_data = json.dumps({"rules": st.session_state.class_rules, "maps": st.session_state.name_maps}, ensure_ascii=False, indent=2)
    
    col_exp, col_imp = st.columns(2)
    with col_exp:
        st.download_button("📥 导出备份当前配置", data=export_data, file_name="my_config.json", mime="application/json", use_container_width=True)
    
    uploaded_file = st.file_uploader("📂 恢复本地备份 (JSON文件)", type=["json"])
    if uploaded_file is not None:
        try:
            config_data = json.load(uploaded_file)
            st.session_state.class_rules = config_data.get("rules", {})
            st.session_state.name_maps = config_data.get("maps", {})
            st.success("✅ 配置恢复成功！")
            st.rerun()
        except Exception:
            st.error("导入失败，文件格式有误。")

# ==================== 5. 执行逻辑 ====================
if submit_button:
    if not user_input or not pwd_input:
        st.warning("⚠️ 请先填写账号和密码！")
    else:
        status = st.empty()
        try:
            with st.spinner("正在后台为您抓取数据，请稍候..."):
                reports_dict = run_automation_web(
                    user_input, pwd_input, report_type, start_date, end_date, 
                    class_rules_config, name_maps_config, default_rule, status
                )
                
                if reports_dict:
                    status.success(f"🎉 成功获取 {len(reports_dict)} 个班级的打卡报告！")
                    st.divider()
                    st.subheader("📋 各班级独立打卡报告（点击右上角即可一键复制）")
                    
                    for c_name, c_content in reports_dict.items():
                        with st.container():
                            st.markdown(f"#### 📍 班级：{c_name}")
                            
                            c_col1, c_col2 = st.columns([3, 1])
                            with c_col1:
                                st.code(c_content, language=None)
                            with c_col2:
                                st.write("") 
                                st.write("")
                                c_file_name = f"{datetime.now().strftime('%Y-%m-%d')}_{c_name}_打卡反馈.md"
                                st.download_button(
                                    label=f"📥 下载文件",
                                    data=c_content,
                                    file_name=c_file_name,
                                    mime="text/markdown",
                                    key=f"dl_{c_name}",
                                    use_container_width=True
                                )
                            st.markdown("---")
                    
                    all_text = "\n\n" + ("=" * 40) + "\n\n".join(reports_dict.values())
                    st.download_button(
                        label="📦 一键打包下载所有班级报告 (Markdown)",
                        data=all_text,
                        file_name=f"{datetime.now().strftime('%Y-%m-%d')}_全部班级打卡反馈.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                else:
                    status.error("⚠️ 未能获取到任何有效数据，请确认输入的账号密码是否正确。")
        except Exception as e:
            status.error(f"❌ 运行遭遇异常：{str(e)}")
