import json
import unittest

import httpx

from kareem_ai.characters import CHARACTERS, character_for, character_prompt
from kareem_ai.core import Engine, Provider
from kareem_ai.voice_catalog import CLOUD_VOICES, DEFAULT_CLOUD_VOICE


class CharacterTests(unittest.IsolatedAsyncioTestCase):
    def test_every_cloud_voice_has_its_own_character_and_preview(self):
        self.assertEqual({c.selection for c in CHARACTERS}, {s for _, s in CLOUD_VOICES})
        self.assertEqual(len({c.style for c in CHARACTERS}), 12)
        self.assertEqual(len({c.title for c in CHARACTERS}), 12)
        self.assertTrue(all(c.summary and c.preview and len(c.preview) <= 200 for c in CHARACTERS))
        for c in CHARACTERS:
            prompt = character_prompt(c.selection)
            self.assertIn(c.name, prompt)
            self.assertIn("tool approval requirements", prompt)
            self.assertIn("fictional assistant character", prompt)

    def test_invalid_or_windows_selection_resolves_to_cloud_default(self):
        for selection in (None, "", "en_US|Microsoft David", "unrecognized"):
            self.assertEqual(character_for(selection).selection, DEFAULT_CLOUD_VOICE)

    async def test_same_character_in_both_drafts_and_merge(self):
        character = next(c for c in CHARACTERS if c.name == "Diana")
        calls = []
        def handler(request):
            body = json.loads(request.content)
            calls.append(body)
            prompt = body["messages"][0]["content"]
            self.assertIn("ACTIVE CHARACTER: Diana", prompt)
            self.assertIn(character.style, prompt)
            self.assertIn("All actions require explicit human approval", prompt)
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"test reply"}}]}\n\ndata: [DONE]\n\n')
        providers = {n: Provider(n, "fake-key", "test-model") for n in ("Gemini", "Groq")}
        result = await Engine(providers, httpx.MockTransport(handler), character.selection).run(
            [{"role": "user", "content": "Help me plan a small project."}], "Merge")
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.text, "test reply")

    async def test_single_provider_uses_selected_arabic_character(self):
        character = next(c for c in CHARACTERS if c.name == "Noura")
        def handler(request):
            prompt = json.loads(request.content)["messages"][0]["content"]
            self.assertIn("ACTIVE CHARACTER: Noura", prompt)
            self.assertIn("Use clear conversational Arabic", prompt)
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"test"}}]}\n\ndata: [DONE]\n\n')
        result = await Engine({"Groq": Provider("Groq", "fake", "test")}, httpx.MockTransport(handler),
                              character.selection).run([], "Groq")
        self.assertEqual(result.text, "test")


if __name__ == "__main__":
    unittest.main()
