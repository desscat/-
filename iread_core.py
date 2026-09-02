import requests
from datetime import datetime, timedelta

# 默认文字模板与矩阵模板定义
DEFAULT_TEMPLATE = """❤️ {start_date}--{end_date} 全阅读打卡 ❤️

{content}
------------------
{stats}

💡 提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少"""

DEFAULT_MATRIX_TEMPLATE = """❤️ {start_date}--{end_date} 全阅读打卡 ❤️

{content}
------------------
{stats}

💡 提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少"""

def auto_login(username, password):
    """根据账号密码调用打卡平台登录 API 换取 Token"""
    url = "https://api.iread.example.com/login"  # 请替换为真实的打卡平台登录接口 URL
    payload = {"username": username, "password": password}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        res_data = resp.json()
        if resp.status_code == 200 and "token" in res_data:
            return res_data["token"], None
        else:
            return None, res_data.get("message", "登录失败，请核对账号密码")
    except Exception as e:
        return None, str(e)

def fetch_data_via_api(token, report_type, start_date, end_date, class_rules, name_maps, default_rules, template, mode="matrix", emoji_config=None):
    """
    抓取打卡数据并生成各班级报告的主逻辑
    """
    if emoji_config is None:
        emoji_config = {"full": "🏆", "part": "🥇", "zero": "❌", "badge": "🎖️"}
    
    full_emoji = emoji_config.get("full", "🏆")
    part_emoji = emoji_config.get("part", "🥇")
    zero_emoji = emoji_config.get("zero", "❌")
    badge_emoji = emoji_config.get("badge", "🎖️")

    # 构建日期列表
    date_list = []
    curr = start_date
    while curr <= end_date:
        date_list.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
    
    total_days = len(date_list)
    if total_days == 0:
        return None, "选定的时间段内没有有效日期！"

    # API 接口地址与请求头
    api_url = "https://api.iread.example.com/get_class_data"  # 请替换为真实的打卡数据接口 URL
    headers = {"Authorization": f"Bearer {token}"}

    reports = {}

    for c_name, rules in class_rules.items():
        # 获取该班级的达标规则
        req_listen = rules.get("listen", default_rules.get("listen", 60))
        req_anim = rules.get("anim", default_rules.get("anim", 15))
        req_books = rules.get("books", default_rules.get("books", 2))
        
        # 解析姓名映射表
        raw_map_text = name_maps.get(c_name, "")
        name_mapping = {}
        for line in raw_map_text.strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                name_mapping[k.strip()] = v.strip()
            elif "：" in line:
                k, v = line.split("：", 1)
                name_mapping[k.strip()] = v.strip()

        # 发送 API 请求获取班级数据
        payload = {
            "class_name": c_name,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }

        try:
            # 此处模拟 API 返回数据结构，如果 API 返回真实数据请直接使用接口的 JSON
            resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                raw_students_data = resp.json().get("students", [])
            else:
                # 若请求失败或环境无真接口，捕获异常后跳出
                return None, f"获取班级 [{c_name}] 数据失败: {resp.status_code}"
        except Exception as e:
            # 提示接口调用的异常情况
            return None, f"请求打卡数据接口异常: {str(e)}"

        # -------------------------------------------------------------
        # 🎯 核心逻辑修正：基于【每日实际时长/数值】精准判定每位学员的打卡状态
        # -------------------------------------------------------------
        full_cnt = 0   # 全勤达标人数
        part_cnt = 0   # 持续加油人数
        zero_cnt = 0   # 未打卡提醒人数
        
        student_lines = []

        for student in raw_students_data:
            s_name = student.get("name", "未命名")
            display_name = name_mapping.get(s_name, s_name)
            
            # daily_records 对应 date_list 每一天的数据：[ {"listen": 60, "anim": 15, "books": 2}, ... ]
            daily_records = student.get("daily_records", [])
            
            student_icons = []
            active_days_count = 0  # 打卡天数计数
            
            for day_data in daily_records:
                l_time = day_data.get("listen", 0)
                a_time = day_data.get("anim", 0)
                b_cnt = day_data.get("books", 0)
                
                # 判断当天是否有任何打卡行为（时长/数值大于0）
                is_active_today = (l_time + a_time + b_cnt) > 0
                
                # 判断当天是否达成规则标准
                is_full_today = (l_time >= req_listen and a_time >= req_anim and b_cnt >= req_books)
                
                if is_active_today:
                    active_days_count += 1
                
                # 记录 Emoji 标记
                if is_full_today:
                    student_icons.append(full_emoji)
                elif is_active_today:
                    student_icons.append(part_emoji)
                else:
                    student_icons.append(zero_emoji)

            # 🎯 统计归类（根据每日打卡天数精准计算）：
            if active_days_count == total_days:
                # 统计时间内每一天都有打卡记录 -> 全勤达标
                full_cnt += 1
                suffix_badge = f" {badge_emoji}" if total_days > 1 else ""
            elif active_days_count == 0:
                # 统计时间内一天都没有打卡 -> 未打卡提醒
                zero_cnt += 1
                suffix_badge = ""
            else:
                # 统计时间内打了部分天数，但也存在缺卡 -> 持续加油
                part_cnt += 1
                suffix_badge = ""

            # 拼装学员单行文本
            if mode == "matrix":
                icons_str = "".join(student_icons)
                student_lines.append(f"{icons_str}  {display_name}{suffix_badge}")
            else:
                student_lines.append(f"{display_name}{suffix_badge}")

        # 计算学情统计比例
        total_students = full_cnt + part_cnt + zero_cnt
        pct = round(full_cnt / total_students * 100) if total_students > 0 else 0

        # 生成学情统计汇总文案
        stats_text = (
            f"📊 学情统计汇总：\n"
            f"🌟 全勤达标：{full_cnt} 人（{pct}%）\n"
            f"💪 持续加油：{part_cnt} 人\n"
            f"⚠️ 未打卡提醒：{zero_cnt} 人"
        )

        # 格式化日期显示
        s_date_str = f"{start_date.month}.{start_date.day}"
        e_date_str = f"{end_date.month}.{end_date.day}"

        # 替换模版变量
        content_body = "\n".join(student_lines)
        rendered_report = template.format(
            start_date=s_date_str,
            end_date=e_date_str,
            content=content_body,
            stats=stats_text
        )

        reports[c_name] = rendered_report

    return reports, None
