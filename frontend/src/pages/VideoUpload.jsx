import React, { useState, useEffect, useRef, useCallback } from 'react'
import { uploadVideo, getVideoJobStatus, listVideoJobs, getProcessedVideoUrl } from '../services/api'
import toast from 'react-hot-toast'


const ACCEPTED_FORMATS = '.mp4,.avi,.mov,.mkv,.webm,.flv,.wmv'
const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500 MB

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '--:--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const d = new Date(timestamp * 1000)
  return d.toLocaleTimeString()
}

function JobCard({ job }) {
  const isProcessing = job.status === 'processing' || job.status === 'queued'
  const isCompleted = job.status === 'completed'
  const isFailed = job.status === 'failed'
  const progressPct = Math.round((job.progress || 0) * 100)
  const downloadUrl = getProcessedVideoUrl(job.job_id)

  // Force <video> to reload when the job transitions to processing/completed.
  const videoKey = `${job.job_id}-${job.status}-${job.progress || 0}`

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 space-y-3">

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-white truncate">{job.filename}</span>
        </div>
        <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
          isProcessing ? 'bg-amber-500/20 text-amber-400' :
          isCompleted ? 'bg-emerald-500/20 text-emerald-400' :
          isFailed ? 'bg-red-500/20 text-red-400' :
          'bg-slate-600/20 text-slate-400'
        }`}>
          {job.status}
        </span>
      </div>


        {isProcessing && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-slate-400">
            <span>{progressPct}% processed</span>
            {job.stage && job.stage !== 'queued' && (
              <span className="text-slate-400">{job.stage.replace('_',' ')}</span>
            )}

            {job.processed_frames > 0 && (
              <span>{job.processed_frames} / {job.total_frames || '?'} frames</span>
            )}
          </div>
          <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary-500 rounded-full transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {(job.total_violations > 0 || job.person_count > 0) && (
            <div className="flex gap-3 text-xs text-slate-400">
              {job.person_count > 0 && (
                <span>👷 {job.person_count} worker(s)</span>
              )}
              {job.total_violations > 0 && (
                <span className="text-amber-400">⚠ {job.total_violations} violation(s)</span>
              )}
              {job.avg_inference_ms > 0 && (
                <span>⏱ {job.avg_inference_ms}ms/frame</span>
              )}
            </div>
          )}
        </div>
      )}





      {isFailed && (
        <div className="text-xs text-red-400 bg-red-500/10 rounded-lg p-2">
          {job.error || 'Processing failed'}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{formatTime(job.created_at)}</span>
        {isCompleted && downloadUrl && (
          <div className="w-full">
            <div className="mt-2">
              <video
                key={videoKey}
                src={downloadUrl}
                controls
                playsInline
                preload="metadata"
                className="w-full max-h-72 rounded-lg border border-slate-700/50 bg-black"
              />
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-slate-500">Preview + download</span>
              <a
                href={downloadUrl}
                download
                className="text-xs font-medium text-primary-400 hover:text-primary-300 transition-colors bg-primary-500/10 hover:bg-primary-500/20 px-3 py-1.5 rounded-lg"
              >
                <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download Result
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function VideoUpload() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [jobs, setJobs] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const [recentJobId, setRecentJobId] = useState(null)
  const pollingRef = useRef(null)
  const fileInputRef = useRef(null)

  const fetchJobs = useCallback(async () => {
    try {
      const res = await listVideoJobs()
      setJobs(res.data.jobs || [])
    } catch {
      // silently fail on poll
    }
  }, [])

  useEffect(() => {
    fetchJobs()
  }, [fetchJobs])

  // Poll for job status updates
  useEffect(() => {
    if (!recentJobId) return

    // Avoid UI reset on transient polling failures.
    // Only reset after a few consecutive failures.
    let consecutiveFailures = 0
    const MAX_CONSECUTIVE_FAILURES = 10

    pollingRef.current = setInterval(async () => {
      try {
        const res = await getVideoJobStatus(recentJobId)
        consecutiveFailures = 0

        if (res.data.status === 'completed' || res.data.status === 'failed') {
          clearInterval(pollingRef.current)
          pollingRef.current = null
          setRecentJobId(null)
          fetchJobs()
          if (res.data.status === 'completed') {
            toast.success('Video processing completed!')
          } else {
            toast.error('Video processing failed')
          }
        } else {
          // Update the job in the list
          setJobs(prev => prev.map(j => j.job_id === recentJobId ? { ...j, ...res.data } : j))
        }
      } catch (err) {
        consecutiveFailures += 1

        // Throttle toast noise: only show after a couple failures.
        if (consecutiveFailures === 2) {
          toast.error('Connection issue while checking job status. Retrying...')
        }

        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
          setRecentJobId(null)
          toast.error('Could not retrieve job status. Please check jobs and retry if needed.')
        }
      }
    }, 2000)

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [recentJobId, fetchJobs])

  const handleFile = (selectedFile) => {
    if (!selectedFile) return

    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase()
    if (!ACCEPTED_FORMATS.includes(ext)) {
      toast.error(`Unsupported format. Accepted: ${ACCEPTED_FORMATS}`)
      return
    }

    if (selectedFile.size > MAX_FILE_SIZE) {
      toast.error(`File too large (${formatBytes(selectedFile.size)}). Max: 500 MB`)
      return
    }

    setFile(selectedFile)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files[0])
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setUploadProgress(0)

    try {
      const res = await uploadVideo(file, (progressEvent) => {
        const pct = progressEvent.total
          ? Math.round((progressEvent.loaded * 100) / progressEvent.total)
          : 0
        setUploadProgress(pct)
      })

      const jobId = res.data?.job_id
      if (!jobId) throw new Error('Upload succeeded but no job_id returned')

      // Keep a stable UI state while processing: don’t clear `file`.
      // Job cards + polling will show the annotated preview once completed.
      setRecentJobId(jobId)
      setUploadProgress(0)
      setFile(null)
      toast.success('Video uploaded! Processing started.')
      fetchJobs()
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Upload failed'
      if (err.code === 'ECONNABORTED') {
        toast.error('Upload timed out. Try a smaller file or check your connection.')
      } else {
        toast.error(msg)
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Video Upload</h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload a video for PPE detection analysis. The system will process it and generate an annotated result.
        </p>
      </div>

      {/* Upload Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`relative cursor-pointer border-2 border-dashed rounded-2xl p-10 text-center transition-all ${
          dragOver
            ? 'border-primary-500 bg-primary-500/10'
            : file
              ? 'border-emerald-500/50 bg-emerald-500/5'
              : 'border-slate-600 hover:border-slate-500 bg-slate-800/30'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_FORMATS}
          className="hidden"
          onChange={(e) => handleFile(e.target.files[0])}
          disabled={uploading}
        />

        {uploading ? (
          <div className="space-y-3">
            <div className="w-14 h-14 mx-auto rounded-full bg-primary-500/20 flex items-center justify-center animate-pulse">
              <svg className="w-7 h-7 text-primary-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
            <p className="text-sm text-slate-300">Uploading... {uploadProgress}%</p>
            <div className="w-full max-w-xs mx-auto h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-primary-500 rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
            </div>
          </div>
        ) : file ? (
          <div className="space-y-3">
            <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/20 flex items-center justify-center">
              <svg className="w-7 h-7 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-white">{file.name}</p>
            <p className="text-xs text-slate-400">{formatBytes(file.size)}</p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={(e) => { e.stopPropagation(); setFile(null) }}
                className="text-xs text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-700 px-3 py-1.5 rounded-lg transition-colors"
              >
                Remove
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleUpload() }}
                disabled={uploading || !!recentJobId}
                className={`text-xs font-medium text-white bg-primary-600 hover:bg-primary-500 px-4 py-1.5 rounded-lg transition-colors ${
                  uploading || !!recentJobId ? 'opacity-60 cursor-not-allowed' : ''
                }`}
              >
                {uploading || !!recentJobId ? 'Processing…' : 'Upload & Process'}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="w-14 h-14 mx-auto rounded-full bg-slate-700/50 flex items-center justify-center">
              <svg className="w-7 h-7 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-sm text-slate-300">
              <span className="text-primary-400 font-medium">Click to browse</span> or drag & drop
            </p>
            <p className="text-xs text-slate-500">MP4, AVI, MOV, MKV, WebM (max 500 MB)</p>
          </div>
        )}
      </div>

      {/* Recent Jobs + Old Jobs */}
      <div className="space-y-8">
        <div>
          <h2 className="text-lg font-semibold text-white mb-3">
            Recent Jobs
            {jobs.length > 0 && (
              <span className="ml-2 text-sm font-normal text-slate-400">({jobs.length})</span>
            )}
          </h2>

          {jobs.length === 0 ? (
            <div className="text-center py-10 text-slate-500">
              <svg className="w-10 h-10 mx-auto mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <p className="text-sm">No videos processed yet</p>
              <p className="text-xs mt-1">Upload a video above to get started</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {jobs.filter(j => j.job_id === recentJobId).length > 0
                ? jobs.filter(j => j.job_id === recentJobId).map((job) => (
                    <JobCard key={job.job_id} job={job} />
                  ))
                : jobs.slice(0, 1).map((job) => (
                    <JobCard key={job.job_id} job={job} />
                  ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-lg font-semibold text-white mb-3">
            Old Jobs
            {jobs.length > 1 && (
              <span className="ml-2 text-sm font-normal text-slate-400">({jobs.length - 1})</span>
            )}
          </h2>

          {jobs.length <= 1 ? (
            <div className="text-center py-6 text-slate-500 text-sm">No old jobs yet</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {jobs
                .filter(j => j.job_id !== (jobs.filter(j => j.job_id === recentJobId).length > 0 ? recentJobId : jobs[0]?.job_id))
                .map((job) => (
                  <JobCard key={job.job_id} job={job} />
                ))}
            </div>
          )}
        </div>
      </div>


      {/* Instructions */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-4">
        <h3 className="text-sm font-medium text-white mb-2">How it works</h3>
        <ol className="text-xs text-slate-400 space-y-1.5 list-decimal list-inside">
          <li>Upload a video file (MP4, AVI, MOV, MKV, WebM, FLV, WMV - max 500 MB)</li>
          <li>The system processes the video through the PPE detection pipeline</li>
          <li>Each frame is analyzed for PPE compliance (helmet, vest, gloves, shoes)</li>
          <li>Results are annotated on the video with bounding boxes and violation markers</li>
          <li>Download the processed video with visual annotations</li>
        </ol>
      </div>
    </div>
  )
}