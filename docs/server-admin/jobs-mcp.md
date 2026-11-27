# Background jobs and MCP

How long-running jobs and the MCP server behave when the server has several libraries.

## Background jobs

Background jobs run in the library they were started from, so the same job can run in two libraries at once. Users see only the jobs they started, and admins see all of them. Each library has its own full-text indexer; they take turns, so arXiv gets one request at a time.

## MCP

The [MCP server](../mcp.md) always works on the owner's library, and only admins can change its settings or token.
