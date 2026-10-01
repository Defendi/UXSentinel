"""Testes unitários herméticos para os modelos de dados do Recorder (UXS-93)."""

import pytest
from pydantic import ValidationError

from uxsentinel.browser.recorder import (
    RecordedStep,
    RecordedTarget,
    RecordedWorkflow,
    SelectorCandidate,
    SelectorStrategy,
    StepStatus,
)


class TestStepStatusEnum:
    """Testes para o enum StepStatus."""

    def test_all_expected_statuses_exist(self) -> None:
        """Verifica se todos os status esperados estão definidos."""
        assert StepStatus.CONFIRMED == "confirmed"
        assert StepStatus.SUGGESTED == "suggested"
        assert StepStatus.ACCEPTED == "accepted"
        assert StepStatus.PENDING_REVIEW == "pending_review"
        assert StepStatus.REJECTED == "rejected"

    def test_str_enum_behavior(self) -> None:
        """Verifica que StepStatus é StrEnum e pode ser comparado como string."""
        assert isinstance(StepStatus.CONFIRMED, str)
        assert StepStatus("accepted") is StepStatus.ACCEPTED


class TestSelectorStrategyEnum:
    """Testes para o enum SelectorStrategy."""

    def test_all_expected_strategies_exist(self) -> None:
        """Verifica se todas as estratégias de seleção esperadas estão definidas."""
        assert SelectorStrategy.TESTID == "data-testid"
        assert SelectorStrategy.ROLE == "role"
        assert SelectorStrategy.LABEL == "label"
        assert SelectorStrategy.TEXT == "text"
        assert SelectorStrategy.CSS == "css"
        assert SelectorStrategy.XPATH == "xpath"


class TestSelectorCandidate:
    """Testes para o modelo SelectorCandidate."""

    def test_valid_candidate_without_name(self) -> None:
        """Instanciação válida com campos mínimos."""
        candidate = SelectorCandidate(
            strategy=SelectorStrategy.TESTID,
            value="submit-btn",
        )
        assert candidate.strategy == SelectorStrategy.TESTID
        assert candidate.value == "submit-btn"
        assert candidate.name is None

    def test_valid_candidate_with_name(self) -> None:
        """Instanciação válida com campo name para role."""
        candidate = SelectorCandidate(
            strategy=SelectorStrategy.ROLE,
            value="button",
            name="Entrar",
        )
        assert candidate.strategy == SelectorStrategy.ROLE
        assert candidate.value == "button"
        assert candidate.name == "Entrar"

    def test_extra_fields_forbidden(self) -> None:
        """Verifica que campos extras não permitidos geram ValidationError."""
        with pytest.raises(ValidationError):
            SelectorCandidate(
                strategy=SelectorStrategy.CSS,
                value=".btn",
                extra_unknown_field="fail",  # type: ignore[call-arg]
            )


class TestRecordedTarget:
    """Testes para o modelo RecordedTarget."""

    def test_target_with_primary_and_fallbacks(self) -> None:
        """Criação com seletor primário e múltiplos fallbacks."""
        primary = SelectorCandidate(strategy=SelectorStrategy.TESTID, value="login-btn")
        fb1 = SelectorCandidate(strategy=SelectorStrategy.ROLE, value="button", name="Entrar")
        fb2 = SelectorCandidate(strategy=SelectorStrategy.CSS, value="button.submit")

        target = RecordedTarget(
            primary=primary,
            fallbacks=[fb1, fb2],
            raw_html_snippet='<button data-testid="login-btn" class="submit">Entrar</button>',
        )
        assert target.primary == primary
        assert len(target.fallbacks) == 2
        assert target.fallbacks[0].strategy == SelectorStrategy.ROLE
        assert target.raw_html_snippet is not None

    def test_target_without_primary(self) -> None:
        """Caso de borda: elemento sem seletor primário resolúvel (primary=None)."""
        target = RecordedTarget(primary=None)
        assert target.primary is None
        assert target.fallbacks == []
        assert target.raw_html_snippet is None


