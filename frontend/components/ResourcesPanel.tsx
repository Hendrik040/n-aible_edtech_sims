"use client"

import React, { useState } from 'react'
import { ChevronDown, ChevronRight, FileText, Download, Target, Database } from 'lucide-react'

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
  preview?: DataFilePreview
}

interface ReferenceFile {
  filename: string
  description?: string
  url: string
}

interface ResourcesPanelProps {
  dataFiles: DataFile[]
  referenceFiles?: ReferenceFile[]
  sceneObjective?: string
  dataPath?: string
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
    <div className="flex flex-col h-full bg-gray-900 text-gray-200 overflow-y-auto">
      {/* Scene Objective */}
      {sceneObjective && (
        <div className="p-4 border-b border-gray-700">
          <div className="bg-emerald-900/40 border border-emerald-700/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Target className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-emerald-300 uppercase tracking-wide">
                Objective
              </span>
            </div>
            <p className="text-sm text-emerald-100 leading-relaxed">{sceneObjective}</p>
            {dataFiles.length > 0 && (
              <p className="text-xs text-emerald-400/70 mt-2">
                Data files are loaded at: <code className="bg-emerald-900/60 px-1.5 py-0.5 rounded text-emerald-300">{dataPath}</code>
              </p>
            )}
          </div>
        </div>
      )}

      {/* Dataset Previews */}
      {dataFiles.length > 0 && (
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-semibold text-gray-200">
              Datasets ({dataFiles.length})
            </span>
          </div>
          <div className="space-y-2">
            {dataFiles.map((file) => {
              const isExpanded = expandedFiles.has(file.filename)
              return (
                <div
                  key={file.filename}
                  className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden"
                >
                  <button
                    onClick={() => toggleFile(file.filename)}
                    className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-gray-750 transition-colors text-left"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      )}
                      <span className="text-sm font-medium text-gray-200 truncate">
                        {file.filename}
                      </span>
                    </div>
                    {file.preview && (
                      <span className="text-xs text-gray-500 flex-shrink-0 ml-2">
                        {file.preview.totalRows ?? '?'} rows x {file.preview.totalCols ?? file.preview.headers?.length ?? '?'} cols
                      </span>
                    )}
                  </button>

                  {isExpanded && (
                    <div className="px-3 pb-3 border-t border-gray-700">
                      {file.description && (
                        <p className="text-xs text-gray-400 mt-2 mb-2">{file.description}</p>
                      )}
                      {file.preview ? (
                        <div className="overflow-x-auto mt-2">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b border-gray-600">
                                {file.preview.headers.map((header) => (
                                  <th
                                    key={header}
                                    className="px-2 py-1.5 text-left font-semibold text-blue-300 whitespace-nowrap"
                                  >
                                    {header}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {file.preview.rows.map((row, i) => (
                                <tr key={i} className="border-b border-gray-700/50">
                                  {row.map((cell, j) => (
                                    <td key={j} className="px-2 py-1 text-gray-300 whitespace-nowrap">
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {file.preview.totalRows && file.preview.totalRows > 5 && (
                            <p className="text-xs text-gray-500 mt-1.5 text-center">
                              Showing first 5 of {file.preview.totalRows} rows
                            </p>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500 mt-2">No preview available</p>
                      )}
                      <div className="mt-2">
                        <code className="text-xs text-gray-500 bg-gray-900 px-2 py-1 rounded">
                          pd.read_csv(&apos;{dataPath}{file.filename}&apos;)
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
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-semibold text-gray-200">
              Reference Materials ({referenceFiles.length})
            </span>
          </div>
          <div className="space-y-2">
            {referenceFiles.map((file) => (
              <a
                key={file.filename}
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-750 transition-colors"
              >
                <Download className="w-4 h-4 text-purple-400 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-200 truncate">{file.filename}</p>
                  {file.description && (
                    <p className="text-xs text-gray-500 truncate">{file.description}</p>
                  )}
                </div>
              </a>
            ))}
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
