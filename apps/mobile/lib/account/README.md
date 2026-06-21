# `account/` — account settings & GDPR self-service (Phase 4-G, ADR-0026)

The signed-in user's account screen and the **GDPR self-service** actions, reachable from the
home's account affordance (`main.dart`) and as the destination of the sign-in flow.

See also [`auth/`](../auth/) (sign-in/consent/verify) and
[`state/auth_state.dart`](../state/auth_state.dart) (the session holder).

## Files

| File | Responsibility |
|------|----------------|
| `account_screen.dart` | Shows `/account/me`; surfaces the missing interaction gates (verify / accept terms); **Download my data** (`GET /account/export`) and **Delete my account** (`DELETE /account`, confirm dialog → clears the session); sign out. Anonymous → a sign-in prompt. |

## GDPR actions

- **Download my data** — fetches the JSON export with the Bearer attached and shows it in a
  copyable dialog. **TODO(deps):** add `share_plus` / `path_provider` to save/share the
  archive as a file rather than copy from a dialog.
- **Delete my account** — irreversible. A confirm dialog → `DELETE /account` → `signOut()`
  clears the JWT everywhere. Per ADR-0026 the backend cascades the full purge.
