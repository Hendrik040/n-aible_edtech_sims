"use client"

import React, { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight, FileText, Target, Database } from 'lucide-react'

interface DataFilePreview {
  headers: string[]
  rows: string[][]
  totalRows?: number
  totalCols?: number
  fileSize?: string
}

interface DataFile {
  filename: string
  description?: string
  preview?: DataFilePreview | string  // structured object or raw CSV text
  s3_key?: string
}

interface ReferenceFile {
  filename: string
  description?: string
  url?: string
  s3_key?: string
}

interface ResourcesPanelProps {
  dataFiles: DataFile[]
  referenceFiles?: ReferenceFile[]
  sceneObjective?: string
  dataPath?: string
}

/** Parse a raw CSV preview string (first N lines) into headers + rows */
function parseCsvPreview(raw: string): DataFilePreview | null {
  if (!raw || typeof raw !== 'string') return null
  const lines = raw.trim().split('\n').filter(Boolean)
  if (lines.length < 1) return null
  const headers = lines[0].split(',').map(h => h.trim())
  const rows = lines.slice(1).map(line => line.split(',').map(c => c.trim()))
  return { headers, rows, totalCols: headers.length }
}

export default function ResourcesPanel({
  dataFiles = [],
  referenceFiles = [],
  sceneObjective,
  dataPath = '/home/daytona/data/',
}: ResourcesPanelProps) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(
    new Set(dataFiles[0]?.filename ? [dataFiles[0].filename] : [])
  )

  // Normalize previews: parse raw CSV strings into structured format
  const normalizedFiles = useMemo(() => {
    return dataFiles.map(file => {
      if (!file.preview) return { ...file, parsedPreview: null }
      if (typeof file.preview === 'string') {
        return { ...file, parsedPreview: parseCsvPreview(file.preview) }
      }
      return { ...file, parsedPreview: file.preview as DataFilePreview }
    })
  }, [dataFiles])

  const toggleFile = (filename: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(filename)) {
        next.delete(filename)
      } else {
        next.add(filename)
      }
      return next
    })
  }

  return (
    <div className="flex flex-col h-full bg-[#0f172a] text-gray-200 overflow-y-auto">
      {/* Scene Objective */}
      {sceneObjective && (
        <div className="p-4 border-b border-[#1e293b]">
          <div className="bg-emerald-900/30 border border-emerald-700/40 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Target className="w-4 h-4 text-emerald-400" />
              <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider">
                Objective
              </span>
            </div>
            <p className="text-sm text-emerald-100 leading-relaxed">{sceneObjective}</p>
            {dataFiles.length > 0 && (
              <p className="text-xs text-emerald-400/70 mt-2">
                Data files are loaded at:{' '}
                <code className="bg-emerald-900/60 px-1.5 py-0.5 rounded text-emerald-300 font-mono">
                  {dataPath}
                </code>
              </p>
            )}
          </div>
        </div>
      )}

      {/* Dataset Previews */}
      {normalizedFiles.length > 0 && (
        <div className="p-4 border-b border-[#1e293b]">
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-blue-400" />
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
              Datasets ({normalizedFiles.length})
            </span>
          </div>
          <div className="space-y-2">
            {normalizedFiles.map((file) => {
              const isExpanded = expandedFiles.has(file.filename)
              const preview = file.parsedPreview
              return (
                <div
                  key={file.filename}
                  className={`bg-[#1e293b] border rounded-lg overflow-hidden transition-colors ${
                    isExpanded ? 'border-blue-500/50' : 'border-[#334155]'
                  }`}
                >
                  <button
                    onClick={() => toggleFile(file.filename)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-[#334155] transition-colors text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    )}
                    <span className="text-sm font-semibold text-gray-100 truncate flex-1">
                      {file.filename}
                    </span>
                    {preview && (
                      <span className="text-[10px] text-gray-500 flex-shrink-0">
                        {preview.rows?.length ?? '?'} rows
                        {preview.totalCols ? ` \u00d7 ${preview.totalCols} cols` : ''}
                      </span>
                    )}
                  </button>

                  {isExpanded && (
                    <div className="px-3 pb-3 border-t border-[#334155]">
                      {file.description && (
                        <p className="text-xs text-gray-400 mt-2 mb-2">{file.description}</p>
                      )}
                      {preview && preview.headers ? (
                        <div className="overflow-x-auto mt-2">
                          <table className="w-full text-[10px] font-mono border-collapse">
                            <thead>
                              <tr>
                                <th className="px-2 py-1.5 text-right text-gray-600 bg-[#1e293b] sticky top-0 font-normal">
                                  #
                                </th>
                                {preview.headers.map((header) => (
                                  <th
                                    key={header}
                                    className="px-2 py-1.5 text-left font-semibold text-blue-400 bg-[#1e293b] whitespace-nowrap sticky top-0 border-b border-[#334155]"
                                  >
                                    {header}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {preview.rows.map((row, i) => (
                                <tr key={i} className="hover:bg-blue-500/5 border-b border-[#1e293b]/80">
                                  <td className="px-2 py-1 text-right text-gray-600">{i}</td>
                                  {row.map((cell, j) => (
                                    <td key={j} className="px-2 py-1 text-gray-400 whitespace-nowrap">
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {preview.totalRows && preview.totalRows > preview.rows.length && (
                            <p className="text-[10px] text-gray-500 mt-1.5 text-center">
                              Showing {preview.rows.length} of {preview.totalRows} rows
                            </p>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500 mt-2">No preview available</p>
                      )}
                      <div className="mt-2">
                        <code className="text-[11px] text-gray-500 bg-[#0f172a] px-2 py-1 rounded font-mono inline-block">
                          {file.filename.match(/\.xlsx?$/i)
                            ? `pd.read_excel('${dataPath}${file.filename}')`
                            : file.filename.endsWith('.json')
                            ? `pd.read_json('${dataPath}${file.filename}')`
                            : `pd.read_csv('${dataPath}${file.filename}')`}
                        </code>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Reference Materials */}
      {referenceFiles && referenceFiles.length > 0 && (
        <div className="p-4 border-b border-[#1e293b]">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="w-4 h-4 text-gray-400" />
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
              Reference Materials ({referenceFiles.length})
            </span>
          </div>
          <div className="space-y-1.5">
            {referenceFiles.map((file) => (
              <div
                key={file.filename}
                className="flex items-center gap-3 px-3 py-2.5 bg-[#1e293b] border border-[#334155] rounded-lg"
              >
                <span className="text-lg flex-shrink-0">📄</span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-gray-200 truncate">{file.filename}</p>
                  {file.description && (
                    <p className="text-[10px] text-gray-500 truncate">{file.description}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scene Objective Tip (bottom section, matching mockup) */}
      {sceneObjective && dataFiles.length > 0 && (
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-4 h-4 text-gray-400" />
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
              Scene Objective
            </span>
          </div>
          <div className="bg-[#1e293b] border border-[#334155] rounded-lg p-3">
            <p className="text-xs text-gray-300 leading-relaxed">{sceneObjective}</p>
            <p className="text-[10px] text-gray-500 mt-2">
              Tip: Data is at{' '}
              <code className="bg-[#334155] px-1 py-0.5 rounded text-blue-400 font-mono">
                {dataPath}
              </code>
            </p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {dataFiles.length === 0 && (!referenceFiles || referenceFiles.length === 0) && (
        <div className="flex-1 flex items-center justify-center p-8">
          <p className="text-gray-500 text-sm text-center">No resources available for this scene.</p>
        </div>
      )}
    </div>
  )
}
