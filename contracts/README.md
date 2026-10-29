# Contracts

`order.schema.json` is the single source of truth for the order payload. All three implementations (Python, TypeScript, C#) must accept exactly what this schema accepts and produce the same validation errors for the same input. The shared fixtures in `contracts/fixtures/` are used by each implementation's tests to check that.
