import requests
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
    url = "https://v2.ireadabc.com/api/login"
    payload = {
        "phone": str(username).strip(),
        "password": str(password).strip()
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, f"登录接口响应异常 (HTTP {resp.status_code})"
            
        res_json = resp.json()
        token = None
        if isinstance(res_json, dict):
            if "data" in res_json and isinstance(res_json["data"], dict):
                token = res_json["data"].get("token")
            if not token:
                token = res_json.get("token")

        if token:
            return token, None
        else:
            msg = res_json.get("msg") or res_json.get("message") or "登录失败，请检查手机号或密码"
            return None, msg
    except Exception as e:
        return None, f"登录请求发生异常：{str(e)}"

def fetch_data_via_api(token, report_type, start_date, end_date, class_rules, name_maps, default_rule, template_str, mode="traditional", emoji_config=None):
    if mode == "matrix":
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

    headers = {
        "Authorization": f"Bearer {token}", 
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 1. 先获取老师名下的班级列表，拿到班级名称和对应的 id
        classes_url = "https://v2.ireadabc.com/api/teacher/classes" # 或者通用的获取班级列表接口
        # 如果上一步获取班级列表用的是别的路由，也可以直接通过通用列表获取，这里尝试兼容多路线
        # 让我们先请求教师班级列表
        cls_resp = requests.get("https://v2.ireadabc.com/api/classes", headers=headers, timeout=10)
        if cls_resp.status_code != 200:
            # 尝试备用班级接口
            cls_resp = requests.get("https://v2.ireadabc.com/api/teacher/classes", headers=headers, timeout=10)
            
        if cls_resp.status_code != 200:
            return None, f"获取班级列表失败 (HTTP {cls_resp.status_code})"
            
        cls_json = cls_resp.json()
        classes_data = cls_json.get("data", [])
        if not classes_data and isinstance(cls_json, list):
            classes_data = cls_json

        if not classes_data:
            return None, "未能在该账号下找到任何班级数据"

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

        reports = {}
        s_str = s_date.strftime("%Y-%m-%d")
        e_str = e_date.strftime("%Y-%m-%d")

        for cls_item in classes_data:
            c_name = cls_item.get("className") or cls_item.get("name")
            c_id = cls_item.get("classId") or cls_item.get("id")
            
            if not c_name or not c_id:
                continue
                
            if class_rules and c_name not in class_rules:
                continue

            # 2. 按照新版 v3 接口规范逐个班级拉取学情数据
            detail_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{c_id}?start={s_str}&end={e_str}"
            det_resp = requests.get(detail_url, headers=headers, timeout=10)
            
            if det_resp.status_code != 200:
                continue
                
            det_json = det_resp.json()
            students = det_json.get("data", [])
            if not students and isinstance(det_json, list):
                students = det_json
            if not students and isinstance(det_json.get("data"), dict):
                students = det_json.get("data", {}).get("students", [])

            if not students:
                continue

            rule = class_rules.get(c_name, default_rule)
            c_map = parsed_maps.get(c_name, {})

            if mode == "matrix":
                days_count = (e_date - s_date).days + 1
                date_title = f"{s_date.month}.{s_date.day}--{e_date.month}.{e_date.day}"
                
                e_full = emoji_config.get("full", "⭐") if emoji_config else "⭐"
                e_part = emoji_config.get("part", "✨") if emoji_config else "✨"
                e_zero = emoji_config.get("zero", "⚪") if emoji_config else "⚪"
                e_badge = emoji_config.get("badge", "👑") if emoji_config else "👑"

                matrix_lines = []
                t_listen = rule.get("listen", 60)
                t_anim = rule.get("anim", 15)
                t_books = rule.get("books", 2)

                for stu in students:
                    zh_name = stu.get("studentName") or stu.get("name", "")
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}{en_name}"
                    
                    records = stu.get("records", [])
                    daily_emojis = []
                    full_days = 0

                    for i in range(days_count):
                        day_dt = s_date + timedelta(days=i)
                        day_str = day_dt.strftime("%Y-%m-%d")
                        
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

                    emoji_str = " ".join(daily_emojis)
                    if full_days == days_count and days_count > 0 and e_badge:
                        emoji_str += f" {e_badge}"

                    matrix_lines.append(f"{emoji_str}  {display_name}")

                matrix_text = "\n".join(matrix_lines)
                reports[c_name] = template_str.format(
                    date_title=date_title,
                    matrix=matrix_text,
                    stats="{stats}"
                )

            else:
                days_count = max(1, (e_date - s_date).days + 1)
                date_title = f"{s_date.month}月{s_date.day}日" if s_date == e_date else f"{s_date.month}.{s_date.day}-{e_date.month}.{e_date.day}"

                t_listen = rule.get("listen", 60) * days_count
                t_anim = rule.get("anim", 15) * days_count
                t_books = rule.get("books", 2) * days_count

                both, listen_only, anim_only, books, none = [], [], [], [], []

                for stu in students:
                    zh_name = stu.get("studentName") or stu.get("name", "")
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}({en_name})" if en_name else zh_name

                    l_time = stu.get("totalListenTime") or stu.get("listenTime", 0)
                    a_time = stu.get("totalAnimTime") or stu.get("animTime", 0)
                    b_cnt = stu.get("totalBooksCount") or stu.get("booksCount", 0)

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

                reports[c_name] = template_str.format(
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

        if not reports:
            return None, "未能成功解析到任何班级的打卡统计数据"

        return reports, None

    except Exception as e:
        return None, f"数据处理发生异常：{str(e)}"
