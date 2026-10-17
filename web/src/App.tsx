import { useState } from 'react';
import type { Screen } from './screens';
import { Home } from './screens/Home/Home';
import { ComingSoon } from './screens/ComingSoon';

/** Top-level navigation: one screen at a time, no router needed yet. */
export function App() {
  const [screen, setScreen] = useState<Screen>('home');

  if (screen === 'home') return <Home onNavigate={setScreen} />;
  return <ComingSoon screen={screen} onBack={() => setScreen('home')} />;
}
