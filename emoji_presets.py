import json


EMOJI_KEYS = ("full", "part", "zero", "badge")
DEFAULT_EMOJIS = {"full": "🏆", "part": "🥇", "zero": "❌", "badge": "🎖️"}


def normalize_emoji_config(config):
    config = config if isinstance(config, dict) else {}
    return {
        key: str(config.get(key) or DEFAULT_EMOJIS[key]).strip()
        for key in EMOJI_KEYS
    }


def normalize_custom_emoji_presets(presets, reserved_names=()):
    if not isinstance(presets, dict):
        return {}

    reserved = set(reserved_names)
    cleaned = {}
    for name, config in presets.items():
        clean_name = str(name).strip()
        if clean_name and clean_name not in reserved:
            cleaned[clean_name] = normalize_emoji_config(config)
    return cleaned


def validate_emoji_config(config):
    labels = {
        "full": "全勤达标",
        "part": "部分达标",
        "zero": "未打卡",
        "badge": "满勤尾巴标记",
    }
    errors = []
    cleaned = {key: str(config.get(key, "")).strip() for key in EMOJI_KEYS}

    for key, value in cleaned.items():
        if not value:
            errors.append(f"“{labels[key]}”不能为空。")
        elif len(value) > 8:
            errors.append(f"“{labels[key]}”请只填写一个 Emoji。")

    status_markers = [cleaned[key] for key in ("full", "part", "zero") if cleaned[key]]
    if len(status_markers) == 3 and len(set(status_markers)) < 3:
        errors.append("全勤、部分达标和未打卡必须使用三个不同的 Emoji。")

    return cleaned, errors


def export_emoji_presets(presets):
    payload = {"version": 1, "emoji_presets": presets}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_emoji_presets(raw_text, reserved_names=()):
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("文件内容必须是 JSON 对象。")

    presets = payload.get("emoji_presets", payload)
    cleaned = normalize_custom_emoji_presets(presets, reserved_names)
    if not cleaned:
        raise ValueError("文件中没有可导入的 Emoji 预设。")

    for name, config in cleaned.items():
        _, errors = validate_emoji_config(config)
        if errors:
            raise ValueError(f"预设“{name}”无效：{errors[0]}")
    return cleaned


if __name__ == "__main__":
    sample = {"我的主题": {"full": "🌟", "part": "👍", "zero": "⭕", "badge": "👑"}}
    assert import_emoji_presets(export_emoji_presets(sample)) == sample
    assert validate_emoji_config(DEFAULT_EMOJIS)[1] == []
    assert validate_emoji_config({**DEFAULT_EMOJIS, "zero": "🏆"})[1]
    print("emoji_presets self-check passed")
