"""冷库管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "warehouse"
REQUIRED_FIELDS = ["冷库编码", "冷库名称", "库区温区"]
STATUS_ORDER = ["已启用", "检修中", "已停用"]
ACTION_RULES = {"启用冷库": "已启用", "安排检修": "检修中", "停用冷库": "已停用"}
NEGATIVE_ACTIONS = ["停用冷库"]

# 批量入口只开放停用与检修两类动作
BATCH_ACTIONS = ["停用冷库", "安排检修"]
# 正在进出库作业的冷库不允许停用或检修，只能跳过等作业结束
BUSY_STATE = "进出库作业中"
IDLE_STATE = "空闲"
BUSY_BLOCKED_ACTIONS = ["停用冷库", "安排检修"]


class WarehouseService:
    def __init__(self) -> None:
        # 幂等键 -> 批量结果；重复提交同一 request_id 直接返回首次结果
        self._batch_history: dict[str, dict[str, Any]] = {}
        self._last_batch: dict[str, Any] | None = None

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("冷库编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def status_summary(self) -> dict[str, Any]:
        """按启用状态统计冷库数量，给列表页统计卡用。"""
        rows = store.rows(MODULE)
        by_status = {status: 0 for status in STATUS_ORDER}
        busy = 0
        for row in rows:
            status = str(row.get("status") or "")
            if status in by_status:
                by_status[status] += 1
            if row.get("作业状态") == BUSY_STATE:
                busy += 1
        return {"total": len(rows), "by_status": by_status, "busy": busy}

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["启用状态"] = STATUS_ORDER[0]
        entry["作业状态"] = IDLE_STATE
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷库档案 {entry_id} 不存在或已归档"
        ok, _, message = self._apply_action(entry, action)
        if not ok:
            return None, message
        return entry, message

    def run_batch_action(
        self,
        ids: list[int],
        action: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """批量执行动作：逐条独立处理，单条失败不影响同组其他记录。

        request_id 相同的重复提交直接返回首次处理结果，不会重复生效。
        """
        if request_id and request_id in self._batch_history:
            cached = dict(self._batch_history[request_id])
            cached["duplicated"] = True
            cached["message"] += "（重复提交，已按首次结果返回）"
            return cached
        if action not in BATCH_ACTIONS:
            return self._remember(request_id, {
                "ok": False,
                "message": f"动作「{action}」不支持批量执行，批量入口仅开放停用冷库与安排检修",
                "action": action,
                "request_id": request_id,
                "results": [],
            })
        if not ids:
            return self._remember(request_id, {
                "ok": False,
                "message": "请先勾选要处理的冷库档案",
                "action": action,
                "request_id": request_id,
                "results": [],
            })
        results: list[dict[str, Any]] = []
        for entry_id in ids:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                results.append({
                    "id": entry_id,
                    "ok": False,
                    "skipped": False,
                    "message": f"冷库档案 {entry_id} 不存在或已归档",
                    "entry": None,
                })
                continue
            ok, skipped, message = self._apply_action(entry, action)
            results.append({
                "id": entry_id,
                "ok": ok,
                "skipped": skipped,
                "message": message,
                "entry": dict(entry),
            })
        succeeded = sum(1 for item in results if item["ok"])
        skipped_count = sum(1 for item in results if item["skipped"])
        failed = len(results) - succeeded - skipped_count
        return self._remember(request_id, {
            "ok": failed == 0,
            "message": (
                f"批量{action}完成：成功 {succeeded} 条，"
                f"跳过 {skipped_count} 条，失败 {failed} 条"
            ),
            "action": action,
            "request_id": request_id,
            "results": results,
        })

    def latest_batch(self) -> dict[str, Any] | None:
        """最近一次批量处理结果，供页面返回后恢复展示。"""
        return self._last_batch

    def _remember(self, request_id: str | None, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("duplicated", False)
        results = result.get("results") or []
        result["total"] = len(results)
        result["succeeded"] = sum(1 for item in results if item["ok"])
        result["skipped"] = sum(1 for item in results if item["skipped"])
        result["failed"] = result["total"] - result["succeeded"] - result["skipped"]
        if request_id:
            self._batch_history[request_id] = dict(result)
        if results:
            self._last_batch = dict(result)
        return result

    def _apply_action(self, entry: dict[str, Any], action: str) -> tuple[bool, bool, str]:
        """状态流转唯一入口，返回 (是否成功, 是否跳过, 说明)。

        已处于目标状态时直接算成功且不再改动，保证重复提交只生效一次。
        """
        if action not in ACTION_RULES:
            return False, False, f"动作「{action}」不属于冷库管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return False, False, f"目标状态「{target}」不在允许的状态序列里"
        if action in BUSY_BLOCKED_ACTIONS and entry.get("作业状态") == BUSY_STATE:
            return False, True, f"冷库正在进出库作业，{action}已跳过，待作业结束后再处理"
        if entry.get("status") == target:
            return True, False, f"冷库已处于「{target}」，无需重复{action}"
        entry["status"] = target
        entry["启用状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return True, False, f"冷库档案已{action}"
