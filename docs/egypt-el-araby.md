# Connecting a Sharp air conditioner in Egypt (El Araby)

Sharp appliances sold in Egypt are distributed by El Araby, and they do **not**
live on the same Cocoro service as the Japanese units this integration was
written against. The service name is `sharp-egy`, and the account login is not
Sharp's at all. It is El Araby's own Azure AD B2C tenant.

Nothing here is specific to one household. It is written down because none of it
is documented anywhere, and because two of the failure modes are actively
misleading: they return a status code that means something other than what
happened, and they cost days if you take them at face value.

Verified against a live account on 2026-08-28. If you are on a different Sharp
distributor, only the "misleading responses" table is likely to transfer.

## The three values, and what they actually are

The integration asks for `app_key`, `app_secret` and `service_name`. What those
words hide:

| Field | What it really is |
| --- | --- |
| `service_name` | `sharp-egy` for Egypt. **Not** `iClub`, which is the library default, and **not** `SYSINNO`, which appears in the app's strings and is a red herring. |
| `app_secret` | A constant belonging to the **app build**, not to your account. Everyone using the same APK has the same one. |
| `app_key` | A `terminalAppId`. It is **minted per installation**, not a durable secret you go and find. |

That last row is the one that changes how you approach this. Two successive
requests to the mint endpoint return two different ids. There is nothing stable
to "extract"; you make one, and then it has to be *bound* to your account.

## How the app does it

Three calls, against `https://hms.cloudlabs.sharp.co.jp/hems/pfApi/ta`:

```
GET  /setting/terminalAppId/?appSecret=<SECRET>
     -> {"terminalAppId": "https://db.cloudlabs.sharp.co.jp/clpf/key/<KEY>"}

POST /setting/login/?appSecret=<SECRET>&serviceName=sharp-egy
     {"terminalAppId": "https://db.cloudlabs.sharp.co.jp/clpf/key/<KEY>",
      "tempAccToken": "<a five-part JWE>"}

GET  /setting/boxInfo/?appSecret=<SECRET>&mode=other
```

A few things worth knowing before you start:

- **`app_key` is only the trailing `<KEY>`.** The mint endpoint hands back the
  full `https://db.cloudlabs.sharp.co.jp/clpf/key/…` URL, but the
  integration's `app_key` field holds the tail and prepends the prefix
  itself. Paste the whole URL in and you get it doubled.
- **After `login`, the API authenticates by session cookie.** `boxInfo` and
  `control/deviceProperty` carry only `appSecret`, no `terminalAppId`.
  Calling them without having logged in on the same connection returns
  **401**, which looks exactly like a bad key and is not.
- **`tempAccToken` is needed exactly once.** It exists to *bind* a
  terminalAppId. Once bound, that id authenticates on its own indefinitely:
  whatever it takes to get a token happens once, at setup, not on a
  schedule and not in the middle of the night.

## The part that has no clean answer: `tempAccToken`

It is an `id_token` from El Araby's Azure AD B2C tenant:

```
tenant     elaiotb2cprd.onmicrosoft.com / elaiotb2cprd.b2clogin.com
policy     b2c_1a_signup_signin      (B2C_1A_ = a custom IEF policy)
client_id  66e7f408-b1bf-46a8-b467-32204ab52f93
flow       response_type=id_token, scope=openid   (implicit, in a WebView)
redirect   https://sharp-cocoroair-egypt
```

The client id is the app's public OAuth client identifier, not a secret. It is
in the APK and in every request the app makes. The URL to open is:

```
https://elaiotb2cprd.b2clogin.com/elaiotb2cprd.onmicrosoft.com/b2c_1a_signup_signin/oauth2/v2.0/authorize
  ?client_id=66e7f408-b1bf-46a8-b467-32204ab52f93
  &response_type=id_token
  &scope=openid
  &redirect_uri=https%3A%2F%2Fsharp-cocoroair-egypt
  &nonce=anything
  &state=anything
```

(all on one line, no spaces)

These do not work, and each was tested rather than assumed:

- **The password grant (ROPC) is not available.** With a correctly formed scope,
  `grant_type=password` against `b2c_1a_signup_signin` returns
  `server_error (AADB2C: An exception has occurred)`. The dedicated policies
  `B2C_1A_ROPC`, `B2C_1_ROPC` and `b2c_1a_signin_ropc` all 404. So there is no
  "store the email and password and mint a token" route.
- **Authorization code + PKCE gains you nothing.** Credentials are still typed
  into B2C's hosted page either way; PKCE only changes how a code comes back.
