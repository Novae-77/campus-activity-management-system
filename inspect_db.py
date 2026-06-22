import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "data" / "campus_activity.sqlite3"


def print_table(title, headers, rows, widths):
    print(f"\n{title}")
    print("-" * sum(widths))
    print("  ".join(str(value)[:width].ljust(width) for value, width in zip(headers, widths)))
    print("-" * sum(widths))
    for row in rows:
        print("  ".join(str(value or "")[:width].ljust(width) for value, width in zip(row, widths)))
    if not rows:
        print("暂无数据")


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}")
        print("请先运行 start-demo.bat。")
        return

    with sqlite3.connect(DB_PATH) as db:
        activity_rows = db.execute(
            """
            SELECT
                a.name,
                t.name,
                substr(a.start_time, 1, 16),
                a.location,
                a.version,
                CASE WHEN a.deleted = 1 THEN '已删除' ELSE '正常' END
            FROM activities a
            JOIN activity_types t ON t.id = a.type_id
            ORDER BY a.rowid DESC
            LIMIT 20
            """
        ).fetchall()

        participant_rows = db.execute(
            """
            SELECT
                a.name,
                u.name,
                p.attendance
            FROM activity_participants p
            JOIN activities a ON a.id = p.activity_id
            JOIN users u ON u.id = p.user_id
            ORDER BY p.rowid DESC
            LIMIT 20
            """
        ).fetchall()

        log_rows = db.execute(
            """
            SELECT
                substr(log_time, 1, 19),
                actor,
                action,
                target
            FROM operation_logs
            ORDER BY sort_order, rowid
            LIMIT 20
            """
        ).fetchall()

        counts = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM activities),
                (SELECT COUNT(*) FROM users),
                (SELECT COUNT(*) FROM activity_participants),
                (SELECT COUNT(*) FROM operation_logs)
            """
        ).fetchone()

    print(f"数据库文件：{DB_PATH}")
    print(
        f"活动 {counts[0]} 条｜人员 {counts[1]} 人｜"
        f"参与记录 {counts[2]} 条｜操作日志 {counts[3]} 条"
    )

    print_table(
        "最近活动",
        ("活动名称", "类型", "开始时间", "地点", "版本", "状态"),
        activity_rows,
        (30, 12, 18, 18, 6, 8),
    )
    print_table(
        "最近参与与签到记录",
        ("活动名称", "人员", "签到状态"),
        participant_rows,
        (30, 12, 12),
    )
    print_table(
        "最近操作日志",
        ("时间", "管理员", "操作", "活动/对象"),
        log_rows,
        (20, 12, 14, 32),
    )


if __name__ == "__main__":
    main()
