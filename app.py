import streamlit as st
import pandas as pd
from datetime import date, timedelta
import re
import json
import os
from supabase import create_client, Client
from iread_core import fetch_data_via_api, auto_login, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

# ---------------- Streamlit 页面配置 ----------------
st.set_page_config(
    page_title="全阅读学情打卡生成器",
    page_icon="⚡",
    layout="wide"
)

# ---------------- Supabase 云端数据库初始化 ----------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

supabase = init_supabase()

def load_config_from_db():
    if not supabase:
        return {}
    try:
        response = supabase.table("app_configs").select("*").eq("id", "user_config").execute()
        if response.data:
            return response.data[0].get("config_data", {})
    except Exception:
        pass
    return {}

def save_config_to_db(config_data):
    if not supabase:
        return False
    try:
        supabase.table("app_configs").upsert({"id": "user_config", "config_data": config_data}).execute()
        return True
    except Exception:
        return False

# ---------------- 初始化 Session State ----------------
db_config = load_config_from_db()

if "auth_token" not in st.session_state:
    st.session_state.auth_token = db_config.get("auth_token", "")
if "emojis" not in st.session_state:
    st.session_state.emojis = db_config.get("emojis", {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"})
if "class_rules" not in st.session_state:
    st.session_state.class_rules = db_config.get("class_rules", {})
if "name_maps" not in st.session_state:
    st.session_state.name_maps = db_config.get("name_maps", {})
if "matrix_template" not in st.session_state:
    st.session_state.matrix_template = db_config.get("matrix_template", DEFAULT_MATRIX_TEMPLATE)
if "traditional_template" not in st.session_state:
    st.session_state.traditional_template = db_config.get("traditional_template", DEFAULT_TEMPLATE)

def sync_to_db():
    current_config = {
        "auth_token": st.session_state.auth_token,
        "emojis": st.session_state.emojis,
        "class_rules": st.session_state.class_rules,
        "name_maps": st.session_state.name_maps,
        "matrix_template": st.session_state.matrix_template,
        "traditional_template": st.session_state.traditional_template
    }
    save_config_to_db(current_config)

# ---------------- 侧边栏设置 (侧边 UI 完整还原) ----------------
with st.sidebar:
    st.header("⚙️ 系统设置 & 配置存储")
    
    st.subheader("🔑 账号登录")
    username = st.text_input("手机号", value="")
    password = st.text_input("密码", type="password", value="")
    
    if st.button("自动登录获取 Token"):
        if username and password:
            token, err = auto_login(username, password)
            if token:
                st.session_state.auth_token = token
                sync_to_db()
                st.success("登录成功！Token 已自动填入并保存")
            else:
                st.error(f"登录失败: {err}")
        else:
            st.warning("请输入手机号和密码")

    token_input = st.text_input("Token (可手动粘贴)", value=st.session_state.auth_token)
    if token_input != st.session_state.auth_token:
        st.session_state.auth_token = token_input
        sync_to_db()

    st.markdown("---")
    st.subheader("🎨 矩阵模式图标配置")
    
    full_in = st.text_input("全勤图标 (三项全满)", value=st.session_state.emojis.get("full", "🥇"))
    part_in = st.text_input("部分达标图标 (加油)", value=st.session_state.emojis.get("part", "🏆"))
    zero_in = st.text_input("未打卡图标", value=st.session_state.emojis.get("zero", "❌"))
    badge_in = st.text_input("全勤尾巴徽章", value=st.session_state.emojis.get("badge", "👑"))

    if (full_in != st.session_state.emojis.get("full") or 
        part_in != st.session_state.emojis.get("part") or 
        zero_in != st.session_state.emojis.get("zero") or 
        badge_in != st.session_state.emojis.get("badge")):
        st.session_state.emojis = {"full": full_in, "part": part_in, "zero": zero_in, "badge": badge_in}
        sync_to_db()

    st.markdown("---")
    if st.button("🧹 清空/重置所有配置", type="secondary"):
        st.session_state.auth_token = ""
        st.session_state.emojis = {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"}
        st.session_state.class_rules = {}
        st.session_state.name_maps = {}
        st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
        st.session_state.traditional_template = DEFAULT_TEMPLATE
        sync_to_db()
        st.rerun()

# ---------------- 主界面 ----------------
st.title("⚡ 全阅读学情打卡生成器")

col1, col2 = st.columns(2)
with col1:
    mode = st.radio("选择汇报模式", ["矩阵日历模式 (matrix)", "传统分组模式 (traditional)"], index=0)
    mode_key = "matrix" if "matrix" in mode else "traditional"

with col2:
    date_option = st.radio("时间范围", ["本周 (周一至昨天)", "自定义日期"], index=0)

today = date.today()
yesterday = today - timedelta(days=1)

if date_option == "本周 (周一至昨天)":
    start_date = today - timedelta(days=today.weekday())
    end_date = yesterday if yesterday >= start_date else start_date
else:
    c_start, c_end = st.columns(2)
    with c_start:
        start_date = st.date_input("开始日期", value=today - timedelta(days=7))
    with c_end:
        end_date = st.date_input("结束日期", value=yesterday)

default_rule = {"listen": 20, "anim": 10, "books": 1}

# ---------------- 高级配置 Expander ----------------
with st.expander("⚙️ 高级配置 (班级规则与姓名映射)", expanded=False):
    tab_rule, tab_map, tab_tpl = st.tabs(["🎯 班级规则配置", "🔤 英文名映射", "📝 汇报模板编辑"])

    with tab_rule:
        st.markdown("##### 独立班级目标设置 (留空则使用默认规则: 20/10/1)")
        class_input = st.text_input("需要单独配置的班级名称 (例如: 康乐E4)")
        if class_input:
            c1, c2, c3 = st.columns(3)
            with c1:
                t_listen = st.number_input("听音目标(分钟)", value=st.session_state.class_rules.get(class_input, {}).get("listen", 20))
            with c2:
                t_anim = st.number_input("动画目标(分钟)", value=st.session_state.class_rules.get(class_input, {}).get("anim", 10))
            with c3:
                t_books = st.number_input("绘本目标(本)", value=st.session_state.class_rules.get(class_input, {}).get("books", 1))
            
            if st.button("保存该班级规则"):
                st.session_state.class_rules[class_input] = {"listen": t_listen, "anim": t_anim, "books": t_books}
                sync_to_db()
                st.success(f"已保存 {class_input} 的定制规则！")

    with tab_map:
        st.markdown("##### 英文名映射设置 (格式: 中文名:英文名，用换行或逗号隔开)")
        map_class_input = st.text_input("映射对应的班级名称 (例如: 康乐E4)", key="map_class")
        map_text_input = st.text_area("映射列表", value=st.session_state.name_maps.get(map_class_input, ""), placeholder="林乐铠:Carl\n吴斯涵:Tian\n庄柏钧:Sam", height=120)
        
        if st.button("保存该班级姓名映射"):
            if map_class_input:
                st.session_state.name_maps[map_class_input] = map_text_input
                sync_to_db()
                st.success(f"已保存 {map_class_input} 的姓名映射！")

    with tab_tpl:
        st.markdown("##### 自定义文本汇报模板")
        if mode_key == "matrix":
            current_tpl = st.text_area("矩阵模式模板", value=st.session_state.matrix_template, height=180)
            if current_tpl != st.session_state.matrix_template:
                st.session_state.matrix_template = current_tpl
                sync_to_db()
        else:
            current_tpl = st.text_area("传统模式模板", value=st.session_state.traditional_template, height=180)
            if current_tpl != st.session_state.traditional_template:
                st.session_state.traditional_template = current_tpl
                sync_to_db()

        if st.button("重置当前模板为默认模板"):
            if mode_key == "matrix":
                st.session_state.matrix_template = DEFAULT_MATRIX_TEMPLATE
            else:
                st.session_state.traditional_template = DEFAULT_TEMPLATE
            sync_to_db()
            st.rerun()

# ---------------- 生成报告 ----------------
current_template = st.session_state.matrix_template if mode_key == "matrix" else st.session_state.traditional_template

if st.button("🚀 立即生成学情报告", type="primary"):
    if not st.session_state.auth_token:
        st.error("请先登录或填入有效的 Token！")
    else:
        with st.spinner("正在抓取全阅读学情数据，请稍候..."):
            reports, err = fetch_data_via_api(
                auth_token=st.session_state.auth_token,
                report_type="daily",
                start_date=start_date,
                end_date=end_date,
                class_rules_config=st.session_state.class_rules,
                name_maps_config=st.session_state.name_maps,
                default_rule=default_rule,
                template_str=current_template,
                mode=mode_key,
                emoji_config=st.session_state.emojis
            )

            if err:
                st.error(f"生成失败: {err}")
            elif not reports:
                st.warning("未找到相关的班级打卡数据。")
            else:
                st.success("学情报告生成成功！")
                st.markdown("---")

                # 获取当前使用的实际图标配置
                full_icon = st.session_state.emojis.get("full", "🥇")
                part_icon = st.session_state.emojis.get("part", "🏆")
                zero_icon = st.session_state.emojis.get("zero", "❌")

                yesterday_str = end_date.strftime("%m.%d").lstrip("0").replace(".0", ".")

                for c_name, c_content in reports.items():
                    st.markdown(f"### 📍 {c_name} 打卡报告")

                    # 强制将表头日期修正止于昨天
                    c_content = re.sub(r'--\d+\.\d+', f'--{yesterday_str}', c_content)

                    lines = c_content.split('\n')
                    full_cnt, part_cnt, zero_cnt = 0, 0, 0

                    for line in lines:
                        line_str = line.strip()
                        # 过滤非学生数据的干扰行
                        if not line_str or "--" in line_str or "学情" in line_str or "提醒" in line_str or "全阅读" in line_str or "打卡" in line_str or "达标" in line_str:
                            continue

                        parts = line_str.split()
                        if parts:
                            emojis_part = parts[0]

                            # 🎯 精确全勤与加油人数计算逻辑：
                            # 1. 只有全部天数均为 full_icon，且无 part_icon 与 zero_icon，才算全勤
                            if part_icon not in emojis_part and zero_icon not in emojis_part and full_icon in emojis_part:
                                full_cnt += 1
                            # 2. 只有整行全是 zero_icon 时，才算未打卡
                            elif full_icon not in emojis_part and part_icon not in emojis_part and zero_icon in emojis_part:
                                zero_cnt += 1
                            # 3. 包含 part_icon 或 混合图标，算持续加油
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

                    # 正确替换模板中的 stats 占位符
                    if "{stats}" in c_content:
                        final_share_content = c_content.replace("{stats}", stats_text).strip()
                    else:
                        final_share_content = re.sub(r'📊 学情统计汇总：[\s\S]*?(?=💡|$)', stats_text + "\n\n", c_content).strip()

                    # 前端复制框呈现
                    st.text_area(
                        label=f"{c_name} 结果",
                        value=final_share_content,
                        height=320,
                        key=f"text_{c_name}"
                    )
