from sqlalchemy.orm import Session

from app.models import AppSetting

FEISHU_ALERTS_ENABLED_KEY = "feishu_alerts_enabled"


def get_setting(db: Session, key: str, default: str) -> str:
    setting = db.get(AppSetting, key)
    return setting.value if setting else default


def set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def feishu_alerts_enabled(db: Session) -> bool:
    return get_setting(db, FEISHU_ALERTS_ENABLED_KEY, "true").lower() == "true"


def set_feishu_alerts_enabled(db: Session, enabled: bool) -> None:
    set_setting(db, FEISHU_ALERTS_ENABLED_KEY, "true" if enabled else "false")
