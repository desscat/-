import streamlit as st
from datetime import date, timedelta
from iread_core import auto_login, fetch_data_via_api, CLASS_RULES_CONFIG

st.set_page_config(page_title="全阅读学情打卡助手", page_icon="⚡", layout="centered")

st.title("⚡ 全阅读学情打卡生成器")
st.write("欢迎使用！在这里可以随时一键生成班级打卡日报。")

# 侧边栏凭证与设置
st.sidebar.header("🔐 身份凭证配置")
username_input = st.sidebar.text_input("全阅读手机号")
password_input = st.sidebar.text_input("全阅读密码", type="password")

report_type = st.sidebar.radio("统计周期", ["昨日汇报", "周汇报", "月汇报"], index=0)

if st.sidebar.button("⚡ 立即生成报告", type="primary"):
    if not username_input or not password_input:
        st.error("请先在左侧填写手机号和密码！")
    else:
        with st.spinner("正在登录并获取打卡数据..."):
            token, err = auto_login(username_input, password_input)
            if err:
                st.error(f"登录失败: {err}")
            else:
                reports, fetch_err = fetch_data_via_api(token, report_type, CLASS_RULES_CONFIG)
                if fetch_err:
                    st.error(f"获取数据失败: {fetch_err}")
                else:
                    st.success("🎉 数据生成成功！")
                    for c_name, c_content in reports.items():
                        st.markdown(f"### 📍 {c_name}")
                        st.code(c_content, language=None)

st.divider()
st.subheader("📋 当前默认监控的班级与标准预览")
for c_name, c_rule in CLASS_RULES_CONFIG.items():
    st.info(f"**{c_name}** -> 听力: {c_rule['listen']}分钟 | 动画: {c_rule['anim']}分钟 | 绘本: {c_rule['books']}本")
