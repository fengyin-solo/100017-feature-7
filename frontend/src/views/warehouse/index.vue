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
      <span class="batch-info">已勾选 {{ selectedIds.length }} 条冷库档案</span>
      <button
        v-for="action in batchActions"
        :key="action"
        class="btn"
        type="button"
        :disabled="!selectedIds.length || batchSubmitting"
        @click="runBatchAction(action, selectedIds)"
      >
        批量{{ action }}
      </button>
      <span v-if="batchSubmitting" class="batch-info">批量处理中…</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input
              ref="selectAllBox"
              type="checkbox"
              :checked="allSelected"
              :disabled="!rows.length"
              @change="toggleSelectAll"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input type="checkbox" :checked="isSelected(row)" @change="toggleSelect(row)" />
          </td>
          <td v-for="column in columns" :key="column">
            {{ column === '启用状态' ? row.status ?? '—' : row[column] ?? '—' }}
          </td>
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

    <section v-if="batchResult" class="batch-result">
      <header class="batch-result-head">
        <strong>批量{{ batchResult.action }}结果</strong>
        <span class="batch-info">{{ resultSummary }} · {{ batchResult.finishedAt }}</span>
        <button class="link" type="button" @click="clearBatchResult">清除结果</button>
      </header>
      <ul class="batch-result-list">
        <li v-for="item in batchResult.items" :key="item.id" class="batch-result-item">
          <span class="badge" :class="`badge-${item.outcome}`">{{ outcomeLabels[item.outcome] ?? item.outcome }}</span>
          <span class="batch-code">{{ item.code }}</span>
          <span class="batch-message">{{ item.message }}</span>
          <button
            v-if="item.retryable"
            class="link"
            type="button"
            :disabled="batchSubmitting"
            @click="retryItem(item)"
          >
            重试
          </button>
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷库管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue'

import { request } from '@/api/client'
import { useWarehouseBatchStore } from '@/stores/warehouseBatch'
import type { BatchResult, BatchResultItem } from '@/stores/warehouseBatch'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/warehouse'
const columns = ["冷库编码", "冷库名称", "库区温区", "设定温度", "库容吨位", "责任人", "启用状态"]
const actions = ["启用冷库", "安排检修", "停用冷库"]
const batchActions = ["停用冷库", "安排检修"]
const statuses = ["已启用", "检修中", "已停用"]
const outcomeLabels: Record<string, string> = {
  success: '成功',
  duplicate: '重复提交',
  busy: '作业占用',
  failed: '失败',
}

const batchStore = useWarehouseBatchStore()

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '启用冷库', value: 0 },
  { label: '检修冷库', value: 0 },
  { label: '停用冷库', value: 0 },
])
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const selectedIds = ref<number[]>([])
const batchSubmitting = ref(false)
const selectAllBox = ref<HTMLInputElement | null>(null)

const batchResult = computed(() => batchStore.lastResult)
const resultSummary = computed(() => {
  const result = batchResult.value
  if (!result) {
    return ''
  }
  if (!result.items.length) {
    return result.message
  }
  const succeeded = result.items.filter((item) => item.outcome === 'success').length
  return `成功 ${succeeded} 条，未生效 ${result.items.length - succeeded} 条`
})

const allSelected = computed(() => rows.value.length > 0 && rows.value.every((row) => isSelected(row)))
const partiallySelected = computed(() => !allSelected.value && rows.value.some((row) => isSelected(row)))

watchEffect(() => {
  if (selectAllBox.value) {
    selectAllBox.value.indeterminate = partiallySelected.value
  }
})

function rowId(row: Row): number {
  return Number(row.id)
}

function isSelected(row: Row): boolean {
  return selectedIds.value.includes(rowId(row))
}

function toggleSelect(row: Row) {
  const id = rowId(row)
  selectedIds.value = isSelected(row)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleSelectAll() {
  selectedIds.value = allSelected.value ? [] : rows.value.map((row) => rowId(row))
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
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? '冷库管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷库管理操作失败'
  }
}

async function submitBatch(action: string, ids: number[]): Promise<BatchResult> {
  const response = await request(`${ENDPOINT}/batch-actions`, {
    method: 'POST',
    body: JSON.stringify({ action, ids }),
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload?.detail ?? '批量处理未生效，请稍后重试')
  }
  return {
    action,
    message: String(payload?.message ?? ''),
    finishedAt: new Date().toLocaleString(),
    items: (payload?.results ?? []) as BatchResultItem[],
  }
}

async function runBatchAction(action: string, ids: number[]) {
  if (!ids.length || batchSubmitting.value) {
    return
  }
  batchSubmitting.value = true
  errorMessage.value = ''
  try {
    const result = await submitBatch(action, ids)
    batchStore.saveResult(result)
    selectedIds.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量处理失败'
  } finally {
    batchSubmitting.value = false
  }
}

async function retryItem(item: BatchResultItem) {
  const action = batchResult.value?.action
  if (!action || batchSubmitting.value) {
    return
  }
  batchSubmitting.value = true
  errorMessage.value = ''
  try {
    const result = await submitBatch(action, [item.id])
    batchStore.mergeResult(result)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '单条重试失败'
  } finally {
    batchSubmitting.value = false
  }
}

function clearBatchResult() {
  batchStore.clearResult()
}

async function reloadStats() {
  try {
    const counts = await Promise.all(
      statuses.map(async (status) => {
        const response = await request(`${ENDPOINT}?status=${encodeURIComponent(status)}&size=1`)
        if (!response.ok) {
          throw new Error('冷库状态统计读取失败')
        }
        const payload = await response.json()
        return Number(payload?.total ?? 0)
      }),
    )
    stats.value = stats.value.map((item, index) => ({ ...item, value: counts[index] ?? 0 }))
  } catch {
    // 统计读取失败不阻塞列表展示
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
    void reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷库管理列表读取失败'
  }
}

onMounted(reload)
</script>
