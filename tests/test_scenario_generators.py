import pytest

from uxsentinel.browser.actions.ai import AiFillActionHandler
from uxsentinel.browser.actions.context import ActionContext
from uxsentinel.browser.actions.forms import FillActionHandler, TypeActionHandler
from uxsentinel.core.models import (
    SemanticStepResult,
    SemanticStrategy,
    Step,
    TestReport,
)
from uxsentinel.scenarios.generators import (
    gera_email,
    gera_inteiro,
    gera_nome,
    gera_numero,
    gera_texto,
    resolve_dynamic_value,
)


def test_gera_numero():
    assert len(gera_numero(4, 0)) == 4
    num_dec = gera_numero(4, 2)
    assert "." in num_dec
    partes = num_dec.split(".")
    assert len(partes[0]) == 4
    assert len(partes[1]) == 2

    assert gera_numero(0, 0) == "0"
    assert len(gera_numero(1, 0)) == 1


def test_gera_inteiro():
    assert len(gera_inteiro(4, 0)) == 4

    res = gera_inteiro(4, 2)
    assert res.startswith("00")
    assert len(res) == 6

    assert gera_inteiro(0, 2) == "00"


def test_gera_nome():
    humano = gera_nome("humano")
    assert " " in humano

    animal = gera_nome("animal")
    assert animal in [
        "Capivara Dourada",
        "Lobo Guará",
        "Arara Azul",
        "Onça Pintada",
        "Tigre Siberiano",
        "Falcão Peregrino",
        "Raposa Vermelha",
        "Golfinho Rotador",
    ]

    coisa = gera_nome("coisa")
    assert coisa in [
        "Cadeira Ergonômica",
        "Teclado Mecânico",
        "Monitor Ultrawide",
        "Garrafa Térmica",
        "Mochila Impermeável",
        "Luminária de Mesa",
        "Fone Bluetooth",
        "Relógio Inteligente",
    ]

    empresa = gera_nome("empresa")
    assert empresa in ["Vértice Soluções", "Horizonte Digital", "Alfa Tecnologia", "Nova Era Sistemas"]

    cidade = gera_nome("cidade")
    assert cidade in [
        "São Paulo",
        "Curitiba",
        "Florianópolis",
        "Belo Horizonte",
        "Porto Alegre",
        "Rio de Janeiro",
    ]

    padrao = gera_nome()
    assert " " in padrao


def test_gera_email():
    email = gera_email()
    assert "@exemplo.com.br" in email

    email_custom = gera_email("teste.com")
    assert "@teste.com" in email_custom


def test_gera_texto():
    assert len(gera_texto(60)) == 60
    assert len(gera_texto(0)) == 0


def test_resolve_dynamic_value():
    assert resolve_dynamic_value(None) == ""
    assert resolve_dynamic_value("texto normal") == "texto normal"

    num_res = resolve_dynamic_value("gera_numero(2,0)")
    assert len(num_res) == 2

    int_res = resolve_dynamic_value("Prefixo gera_inteiro(3,1)")
    assert "Prefixo 0" in int_res
    assert len(int_res) == 12  # "Prefixo " (8) + "0" (1) + 3 digits (3)

    espacos_res = resolve_dynamic_value("gera_inteiro( 4 , 2 )")
    assert espacos_res.startswith("00")
    assert len(espacos_res) == 6

    chaves_res = resolve_dynamic_value("${gera_inteiro(4,2)}")
    assert chaves_res.startswith("00")
    assert len(chaves_res) == 6


@pytest.mark.asyncio
async def test_integration_handlers():
    class MockDriver:
        def __init__(self):
            self.fill_args = None
            self.type_args = None
            self.ai_fill_args = None

        async def fill(self, selector, value, **kwargs):
            self.fill_args = (selector, value)

        async def type_text(self, selector, value, **kwargs):
            self.type_args = (selector, value)

        async def ai_fill(self, target, value, **kwargs):
            self.ai_fill_args = (target, value)
            return SemanticStepResult(
                step_index=0,
                action="ai_fill",
                target=target,
                strategy=SemanticStrategy.ACCESSIBILITY,
                confidence=0.95,
                passed=True,
                reasoning="ok",
            )

    driver = MockDriver()
    report = TestReport(scenario_id="1", scenario_title="T")
    ctx_fill = ActionContext(
        step=Step(action="fill", selector="#input", value="gera_inteiro(4,2)"),
        step_index=0,
        driver=driver,
        scenario=None,
        report=report,
        out_dir=None,
    )

    handler_fill = FillActionHandler()
    await handler_fill.execute(ctx_fill)

    assert driver.fill_args[0] == "#input"
    val_fill = driver.fill_args[1]
    assert val_fill.startswith("00")
    assert len(val_fill) == 6

    ctx_type = ActionContext(
        step=Step(action="type", selector="#input2", value="gera_numero(2,0)"),
        step_index=1,
        driver=driver,
        scenario=None,
        report=report,
        out_dir=None,
    )
    handler_type = TypeActionHandler()
    await handler_type.execute(ctx_type)

    assert driver.type_args[0] == "#input2"
    val_type = driver.type_args[1]
    assert len(val_type) == 2

    ctx_ai_fill = ActionContext(
        step=Step(action="ai_fill", ai_fill="campo", value="gera_email(teste.com)"),
        step_index=2,
        driver=driver,
        scenario=None,
        report=report,
        out_dir=None,
    )
    handler_ai_fill = AiFillActionHandler()
    await handler_ai_fill.execute(ctx_ai_fill)

    assert driver.ai_fill_args[0] == "campo"
    val_ai_fill = driver.ai_fill_args[1]
    assert "@teste.com" in val_ai_fill