- **Home Assistant's built-in OAuth2 helpers cannot be used.** They work by
  having the identity provider redirect the browser back to Home Assistant's
  `/auth/external/callback`. B2C matches `redirect_uri` **exactly** against what
  is registered on the application, the registration here is fixed to
  `https://sharp-cocoroair-egypt`, and you cannot add a redirect URI to someone
  else's app registration.

**What does work** is doing the sign-in in a browser yourself and taking the
token out of where the app's WebView would have received it:

1. Open the authorize URL for the tenant above in a normal browser.
2. Sign in with your Cocoro account.
3. The browser finishes on an address that **fails to load**, beginning
   `https://sharp-cocoroair-egypt#id_token=…`. The failure is expected: that
   page does not exist. The address bar is the point.
4. That `id_token` is your `tempAccToken`. Use it promptly; it is good for
   minutes.

Do this in a real browser rather than posting the form yourself: the hosted
flow can insert multi-factor auth, a consent screen, terms to accept, or a
forced password change, and only a real browser can get through all of those.

## Getting `app_secret`

It is a constant in the Android app, so it comes out of the APK or out of one
observed request. It is not published here, and it should not be: it is
effectively an API credential shared by every user of that build.

The traffic-capture routes people usually reach for (a proxy with TLS
interception, or an instrumented emulator) do work and will show you both the
secret and a live `tempAccToken` in one go. **You do not need a capture for
`app_key`**, though, because that is minted, not found. A capture is only for
the secret.

## The failure mode that will actually get you

**Binding a fresh `terminalAppId` does not pair it to your devices.**

`boxInfo` returns **every box on the account regardless of pairing**, so a box
appears in the list and then refuses every call against it. Each box separately
lists the terminals it trusts, in `terminalAppInfo`, and only a terminal on that
list can read it.

Measured on a two-appliance account, with the terminals abbreviated:

```
first appliance    trusts  T1 (app 1.0.1),  T2 (app 1.0.4)
second appliance   trusts  T2 (app 1.0.4),  T3 (app 1.0.4)
```

Only **T2** is on both, and T2 is the only one of the three that works as an
`app_key`. **T3 had been minted and bound fresh**, and it reads one box and
400s on the other.

Why that breaks everything rather than half of everything: device enumeration
walks every box `boxInfo` returns and raises on the first one it cannot read. One
unreadable box therefore stops the whole integration from loading, including the
appliances that were fine.

Two consequences:

- **If you already have a working key, keep it.** Minting a new one will pair it
  to fewer boxes, not more.
- **Pairing accrues in the phone app**, when a device is added there. If a newly
  bound terminal cannot see an appliance, add or re-add that appliance in the
  Cocoro app with that installation. There is no API call here that will do it
  for you.

Each box also reports `pairedTerminalNum` and a `maxFlag`. Minting repeatedly
fills the slots, so it is possible to lose access by trying too many times.
Check `terminalAppInfo` before you mint anything.

If you cannot get one key onto every box, the remaining options are to remove
the unreachable appliance from the Cocoro account, or to run a build of this
integration that can be told to skip named device ids so enumeration never
touches them.

## Misleading responses, and what they really mean

| What you see | What it means |
| --- | --- |
| `400` + `{"errorCode":null,"errorMessage":null}` from `setting/login/` | The bind did **not** happen. It reads like success. Every later call will 401. |
| `400` + an **empty body** from `control/deviceProperty` | This terminal is not paired to that box. It looks like a malformed request, but it is an authorization failure with the wrong status code. |
| `401` from `boxInfo` | You never logged in on this connection, or the bind failed earlier. Not necessarily a bad key. |
| `500` from `setting/login/` | The `tempAccToken` was expired or malformed. They last minutes. |
| Every call fails, and the secret ends in `=` | See below. |
| `405` from `control/deviceControl` on a GET | It is POST-only. |

**The `=` at the end of `app_secret`.** The integration interpolates
`app_secret` straight into a query string without encoding it, so a trailing `=`
has to be pre-encoded as `%3D` in the field. Enter it raw and nothing
authenticates.

## Checking it worked

Do not trust the response from `login`. The only test that counts is whether an
authenticated endpoint answers, and whether it answers for **every** box:

1. `POST setting/login/` with the key.
2. `GET setting/boxInfo/` on the same connection: expect 200 and a box list.
3. `GET control/deviceProperty` for each box: expect 200 for all of them.

If step 3 succeeds for some boxes and 400s for others, you have a pairing
problem, not a credentials problem, and the section above applies.
