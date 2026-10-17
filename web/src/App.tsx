import { useCallback, useMemo, useState } from 'react';
import { NavContext } from './routes';
import type { Nav, Route, SingSetup } from './routes';
import { Home } from './screens/Home/Home';
import { SoloSetup } from './screens/Solo/SoloSetup';
import { Sing } from './screens/Sing/Sing';
import { Results } from './screens/Results/Results';
import { Practice } from './screens/Practice/Practice';
import { History } from './screens/History/History';
import { BattleSetup } from './screens/Battle/BattleSetup';
import { BattleTurn } from './screens/Battle/BattleTurn';

/** Top-level navigation: one route at a time, shared through NavContext. */
export function App() {
  const [route, setRoute] = useState<Route>(devStartRoute);

  const go = useCallback((next: Route) => {
    setRoute(next);
    window.scrollTo(0, 0);
  }, []);
  const nav = useMemo<Nav>(() => ({ route, go, home: () => go({ name: 'home' }) }), [route, go]);

  return <NavContext.Provider value={nav}>{renderRoute(route, go)}</NavContext.Provider>;
}

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
    case 'home':
      return <Home onNavigate={(screen) => go({ name: screen })} />;
    case 'solo':
      return <SoloSetup />;
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
      return <BattleSetup />;
    case 'battleturn':
      return <BattleTurn result={route.result} />;
  }
}
