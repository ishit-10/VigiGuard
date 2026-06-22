import React, { useState, useEffect } from 'react'
import { getCameras, createCamera, updateCamera, deleteCamera } from '../services/api'

export default function Cameras() {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingCamera, setEditingCamera] = useState(null)
  const [formData, setFormData] = useState({
    camera_id: '',
    name: '',
    source: '',
    location: '',
  })

  const fetchCameras = async () => {
    try {
      const res = await getCameras()
      setCameras(res.data)
    } catch (err) {
      console.error('Failed to fetch cameras:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCameras() }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      if (editingCamera) {
        await updateCamera(editingCamera.camera_id, formData)
      } else {
        await createCamera(formData)
      }
      setShowForm(false)
      setEditingCamera(null)
      setFormData({ camera_id: '', name: '', source: '', location: '' })
      fetchCameras()
    } catch (err) {
      console.error('Failed to save camera:', err)
    }
  }

  const handleEdit = (camera) => {
    setEditingCamera(camera)
    setFormData({
      camera_id: camera.camera_id,
      name: camera.name,
      source: camera.source,
      location: camera.location || '',
    })
    setShowForm(true)
  }

  const handleDelete = async (cameraId) => {
    if (!window.confirm('Delete this camera configuration?')) return
    try {
      await deleteCamera(cameraId)
      fetchCameras()
    } catch (err) {
      console.error('Failed to delete camera:', err)
    }
  }

  const handleToggleActive = async (camera) => {
    try {
      await updateCamera(camera.camera_id, { active: !camera.active })
      fetchCameras()
    } catch (err) {
      console.error('Failed to toggle camera:', err)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Cameras</h1>
          <p className="text-sm text-slate-400 mt-1">Manage camera configurations</p>
        </div>
        <button
          onClick={() => {
            setShowForm(!showForm)
            setEditingCamera(null)
            setFormData({ camera_id: '', name: '', source: '', location: '' })
          }}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-500/20 text-primary-400 border border-primary-500/30 hover:bg-primary-500/30 transition-all"
        >
          {showForm ? 'Cancel' : '+ Add Camera'}
        </button>
      </div>

      {/* Add/Edit Form */}
      {showForm && (
        <div className="card fade-in">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">
              {editingCamera ? 'Edit Camera' : 'Add New Camera'}
            </h3>
          </div>
          <div className="card-body">
            <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Camera ID</label>
                <input
                  type="text"
                  required
                  value={formData.camera_id}
                  onChange={e => setFormData({ ...formData, camera_id: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/50 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-primary-500/50"
                  placeholder="camera_01"
                  disabled={!!editingCamera}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Name</label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/50 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-primary-500/50"
                  placeholder="Main Entrance Camera"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Source</label>
                <input
                  type="text"
                  required
                  value={formData.source}
                  onChange={e => setFormData({ ...formData, source: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/50 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-primary-500/50"
                  placeholder="0 (camera index) or RTSP URL"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Location</label>
                <input
                  type="text"
                  value={formData.location}
                  onChange={e => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/50 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-primary-500/50"
                  placeholder="Platform 1"
                />
              </div>
              <div className="md:col-span-2 flex gap-3">
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-500/20 text-primary-400 border border-primary-500/30 hover:bg-primary-500/30 transition-all"
                >
                  {editingCamera ? 'Update Camera' : 'Add Camera'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-slate-700/50 text-slate-400 border border-slate-600/50 hover:bg-slate-700/70 transition-all"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Cameras List */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-slate-400 text-sm">Loading cameras...</p>
        </div>
      ) : cameras.length === 0 ? (
        <div className="card">
          <div className="card-body text-center py-12">
            <svg className="w-12 h-12 mx-auto text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <p className="text-slate-400">No cameras configured</p>
            <p className="text-xs text-slate-500 mt-1">Add a camera to start PPE monitoring</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cameras.map((camera) => (
            <div key={camera.id} className="card fade-in">
              <div className="card-body">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-white">{camera.name}</h3>
                      <span className={`status-badge ${camera.active ? 'bg-success-500/20 text-success-400' : 'bg-slate-500/20 text-slate-400'}`}>
                        {camera.active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">ID: {camera.camera_id}</p>
                    {camera.location && (
                      <p className="text-xs text-slate-500 mt-0.5">Location: {camera.location}</p>
                    )}
                    <p className="text-xs text-slate-500 mt-0.5 font-mono">Source: {camera.source}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleToggleActive(camera)}
                      className={`p-2 rounded-lg text-xs transition-all ${
                        camera.active
                          ? 'bg-warning-500/20 text-warning-400 hover:bg-warning-500/30'
                          : 'bg-success-500/20 text-success-400 hover:bg-success-500/30'
                      }`}
                      title={camera.active ? 'Deactivate' : 'Activate'}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={camera.active
                          ? "M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                          : "M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"} />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleEdit(camera)}
                      className="p-2 rounded-lg bg-primary-500/20 text-primary-400 hover:bg-primary-500/30 transition-all"
                      title="Edit"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(camera.camera_id)}
                      className="p-2 rounded-lg bg-danger-500/20 text-danger-400 hover:bg-danger-500/30 transition-all"
                      title="Delete"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
                  <span>Created: {new Date(camera.created_at).toLocaleDateString()}</span>
                  <span>Updated: {new Date(camera.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}