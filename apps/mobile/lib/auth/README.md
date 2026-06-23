# `auth/` — sign-in, consent, verify & the interaction gate (Phase 4-G, ADR-0026)

The account/auth layer for the client. No registration form: the user picks a config-driven
provider and authorizes (OAuth2/OIDC auth-code + PKCE); the backend mints a **session JWT**
that the [`ApiClient`](../api/client.dart) attaches as `Authorization: Bearer <token>` on
every request. Anonymous **reads stay open**; **interaction** (react/comment/promote/upload/
follow) is gated on *signed-in + email-verified + agreement-accepted*.

Sibling: [`account/`](../account/) (the account settings + GDPR screen) and
[`state/auth_state.dart`](../state/auth_state.dart) (the session holder).

## Files

| File | Responsibility |
|------|----------------|
| `login_screen.dart` | Lists `GET /auth/providers` as buttons **and** (when `dev_login` is enabled) a self-contained **email-code** sign-in form; handles the empty case; runs the chosen flow and adopts the session. |
| `oauth_flow.dart` | The native auth-code+PKCE handoff (paste fallback): fetch authorize URL, capture `code`/`state`, exchange at `/auth/{p}/callback`. |
| `web_oauth.dart` (+ `_stub`/`_web`) | The **web** OAuth flow: a real full-page redirect to the provider, with the PKCE verifier/state stashed in `sessionStorage`. On the return load `AuthState.completePendingWebOAuth()` reads `?code&state` and exchanges. Conditional-import split (`package:web` web-only). |

## Sign-in paths

1. **Email-code (dev login)** — `POST /auth/dev/start` emails a one-time code (echoed in the
   response in non-prod), `POST /auth/dev/verify` exchanges email+code for a session and an
   email-verified user. No external provider. Gated by the `auth.dev_login_enabled` config —
   **disable in production** once social login is configured.
2. **Google / OAuth (web)** — full-page redirect → provider → back to the **app origin**, then
   the boot-time capture finishes the exchange. The client sends its own `redirect_uri`
   (`<origin>/`) to `/auth/{p}/login` and echoes it on the callback.

### Google Cloud console setup (required for the OAuth path)

The web redirect URI is the **app origin with a trailing slash**. Register it under the OAuth
2.0 Client → **Authorized redirect URIs**, exactly:

- `http://localhost:8080/` (local), and the public test origin, e.g. `https://<host>/`.

(The earlier `…/api/auth/google/callback` URI was for a server-side callback and no longer
applies to the web client.) The provider's allowlist is the security boundary — the backend
accepts the client-supplied `redirect_uri` but the provider rejects any URI not registered.
| `agreement_screen.dart` | Versioned Terms/privacy consent → `POST /auth/agreement/accept`. |
| `verify_email_screen.dart` | Request a code → confirm → refresh (`/auth/verify/request` + `/confirm`). |
| `interaction_gate.dart` | **`ensureCanInteract(context, api, auth)`** — the sign-in-on-interaction helper (below). |

## Session & Bearer wiring

- [`AuthState`](../state/auth_state.dart) (`ChangeNotifier`) holds the JWT + [`SessionUser`]
  and the two gate flags. On `adopt()` / `load()` it sets `ApiClient.sessionToken`, which the
  client sends as a Bearer; `signOut()` clears it. `canInteract` = signed-in + verified +
  consented.
- **Persistence:** `shared_preferences` is **not** a dependency, so the session is held **in
  memory** (`InMemorySessionStore`) and is lost on app restart. The store is a pluggable
  `SessionStore` interface — add the dep and a `PrefsSessionStore`, pass it to `AuthState`,
  and persistence is done with no other changes. **TODO(deps): `shared_preferences`.**

## Sign-in-on-interaction (for IU2)

`ensureCanInteract` walks whatever gate is missing — **sign in → accept agreement → verify
email** — and returns whether the user may now interact, so the caller resumes its pending
action ("ask, then resume"):

```dart
import '../auth/interaction_gate.dart';

Future<void> onLike(BuildContext context) async {
  if (await ensureCanInteract(context, api, auth)) {
    await api.toggleReaction(eventId, 'like'); // the pending action, resumed
  }
}
```

**TODO(IU2): wire `ensureCanInteract` into the feed/event overlays.** These files are
**not** edited in Phase 4-G (scope fence). The integration points are the overlay-rail /
detail-panel callbacks that perform writes:

- `lib/feed/video_feed.dart` — `onReact`, `onComment`, `onPromote`, `onFollow` callbacks.
- `lib/feed/overlay_rail.dart` — `showReactionSheet` (gate before opening).
- `lib/event/reaction_bar.dart`, `comments_section.dart`, `source_vote_bar.dart`,
  `link_picker.dart` — gate before the `api.toggle/add/cast/create*` calls.
- (future) the upload entry — gate before submit.

Each is the same shape: wrap the existing write in
`if (await ensureCanInteract(context, api, auth)) { …existing call… }`. The `AuthState` must
be threaded down from `main.dart` (e.g. via constructor or an `InheritedWidget`) — it is
created once at app boot in `ChronosApp`.

## Dependency limitations (no new deps added in 4-G)

| Want | Missing dep | Current fallback |
|------|-------------|------------------|
| Persist session across launches | `shared_preferences` | in-memory `SessionStore` |
| Launch + auto-capture the OAuth redirect on **native** | `url_launcher` | paste-the-`code` dialog (`oauth_flow.dart`). **Web is fully automatic** via `web_oauth.dart`. |
| Save / share the data export as a file | `share_plus` / `path_provider` | export shown in a copyable dialog (`account/`) |

Each fallback is isolated behind one widget/method.
