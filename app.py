import streamlit as st
from datetime import date, timedelta
import re
from iread_core import fetch_data_via_api, auto_login, DEFAULT_TEMPLATE, DEFAULT_MATRIX_TEMPLATE

st.set_page_config(
    page_title="全阅读学情打卡生成器",
    page_icon="⚡",
    layout="centered"
)

st.title("⚡ 全阅读学情打卡生成器")

# 初始化 session_state
if "auth_token" not in st.session_state:
    st.session_state.auth_token = ""
if "emojis" not in st.session_state:
    st.session_state.emojis = {"full": "🥇", "part": "🏆", "zero": "❌", "badge": "👑"}

# 侧边栏设置
with st.sidebar:
    st.header("⚙️ 系统设置")
    
    # 登录区
    st.subheader("🔑 账号登录")
    username = st.text_input("手机号", value="")
    password = st.text_input("密码", type="password", value="")
    
    if st.button("自动登录获取 Token"):
        if username and password:
            token, err = auto_login(username, password)
            if token:
                st.session_state.auth_token = token
                st.success("登录成功！Token 已自动填入")
            else:
                st.error(f"登录失败: {err}")
        else:
            st.warning("请输入手机号和密码")

    token_input = st.text_input("Token (可手动粘贴)", value=st.session_state.auth_token)
    st.session_state.auth_token = token_input

    st.markdown("---")
    st.subheader("🎨 图标配置 (矩阵模式)")
    st.session_state.emojis["full"] = st.text_input("全勤图标 (三项全满)", value=st.session_state.emojis["full"])
    st.session_state.emojis["part"] = st.text_input("部分达标图标 (加油)", value=st.session_state.emojis["part"])
    st.session_state.emojis["zero"] = st.text_input("未打卡图标", value=st.session_state.emojis["zero"])
    st.session_state.emojis["badge"] = st.text_input("全勤尾巴徽章", value=st.session_state.emojis["badge"])

# 主界面：参数选择
col1, col2 = st.columns(2)
with col1:
    mode = st.radio("选择汇报模式", ["矩阵日历模式 (matrix)", "传统分组模式 (traditional)"], index=0)
    mode_key = "matrix" if "matrix" in mode else "traditional"

with col2:
    date_option = st.radio("时间范围", ["本周 (周一至昨天)", "自定义日期"], index=0)

today = date.today()
yesterday = today - timedelta(days=1)

if date_option == "本周 (周一至昨天)":
    # 周一作为起始点
    start_date = today - timedelta(days=today.weekday())
    # 结束点严格定为昨天（如果今天就是周一，则结束点也是昨天）
    end_date = yesterday if yesterday >= start_date else start_date
else:
    c_start, c_end = st.columns(2)
    with c_start:
        start_date = st.date_input("开始日期", value=today - timedelta(days=7))
    with c_end:
        end_date = st.date_input("结束日期", value=yesterday)

# 规则与姓名映射默认值
default_rule = {"listen": 20, "anim": 10, "books": 1}

with st.expander("⚙️ 高级配置 (班级规则与姓名映射)", expanded=False):
    custom_template = st.text_area(
        "自定义模板", 
        value=DEFAULT_MATRIX_TEMPLATE if mode_key == "matrix" else DEFAULT_TEMPLATE,
        height=150
    )

# 生成报告按钮
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
                class_rules_config={},
                name_maps_config={},
                default_rule=default_rule,
                template_str=custom_template,
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

                f_emoji = st.session_state.emojis.get("full", "🥇")
                p_emoji = st.session_state.emojis.get("part", "🏆")
                z_emoji = st.session_state.emojis.get("zero", "❌")

                # 格式化日期标题，防止出现未来日期
                yesterday_str = yesterday.strftime("%m.%d").lstrip("0").replace(".0", ".")

                for c_name, c_content in reports.items():
                    st.markdown(f"### 📍 {c_name} 打卡报告")

                    # 💡 强制修正表头日期：确保结束日期精确止于昨天
                    c_content = re.sub(r'--\d+\.\d+', f'--{yesterday_str}', c_content)

                    lines = c_content.split('\n')
                    full_cnt, part_cnt, zero_cnt = 0, 0, 0

                    for line in lines:
                        line_str = line.strip()
                        # 跳过非学生信息的排版行
                        if not line_str or "--" in line_str or "学情" in line_str or "提醒" in line_str or "全阅读" in line_str or "打卡" in line_str:
                            continue

                        emojis_part = line_str.split()[0] if line_str else ""
                        if f_emoji in emojis_part or p_emoji in emojis_part or z_emoji in emojis_part:
                            # 判定标准：整行全为 full_emoji 且无 part 和 zero，记为全勤
                            if p_emoji not in emojis_part and z_emoji not in emojis_part:
                                full_cnt += 1
                            elif f_emoji not in emojis_part and p_emoji not in emojis_part:
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

                    final_share_content = c_content.replace("{stats}", stats_text).strip()

                    # 显示报告区域
                    st.text_area(
                        label=f"{c_name} 结果",
                        value=final_share_content,
                        height=280,
                        key=f"text_{c_name}"
                    )
