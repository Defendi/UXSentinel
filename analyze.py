import base64
import json

from anthropic import Anthropic

client = Anthropic()  # usa ANTHROPIC_API_KEY do ambiente

SYSTEM_PROMPT = """
Você é um analista de QA sênior revisando o frontend de um sistema Odoo
para cooperativas de seguro automotivo no Brasil.

Para cada tela recebida (screenshot + texto extraído do DOM), avalie:

1. TEXTO NÃO TRADUZIDO: qualquer texto em inglês que deveria estar em
   português (labels, botões, mensagens de erro/validação, placeholders).
2. TEXTO TÉCNICO EXPOSTO: nomes de campo internos do Odoo (ex: campos
   começando com x_studio_, model.field, IDs técnicos, nomes de tabela)
   visíveis para o usuário final.
3. LAYOUT DE MODAIS: sobreposição de elementos, botões cortados, modal
   maior que a viewport, campos sem label, quebra visual.
4. REGRA DE NEGÓCIO: compare o que a tela mostra com o "comportamento
   esperado" informado. Aponte divergências (campo obrigatório ausente,
   fluxo que deveria bloquear e não bloqueia, dado que não deveria
   aparecer para aquele perfil de usuário, etc).

Responda SOMENTE em JSON, neste formato, sem markdown:
{
  "status": "ok" | "problemas_encontrados",
  "issues": [
    { "categoria": "traducao" | "texto_tecnico" | "layout" | "regra_negocio",
      "severidade": "baixa" | "media" | "alta",
      "descricao": "string em português, específica e acionável" }
  ]
}
""".strip()


def analyze_screenshot(flow_name: str, checkpoint_expected: str, screenshot_path: str, dom_text: str) -> dict:
    with open(screenshot_path, "rb") as f:
        screenshot_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Fluxo: {flow_name}\n"
                            f"Comportamento esperado: {checkpoint_expected}\n\n"
                            f"Texto extraído do DOM (para conferência, pode conter ruído):\n"
                            f"{dom_text[:4000]}"
                        ),
                    },
                ],
            }
        ],
    )

    text_block = next((b for b in response.content if b.type == "text"), None)
    try:
        return json.loads(text_block.text)
    except (json.JSONDecodeError, AttributeError):
        return {"status": "erro_parse", "raw": getattr(text_block, "text", None)}
