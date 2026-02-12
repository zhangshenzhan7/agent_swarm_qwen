import { useState, useEffect } from 'react'

const OUTPUT_TYPES = [
  { value: 'report', label: '文本报告' },
  { value: 'code', label: '代码' },
  { value: 'website', label: '网站' },
  { value: 'image', label: '图像' },
  { value: 'video', label: '视频' },
  { value: 'dataset', label: '数据集' },
  { value: 'document', label: '文档' },
  { value: 'composite', label: '组合输出' },
] as const

const SUB_TYPES = OUTPUT_TYPES.filter((t) => t.value !== 'composite')

interface OutputTypeSelectorProps {
  value: string
  onChange: (value: string, subTypes?: string[]) => void
}

export function OutputTypeSelector({ value, onChange }: OutputTypeSelectorProps) {
  const [selectedSubTypes, setSelectedSubTypes] = useState<string[]>([])

  useEffect(() => {
    if (value !== 'composite') {
      setSelectedSubTypes([])
    }
  }, [value])

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newValue = e.target.value
    if (newValue === 'composite') {
      onChange(newValue, [])
    } else {
      onChange(newValue)
    }
  }

  const handleSubTypeToggle = (subType: string) => {
    const updated = selectedSubTypes.includes(subType)
      ? selectedSubTypes.filter((t) => t !== subType)
      : [...selectedSubTypes, subType]
    setSelectedSubTypes(updated)
    onChange('composite', updated)
  }

  return (
    <div className="space-y-2">
      <label className="block text-xs text-gray-400">输出类型</label>
      <select
        value={value}
        onChange={handleTypeChange}
        className="w-full px-3 py-2 rounded-lg bg-[#0a0e17] border border-cyan-500/30
                   text-white text-sm focus:outline-none focus:border-cyan-400 transition-colors"
      >
        {OUTPUT_TYPES.map((type) => (
          <option key={type.value} value={type.value}>
            {type.label}
          </option>
        ))}
      </select>

      {value === 'composite' && (
        <div className="p-3 rounded-lg bg-[#0a0e17] border border-purple-500/30 space-y-2">
          <p className="text-xs text-gray-400">选择要包含的子输出类型：</p>
          <div className="grid grid-cols-2 gap-2">
            {SUB_TYPES.map((type) => (
              <label
                key={type.value}
                className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer
                           hover:text-white transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selectedSubTypes.includes(type.value)}
                  onChange={() => handleSubTypeToggle(type.value)}
                  className="rounded border-gray-600 bg-[#0a0e17] text-cyan-500
                             focus:ring-cyan-500 focus:ring-offset-0"
                />
                {type.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
