import asyncio
import json
import threading
import unittest

import httpx

from kareem_ai.core import Engine, Provider, ProviderError, cancellable, discover


def stream(text):
    event = {"choices": [{"delta": {"content": text}}]}
    return httpx.Response(200, text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
                          headers={"content-type": "text/event-stream"})


class CoreTests(unittest.IsolatedAsyncioTestCase):
    def providers(self):
        return {n: Provider(n, "test-secret", "test-model") for n in ("Gemini", "Groq")}

    async def test_merge_uses_two_independent_drafts_then_synthesis(self):
        calls = []
        async def handle(request):
            body = json.loads(request.content)
            calls.append((request.url.host, body))
            if len(calls) <= 2:
                self.assertEqual(body["messages"][-1]["content"], "question")
                return stream("draft " + request.url.host)
            self.assertIn("draft api.groq.com", body["messages"][-1]["content"])
            self.assertIn("draft generativelanguage.googleapis.com", body["messages"][-1]["content"])
            return stream("combined answer")
        tokens = []
        engine = Engine(self.providers(), httpx.MockTransport(handle))
        answer = await engine.run([{"role": "user", "content": "question"}], "Merge", token=tokens.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(answer.text, "combined answer")
        self.assertEqual(tokens, ["combined answer"])
        self.assertEqual(len(answer.drafts), 2)
        self.assertFalse(answer.degraded)

    async def test_rate_limit_does_not_retry_and_survivor_is_labelled(self):
        calls = []
        def handle(request):
            calls.append(request)
            if request.url.host == "api.groq.com":
                return httpx.Response(429, text="test-secret")
            return stream("survivor")
        logs = []
        answer = await Engine(self.providers(), httpx.MockTransport(handle)).run([], "Merge", logs.append)
        self.assertEqual(len(calls), 2)
        self.assertTrue(answer.degraded)
        self.assertEqual(answer.text, "survivor")
        self.assertNotIn("test-secret", " ".join(logs))
        self.assertIn("No retry", " ".join(logs))

    async def test_both_fail(self):
        with self.assertRaises(ProviderError):
            await Engine(self.providers(), httpx.MockTransport(lambda _: httpx.Response(401))).run([], "Merge")

    async def test_synthesis_failure_preserves_draft(self):
        calls = []
        def handle(request):
            calls.append(request)
            return stream("draft") if len(calls) <= 2 else httpx.Response(429)
        answer = await Engine(self.providers(), httpx.MockTransport(handle)).run([], "Merge")
        self.assertEqual(len(calls), 3)
        self.assertEqual(answer.text, "draft")
        self.assertTrue(answer.degraded)

    async def test_single_provider_one_call_and_usage(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"hello"}}],"usage":{"total_tokens":12}}\n\ndata: [DONE]\n\n')
        result = await Engine(self.providers(), httpx.MockTransport(handle)).run([], "Groq")
        self.assertEqual(result.text, "hello")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.usage["Groq"]["total_tokens"], 12)

    async def test_cancel_stops_requests(self):
        cancelled = asyncio.Event()
        async def slow():
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        stop = threading.Event()
        asyncio.get_running_loop().call_later(0.02, stop.set)
        with self.assertRaises(asyncio.CancelledError):
            await cancellable(slow(), stop)
        self.assertTrue(cancelled.is_set())

    async def test_discover_and_auth(self):
        def handle(request):
            self.assertEqual(request.headers["authorization"], "Bearer test-secret")
            self.assertTrue(str(request.url).endswith("/models"))
            return httpx.Response(200, json={"data": [{"id": "models/test-chat"}]})
        self.assertEqual(await discover(self.providers()["Gemini"], httpx.MockTransport(handle)), ["test-chat"])

    async def test_missing_key_sends_nothing(self):
        providers = self.providers()
        providers["Groq"].key = ""
        def handle(_):
            self.fail("No request should have been made")
        with self.assertRaises(ProviderError):
            await Engine(providers, httpx.MockTransport(handle)).run([], "Merge")

    async def test_context_limit(self):
        with self.assertRaises(ProviderError):
            await Engine(self.providers()).run([{"role": "user", "content": "x" * 43000}], "Groq")

    async def test_empty_and_bad_stream_rejected(self):
        for data in ("data: [DONE]\n\n", "data: invalid\n\n"):
            with self.assertRaises(ProviderError):
                await Engine(self.providers(), httpx.MockTransport(lambda _: httpx.Response(200, text=data))).run([], "Groq")


if __name__ == "__main__":
    unittest.main()
