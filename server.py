import argparse
import json
import sqlite3
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "campus_activity.sqlite3"
MAX_BODY_SIZE = 16 * 1024 * 1024


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database():
    DATA_DIR.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                number TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS activity_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location TEXT NOT NULL,
                leader_id TEXT NOT NULL,
                introduction TEXT NOT NULL,
                minutes TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                cancelled INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (type_id) REFERENCES activity_types(id),
                FOREIGN KEY (leader_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS activity_participants (
                activity_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                attendance TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (activity_id, user_id),
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS activity_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS activity_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                version_time TEXT NOT NULL,
                actor TEXT NOT NULL,
                note TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operation_logs (
                id TEXT PRIMARY KEY,
                log_time TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                detail TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_activities_start
            ON activities(start_time);

            CREATE INDEX IF NOT EXISTS idx_activities_type
            ON activities(type_id);

            CREATE INDEX IF NOT EXISTS idx_participants_user
            ON activity_participants(user_id);

            CREATE INDEX IF NOT EXISTS idx_logs_time
            ON operation_logs(log_time);
            """
        )


def is_initialized(db):
    row = db.execute(
        "SELECT value FROM app_meta WHERE key = 'initialized'"
    ).fetchone()
    return bool(row and row["value"] == "1")


def read_state():
    with connect() as db:
        if not is_initialized(db):
            return None

        users = [
            {
                "id": row["id"],
                "name": row["name"],
                "number": row["number"],
                "active": bool(row["active"]),
            }
            for row in db.execute(
                "SELECT * FROM users ORDER BY sort_order, rowid"
            )
        ]

        types = [
            {
                "id": row["id"],
                "name": row["name"],
                "color": row["color"],
                "active": bool(row["active"]),
            }
            for row in db.execute(
                "SELECT * FROM activity_types ORDER BY sort_order, rowid"
            )
        ]

        participants = {}
        for row in db.execute(
            """
            SELECT * FROM activity_participants
            ORDER BY activity_id, sort_order, rowid
            """
        ):
            participants.setdefault(row["activity_id"], []).append(
                {
                    "userId": row["user_id"],
                    "attendance": row["attendance"],
                }
            )

        images = {}
        for row in db.execute(
            """
            SELECT * FROM activity_images
            ORDER BY activity_id, sort_order, id
            """
        ):
            images.setdefault(row["activity_id"], []).append(
                {
                    "name": row["name"],
                    "data": row["data"],
                    "uploadedAt": row["uploaded_at"],
                    "uploadedBy": row["uploaded_by"],
                }
            )

        versions = {}
        for row in db.execute(
            """
            SELECT * FROM activity_versions
            ORDER BY activity_id, sort_order, id
            """
        ):
            versions.setdefault(row["activity_id"], []).append(
                {
                    "version": row["version"],
                    "time": row["version_time"],
                    "actor": row["actor"],
                    "note": row["note"],
                }
            )

        activities = []
        for row in db.execute(
            "SELECT * FROM activities ORDER BY sort_order, rowid"
        ):
            activity_id = row["id"]
            activities.append(
                {
                    "id": activity_id,
                    "name": row["name"],
                    "typeId": row["type_id"],
                    "start": row["start_time"],
                    "end": row["end_time"],
                    "location": row["location"],
                    "leaderId": row["leader_id"],
                    "introduction": row["introduction"],
                    "participants": participants.get(activity_id, []),
                    "minutes": row["minutes"],
                    "images": images.get(activity_id, []),
                    "archived": bool(row["archived"]),
                    "cancelled": bool(row["cancelled"]),
                    "deleted": bool(row["deleted"]),
                    "version": row["version"],
                    "versions": versions.get(activity_id, []),
                    "createdBy": row["created_by"],
                    "createdAt": row["created_at"],
                    "updatedBy": row["updated_by"],
                    "updatedAt": row["updated_at"],
                }
            )

        logs = [
            {
                "id": row["id"],
                "time": row["log_time"],
                "actor": row["actor"],
                "action": row["action"],
                "target": row["target"],
                "detail": row["detail"],
            }
            for row in db.execute(
                "SELECT * FROM operation_logs ORDER BY sort_order, rowid"
            )
        ]

        return {
            "users": users,
            "types": types,
            "activities": activities,
            "logs": logs,
        }


def validate_state(state):
    if not isinstance(state, dict):
        raise ValueError("state 必须是对象")

    for key in ("users", "types", "activities", "logs"):
        if not isinstance(state.get(key), list):
            raise ValueError(f"{key} 必须是数组")

    user_ids = {item.get("id") for item in state["users"]}
    type_ids = {item.get("id") for item in state["types"]}

    if None in user_ids or None in type_ids:
        raise ValueError("人员和活动类型必须包含 id")

    for activity in state["activities"]:
        if activity.get("leaderId") not in user_ids:
            raise ValueError("活动负责人不存在")
        if activity.get("typeId") not in type_ids:
            raise ValueError("活动类型不存在")
        for participant in activity.get("participants", []):
            if participant.get("userId") not in user_ids:
                raise ValueError("活动参与人员不存在")


def write_state(state):
    validate_state(state)

    with connect() as db:
        db.execute("BEGIN")
        db.execute("DELETE FROM activity_images")
        db.execute("DELETE FROM activity_versions")
        db.execute("DELETE FROM activity_participants")
        db.execute("DELETE FROM activities")
        db.execute("DELETE FROM operation_logs")
        db.execute("DELETE FROM activity_types")
        db.execute("DELETE FROM users")

        for index, user in enumerate(state["users"]):
            db.execute(
                """
                INSERT INTO users (id, name, number, active, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    user["name"].strip(),
                    user["number"].strip(),
                    int(bool(user.get("active", True))),
                    index,
                ),
            )

        for index, activity_type in enumerate(state["types"]):
            db.execute(
                """
                INSERT INTO activity_types
                (id, name, color, active, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    activity_type["id"],
                    activity_type["name"].strip(),
                    activity_type.get("color", "#667085"),
                    int(bool(activity_type.get("active", True))),
                    index,
                ),
            )

        for index, activity in enumerate(state["activities"]):
            db.execute(
                """
                INSERT INTO activities (
                    id, name, type_id, start_time, end_time, location,
                    leader_id, introduction, minutes, archived, cancelled,
                    deleted, version, created_by, created_at, updated_by,
                    updated_at, sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity["id"],
                    activity["name"].strip(),
                    activity["typeId"],
                    activity["start"],
                    activity["end"],
                    activity["location"].strip(),
                    activity["leaderId"],
                    activity.get("introduction", "").strip(),
                    activity.get("minutes", ""),
                    int(bool(activity.get("archived", False))),
                    int(bool(activity.get("cancelled", False))),
                    int(bool(activity.get("deleted", False))),
                    int(activity.get("version", 1)),
                    activity.get("createdBy", "系统管理员"),
                    activity.get("createdAt", ""),
                    activity.get("updatedBy", "系统管理员"),
                    activity.get("updatedAt", ""),
                    index,
                ),
            )

            for participant_index, participant in enumerate(
                activity.get("participants", [])
            ):
                db.execute(
                    """
                    INSERT INTO activity_participants
                    (activity_id, user_id, attendance, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        activity["id"],
                        participant["userId"],
                        participant.get("attendance", "待登记"),
                        participant_index,
                    ),
                )

            for image_index, image in enumerate(activity.get("images", [])):
                db.execute(
                    """
                    INSERT INTO activity_images (
                        activity_id, name, data, uploaded_at,
                        uploaded_by, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        activity["id"],
                        image.get("name", "活动图片"),
                        image.get("data", ""),
                        image.get("uploadedAt", ""),
                        image.get("uploadedBy", "系统管理员"),
                        image_index,
                    ),
                )

            for version_index, version in enumerate(
                activity.get("versions", [])
            ):
                db.execute(
                    """
                    INSERT INTO activity_versions (
                        activity_id, version, version_time,
                        actor, note, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        activity["id"],
                        int(version.get("version", 1)),
                        version.get("time", ""),
                        version.get("actor", "系统管理员"),
                        version.get("note", ""),
                        version_index,
                    ),
                )

        for index, log in enumerate(state["logs"]):
            db.execute(
                """
                INSERT INTO operation_logs (
                    id, log_time, actor, action, target, detail, sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log["id"],
                    log.get("time", ""),
                    log.get("actor", "系统管理员"),
                    log.get("action", ""),
                    log.get("target", ""),
                    log.get("detail", ""),
                    index,
                ),
            )

        db.execute(
            """
            INSERT INTO app_meta (key, value)
            VALUES ('initialized', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )


class DemoRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CampusActivityDemo/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "database": str(DB_PATH.name),
                    "initialized": read_state() is not None,
                }
            )
            return

        if path == "/api/state":
            state = read_state()
            self.send_json(
                {
                    "ok": True,
                    "initialized": state is not None,
                    "state": state,
                }
            )
            return

        if path == "/":
            self.path = "/activity-demo.html"
        super().do_GET()

    def do_PUT(self):
        path = urlparse(self.path).path
        if path != "/api/state":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_SIZE:
                raise ValueError("请求内容为空或过大")

            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            state = payload.get("state", payload)
            write_state(state)
            self.send_json({"ok": True})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self.send_json(
                {"ok": False, "error": str(error)},
                status=HTTPStatus.BAD_REQUEST,
            )
        except sqlite3.IntegrityError as error:
            self.send_json(
                {"ok": False, "error": f"数据库约束错误：{error}"},
                status=HTTPStatus.CONFLICT,
            )

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, PUT, OPTIONS")
        self.end_headers()

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(
        description="校园组织活动管理系统 Demo 后端"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()

    init_database()
    server = ThreadingHTTPServer((args.host, args.port), DemoRequestHandler)
    print(f"校园活动管理 Demo 已启动：http://{args.host}:{args.port}")
    print(f"SQLite 数据库：{DB_PATH}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
