import requests
import json
from datetime import date, timedelta

DEFAULT_TEMPLATE = """📌 {class_name} {report_type}（{date_title}）

🌟 【听音&动画双达标】({both_count}人)：
{both_list}

🎵 【仅听音达标】({listen_only_count}人)：
{listen_only_list}

📺 【仅动画达标】({anim_only_count}人)：
{anim_only_list}

📖 【绘本达标】({books_count}人)：
{books_list}

❌ 【未达标/未打卡】({none_count}人)：
{none_list}

--------------------
💡 达标标准：每日听音 ≥ {target_listen}分钟，每日动画 ≥ {target_anim}分钟，绘本 ≥ {target_books}本。"""

DEFAULT_MATRIX_TEMPLATE = """❤️ {date_title} 全阅读打卡 ❤️

{matrix}

提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少

--------------------
{stats}"""

def auto_login(username, password):
    url = "https://iread.e-plan.cn/api/v1/user/login"
    payload = {"username": username, "password": password}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        res_json = resp.json()
        if res_json.get("code") == 200 or res_json.get("status") == "success":
            token = res_json.get("data", {}).get("token") or res_json.get("token")
            return token, None
        else:
            return None, res_json.get("msg", "登录失败，请检查账号密码")
    except Exception as e:
        return None, str(e)

