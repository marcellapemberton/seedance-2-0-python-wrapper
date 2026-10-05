# Seedance 2.0 model contract

This table is intentionally short. Update it only after checking the live [Argolink model page](https://argolink.io/gh-seedance-2-0-python-wrapper).

- Model ID: `seedance-2.0`
- Argolink model page: `https://argolink.io/gh-seedance-2-0-python-wrapper` (tracked shortlink; destination is the model page)
- Endpoint family: `/v1/videos/generations`
- Listed video tiers: 480p `$0.0703`/second, 720p `$0.1512`/second, 1080p `$0.3742`/second, 4k `$0.7691`/second.
- Base generation rate: `$0.0703`/second before any tier multiplier.

## Request boundary

- Authentication: `Authorization: Bearer $ARGOLINK_API_KEY`.
- Base URL: `https://api.argolink.io`.
- Model ID: `seedance-2.0`.
- Endpoint: `/v1/videos/generations`.
- For media jobs, save the returned task identifier, poll the documented task endpoint, and download the final URL before its retention window ends.

Do not copy prices or limits from third-party lists into this file; the model page and catalog are the current source of truth.
