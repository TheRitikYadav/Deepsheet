# Auto-dialer (GUI, human-like)

Takes call requests from an HTTP API and dials them **on the phone's real dialer
screen**, tapping the keypad the way a person would. Before calling, it reads
the number back from the screen. If that number is not exactly the one the API
sent, it does **not** call and it tells the user.

No `ACTION_CALL`, no `tel:` pre-fill, no telephony API: every digit is a touch
on the screen.

```
 your system ──POST /calls──►  autodialer (PC / Raspberry Pi)  ──adb (USB/Wi-Fi)──►  Android phone
                 or polled         │                                                   │
                                   │ 1. open Phone app keypad (empty)                  │
                                   │ 2. tap each digit, human-like timing & position   │
                                   │ 3. read the number shown on screen                │
                                   │ 4a. same as API number?  → tap green call button  │
                                   │ 4b. different?           → wipe it, DON'T call,   │
                                   │                            notify user            │
                                   └──── result: GET /calls/{id}, webhook, phone notification
```

## What "human-like" means here

| Real person | What the tool does |
|---|---|
| Doesn't hit the exact centre of a key | Touch point is Gaussian-distributed around the key centre, kept well inside the key |
| Each press lasts a different time | Real touch-down → touch-up gesture held 55–130 ms (random), with a 1–3 px finger roll |
| Uneven typing rhythm | Log-normal gap between keys (median ≈ 0.32 s) |
| Reads numbers in chunks | Occasional extra pause every 3–5 digits |
| Glances before pressing call | 0.7–1.6 s pause before the call button |
| `+` | Long-press on `0`, like on a real dialer |

All values live in `autodialer/human.py` (`HumanProfile`).

## Setup

1. On the phone: enable **Developer options → USB debugging** (and, on Xiaomi/
   Oppo/Vivo, **USB debugging (Security settings)** so taps are allowed).
2. On the computer: install [platform-tools](https://developer.android.com/tools/releases/platform-tools)
   (`adb`) and Python 3.10+.
3. Connect the phone, accept the "Allow USB debugging" prompt, check `adb devices`.
4. Install and check that the dialer is recognised:

```bash
pip install -r requirements.txt
python -m autodialer inspect      # opens the keypad and lists what it found
python -m autodialer dial "+91 98765 43210"   # one-off test call
```

The phone screen must be on and unlocked (a PIN/pattern lock cannot be
bypassed; set the screen to stay awake while charging in Developer options).

## Running the API

```bash
export AUTODIALER_API_TOKEN=change-me        # optional, recommended
python -m autodialer serve --port 8000
```

### Send a call request

```bash
curl -X POST http://localhost:8000/calls \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{
        "phone_number": "+91 98765 43210",
        "name": "Asha Verma",
        "reference": "lead-1042",
        "info": {"campaign": "renewals"},
        "callback_url": "https://your-system.example/dial-result"
      }'
```

Returns `202` with a job id. Requests are dialed one at a time, in order.

### Check the result

`GET /calls/{id}` (or the `callback_url` / `AUTODIALER_WEBHOOK_URL` receives
the same JSON when the job ends):

```json
{
  "id": "1759840000-1",
  "status": "mismatch",
  "called": false,
  "expected_number": "+919876543210",
  "displayed_number": "+91 98765 4321",
  "message": "dialed number +9198765 4321 does not match requested +919876543210; call NOT placed",
  "steps": ["opened dialer keypad", "tapped 13 keys", "screen shows '+91 98765 4321'", "cleared wrong number"]
}
```

| `status` | Meaning | Called? |
|---|---|---|
| `called` | Screen matched the API number, call button tapped | yes |
| `mismatch` | Screen showed a different number; it was wiped | **no**, user notified |
| `invalid_number` | API sent something that isn't a dialable number | **no**, phone untouched |
| `failed` | Keypad / call button not found, adb error, … | **no**, user notified |

Other endpoints: `GET /calls` (history), `GET /health`.

### Pulling requests from your API instead

If your system can't push, point the tool at an endpoint that returns pending calls:

```bash
export AUTODIALER_POLL_URL=https://your-system.example/pending-calls
export AUTODIALER_POLL_INTERVAL=10
```

It may return one object, a list, or `{"calls": [...]}` with the same fields as
`POST /calls`. Give each a `reference` so it is not dialed twice.

## How the user is notified

When a call is not placed:

* a notification appears **on the phone** ("Call not placed (Asha Verma)" + reason),
* the result is POSTed to `callback_url` / `AUTODIALER_WEBHOOK_URL`,
* it is logged and visible at `GET /calls/{id}`.

## Configuration (environment variables)

| Variable | Default | |
|---|---|---|
| `AUTODIALER_ADB_SERIAL` | – | Which phone, if several are connected (`adb devices`) |
| `AUTODIALER_ADB_PATH` | `adb` | Path to adb |
| `AUTODIALER_DIALER_PACKAGE` | system default | e.g. `com.google.android.dialer`, `com.samsung.android.dialer` |
| `AUTODIALER_ID_OVERRIDES` | – | JSON for dialers with unusual ids, e.g. `{"digits_field": ["my_digits"], "call_button": ["my_call"]}` |
| `AUTODIALER_API_TOKEN` | – | Require `Authorization: Bearer <token>` |
| `AUTODIALER_WEBHOOK_URL` | – | Where to POST every result |
| `AUTODIALER_NOTIFY_ON_PHONE` | `1` | Post a phone notification on failure/mismatch |
| `AUTODIALER_POLL_URL` / `_POLL_INTERVAL` | – / `10` | Pull mode |
| `AUTODIALER_MIN_GAP` | `5` | Minimum seconds between two calls |

Keys, the number field and the call button are found from the live screen
layout (`uiautomator dump`), so they work at any screen size. Stock Google
Phone, AOSP and Samsung dialers use standard ids. For other dialers, run
`python -m autodialer inspect` and add overrides if something is missing.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a simulated dialer (`tests/fake_phone.py`) that responds to
touches like a real one. They cover the correct-call path, missed taps and
wrong keys (no call), leftover numbers, `+` numbers, invalid input and the API.

## Use responsibly

Only use this to call people who expect your calls, and follow the
telemarketing and consent rules where you operate (e.g. TRAI DND in India,
TCPA in the US).