class TestRecordedStep:
    """Testes para o modelo RecordedStep."""

    def test_minimal_step_instantiation(self) -> None:
        """Instanciação de passo com valores default."""
        step = RecordedStep(index=0, action="click")
        assert step.index == 0
        assert step.action == "click"
        assert step.target is None
        assert step.status == StepStatus.CONFIRMED
        assert step.advisor_confidence is None
        assert step.advisor_justification is None

    def test_suggested_and_accepted_status(self) -> None:
        """Testa diferenciação clara entre status SUGGESTED e ACCEPTED."""
        step_suggested = RecordedStep(
            index=1,
            action="assert",
            status=StepStatus.SUGGESTED,
            advisor_justification="Validação inferida de sucesso de login",
            advisor_confidence=0.88,
        )
        assert step_suggested.status == StepStatus.SUGGESTED
        assert step_suggested.advisor_confidence == 0.88

        step_accepted = RecordedStep(
            index=1,
            action="assert",
            status=StepStatus.ACCEPTED,
            advisor_justification="Aprovado pelo operador humano",
            advisor_confidence=0.88,
        )
        assert step_accepted.status == StepStatus.ACCEPTED

    def test_invalid_confidence_range(self) -> None:
        """Verifica validação de limites de advisor_confidence (0.0 <= conf <= 1.0)."""
        with pytest.raises(ValidationError):
            RecordedStep(index=0, action="click", advisor_confidence=1.5)

        with pytest.raises(ValidationError):
            RecordedStep(index=0, action="click", advisor_confidence=-0.1)

    def test_negative_index_rejected(self) -> None:
        """Verifica que index negativo é rejeitado."""
        with pytest.raises(ValidationError):
            RecordedStep(index=-1, action="click")


class TestRecordedWorkflow:
    """Testes para o modelo RecordedWorkflow."""

    def test_empty_workflow(self) -> None:
        """Caso de borda: workflow gravado sem passos registrados."""
        workflow = RecordedWorkflow(
            session_id="sess_12345",
            name="Cenário Vazio",
            url="https://exemplo.com",
            created_at="2026-10-01T14:00:00Z",
        )
        assert workflow.session_id == "sess_12345"
        assert workflow.name == "Cenário Vazio"
        assert workflow.steps == []
        assert workflow.paused is False
        assert workflow.objective is None

    def test_workflow_with_steps_roundtrip_json(self) -> None:
        """Serialização e deserialização JSON completas com Pydantic v2."""
        step_click = RecordedStep(
            index=0,
            action="click",
            target=RecordedTarget(
                primary=SelectorCandidate(
                    strategy=SelectorStrategy.ROLE,
                    value="button",
                    name="Começar",
                ),
            ),
        )
        step_fill = RecordedStep(
            index=1,
            action="fill",
            target=RecordedTarget(
                primary=SelectorCandidate(
                    strategy=SelectorStrategy.TESTID,
                    value="username-field",
                ),
            ),
            value="usuario.teste",
        )
        step_suggested = RecordedStep(
            index=2,
            action="assert",
            status=StepStatus.SUGGESTED,
            advisor_justification="Ponto de confirmação provável",
            advisor_confidence=0.92,
        )

        workflow = RecordedWorkflow(
            session_id="session-abc",
            name="Login de Teste",
            url="https://app.teste.local/login",
            objective="Autenticar usuário e verificar tela inicial",
            steps=[step_click, step_fill, step_suggested],
            created_at="2026-10-01T14:30:00Z",
            paused=False,
        )

        # Serialização para dict e json
        raw_dict = workflow.model_dump()
        raw_json = workflow.model_dump_json()

        assert raw_dict["session_id"] == "session-abc"
        assert len(raw_dict["steps"]) == 3
        assert raw_dict["steps"][0]["target"]["primary"]["strategy"] == "role"
        assert raw_dict["steps"][2]["status"] == "suggested"

        # Deserialização e validação
        restored_from_dict = RecordedWorkflow.model_validate(raw_dict)
        restored_from_json = RecordedWorkflow.model_validate_json(raw_json)

        assert restored_from_dict == workflow
        assert restored_from_json == workflow
        assert restored_from_json.steps[2].status == StepStatus.SUGGESTED
        assert restored_from_json.steps[2].advisor_confidence == 0.92
