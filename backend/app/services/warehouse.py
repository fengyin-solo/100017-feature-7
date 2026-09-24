"""冷库管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "warehouse"
REQUIRED_FIELDS = ["冷库编码", "冷库名称", "库区温区"]
STATUS_ORDER = ["已启用", "检修中", "已停用"]
ACTION_RULES = {"启用冷库": "已启用", "安排检修": "检修中", "停用冷库": "已停用"}
NEGATIVE_ACTIONS = ["停用冷库"]

# 停用与检修会中断作业：冷库上还有进行中的出入库单时必须先拦住。
GUARDED_ACTIONS = ["安排检修", "停用冷库"]
ACTIVE_INBOUND_STATUSES = ["待收货", "已收货"]
ACTIVE_OUTBOUND_STATUSES = ["待拣货", "已拣货"]


class WarehouseService:
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

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷库档案 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于冷库管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        busy = self._busy_operations(entry, action)
        if busy:
            return None, f"冷库仍有进出库作业（{'、'.join(busy)}），请先完成或转移作业"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"冷库档案已{action}"

    def run_batch_action(self, action: str, entry_ids: list[int]) -> tuple[list[dict[str, Any]], str]:
        """批量执行冷库动作：逐条处理互不影响，正在作业的冷库跳过，重复提交只生效一次。"""
        if action not in ACTION_RULES:
            return [], f"动作「{action}」不属于冷库管理可执行范围"
        if not entry_ids:
            return [], "请先勾选要处理的冷库档案"
        target = ACTION_RULES[action]
        results: list[dict[str, Any]] = []
        for entry_id in dict.fromkeys(entry_ids):
            entry = store.find(MODULE, entry_id)
            if entry is None:
                results.append(self._batch_item(entry_id, "—", "failed", f"冷库档案 {entry_id} 不存在或已归档", retryable=False))
                continue
            code = str(entry.get("冷库编码", ""))
            if entry.get("status") == target:
                results.append(self._batch_item(entry_id, code, "duplicate", f"冷库已处于「{target}」，本次重复提交不再重复处理", retryable=False))
                continue
            busy = self._busy_operations(entry, action)
            if busy:
                results.append(self._batch_item(entry_id, code, "busy", f"冷库仍有进出库作业（{'、'.join(busy)}），已跳过，请先完成或转移作业", retryable=True))
                continue
            entry["status"] = target
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            results.append(self._batch_item(entry_id, code, "success", f"冷库档案已{action}", retryable=False))
        succeeded = sum(1 for item in results if item["outcome"] == "success")
        message = f"批量{action}完成：成功 {succeeded} 条，未生效 {len(results) - succeeded} 条"
        return results, message

    def _busy_operations(self, entry: dict[str, Any], action: str) -> list[str]:
        """列出冷库上仍在进行的出入库作业；仅停用、检修类动作需要拦截。"""
        if action not in GUARDED_ACTIONS:
            return []
        code = str(entry.get("冷库编码", ""))
        if not code:
            return []
        busy: list[str] = []
        for row in store.rows("inbound"):
            if row.get("作业冷库") == code and row.get("status") in ACTIVE_INBOUND_STATUSES:
                busy.append(f"入库单{row.get('入库单号', row.get('id'))}（{row.get('status')}）")
        for row in store.rows("outbound"):
            if row.get("作业冷库") == code and row.get("status") in ACTIVE_OUTBOUND_STATUSES:
                busy.append(f"出库单{row.get('出库单号', row.get('id'))}（{row.get('status')}）")
        return busy

    @staticmethod
    def _batch_item(entry_id: int, code: str, outcome: str, message: str, *, retryable: bool) -> dict[str, Any]:
        return {
            "id": entry_id,
            "code": code,
            "outcome": outcome,
            "message": message,
            "retryable": retryable,
        }
