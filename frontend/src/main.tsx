import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { AppProviders } from './app/providers/AppProviders';
import { AppRouter } from './app/router/AppRouter';
import './styles.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root was not found in the document.');
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      <AppRouter />
    </AppProviders>
  </StrictMode>,
);
