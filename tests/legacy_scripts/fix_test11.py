import pathlib

p = pathlib.Path("tests/core/test_external_tools_v1.py")
t = p.read_text(encoding="utf-8")

# Fix test_11: Codex CLI is now FREE_OR_LOCAL (OSS/local Ollama), not PAID
old = """    def test_11_paid_models_blocked(self) -> None:
        registry = create_default_registry()
        codex = registry.get("codex_cli")
        self.assertIsNotNone(codex)
        self.assertEqual(codex.cost_policy, CostPolicy.PAID)

        # Settings block paid by default
        settings = GoldenAISettings()
        self.assertFalse(settings.tools.allow_remote_paid)

        # A paid tool's execute should return BLOCKED_PAID when paid is not allowed
        pm = PermissionManager(settings)
        adapter = _DummyAdapter(codex, pm)
        result = adapter.execute("run_code")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "BLOCKED_PAID")"""

new = """    def test_11_paid_models_blocked(self) -> None:
        registry = create_default_registry()
        codex = registry.get("codex_cli")
        self.assertIsNotNone(codex)
        # Codex CLI is now FREE_OR_LOCAL (uses OSS/local Ollama, not paid API)
        self.assertEqual(codex.cost_policy, CostPolicy.FREE_OR_LOCAL)

        # Settings block paid by default
        settings = GoldenAISettings()
        self.assertFalse(settings.tools.allow_remote_paid)
        self.assertFalse(settings.coding_agent.paid_fallback)

        # A truly paid tool should still be blocked
        paid_tool = ToolDefinition(
            id="paid_tool_test",
            name="Paid Tool",
            category="llm",
            description="A paid tool for testing",
            cost_policy=CostPolicy.PAID,
        )
        pm = PermissionManager(settings)
        adapter = _DummyAdapter(paid_tool, pm)
        result = adapter.execute("run_code")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "BLOCKED_PAID")"""

if old in t:
    t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("Fixed test_11_paid_models_blocked")
else:
    print("Pattern not found")