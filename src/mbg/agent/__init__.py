"""The agent tool surface: one registry, exposed as a CLI and an MCP server.

An AI agent drives MBG through ``mbg <group> <action> [options]`` (any harness
with a shell) or through the same tools over MCP (``mbg mcp``). Every call
prints exactly one JSON document — the result envelope described in
:mod:`mbg.agent.envelope` — and keeps logs and bulk data on disk.

Nothing in this package imports gLayout at module level: listing the tools,
checking a netlist or reading a PDK profile starts instantly, and only the
handlers that lay out or verify a circuit load the layout stack.
"""
