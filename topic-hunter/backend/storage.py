import json
import uuid
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
HISTORY_FILE = DATA_DIR / "topic_history.json"
BACKLOG_FILE = DATA_DIR / "topic_backlog.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {"topics": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict):
    _ensure_data_dir()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_used_titles() -> list[str]:
    data = _read_json(HISTORY_FILE)
    return [t["title"] for t in data.get("topics", [])]


def save_topics_to_backlog(topics: list[dict]):
    _ensure_data_dir()
    data = _read_json(BACKLOG_FILE)
    existing_ids = {t["topic_id"] for t in data["topics"]}
    for topic in topics:
        if topic["topic_id"] not in existing_ids:
            topic["added_at"] = datetime.utcnow().isoformat()
            data["topics"].append(topic)
    _write_json(BACKLOG_FILE, data)


def mark_topic_used(topic: dict):
    _ensure_data_dir()
    history = _read_json(HISTORY_FILE)
    topic["used_at"] = datetime.utcnow().isoformat()
    history["topics"].append(topic)
    _write_json(HISTORY_FILE, history)

    backlog = _read_json(BACKLOG_FILE)
    backlog["topics"] = [t for t in backlog["topics"] if t["topic_id"] != topic["topic_id"]]
    _write_json(BACKLOG_FILE, backlog)


def get_backlog() -> list[dict]:
    return _read_json(BACKLOG_FILE).get("topics", [])


def assign_topic_id() -> str:
    return str(uuid.uuid4())[:8]
