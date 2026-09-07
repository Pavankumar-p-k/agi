import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './design-tokens.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
const queryClient = new QueryClient();
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></React.StrictMode>);
