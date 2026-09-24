import { defineStore } from 'pinia'

export interface BatchResultItem {
  id: number
  code: string
  outcome: 'success' | 'duplicate' | 'busy' | 'failed'
  message: string
  retryable: boolean
}

export interface BatchResult {
  action: string
  message: string
  finishedAt: string
  items: BatchResultItem[]
}

const STORAGE_KEY = 'warehouse-batch-result'

function loadResult(): BatchResult | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as BatchResult) : null
  } catch {
    return null
  }
}

function persist(result: BatchResult | null) {
  try {
    if (result) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(result))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // 本地存储不可用时只保留在内存里
  }
}

export const useWarehouseBatchStore = defineStore('warehouseBatch', {
  state: () => ({
    lastResult: loadResult() as BatchResult | null,
  }),
  actions: {
    saveResult(result: BatchResult) {
      this.lastResult = result
      persist(result)
    },
    mergeResult(result: BatchResult) {
      // 单条重试只回传一条结果：按 id 覆盖旧结果，保留其余条目
      const current = this.lastResult
      if (!current || current.action !== result.action) {
        this.saveResult(result)
        return
      }
      const incoming = new Map(result.items.map((item) => [item.id, item]))
      const items = current.items.map((item) => incoming.get(item.id) ?? item)
      for (const item of result.items) {
        if (!items.some((old) => old.id === item.id)) {
          items.push(item)
        }
      }
      this.saveResult({ ...result, items })
    },
    clearResult() {
      this.lastResult = null
      persist(null)
    },
  },
})
