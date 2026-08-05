import asyncio
try:
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        raise RuntimeError("Loop is closed")
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import streamlit as st
from datetime import datetime, timedelta
from iread_core import run_automation, CLASS_RULES_CONFIG

st.set_page_config(page_title="全阅读打卡统计助手", page_icon="📚", layout="centered")

st.title("📚 全阅读班级打卡自动化助手")
st.write("欢迎使用！在这里可以随时手动查询打卡情况或生成日报。")

# 侧边栏配置
st.sidebar.header("⚙️ 账号与通知配置")
username_input = st.sidebar.text_input("全阅读账号", type="default")
password_input = st.sidebar.text_input("全阅读密码", type="password")
pushplus_input = st.sidebar.text_input("PushPlus Token", type="password")

target_date = st.sidebar.date_input("选择统计日期", datetime.now() - timedelta(days=1))

if st.sidebar.button("🚀 立即手动生成并推送", type="primary"):
    if not username_input or not password_input:
        st.error("请先填写全阅读的账号和密码！")
    else:
        with st.spinner("正在连接后台抓取数据，请稍候..."):
            result = run_automation(
                username=username_input,
                password=password_input,
                pushplus_token=pushplus_input,
                target_date=target_date.strftime("%Y-%m-%d")
            )
            st.success(f"执行结果: {result}")

st.divider()
st.subheader("📋 当前监控的班级规则预览")
for c_name, c_rule in CLASS_RULES_CONFIG.items():
    st.info(f"**{c_name}** -> 听力: {c_rule['listen']}分钟 | 动画: {c_rule['anim']}分钟 | 阅读: {c_rule['books']}本")
