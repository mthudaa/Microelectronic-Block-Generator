"""The MCP server speaks the protocol: spawn `scripts/mbg mcp` like a client.

No EDA tools needed. If the official `mcp` Python SDK is installed, a second
test drives the server with the SDK's own client as an interoperability check.
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MBG = os.path.join(ROOT, "scripts", "mbg")


def exchange(messages):
    p = subprocess.run([MBG, "mcp"], input="\n".join(json.dumps(m) for m in messages) + "\n",
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}}


class McpProtocol(unittest.TestCase):

    def test_handshake_list_and_call(self):
        out = exchange([
            INIT,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "pdk", "arguments": {"action": "list"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "netlist_check",
                        "arguments": {"netlist": "tests/netlists/ota_5t.spice"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        ])
        by_id = {m["id"]: m for m in out}
        self.assertEqual(set(by_id), {1, 2, 3, 4, 5})      # no reply to the notification
        init = by_id[1]["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertIn("tools", init["capabilities"])
        names = {t["name"] for t in by_id[2]["result"]["tools"]}
        for n in ("doctor", "pdk", "netlist_check", "sim_run", "measure_vref",
                  "layout_generate", "layout_view", "verify", "flow_run", "job"):
            self.assertIn(n, names)
        for t in by_id[2]["result"]["tools"]:
            self.assertEqual(t["inputSchema"]["type"], "object")
        call = by_id[3]["result"]
        self.assertFalse(call["isError"])
        env = json.loads(call["content"][0]["text"])
        self.assertEqual(env["status"], "PASS")
        self.assertEqual(call["structuredContent"]["tool"], "pdk.list")
        self.assertEqual(json.loads(by_id[4]["result"]["content"][0]["text"])["status"], "PASS")
        self.assertEqual(by_id[5]["result"], {})

    def test_errors(self):
        out = exchange([
            INIT,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "no_such_tool", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "verify", "arguments": {"check": "nope"}}},
        ])
        by_id = {m["id"]: m for m in out}
        self.assertTrue(by_id[2]["result"]["isError"])
        self.assertEqual(by_id[3]["error"]["code"], -32601)
        self.assertTrue(by_id[4]["result"]["isError"])

    def test_unknown_protocol_version_gets_the_latest(self):
        out = exchange([{**INIT, "params": {**INIT["params"], "protocolVersion": "1999-01-01"}}])
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-11-25")

    def test_old_clients_get_no_structured_content(self):
        out = exchange([
            {**INIT, "params": {**INIT["params"], "protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "pdk", "arguments": {"action": "list"}}},
        ])
        self.assertNotIn("structuredContent", out[1]["result"])


try:
    import mcp  # noqa: F401
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAVE_SDK = True
except Exception:                                            # noqa: BLE001
    HAVE_SDK = False


@unittest.skipUnless(HAVE_SDK, "official `mcp` SDK not installed")
class OfficialSdkClient(unittest.TestCase):

    def test_sdk_client_lists_and_calls(self):
        import asyncio

        async def go():
            params = StdioServerParameters(command=MBG, args=["mcp"], cwd=ROOT)
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = await s.list_tools()
                    res = await s.call_tool("pdk", {"action": "info", "model": "ppolyf_u_1k"})
                    return [t.name for t in tools.tools], res
        names, res = asyncio.run(go())
        self.assertIn("layout_generate", names)
        # mcp 1.x spells it isError, 2.x is_error
        self.assertFalse(getattr(res, "is_error", getattr(res, "isError", None)))
        self.assertIn("ppolyf_u_1k", res.content[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
