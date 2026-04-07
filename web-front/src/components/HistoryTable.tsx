import { Table, Alert } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useProfitStore } from '../stores/useProfitStore'
import type { HistoryRow } from '../types'

const numSorter = (field: keyof HistoryRow) => (a: HistoryRow, b: HistoryRow) =>
  parseFloat(a[field]) - parseFloat(b[field])

const columns: ColumnsType<HistoryRow> = [
  { title: '交易对', dataIndex: 'symbol', key: 'symbol' },
  { title: '昨日利润', dataIndex: 'yesterdayProfit', key: 'yesterdayProfit', sorter: numSorter('yesterdayProfit') },
  { title: '昨日BNB', dataIndex: 'yesterdayVol', key: 'yesterdayVol', sorter: numSorter('yesterdayVol') },
  { title: '昨日手续费', dataIndex: 'yesterdayCommission', key: 'yesterdayCommission', sorter: numSorter('yesterdayCommission') },
  { title: '周利润', dataIndex: 'weekProfit', key: 'weekProfit', sorter: numSorter('weekProfit') },
  { title: '周BNB', dataIndex: 'weekVol', key: 'weekVol', sorter: numSorter('weekVol') },
  { title: '周手续费', dataIndex: 'weekCommission', key: 'weekCommission', sorter: numSorter('weekCommission') },
  { title: '月利润', dataIndex: 'monthProfit', key: 'monthProfit', sorter: numSorter('monthProfit') },
  { title: '月BNB', dataIndex: 'monthVol', key: 'monthVol', sorter: numSorter('monthVol') },
  { title: '月手续费', dataIndex: 'monthCommission', key: 'monthCommission', sorter: numSorter('monthCommission') },
  { title: '总利润', dataIndex: 'allProfit', key: 'allProfit', sorter: numSorter('allProfit') },
  { title: '总BNB', dataIndex: 'allVol', key: 'allVol', sorter: numSorter('allVol') },
  { title: '总手续费', dataIndex: 'allCommission', key: 'allCommission', sorter: numSorter('allCommission') },
]

export default function HistoryTable() {
  const { historyRows, historyUpdateTime } = useProfitStore()

  return (
    <div>
      <Alert
        style={{ marginBottom: 16 }}
        message={`更新于：${historyUpdateTime}，利润为净利润，即算上手续费和资金费率后的利润，手续费为负代表付出手续费，手续费为正代表收取手续费`}
        type="warning"
      />
      <Table
        columns={columns}
        dataSource={historyRows}
        rowKey="key"
        pagination={false}
        showSorterTooltip={false}
        scroll={{ x: true }}
      />
    </div>
  )
}
