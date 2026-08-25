# Governed object-storage CSV connector

Large or scheduled connector batches use the provider-neutral ingestion port rather than the
inline upload path. A source must be enabled, verified, and configured with
`access_method=object_storage`. Operators place UTF-8 CSV under the source-isolated prefix:

```text
sources/{source_uuid}/batch-name.csv
```

They then submit the object key and lowercase SHA-256 digest to
`POST /api/v1/data-sources/{source_uuid}/imports/object-storage`. The adapter:

- refuses keys outside the source prefix;
- refuses objects larger than 10 MiB;
- verifies the digest before parsing;
- requires registered indicator codes for verified sources;
- enforces indicator units and declared ranges;
- uses the same idempotency, geography validation, quarantine, lineage, and run accounting as the
  bounded file fallback.

The endpoint reads from the configured S3-compatible store and never accepts storage credentials
or arbitrary endpoint URLs from a request. Production scheduling may call the same provider path
from the ingestion worker. This adapter does not claim integration with any external data owner;
the source contract, license, credentials, and delivery schedule must be approved separately.
