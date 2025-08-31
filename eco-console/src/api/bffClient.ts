/* D:\EcodiaOS\eco-console\src\api\bffClient.ts */
// src/api/bffClient.ts
import axios from 'axios';

// The BFF is running on port 8000 alongside the other services.
const BFF_BASE_URL = process.env.REACT_APP_BFF_URL || 'http://localhost:8000';

const bffClient = axios.create({
  baseURL: BFF_BASE_URL,
  timeout: 15000, // 15 second timeout for requests
});

bffClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // Centralized error handling
    const message = error.response?.data?.detail || error.message;
    console.error(`API Error: ${message}`);
    return Promise.reject(message);
  }
);

export default bffClient;