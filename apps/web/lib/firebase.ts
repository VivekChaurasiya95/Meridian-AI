/**
 * Firebase Auth (browser) for Google/GitHub social sign-in.
 *
 * Config comes from NEXT_PUBLIC_FIREBASE_* env vars (see .env.example).
 * These values identify the Firebase web app; they are not secrets.
 * Sign-in uses popups, then the ID token is exchanged at the Meridian
 * API for the normal session cookie (see lib/api loginWithFirebase).
 */

import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GithubAuthProvider,
  GoogleAuthProvider,
  signInWithPopup,
  type Auth,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export function isFirebaseConfigured(): boolean {
  return Boolean(
    firebaseConfig.apiKey &&
      firebaseConfig.authDomain &&
      firebaseConfig.projectId &&
      firebaseConfig.appId,
  );
}

let cachedAuth: Auth | null = null;

function firebaseAuth(): Auth {
  if (!isFirebaseConfigured()) {
    throw new Error(
      "Social sign-in is not configured. Add the NEXT_PUBLIC_FIREBASE_* values to apps/web/.env.local.",
    );
  }
  if (!cachedAuth) {
    const app: FirebaseApp = initializeApp(firebaseConfig);
    cachedAuth = getAuth(app);
  }
  return cachedAuth;
}

/** Open the Google popup and return the Firebase ID token. */
export async function signInWithGoogle(): Promise<string> {
  const credential = await signInWithPopup(
    firebaseAuth(),
    new GoogleAuthProvider(),
  );
  return credential.user.getIdToken();
}

/** Open the GitHub popup and return the Firebase ID token. */
export async function signInWithGithub(): Promise<string> {
  const credential = await signInWithPopup(
    firebaseAuth(),
    new GithubAuthProvider(),
  );
  return credential.user.getIdToken();
}
