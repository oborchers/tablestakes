# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | Yes                |

## Reporting a Vulnerability

Please report security vulnerabilities using [GitHub's private vulnerability reporting](https://github.com/oborchers/tablestakes/security/advisories/new).

You will receive a response within 7 days. If confirmed, a fix will be released as soon as practical.

## Scope

tablestakes reads and writes files at paths provided by the MCP client (the LLM). It does not sanitize or restrict file paths. The MCP client is responsible for ensuring that only authorized paths are passed to tablestakes tools.
