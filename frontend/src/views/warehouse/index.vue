<template>
  <section class="page" data-module="warehouse">
    <header class="page-head">
      <div>
        <h2>冷库管理管理</h2>
        <p class="page-desc">维护冷库档案，围绕冷库编码、冷库名称、库区温区、设定温度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记冷库档案</button>
        <button class="btn" type="button" @click="exportRows">导出冷库管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <span class="batch-count">已选 {{ selectedIds.length }} 项</span>
      <button
        class="btn primary"
        type="button"
        :disabled="!selectedIds.length || batchSubmitting"
        @click="submitBatch('停用冷库')"
      >
        批量停用
      </button>
      <button
        class="btn"
        type="button"
        :disabled="!selectedIds.length || batchSubmitting"
        @click="submitBatch('安排检修')"
      >
        批量安排检修
      </button>
      <button
        class="btn ghost"
        type="button"
        :disabled="!selectedIds.length || batchSubmitting"
        @click="clearSelection"
      >
        清空选择
      </button>
      <span class="batch-hint">正在进出库作业的冷库会自动跳过并说明原因</span>
    </div>

    <section v-if="batchStore.hasResult" class="batch-result">
      <header class="batch-result-head">
        <strong>批量{{ batchStore.action }}结果</strong>
        <span>
          成功 {{ batchStore.succeededCount }} 条 · 跳过 {{ batchStore.skippedCount }} 条 ·
          失败 {{ batchStore.failedItems.length }} 条
        </span>
        <span class="batch-hint">{{ batchStore.finishedAt }}</span>
        <button class="link" type="button" @click="batchStore.clear()">收起结果</button>
      </header>
      <ul class="batch-result-list">
        <li v-for="item in batchStore.items" :key="item.id">
          <span class="tag" :class="resultClass(item)">{{ resultLabel(item) }}</span>
          <span class="batch-item-name">{{ item.code }} {{ item.name }}</span>
          <span class="batch-item-message">{{ item.message }}</span>
          <button
            v-if="!item.ok && !item.skipped"
            class="link"
            type="button"
            :disabled="retryingId !== null"
            @click="retryItem(item)"
          >
            {{ retryingId === item.id ? '重试中…' : '重试' }}
          </button>
        </li>
      </ul>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input type="checkbox" :checked="allChecked" @change="toggleAll" />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input
              type="checkbox"
              :checked="selectedIds.includes(Number(row.id))"
              @change="toggleOne(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无冷库管理数据，可先登记冷库档案</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷库管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useWarehouseBatchStore, type BatchItem } from '@/stores/warehouseBatch'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/warehouse'
const columns = ["冷库编码", "冷库名称", "库区温区", "设定温度", "库容吨位", "责任人", "作业状态", "启用状态"]
const actions = ["启用冷库", "安排检修", "停用冷库"]
const batchActions = ["停用冷库", "安排检修"]

const batchStore = useWarehouseBatchStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const summary = ref<{ total: number; by_status: Record<string, number>; busy: number }>({
  total: 0,
  by_status: {},
  busy: 0,
})
const selectedIds = ref<number[]>([])
const batchSubmitting = ref(false)
const retryingId = ref<number | null>(null)

const stats = computed(() => [
  { label: '启用冷库', value: summary.value.by_status['已启用'] ?? 0 },
  { label: '检修冷库', value: summary.value.by_status['检修中'] ?? 0 },
  { label: '停用冷库', value: summary.value.by_status['已停用'] ?? 0 },
])

const allChecked = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)

function toggleAll() {
  selectedIds.value = allChecked.value ? [] : rows.value.map((row) => Number(row.id))
}

function toggleOne(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((current) => current !== id)
    : [...selectedIds.value, id]
}

function clearSelection() {
  selectedIds.value = []
}

function newRequestId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `batch-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function toBatchItem(result: Record<string, unknown>): BatchItem {
  const entry = (result.entry ?? {}) as Record<string, unknown>
  const id = Number(result.id)
  return {
    id,
    ok: Boolean(result.ok),
    skipped: Boolean(result.skipped),
    message: String(result.message ?? ''),
    code: String(entry['冷库编码'] ?? `#${id}`),
    name: String(entry['冷库名称'] ?? ''),
  }
}

function resultLabel(item: BatchItem) {
  if (item.ok) return '成功'
  if (item.skipped) return '跳过'
  return '失败'
}

function resultClass(item: BatchItem) {
  if (item.ok) return 'ok'
  if (item.skipped) return 'skip'
  return 'fail'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '冷库档案登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '冷库管理动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷库管理操作失败'
  }
}

async function submitBatch(action: string) {
  if (!selectedIds.value.length || batchSubmitting.value || !batchActions.includes(action)) return
  batchSubmitting.value = true
  errorMessage.value = ''
  const requestId = newRequestId()
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ ids: selectedIds.value, action, request_id: requestId }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '批量处理请求被拒绝，请稍后重试')
    }
    const items = ((payload.results ?? []) as Record<string, unknown>[]).map(toBatchItem)
    batchStore.record(action, requestId, items)
    selectedIds.value = []
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量处理失败'
  } finally {
    batchSubmitting.value = false
  }
}

async function retryItem(item: BatchItem) {
  if (retryingId.value !== null) return
  retryingId.value = item.id
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ ids: [item.id], action: batchStore.action, request_id: newRequestId() }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '重试请求被拒绝，请稍后再试')
    }
    const [result] = (payload.results ?? []) as Record<string, unknown>[]
    if (result) {
      batchStore.replaceItem(toBatchItem(result))
    }
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重试失败'
  } finally {
    retryingId.value = null
  }
}

async function restoreBatchResult() {
  if (batchStore.hasResult) return
  try {
    const response = await request(`${ENDPOINT}/batch/latest`)
    if (!response.ok) return
    const payload = await response.json()
    const results = (payload.results ?? []) as Record<string, unknown>[]
    if (results.length) {
      batchStore.record(String(payload.action ?? ''), String(payload.request_id ?? ''), results.map(toBatchItem))
    }
  } catch {
    // 恢复历史结果失败不影响列表正常使用
  }
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) return
    summary.value = await response.json()
  } catch {
    // 统计卡刷新失败不打断列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('冷库档案列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷库管理列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
  void restoreBatchResult()
})
</script>
