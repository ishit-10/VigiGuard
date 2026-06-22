import axios from 'axios';

// Use relative /api so Vite dev-server proxy forwards to the backend
const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ===== System =====
export const getSystemStatus = () => api.get('/system/status');
export const getSystemInfo = () => api.get('/system/info');

// ===== Detection =====
export const getDetectionEvents = (params) => api.get('/detection/events', { params });
export const getLatestDetection = () => api.get('/detection/latest');

// ===== Alerts =====
export const getAlerts = (params) => api.get('/alerts/', { params });
export const getActiveAlerts = () => api.get('/alerts/active');
export const getAlert = (id) => api.get(`/alerts/${id}`);
export const acknowledgeAlert = (id, acknowledgedBy = 'operator') =>
  api.post(`/alerts/${id}/acknowledge`, null, { params: { acknowledged_by: acknowledgedBy } });
export const resolveAlert = (id) => api.post(`/alerts/${id}/resolve`);

// ===== Violations =====
export const getViolations = (params) => api.get('/violations/', { params });
export const getViolationsSummary = () => api.get('/violations/summary');

// ===== Metrics =====
export const getMetricsSummary = () => api.get('/metrics/summary');
export const getMetricSnapshots = (params) => api.get('/metrics/snapshots', { params });
export const getComplianceHistory = (hours) => api.get('/metrics/compliance', { params: { hours } });
export const getViolationsTrend = (hours) => api.get('/metrics/violations-trend', { params: { hours } });

// ===== Cameras =====
export const getCameras = () => api.get('/cameras/');
export const createCamera = (data) => api.post('/cameras/', data);
export const updateCamera = (id, data) => api.put(`/cameras/${id}`, data);
export const deleteCamera = (id) => api.delete(`/cameras/${id}`);

// ===== Video Upload =====
export const uploadVideo = (file, onProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/video-upload/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
    // Uploads can be large (up to 500MB) and may require more time on slow links.
    // Keep this high to avoid ECONNABORTED during the actual request body upload.
    timeout: 30 * 60 * 1000, // 30 min

  });
};

export const getVideoJobStatus = (jobId) => api.get(`/video-upload/jobs/${jobId}`);
export const listVideoJobs = () => api.get('/video-upload/jobs');
// Return an absolute URL to avoid issues with Vite base paths during playback.
export const getProcessedVideoUrl = (jobId) => {
  const base = api.defaults.baseURL || '/api/v1'
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}${base}/video-upload/download/${jobId}`
}


export default api;
