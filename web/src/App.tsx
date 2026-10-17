import { useState } from 'react';
import type { Screen } from './screens';
import { Home } from './screens/Home/Home';
import { ComingSoon } from './screens/ComingSoon';

/** Top-level navigation: one screen at a time, no router needed yet. */
export function App() {
  const [screen, setScreen] = useState<Screen>('home');

  const navigate = (next: Screen) => {
    if (next === 'solo') {
      window.location.assign('/karaoke/live/');
      return;
    }
    setScreen(next);
  };

  if (screen === 'home') return <Home onNavigate={navigate} />;
  return <ComingSoon screen={screen} onBack={() => setScreen('home')} />;
}
