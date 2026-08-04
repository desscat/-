import re
from datetime import datetime, date, timedelta
import requests

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
    if text is None:
        return 0
    nums = re.findall(r'\d+', str(text))
    return int(nums[0]) if nums else 0

def process_student_data(class_name, name, listen, anim, books, req_listen, req_anim, req_books, name_map_str):
    listen = clean_num(listen)
    anim = clean_num(anim)
    books = clean_num(books)
    
    clean_name = re.sub(r'[a-zA-Z\s]', '', name)
    class_mapping = parse_name_map(map_str=name_map_str)
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

def generate_custom_report(template_str, class_name, date_title, student_list, req_listen, req_anim, req_books, name_map_str):
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
    
    return template_str.format(
        class_name=class_name,
        date_title=date_title,
        tops=tops_formatted,
        mids=mids_formatted,
        zeros=zeros_formatted
    )

def auto_login(username, password):
    login_url = "https://v2.ireadabc.com/api/login"
    payload = {"phone": str(username).strip(), "password": str(password).strip()}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            res = resp.json()
            data = res.get("data")
            if isinstance(data, dict):
                token = data.get("token")
                if token:
                    return token, None
            return None, res.get("message") or "登录成功但未解析到 Token"
        return None, f"服务器返回异常({resp.status_code})"
    except Exception as e:
        return None, f"网络错误：{str(e)}"

def run_automation(username, password, start_date, end_date, class_rules_config, name_maps_config, default_rule):
    # 1. 自动登录获取 Token
    token, err = auto_login(username, password)
    if err:
        raise Exception(f"登录失败: {err}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Token": token.strip(),
        "Client-Type": "BROWSER"
    }
    
    s_date = start_date.strftime("%Y-%m-%d")
    e_date = end_date.strftime("%Y-%m-%d")
    date_title = f"{s_date}至{e_date}" if s_date != e_date else start_date.strftime("%m月%d日")
    days_count = (end_date - start_date).days + 1
    if days_count < 1:
        days_count = 1

    default_template = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟【今日光荣榜】
{tops}

💪【再努努力】
{mids}

⏰【该起床打卡啦】
{zeros}"""

    # 2. 获取班级列表
    classes_url = "https://v2.ireadabc.com/api/teacher/classes/page/all"
    resp = requests.get(classes_url, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise Exception(f"获取班级列表失败，状态码: {resp.status_code}")
        
    res_json = resp.json()
    raw_data = res_json.get("data", [])
    classes_data = []
    if isinstance(raw_data, list):
        classes_data = raw_data
    elif isinstance(raw_data, dict):
        classes_data = raw_data.get("rows", []) or raw_data.get("list", []) or raw_data.get("records", [])

    if not classes_data:
        raise Exception("获取到的班级列表为空。")

    all_reports = []

    # 3. 循环拉取各个班级数据并生成报告
    for item in classes_data:
        class_id = str(item.get("class_id") or item.get("id"))
        class_name = item.get("class_name") or item.get("name") or f"班级_{class_id}"
        
        stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
        params = {"start": s_date, "end": e_date}
        stat_resp = requests.get(stats_url, headers=headers, params=params, timeout=20)

        if stat_resp.status_code == 200:
            s_json = stat_resp.json()
            students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
            if isinstance(students_raw, dict):
                students_raw = students_raw.get("rows", []) or students_raw.get("list", []) or students_raw.get("students", [])

            students_data = []
            for s in students_raw:
                students_data.append({
                    "name": s.get("name") or s.get("student_name") or "",
                    "listen": s.get("listen") or s.get("audio_time") or 0,
                    "anim": s.get("animation") or s.get("anim") or s.get("video_time") or 0,
                    "books": s.get("grading") or s.get("read") or s.get("book") or s.get("book_count") or 0
                })

            base_rule = next((class_rules_config[k] for k in class_rules_config if k in class_name or class_name in k), default_rule)
            matched_rule = {
                "listen": base_rule["listen"] * days_count,
                "anim": base_rule["anim"] * days_count,
                "books": base_rule["books"] * days_count
            }

            matched_name_map = next((name_maps_config[k] for k in name_maps_config if k in class_name or class_name in k), "")

            md_res = generate_custom_report(
                default_template, class_name, date_title, students_data,
                matched_rule["listen"], matched_rule["anim"], matched_rule["books"],
                matched_name_map
            )
            all_reports.append(md_res)

    return "\n\n---\n\n".join(all_reports)
