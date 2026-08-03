def execute_daily_report():
    print(f"\n==================== ⏰ 自动打卡任务开始 [{datetime.now()}] ====================")
    status = DummyStatus()
    
    # 🎯 计算并获取【昨天】的日期
    yesterday = date.today() - timedelta(days=1)
    
    try:
        # 执行抓取，将开始和结束日期都设为【昨天】
        report_text = run_automation_web(
            username=IREAD_USER,
            password=IREAD_PWD,
            report_type="今日汇报",  # 这里的类型保持不变即可
            start_date=yesterday,
            end_date=yesterday,
            class_rules_config=CLASS_RULES_CONFIG,
            name_maps_config=NAME_MAPS_CONFIG,
            default_rule=DEFAULT_RULE,
            status_placeholder=status
        )
        
        if report_text and report_text.strip():
            # 拼接微信推送标题（显示为昨天的日期）
            title = f"📚 全阅读学情打卡报告 ({yesterday.strftime('%m月%d日')})"
            send_to_wechat(title, report_text)
        else:
            print("⚠️ 未获取到有效报告，跳过微信推送。")
            
    except Exception as e:
        error_msg = f"❌ 今日定时任务运行失败：{str(e)}"
        print(error_msg)
        send_to_wechat("⚠️ 全阅读自动打卡报错提醒", error_msg)
