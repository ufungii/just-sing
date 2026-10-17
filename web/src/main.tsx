import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Fonts are bundled (not fetched from Google) so the desktop app and offline demo look identical.
import '@fontsource/silkscreen/400.css';
import '@fontsource/silkscreen/700.css';
import '@fontsource/pixelify-sans/400.css';
import '@fontsource/pixelify-sans/500.css';
import '@fontsource/pixelify-sans/700.css';
import '@fontsource/dotgothic16/400.css';
import '@fontsource/jua/400.css';
import './styles/global.css';

import { App } from './App';
import { AuthProvider } from './lib/auth';
import { initMenuMusic } from './lib/menuMusic';

initMenuMusic();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
