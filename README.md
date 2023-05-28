Simple command-line interface for the Wayback Machine's Save Page Now (SPN) API.

## Installation
```bash
pip install spn
```

## API Keys

Get your API keys [here](https://archive.org/account/s3.php) and put them in
`~/.config.spn/config.yaml`:

```yaml
---
access_key: YOUR_ACCESS_KEY
secret_key: YOUR_SECRET_KEY
```

Or use environment variables:

```bash
export SPN_ACCESS_KEY=YOUR_ACCESS_KEY
export SPN_SECRET_KEY=YOUR_SECRET_KEY
```

Or use command parameters:

```bash
spn --access-key=YOUR_ACCESS_KEY --secret-key=YOUR_SECRET_KEY
```

## Examples

```bash
# save a single url to the wayback machine
spn https://www.theguardian.com/politics/2023/may/28/more-than-half-of-voters-now-want-britain-to-forge-closer-ties-with-the-eu-poll-reveals

# save urls from a file
spn -i urls

# save urls from a pipe and only save urls not already saved in the last 3 days
some-command-that-outputs-urls | spn -i - --if-not-archived-within=3d
```

## Official API Documentation
https://docs.google.com/document/d/1Nsv52MvSjbLb2PCpHlat0gkzw0EvtSgpKHu4mk0MnrA/edit
