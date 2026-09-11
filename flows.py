"""
Cada "flow" é um roteiro de negócio conhecido: uma sequência de passos
(navegar, clicar, preencher) + um checkpoint onde o agente para, tira
screenshot e manda para análise do Claude.

"expected_behavior" descreve em português o que a tela DEVERIA
mostrar/fazer — isso vira o contexto que o Claude usa pra julgar se a
regra de negócio está sendo respeitada.
"""

import os

FLOWS = [
    {
        "name": "login",
        "steps": [
            {"action": "goto", "url": "/odoo/login"},
            {"action": "fill", "selector": "#login", "value": os.environ.get("QA_USER", "")},
            {"action": "fill", "selector": "#password", "value": os.environ.get("QA_PASSWORD", "")},
            {"action": "click", "selector": "button[type=submit]"},
            {"action": "wait_for_url", "url": "**/odoo"},
        ],
        "checkpoint": {
            "expected_behavior": (
                "Usuário autenticado deve cair no dashboard principal, sem "
                "mensagens de erro, sem campos técnicos (ex: nomes internos "
                "de módulo) visíveis."
            ),
        },
    },
    {
        "name": "abrir_apolice_e_modal_sinistro",
        "steps": [
            {"action": "goto", "url": "/odoo/apolices"},
            {"action": "click", "selector": "tr.o_data_row >> nth=0"},
            {"action": "click", "selector": "button:has-text('Registrar Sinistro')"},
            {"action": "wait_for_selector", "selector": ".modal-dialog"},
        ],
        "checkpoint": {
            "expected_behavior": (
                "O modal de registro de sinistro deve abrir centralizado, "
                "com título e labels em português, sem sobreposição de "
                "campos, sem nomes técnicos de campo (ex: 'x_studio_...') "
                "visíveis ao usuário. Os campos obrigatórios da regra de "
                "negócio (tipo de sinistro, data, veículo, descrição) devem "
                "estar presentes."
            ),
        },
    },
    # Adicione aqui os fluxos reais do seu Odoo: emissão de boleto,
    # geração de PIX, cadastro de veículo (FIPE), etc. Um flow por regra
    # de negócio que você quer proteger de regressão.
]
