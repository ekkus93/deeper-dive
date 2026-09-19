# DD-172 Network hardening audit

This audit covers the network paths used by automated supplemental research and distinguishes them from explicit user URL imports.

## Automated research fetch boundary

`ResearchSafeFetcher` is the mandatory fetch boundary for automated supplemental research. It accepts only HTTP/HTTPS URLs, resolves the hostname before every request, rejects the request if any returned address is non-global, disables automatic redirects, and re-runs URL/DNS validation for every redirect target. The response body is bounded by `FetchRequest.max_bytes`, request time is bounded by `FetchRequest.timeout_seconds`, redirect count is bounded, and only `text/html` and `text/plain` are accepted.

The security tests cover IPv4 loopback, RFC1918 private space, IPv4 link-local, IPv6 loopback, IPv6 unique-local, IPv6 link-local, mixed public/private DNS answer sets, a multi-hop redirect chain ending at a private IPv6 target, redirect limits, oversized bodies, timeouts, invalid schemes, and invalid content types.

## DNS rebinding assumption

The pre-request DNS check rejects an answer set if *any* returned address is non-global. Redirect targets are resolved and checked independently. The standard-library transport subsequently performs its own connection-time name resolution, so the current implementation does not cryptographically pin the validated DNS answer to the socket peer. This is a documented residual TOCTOU/rebinding limitation of the urllib transport rather than a claim of complete DNS pinning.

Automated research therefore treats the resolver and network environment as part of the local trust boundary. A future transport that exposes or pins the connected peer address can close this residual gap without changing the `DocumentFetcher` contract. The application must not weaken the current pre-request and per-redirect checks in the meantime.

## User-explicit URL behavior

Explicit URL import is a separate user-initiated path (`source add --url` / `DeeperDiveService.add_url_sources`) and is not an automated-research fetch. The user explicitly chooses the URL to import. This distinction is intentional: automated discovery is constrained by the research-safe fetch boundary, while explicit imports follow the user-source parser path. Code must not route automatically discovered search results through the explicit-user URL path to bypass SSRF controls.

## Limits and timeout audit

The fetch contract defaults to a 15-second timeout and a 2,000,000-byte maximum response. `UrllibTransport` reads at most `max_bytes + 1`, allowing the service to detect and reject an oversized response without buffering an unbounded body. Redirects default to five hops. These bounds remain caller-configurable through `FetchRequest` but are always finite in the normal automated-research path.

## DD-172 conclusion

The existing automated research boundary remains fail-closed for invalid schemes, non-public address answers, redirect targets, oversized responses, unsupported content types, and transport failures. The expanded tests make the IPv4/IPv6 and redirect-chain assumptions explicit. DNS answer-to-socket pinning remains a documented residual hardening opportunity and must not be represented as already solved.
