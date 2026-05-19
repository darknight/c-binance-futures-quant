import React from 'react'
import { Table, Alert } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { create } from 'zustand'
import { fetchBigLossTrades } from '../api/dashboard'
import type { BigLossTradeItem } from '../types'

interface BigLossState {
  data: BigLossTradeItem[]
  loading: boolean
  fetch: () => Promise<void>
}

const useBigLossStore = create<BigLossState>((set) => ({
  data: [],
  loading: true,
  fetch: async () => {
    try {
      const resp = await fetchBigLossTrades()
      if (resp.s === 'ok') set({ data: resp.d, loading: false })
    } catch {
      set({ loading: false })
    }
  },
}))

const columns: ColumnsType<BigLossTradeItem> = [
  { title: '交易对', dataIndex: 'symbol', key: 'symbol' },
  { title: '时间', dataIndex: 'time', key: 'time' },
  { title: '方向', dataIndex: 'direction', key: 'direction' },
  {
    title: '收益金额',
    dataIndex: 'profit',
    key: 'profit',
    sorter: (a, b) => Number(a.profit) - Number(b.profit),
  },
  {
    title: '收益占余额比例',
    dataIndex: 'profitPercentByBalance',
    key: 'profitPercentByBalance',
    sorter: (a, b) =>
      parseFloat(a.profitPercentByBalance) - parseFloat(b.profitPercentByBalance),
  },
  {
    title: '价格变化',
    dataIndex: 'priceRate',
    key: 'priceRate',
    sorter: (a, b) => parseFloat(a.priceRate) - parseFloat(b.priceRate),
  },
]

export default function BigLossTable() {
  const { data, loading, fetch: fetchData } = useBigLossStore()
  const mounted = React.useRef(false)

  React.useEffect(() => {
    if (mounted.current) return
    mounted.current = true
    fetchData()
    const timer = setInterval(fetchData, 60_000)
    return () => clearInterval(timer)
  }, [fetchData])

  if (!loading && data.length === 0) {
    return (
      <Alert
        message="当前暂未读取到大额亏损交易，该数据自2023年5月19日开始记录"
        type="warning"
      />
    )
  }

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey={(_, i) => String(i)}
      loading={loading}
      pagination={{ pageSize: 10 }}
      showSorterTooltip={false}
    />
  )
}
