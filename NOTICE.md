# Source provenance

The backend source was extracted from `crates/agit-selfhost` in
`https://github.com/binawoh/agent-git` at commit
`9b1001cda422a47a9e0dde2d1c5060534b4a7acc`.
Deployment examples, collection tools, the protocol test, and npm packaging
also originate in that fork's `selfhost` directory.

The initial shared AgentGit library and compatible test client were pinned to
`66c3a042c6b6643de7627b19b8a65984054beb1c` in that fork. This is the source
revision used for the original `@jooooesg/agit-selfhost@0.1.0` release.
The current shared library and companion client revision is pinned in `Cargo.toml`.

The upstream project is `https://github.com/Einsia/agent-git`, licensed under
the MIT License, Copyright (c) 2026 Einsia. Its license notice is retained in
`LICENSE`. The backend and integration changes were developed in the user's
fork; this repository is not an upstream or official cloud-service repository.

No runtime credentials, private keys, native user transcripts, server databases,
or machine-specific deployment reports belong in this source repository.
