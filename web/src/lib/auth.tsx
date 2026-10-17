/**
 * Optional Auth0 login. With VITE_AUTH0_CLIENT_ID unset there is no Auth0 provider at all and the app
 * is guest-only. With it set, the user logs in by redirect (origin as redirect_uri), the access token is
 * attached to every API call as a Bearer header, and after login the guest history is claimed once.
 */
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';
import { useEffect, type ReactNode } from 'react';
import { claimGuest, setAccessTokenProvider } from './api';

const env = import.meta.env;
export const AUTH_ENABLED = Boolean(env.VITE_AUTH0_CLIENT_ID);

export interface Account {
  enabled: boolean;
  loading: boolean;
  /** Name or email of the logged-in user; null for guests. */
  name: string | null;
  login: () => void;
  logout: () => void;
}

const GUEST: Account = { enabled: false, loading: false, name: null, login: () => {}, logout: () => {} };

/** Who is logged in. The constant `AUTH_ENABLED` never changes at runtime, so the hook choice is stable. */
export const useAccount: () => Account = AUTH_ENABLED
  ? function useAuth0Account() {
      const a = useAuth0();
      return {
        enabled: true,
        loading: a.isLoading,
        name: a.isAuthenticated ? a.user?.name ?? a.user?.email ?? 'player' : null,
        login: () => void a.loginWithRedirect(),
        logout: () => void a.logout({ logoutParams: { returnTo: window.location.origin } }),
      };
    }
  : () => GUEST;

/** Registers the token getter for api.ts and claims guest history once per login. */
function Bridge({ children }: { children: ReactNode }) {
  const { isAuthenticated, getAccessTokenSilently } = useAuth0();
  useEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenProvider(null);
      return;
    }
    setAccessTokenProvider(() => getAccessTokenSilently());
    claimGuest().catch(() => {
      // no guest history, or the server is down: nothing to attach
    });
    return () => setAccessTokenProvider(null);
  }, [isAuthenticated, getAccessTokenSilently]);
  return children;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) return children;
  return (
    <Auth0Provider
      domain={env.VITE_AUTH0_DOMAIN}
      clientId={env.VITE_AUTH0_CLIENT_ID}
      authorizationParams={{ redirect_uri: window.location.origin, audience: env.VITE_AUTH0_AUDIENCE || undefined }}
      cacheLocation="localstorage"
      onRedirectCallback={() => window.history.replaceState({}, document.title, window.location.pathname)}
    >
      <Bridge>{children}</Bridge>
    </Auth0Provider>
  );
}
