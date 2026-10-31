# MailTester Ninja for Python

Official client for the [MailTester Ninja](https://mailtester.ninja) email verification API. Check in real time whether an email address is valid and deliverable: each address is checked against the recipient's mail server, and nothing is stored. With a paid key, `find` also looks up a person's work email from their name and company domain.

- No dependencies (standard library only), typed, Python 3.9+
- Free to try: no signup with `key="free"`, or a [free API token](https://mailtester.ninja/free-email-verification-api/) for 50 checks a day

```bash
pip install mailtester-ninja
```

## Quickstart

```python
from mailtester_ninja import MailTester

mt = MailTester()  # reads MAILTESTER_KEY, falls back to "free"

result = mt.verify("info@apple.com")
print(result.code, result.message)  # ok Accepted
```

## Reading the verdict

Branch on `code`, show `message` to people.

| `code` | Meaning | Typical `message` |
|--------|---------|-------------------|
| `ok` | Valid and deliverable | Accepted |
| `ko` | Invalid, will bounce | Rejected, No MX, Disposable, Limited |
| `mb` | Uncertain: catch-all domain, or the server could not be probed | Catch-All, MX Error, Timeout, SPAM Block, Greylisted |

A catch-all domain is never reported as valid. Shortcuts: `result.is_valid`, `result.is_invalid`, `result.is_uncertain`, and `mt.is_deliverable(email)`.

## Verify a list

`verify_many` checks one address at a time and paces the calls for you: 30 seconds apart on the free tier, 1 second with a paid key (override with `delay`). Errors are reported per address, the loop keeps going.

```python
for email, result, error in mt.verify_many(["info@apple.com", "someone@example.com"]):
    if error:
        print(email, "no verdict:", error.message)
    else:
        print(email, result.code, result.message)
```

## Find a work email (paid key)

`find` calls the Finder API: it tests the most common address formats one by one (first.last, flast, first, firstlast, first_last, f.last) and returns the first one the mail server accepts.

```python
r = mt.find("Jean-Pierre", "De La Tour", "example.com")
if r.found:
    print(r.email)             # an address the mail server just accepted
else:
    print(r.message, r.guess)  # e.g. Catch-All and the most common format
print(r.permutations)          # formats tested, each one counted as a verification
```

- Each format tested counts as one verification against your daily limit, even when nothing is found. The search paces itself within the rate of your key.
- On a catch-all domain nothing can be confirmed: `found` is `False` and `guess` holds the most common format.
- Personal email providers such as gmail.com are not searched (`message` is `Webmail`).
- A free key raises `MailTesterKeyError`; over the rate of your key, `MailTesterRateLimitError` carries `retry_after`.

## Errors

An error is never a verdict: do not drop an address because of it.

| Exception | When |
|-----------|------|
| `MailTesterKeyError` | The key is invalid or disabled, or `find` was called with a free key. |
| `MailTesterRateLimitError` | A limit was reached (HTTP 429). `retry_after` is set on the free tier and by `find`. |
| `MailTesterError` | Any other HTTP or network error (`status` when there is one). |

## Keys and limits

| Key | Daily checks | Pace |
|-----|--------------|------|
| `free` | 10 per IP | 1 request every 30 s |
| Free token `mtf_...` ([get one](https://mailtester.ninja/free-email-verification-api/)) | 50 per token | 1 request every 30 s |
| Paid key `sub_...` ([plans](https://mailtester.ninja/verify-emails-unlimited/)) | 100,000 to 200,000+ | daily limit / 8640 per 10 s (Pro 11, Ultimate 23) |

Options: `MailTester(key=None, base_url=..., timeout=60.0)`. The key defaults to the `MAILTESTER_KEY` environment variable, then to `free`.

## Links

- [API documentation](https://mailtester.ninja/api/) and [OpenAPI 3.1 specification](https://mailtester.ninja/openapi.json)
- [Integrations](https://mailtester.ninja/integrations/): n8n, Zapier, Make, Clay, Google Sheets
- [Code examples](https://github.com/mailtester-ninja/mailtester-api-examples) for other languages
- [JavaScript and TypeScript client](https://www.npmjs.com/package/@mailtester-ninja/client)

## License

MIT
