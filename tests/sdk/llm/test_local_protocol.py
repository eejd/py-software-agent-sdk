"""Exercise the SDK and LiteLLM over an actual local OpenAI-compatible socket."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar, Sequence

from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool.schema import Action
from openhands.sdk.tool.tool import ToolDefinition


class AddAction(Action):
    a: int
    b: int


class AddTool(ToolDefinition[AddAction, None]):
    name: ClassVar[str] = "add"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["AddTool"]:
        return [cls(description="Add two integers", action_type=AddAction)]


def test_local_openai_tool_roundtrip():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            assert self.path == "/v1/chat/completions"
            if len(requests) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_42", "type": "function", "function": {
                        "name": "add", "arguments": '{"a":19,"b":23,"summary":"Add numbers"}'
                    }
                }]}
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": "The answer is 42."}
                finish = "stop"
            body = json.dumps({"id": "chatcmpl-local", "object": "chat.completion", "created": 1,
                               "model": "gpt-4o", "choices": [{"index": 0, "message": message,
                               "finish_reason": finish}], "usage": {"prompt_tokens": 10,
                               "completion_tokens": 5, "total_tokens": 15}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        llm = LLM(model="openai/gpt-4o", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                  api_key="local", num_retries=0, native_tool_calling=True)
        user = Message(role="user", content=[TextContent(text="Add 19 and 23")])
        first = llm.completion([user], tools=list(AddTool.create()))
        call = first.message.tool_calls[0]
        assert call.name == "add"
        args = json.loads(call.arguments)
        assert args["a"] + args["b"] == 42
        tool = Message(role="tool", name="add", tool_call_id=call.id,
                       content=[TextContent(text=str(args["a"] + args["b"]))])
        second = llm.completion([user, first.message, tool], tools=list(AddTool.create()))
        assert "42" in second.raw_response.choices[0].message.content
        wire_tool = requests[1]["messages"][-1]
        assert wire_tool["role"] == "tool"
        assert wire_tool["tool_call_id"] == "call_42"
        assert "42" in str(wire_tool["content"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
