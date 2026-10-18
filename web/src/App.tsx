import { useCallback, useEffect, useMemo, useState } from 'react';
import { NavContext } from './routes';
import type { Nav, Route, SingSetup } from './routes';
import { Zibran } from './screens/EasterEgg/Zibran';
import { setMenuMusicWanted } from './lib/menuMusic';
import { Home } from './screens/Home/Home';
import { SoloSetup } from './screens/Solo/SoloSetup';
import { Sing } from './screens/Sing/Sing';
import { Results } from './screens/Results/Results';
import { Practice } from './screens/Practice/Practice';
import { History } from './screens/History/History';
import { Online } from './screens/Online/Online';
import { BattleTurn } from './screens/Battle/BattleTurn';
import { Duet } from './screens/Duet/Duet';

/** Top-level navigation: one route at a time, shared through NavContext. */
export function App() {
  const [route, setRoute] = useState<Route>(() => (new URLSearchParams(location.search).has('room') ? { name: 'online' } : devStartRoute()));

  const go = useCallback((next: Route) => {
    setRoute(next);
    window.scrollTo(0, 0);
  }, []);
  const nav = useMemo<Nav>(() => ({ route, go, home: () => go({ name: 'home' }) }), [route, go]);

  const music = MENU_MUSIC_SCREENS.has(route.name);
  useEffect(() => setMenuMusicWanted(music), [music]);

  return (
    <NavContext.Provider value={nav}>
      {renderRoute(route, go)}
    </NavContext.Provider>
  );
}

/**
 * Screens with menu music. It is off wherever the microphone is in use or timing matters:
 * solo and battle setup (mic and tap-along checks), the online lobby (mic check), singing,
 * duets, and spoken practice. The battle hand-off / winner screen has no mic, so it keeps music.
 */
const MENU_MUSIC_SCREENS = new Set<Route['name']>(['home', 'results', 'history', 'battleturn']);

/**
 * Development only: open a screen directly with a URL hash, e.g. http://localhost:5173/#sing.
 * Screens that need data get a sample built from the synthetic demo clip. Stripped from production builds.
 */
function devStartRoute(): Route {
  if (!import.meta.env.DEV) return { name: 'home' };
  const setup: SingSetup = {
    runId: 'dev',
    clipId: 'synthetic-demo',
    register: 0,
    calibrationOffset: null,
    playerName: 'Dev',
    match: null,
  };
  switch (location.hash.slice(1)) {
    case 'solo':
    case 'practice':
    case 'history':
    case 'battle':
      return { name: location.hash.slice(1) as 'solo' | 'practice' | 'history' | 'battle' };
    case 'sing':
      return { name: 'sing', setup };
    case 'results':
      return {
        name: 'results',
        result: {
          setup,
          phrases: [{ phrase_id: 'p1', rating: 'great', pitch: 82, timing: 74, score: 80.4, coverage: 0.9 }],
          local: { total: 80.4, pitch: 82, timing: 74 },
          saved: null,
          saveError: 'Saving is off in this dev preview.',
        },
      };
    default:
      return { name: 'home' };
  }
}

function renderRoute(route: Route, go: (r: Route) => void) {
  switch (route.name) {
    case 'zibran':
      return <Zibran />;
    case 'home':
      return <Home onNavigate={(screen) => go({ name: screen })} />;
    case 'solo':
      return <SoloSetup key="1p" />;
    case 'sing':
      // key: a new run (rematch, new song) always starts a fresh singing screen
      return <Sing key={route.setup.runId} setup={route.setup} />;
    case 'results':
      return <Results result={route.result} />;
    case 'practice':
      return <Practice />;
    case 'history':
      return <History />;
    case 'battle':
      // 1P vs 2P lives on the local setup screen; this route opens it in two-player mode.
      return <SoloSetup key="2p" initialPlayers={2} />;
    case 'duet':
      return <Duet key={route.setup.matchId} setup={route.setup} onLeave={() => go({ name: 'home' })} />;
    case 'online':
      return <Online room={route.room} notice={route.notice} />;
    case 'battleturn':
      return <BattleTurn result={route.result} />;
  }
}
