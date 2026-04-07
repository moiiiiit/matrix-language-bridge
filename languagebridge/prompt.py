"""System prompt construction for LLM translation calls."""

from languagebridge.llm.base import TranslationContext


def build_system_prompt(context: TranslationContext) -> str:
    terms = ", ".join(context.preserve_terms) if context.preserve_terms else "none"
    dialect_line = (
        f"\n- The family speaks {context.dialect} — use natural phrasing for that dialect."
        if context.dialect
        else ""
    )
    return f"""You translate chat messages for the {context.family_name} family group chat.

Rules:
- Detect the source language automatically. Messages may be romanized Marathi, romanized Hindi, Devanagari script, English, or any mix of these.
- Translate into {context.target_language}.{dialect_line}
- Leave these terms untranslated (family address terms and names): {terms}
- Keep the tone {context.tone}. Do not formalize casual messages.
- If the message is already in {context.target_language}, respond with exactly: [SKIP]
- If the message is too short or ambiguous to translate meaningfully (single emoji, a name, "ok", "haha", etc.), respond with: [SKIP]
- Respond with ONLY the translation. No preamble, no explanation, no quotation marks around the output."""
