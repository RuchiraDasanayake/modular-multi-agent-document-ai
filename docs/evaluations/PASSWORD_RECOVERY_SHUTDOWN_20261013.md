# Disable unauthenticated password recovery

Date: 13 October 2026. Owning service: gateway. Surface: `core`; action: `simplify`.

The former forgot-password endpoint looked up an email, generated a reset token
and returned that token in its unauthenticated response. The reset endpoint
accepted the token to change the account password. Knowing an email address
therefore granted account recovery without proving ownership of that address.
The frontend also presented an email-delivery message despite having no delivery
service. Hiding a button would not fix the server vulnerability.

Both unauthenticated endpoints now return HTTP 503 with the same recovery
unavailable message for every valid request. They have no database dependency:
they neither query accounts, mint tokens nor consume previously issued tokens.
Existing reset tokens are unusable through the application. The database table
is retained for compatibility; this change does not delete account data.
Authenticated password changes still require the current password.

The forgot/reset pages now explain that recovery is unavailable and direct the
user to their administrator. A future recovery implementation must verify control
of an independent delivery channel and atomically consume short-lived, securely
stored tokens. There is no hidden development-mode bypass.

Three regression cases failed before the fix because both endpoints still
reached the database; all 49 gateway tests pass after the fix. The cases verify
that registered/unknown email requests and previously issued reset-token requests
all fail without querying or changing account records. No real user's password
was changed during testing.

Running deployments must restart the gateway with the updated code. Native HTTP
verification is recorded separately after that restart; unit tests alone do not
prove that a previously running process has acquired the fix.
