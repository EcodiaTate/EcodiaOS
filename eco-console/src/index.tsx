import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import ErrorBoundary from './components/common/ErrorBoundary';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found');

const root = createRoot(rootEl);
const queryClient = new QueryClient();
window.addEventListener('error', (e) => console.error('[window.error]', e.error || e.message));
window.addEventListener('unhandledrejection', (e) => console.error('[unhandledrejection]', e.reason));

root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>
);

reportWebVitals(console.log);
reportWebVitals();
