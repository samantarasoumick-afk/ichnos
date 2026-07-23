import axios from "axios";

const TOKEN_KEY = "mip_token";

const api = axios.create({
  baseURL: "/backend",
});

// Attach the stored JWT to every request. Reading localStorage only
// makes sense in the browser - during SSR/build there's no window,
// and requests made at that point don't have a user session anyway.
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers = config.headers ?? {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// A 401 means the token is missing, invalid, or expired - in every
// case the right move is the same: drop it and send the user to
// /login, rather than letting every page handle that individually.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      typeof window !== "undefined" &&
      error?.response?.status === 401 &&
      window.location.pathname !== "/login" &&
      window.location.pathname !== "/register"
    ) {
      window.localStorage.removeItem(TOKEN_KEY);
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
export { TOKEN_KEY };
