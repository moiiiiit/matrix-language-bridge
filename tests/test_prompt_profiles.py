from languagebridge.llm.base import TranslationContext
from languagebridge.prompt import build_system_prompt


def test_prompt_uses_profile_appendix() -> None:
    ctx = TranslationContext(
        family_name="Test Family",
        source_language_hint="mr",
        target_language="en",
        prompt_appendix="CUSTOM_APPENDIX_RULE",
        preserve_terms=["kaka"],
    )

    prompt = build_system_prompt(ctx)

    assert "Translate into en." in prompt
    assert "CUSTOM_APPENDIX_RULE" in prompt
    assert "kaka" in prompt
