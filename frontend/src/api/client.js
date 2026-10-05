import axios from 'axios';

/**
 * Origin of the FastAPI backend. Override with VITE_BACKEND_ORIGIN; set it to an
 * empty string to route everything through the Vite dev proxy instead.
 */
export const BACKEND_ORIGIN =
  import.meta.env.VITE_BACKEND_ORIGIN ?? 'http://localhost:8000';

const client = axios.create({
  baseURL: `${BACKEND_ORIGIN}/api`,
  timeout: 300_000,
});

/**
 * Artifact images are stored on the backend filesystem. Turn the relative
 * `/static/artifacts/...` path returned by the API into a loadable URL.
 */
export function resolveAssetUrl(url) {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${BACKEND_ORIGIN}${url.startsWith('/') ? url : `/${url}`}`;
}

/** Extract a human-readable message from an axios/network error. */
export function describeError(error, fallback = 'Something went wrong.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
  }
  if (error?.code === 'ECONNABORTED') return 'The request timed out.';
  if (error?.request) return 'Cannot reach the NexusNote backend on port 8000.';
  return error?.message || fallback;
}

export async function fetchGraph() {
  const { data } = await client.get('/graph');
  return data;
}

export async function fetchConcept(conceptId) {
  const { data } = await client.get(`/concept/${encodeURIComponent(conceptId)}`);
  return data;
}

export async function uploadDocument(file, onUploadProgress) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await client.post('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });
  return data;
}

export async function fetchHealth() {
  const { data } = await client.get('/health');
  return data;
}

export default client;
