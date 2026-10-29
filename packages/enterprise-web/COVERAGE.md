# Measured server coverage

36 Node tests pass with zero failures and zero skips against the actual local Firestore emulator. The MCP integration uses the official v2 client and server, not a fake transport. Clerk fixtures are RSA signed with runtime-generated test keys and verified through the official SDK.

Measured server `.ts` coverage: **98.10% lines**, **91.36% branches**, **100% functions**. Cobertura contains 844 instrumented lines with 828 covered, 486 branches with 444 covered. LCOV and Cobertura files are committed as reviewable evidence. `npm run coverage` enforces 90% lines, 80% branches, 90% functions; `scripts/check-coverage.py` checks nonempty real hits and >=90% line coverage per server module.

React `.tsx` rendering is excluded from this server measurement. Browser, live Clerk, production Firestore load/index/IAM and payment integration validation are separate gates. No GPU, cloud deployment or external LLM result is implied. The support-provider test uses a deterministic HTTP response fixture and is labeled as such.

## October 29 model-contract review

Firestore-emulator validation passed. The server library measured **98.32% line
coverage and 92.74% branch coverage**, with valid Cobertura and LCOV artifacts.
Model preparation, HTTP authorization and MCP negotiation were exercised.
No NVIDIA inference or hardware execution is implied by these tests.