def fetch_data_via_api(token, report_type, start_date, end_date, class_rules, name_maps, default_rule, template_str, mode="traditional", emoji_config=None):
    if mode == "matrix":
        # 矩阵模式：固定获取本周一至今天
        today = date.today()
        s_date = today - timedelta(days=today.weekday())
        e_date = today
    else:
        if report_type == "昨日汇报":
            s_date = date.today() - timedelta(days=1)
            e_date = s_date
        elif report_type == "周汇报":
            today = date.today()
            s_date = today - timedelta(days=today.weekday())
            e_date = today
        elif report_type == "月汇报":
            today = date.today()
            s_date = today.replace(day=1)
            e_date = today
        else:
            s_date, e_date = start_date, end_date

    url = f"https://iread.e-plan.cn/api/v1/teacher/student-study-records?start_date={s_date}&end_date={e_date}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, f"接口请求失败，状态码：{resp.status_code}"
        
        res_json = resp.json()
        raw_data = res_json.get("data", [])
        
        if not raw_data:
            return None, "暂未查询到该时间段内的学生打卡数据"

        # 解析英文名映射表
        parsed_maps = {}
        for c_name, map_str in name_maps.items():
            parsed_maps[c_name] = {}
            if map_str:
                for line in map_str.split("\n"):
                    if ":" in line or "：" in line:
                        line_clean = line.replace("：", ":")
                        parts = line_clean.split(":")
                        if len(parts) == 2:
                            parsed_maps[c_name][parts[0].strip()] = parts[1].strip()

        # 按班级归类数据
        grouped_data = {}
        for item in raw_data:
            c_name = item.get("className", "默认班级")
            if class_rules and c_name not in class_rules:
                continue
            if c_name not in grouped_data:
                grouped_data[c_name] = []
            grouped_data[c_name].append(item)

        if not grouped_data:
            return None, "未找到已配置班级的打卡数据，请确认班级名称是否一致"

        reports = {}
        
        if mode == "matrix":
            # 计算天数列表 (周一至今天)
            days_count = (e_date - s_date).days + 1
            date_title = f"{s_date.month}.{s_date.day}--{e_date.month}.{e_date.day}"
            
            e_full = emoji_config.get("full", "⭐") if emoji_config else "⭐"
            e_part = emoji_config.get("part", "✨") if emoji_config else "✨"
            e_zero = emoji_config.get("zero", "⚪") if emoji_config else "⚪"
            e_badge = emoji_config.get("badge", "👑") if emoji_config else "👑"

            for c_name, students in grouped_data.items():
                rule = class_rules.get(c_name, default_rule)
                t_listen = rule.get("listen", 60)
                t_anim = rule.get("anim", 15)
                t_books = rule.get("books", 2)
                
                c_map = parsed_maps.get(c_name, {})
                matrix_lines = []

                for stu in students:
                    zh_name = stu.get("studentName", "")
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}{en_name}"
                    
                    records = stu.get("records", [])
                    daily_emojis = []
                    full_days = 0

                    for i in range(days_count):
                        day_dt = s_date + timedelta(days=i)
                        day_str = day_dt.strftime("%Y-%m-%d")
                        
                        # 查找当日数据
                        rec = next((r for r in records if r.get("date") == day_str), None)
                        if rec:
                            l_time = rec.get("listenTime", 0)
                            a_time = rec.get("animTime", 0)
                            b_cnt = rec.get("booksCount", 0)
                            
                            is_listen = l_time >= t_listen
                            is_anim = a_time >= t_anim
                            is_books = b_cnt >= t_books
                            
                            if is_listen and is_anim and is_books:
                                daily_emojis.append(e_full)
                                full_days += 1
                            elif (l_time > 0 or a_time > 0 or b_cnt > 0):
                                daily_emojis.append(e_part)
                            else:
                                daily_emojis.append(e_zero)
                        else:
                            daily_emojis.append(e_zero)

                    # 满勤追加后缀标记
                    emoji_str = " ".join(daily_emojis)
                    if full_days == days_count and days_count > 0 and e_badge:
                        emoji_str += f" {e_badge}"

                    matrix_lines.append(f"{emoji_str}  {display_name}")

                matrix_text = "\n".join(matrix_lines)
                
                # 填充模板（{stats} 在 app.py 中动态计算替换）
                report_content = template_str.format(
                    date_title=date_title,
                    matrix=matrix_text,
                    stats="{stats}"
                )
                reports[c_name] = report_content

        else:
            # 传统分组文字汇总模式
            days_count = max(1, (e_date - s_date).days + 1)
            date_title = f"{s_date.month}月{s_date.day}日" if s_date == e_date else f"{s_date.month}.{s_date.day}-{e_date.month}.{e_date.day}"

            for c_name, students in grouped_data.items():
                rule = class_rules.get(c_name, default_rule)
                t_listen = rule.get("listen", 60) * days_count
                t_anim = rule.get("anim", 15) * days_count
                t_books = rule.get("books", 2) * days_count

                c_map = parsed_maps.get(c_name, {})
                both, listen_only, anim_only, books, none = [], [], [], [], []

                for stu in students:
                    zh_name = stu.get("studentName", "")
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}({en_name})" if en_name else zh_name

                    l_time = stu.get("totalListenTime", 0)
                    a_time = stu.get("totalAnimTime", 0)
                    b_cnt = stu.get("totalBooksCount", 0)

                    is_listen = l_time >= t_listen
                    is_anim = a_time >= t_anim
                    is_books = b_cnt >= t_books

                    if is_listen and is_anim:
                        both.append(display_name)
                    elif is_listen:
                        listen_only.append(display_name)
                    elif is_anim:
                        anim_only.append(display_name)
                    else:
                        none.append(display_name)

                    if is_books:
                        books.append(display_name)

                report_content = template_str.format(
                    class_name=c_name,
                    report_type=report_type,
                    date_title=date_title,
                    target_listen=rule.get("listen", 60),
                    target_anim=rule.get("anim", 15),
                    target_books=rule.get("books", 2),
                    both_count=len(both),
                    both_list="、".join(both) if both else "无",
                    listen_only_count=len(listen_only),
                    listen_only_list="、".join(listen_only) if listen_only else "无",
                    anim_only_count=len(anim_only),
                    anim_only_list="、".join(anim_only) if anim_only else "无",
                    books_count=len(books),
                    books_list="、".join(books) if books else "无",
                    none_count=len(none),
                    none_list="、".join(none) if none else "无"
                )
                reports[c_name] = report_content

        return reports, None

    except Exception as e:
        return None, f"数据处理发生异常：{str(e)}"
