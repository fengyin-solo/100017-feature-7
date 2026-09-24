import { defineStore } from 'pinia'

/** 批量结果里单条记录的展示结构。 */
export interface BatchItem {
  id: number
  ok: boolean
  skipped: boolean
  message: string
  code: string
  name: string
}

/** 冷库批量处理结果：留在 store 里，路由切换后回到列表页仍能看到。 */
export const useWarehouseBatchStore = defineStore('warehouseBatch', {
  state: () => ({
    action: '',
    requestId: '',
    finishedAt: '',
    items: [] as BatchItem[],
  }),
  getters: {
    hasResult: (state) => state.items.length > 0,
    succeededCount: (state) => state.items.filter((item) => item.ok).length,
    skippedCount: (state) => state.items.filter((item) => item.skipped).length,
    failedItems: (state) => state.items.filter((item) => !item.ok && !item.skipped),
  },
  actions: {
    record(action: string, requestId: string, items: BatchItem[]) {
      this.action = action
      this.requestId = requestId
      this.finishedAt = new Date().toLocaleString()
      this.items = items
    },
    replaceItem(item: BatchItem) {
      const index = this.items.findIndex((current) => current.id === item.id)
      if (index >= 0) {
        this.items.splice(index, 1, item)
      }
    },
    clear() {
      this.action = ''
      this.requestId = ''
      this.finishedAt = ''
      this.items = []
    },
  },
})
