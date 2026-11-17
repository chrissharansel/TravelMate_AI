import axios from "axios";

export const BASE = import.meta.env.VITE_API_URL || "/api";
const api = axios.create({ baseURL: BASE, headers: { "X-User-Id": "demo-user" } });

export const errText = (e) =>
  e?.response?.data?.detail
    ? typeof e.response.data.detail === "string" ? e.response.data.detail : JSON.stringify(e.response.data.detail)
    : e?.message || "Something went wrong";

export const planTrip = (body) => api.post("/trips/plan", body).then((r) => r.data);
export const listTrips = () => api.get("/trips").then((r) => r.data);
export const getTrip = (id, version) => api.get(`/trips/${id}`, { params: version ? { version } : {} }).then((r) => r.data);
export const approveTrip = (id, version) => api.post(`/trips/${id}/approve`, { version }).then((r) => r.data);
export const saveTrip = (id) => api.post(`/trips/${id}/save`).then((r) => r.data);
export const reviseTrip = (id, body) => api.post(`/trips/${id}/revise`, body).then((r) => r.data);
export const getPreferences = () => api.get("/preferences").then((r) => r.data);
export const putPreferences = (body) => api.put("/preferences", body).then((r) => r.data);
export const confirmMemory = (key) => api.post(`/memory/${encodeURIComponent(key)}/confirm`).then((r) => r.data);
export const deleteMemory = (key) => api.delete(`/memory/${encodeURIComponent(key)}`).then((r) => r.data);

export const inr = (n) => (n === null || n === undefined ? "-" : "₹" + Number(n).toLocaleString("en-IN"));
